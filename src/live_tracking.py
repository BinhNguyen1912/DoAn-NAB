"""
LiveTrackingSession — vòng lặp bám đối tượng cho LUỒNG TRỰC TIẾP (chạy trong tiến trình worker).

Chức năng: mở nguồn frame, chờ ô chọn đối tượng (hoặc nhận sẵn), bám bằng engine VOS **cách quãng**
           (mỗi `vos_every` frame) và dùng **LK optical flow** cho các frame còn lại; vẽ overlay và
           ghi **frame mới nhất** + **trạng thái** ra thư mục chia sẻ để API đọc và phát.
Input  : engine (TrackerEngine hoặc engine giả trong test), LiveTrackConfig.
Output : `<out_dir>/frame.jpg` (JPEG mới nhất), `<out_dir>/status.json`, `<out_dir>/worker.log`,
         và `<out_dir>/drift_samples.csv` (từng mẫu drift — xem `src/drift_samples.py`; file chỉ
         sinh ra khi phiên thật sự đo được mẫu nào).
Lưu ý  : đây là phần CHẠY TRONG TIẾN TRÌNH RIÊNG (tools/live_worker.py) — nhờ vậy API vẫn không
         import torch/SAM 2 (ADR-0005).
         **Kiến trúc hybrid (Phase 4c):** VOS (97 ms @image_size 192) không thể chạy mỗi frame
         nếu muốn hình mượt; LK (2–3 ms, `docs/research/09`) lấp các frame giữa hai lần suy luận.
         **Hai luồng:** model chạy trong LUỒNG RIÊNG (`_VosWorker`), luồng chính chỉ đọc frame +
         LK + vẽ + ghi ⇒ model 78 ms không chặn nhịp phát. Đo trên máy này (192 px, binh1.mp4):
         chạy đơn luồng chỉ được 18 FPS, tách luồng đạt ~30 FPS (xem docs/task/08-11-2026).
         GIỚI HẠN PHẢI NÓI THẬT trong báo cáo: **mask chỉ được cập nhật ở nhịp VOS**
         (`vos_fps` trong status), phần giữa hai lần là mask cũ được TỊNH TIẾN theo LK —
         không phải mask mới. Vì vậy không được claim "mask 30 FPS".
         Giao tiếp qua FILE trong /dev/shm (tmpfs), ghi atomic bằng os.replace.
"""

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path

import cv2
import numpy as np

from src.device import normalize_device
from src.drift_samples import DRIFT_CSV_NAME, DriftSampleLog
from src.light_tracker import LkBoxTracker, shift_mask
from src.mask_filter import MaskSmoother, mask_iou
from src.live_pipeline import _OVERLAY_ALPHA, _OVERLAY_COLOR_BOX, _OVERLAY_COLOR_MASK
from src.video_source import open_video_source

FRAME_NAME = "frame.jpg"
STATUS_NAME = "status.json"
BBOX_NAME = "bbox.json"

STATE_LOADING = "loading"            # đang nạp model (20–60 s trên CPU)
STATE_WAITING = "waiting_selection"  # đã có khung hình, chờ người dùng chọn đối tượng
STATE_TRACKING = "tracking"
STATE_ERROR = "error"
STATE_STOPPED = "stopped"

_FPS_WINDOW_S = 2.0
_STAT_WINDOW = 200        # số mẫu giữ để lấy phân vị (p05/p95); 200 ⇒ p05 có nghĩa
# Số mẫu TỐI THIỂU để được phép công bố phân vị. Phải >= 30, không phải 5: với n = 5,
# `np.percentile(values, 5)` lấy CHỈ SỐ 0,2 ⇒ nằm giữa **min** và phần tử nhỏ thứ 2 (tức "một mẫu
# xui"), công bố nó thành "p05" là lỗi trung thực — một phiên 0,7 s có thể hiện "p05 = 0,0".
# n = 30 ⇒ chỉ số 1,45 (vẫn gần min), nên CỜ chẩn đoán (nếu có) phải đòi >= 100 mẫu
# (xem docs/plan/09-11-2026-chan-doan-chat-luong-bam.md).
_STAT_MIN_SAMPLES = 30
# Số mẫu tối thiểu để công bố TỈ LỆ (không phải phân vị) — 5 mẫu đã đủ nói "1/5 lần mất dấu".
_EMPTY_WINDOW_MIN = 5
_SHOWN_HISTORY = 90       # số frame giữ ô bao đã phát, để tra đúng frame VOS đã thấy


@dataclass
class LiveTrackConfig:
    """Tham số một phiên bám trực tiếp."""

    source: str
    out_dir: Path
    display_fps: float = 30.0     # nhịp PHÁT frame (LK/lặp frame), không phải nhịp VOS
    vos_every: int = 3            # 1 = chạy VOS mỗi frame (tắt LK, hình ~10 FPS @192)
    trajectory_len: int = 100
    mask_smoothing: float = 1.0   # 1.0 = TẮT làm mượt (mặc định: đo 10-11 thấy không cải
                                  # thiện IoU hiển thị mà thêm trễ — xem docs/task/08-11-2026-minh-bach-nhip-mask-va-fix-bbox-live.md)
    jpeg_quality: int = 80
    loop_files: bool = True
    stop_after_frames: int | None = None      # cho test/thử nhanh
    # Thiết bị model THẬT SỰ chạy (`cpu` | `cuda`). Trước đây chỉ có trong `worker.log` ⇒ status.json,
    # API và HUD đều không biết phiên đang chạy CPU hay GPU, trong khi mọi số FPS trong báo cáo phải
    # gắn với một thiết bị cụ thể (ticket 21).
    device: str = "cpu"

    def __post_init__(self) -> None:
        """Kiểm tra tham số ở MỘT chỗ — trước đây schema API cho 0.0 còn worker clamp 0.05,
        hai bên hiểu khác nhau (lỗi P2, review 08-11)."""
        # Cùng hàm chuẩn hoá với CLI/API/worker ⇒ `--device CUDA ` cũng thành `cuda`.
        self.device = normalize_device(self.device)
        if not 0.0 < float(self.mask_smoothing) <= 1.0:
            raise ValueError(
                f"mask_smoothing phải trong khoảng (0, 1]; nhận {self.mask_smoothing!r} "
                "(1.0 = tắt làm mượt)"
            )
        if int(self.vos_every) < 1:
            raise ValueError(f"vos_every phải >= 1; nhận {self.vos_every!r}")
        if float(self.display_fps) <= 0:
            raise ValueError(f"display_fps phải > 0; nhận {self.display_fps!r}")


@dataclass
class LiveTrackStats:
    """Số liệu đo được của phiên (ghi ra status.json mỗi frame đã phát)."""

    state: str = STATE_LOADING
    # Thiết bị model chạy (`cpu` | `cuda`) — đi cùng mọi số trong status.json để không ai trích FPS
    # CPU cho một phiên GPU (hoặc ngược lại). `""` = **chưa biết**. `LiveTrackingSession` luôn điền
    # từ `LiveTrackConfig.device` (mặc định `cpu` = mặc định của worker).
    # `state=error` ở cửa vào (tên thiết bị rác) thì đây là thiết bị **được YÊU CẦU**, có thể
    # ngoài `cpu|cuda` (nguyên văn người dùng gõ) — `message` nói rõ lỗi (P3 review 12-11).
    device: str = "cpu"
    frames: int = 0               # số frame ĐÃ PHÁT (nhịp display)
    vos_runs: int = 0             # số lần CHẠY MODEL (mask mới)
    measured_fps: float = 0.0     # FPS phát thực đo
    vos_fps: float = 0.0          # FPS của VOS (nhịp mask thật)
    vos_ms: float = 0.0           # độ trễ suy luận gần nhất
    lk_ms: float = 0.0            # độ trễ LK gần nhất
    # IoU trung bình giữa hai mask VOS liên tiếp (1,0 = không nhấp nháy). `None` = CHƯA ĐO (cửa sổ
    # rỗng) — `0,0` là số ĐO ĐƯỢC (hai mask rời nhau hoàn toàn) hoặc "đang mất dấu"; `stability_n`
    # cho biết cửa sổ có bao nhiêu mẫu (ticket 18: trước đây `0` mang cả hai nghĩa).
    stability: float | None = None
    stability_n: int = 0          # số mẫu của cửa sổ IoU (0 ⇒ `stability is None`)
    # IoU giữa hai mask ĐÃ LÀM MƯỢT (càng cao càng êm mắt). Cùng encoding với `stability`
    # (ticket 19): `None` + `stability_shown_n == 0` = CHƯA ĐO (chưa có cặp mask nào để so, ví dụ
    # chưa chọn ô / engine trả `mask is None`). Tắt làm mượt KHÔNG làm cửa sổ rỗng — lúc đó
    # `stability_shown` đo trên mask thô, gần bằng `stability`. `0,0` + n > 0 = số ĐO ĐƯỢC (màn
    # hình đang trống / hai mask rời nhau).
    stability_shown: float | None = None
    stability_shown_n: int = 0    # số mẫu của `_shown_iou_window` (0 ⇒ `stability_shown is None`)
    drift_iou: float | None = None        # IoU(ô bao đã phát, ô bao VOS sửa lại) — độ tự nhất quán
    drift_iou_p05: float | None = None    # phân vị 5 % (đuôi xấu: lúc nội suy lệch nhất)
    drift_n: int = 0                      # số mẫu drift (0 ⇒ CHƯA ĐO, không phải "drift = 0")
    mask_age_ms: float | None = None      # tuổi mask đang hiện (từ lúc kết quả model sẵn sàng)
    mask_age_total_ms: float | None = None  # + vos_ms ⇒ tuổi dữ liệu ảnh người xem thực thấy
    mask_age_p95: float | None = None     # phân vị 95 % của mask_age_total_ms
    age_n: int = 0                        # số mẫu tuổi mask (0 ⇒ CHƯA ĐO)
    empty_runs: int = 0           # số lần VOS trả mask RỖNG (mất dấu thật) — TRỌN ĐỜI phiên
    # Cùng sự kiện nhưng đếm trong `_STAT_WINDOW` lần VOS GẦN NHẤT: `empty_runs` không bao giờ
    # giảm nên UI in "mất dấu 26 lần" cho một sự việc đã qua; tỉ lệ theo cửa sổ thì trở về 0 khi
    # model bám lại được. `None` = chưa đủ mẫu (`empty_window_n` cho biết còn thiếu bao nhiêu).
    empty_frac_window: float | None = None
    empty_window_n: int = 0
    mask_holds: int = 0           # số lần bộ lọc GIỮ mask cũ (model "chớp" mất vật)
    mask_drops: int = 0           # số lần mask hiển thị RỖNG (mất dấu thật)
    lost_streak: int = 0
    bbox: list = field(default_factory=list)
    message: str = ""


@dataclass
class _FrameResult:
    """Kết quả một frame để vẽ overlay (giống `TrackingResult` nhưng không import tracker_engine)."""

    frame_idx: int
    bbox: tuple
    mask: object
    elapsed_ms: float


def write_json_atomic(path: Path, data: dict) -> None:
    """Ghi JSON atomic — API đọc không bao giờ thấy file dở."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    os.replace(tmp, path)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as handle:
        handle.write(data)
    os.replace(tmp, path)


def read_bbox(path: Path):
    """Đọc ô chọn do API ghi; None nếu chưa có hoặc hỏng."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    try:
        bbox = (int(data["x"]), int(data["y"]), int(data["w"]), int(data["h"]))
    except (KeyError, TypeError, ValueError):
        return None
    return bbox if bbox[2] > 0 and bbox[3] > 0 else None


def status_payload(stats: "LiveTrackStats") -> dict:
    """Payload `status.json` — MỘT nguồn duy nhất cho cả trạng thái "loading" lẫn phiên đang chạy.

    Trước đây `tools/live_worker.py` tự viết một dict 7 khoá, phiên chạy ghi 14 khoá ⇒ người đọc
    file trong 20–60 s nạp model thấy schema khác (P3, review 08-11).
    """
    return {
        "state": stats.state,
        "device": stats.device,
        "frames": stats.frames,
        "vos_runs": stats.vos_runs,
        "measured_fps": stats.measured_fps,
        "vos_fps": stats.vos_fps,
        "vos_ms": stats.vos_ms,
        "lk_ms": stats.lk_ms,
        "drift_iou": stats.drift_iou,
        "drift_iou_p05": stats.drift_iou_p05,
        "drift_n": stats.drift_n,
        "mask_age_ms": stats.mask_age_ms,
        "mask_age_total_ms": stats.mask_age_total_ms,
        "mask_age_p95": stats.mask_age_p95,
        "age_n": stats.age_n,
        "stability": stats.stability,
        "stability_n": stats.stability_n,
        "stability_shown": stats.stability_shown,
        "stability_shown_n": stats.stability_shown_n,
        "empty_runs": stats.empty_runs,
        "empty_frac_window": stats.empty_frac_window,
        "empty_window_n": stats.empty_window_n,
        "mask_holds": stats.mask_holds,
        "mask_drops": stats.mask_drops,
        "lost_streak": stats.lost_streak,
        "bbox": stats.bbox,
        "message": stats.message,
    }


def xyxy_to_xywh(bbox) -> tuple:
    """(x1,y1,x2,y2) → (x,y,w,h)."""
    x1, y1, x2, y2 = (int(v) for v in bbox)
    return (x1, y1, max(1, x2 - x1), max(1, y2 - y1))


def _bbox_iou(a, b):
    """IoU hai ô bao (x1,y1,x2,y2), toạ độ **bao gồm** như `tracker_engine._mask_to_bbox`.

    Trả `None` khi một ô có diện tích 0 (mask mảnh 1 cột/hàng ⇒ `x1 == x2`) — KHÔNG trả 0,0:
    hai ô giống hệt nhau mà cho IoU 0 sẽ kéo p05 xuống một cách giả tạo (bẫy "IoU khi một bên
    rỗng" đã gặp 3 lần trong repo). Bên gọi phải BỎ mẫu `None`, không quy đổi thành điểm.
    """
    ax1, ay1, ax2, ay2 = (float(v) for v in a)
    bx1, by1, bx2, by2 = (float(v) for v in b)
    aw, ah = ax2 - ax1 + 1.0, ay2 - ay1 + 1.0     # +1: toạ độ bao gồm (pixel cuối nằm trong hộp)
    bw, bh = bx2 - bx1 + 1.0, by2 - by1 + 1.0
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return None
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1) + 1.0)
    iy = max(0.0, min(ay2, by2) - max(ay1, by1) + 1.0)
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else None


def _bbox_hop_le(bbox) -> bool:
    """bbox (x1,y1,x2,y2) có dùng được để dịch mask? Engine trả (0,0,0,0) khi mask rỗng.

    Cho phép bbox MỎNG 1 px (`x1 == x2`) vì mask 1 cột/hàng vẫn là đối tượng thật (vật ở xa);
    chỉ loại hộp suy biến hoàn toàn `(0,0,0,0)` hoặc toạ độ âm/đảo.
    """
    try:
        x1, y1, x2, y2 = (int(v) for v in bbox)
    except (TypeError, ValueError):
        return False
    if x1 < 0 or y1 < 0:
        return False
    return x2 >= x1 and y2 >= y1 and (x2 > 0 or y2 > 0)


def xywh_to_xyxy(bbox) -> tuple:
    """(x,y,w,h) → (x1,y1,x2,y2)."""
    x, y, w, h = (int(v) for v in bbox)
    return (x, y, x + w, y + h)


class _VosWorker(threading.Thread):
    """Chạy model ở LUỒNG RIÊNG để nó không chặn nhịp phát frame.

    Chức năng: nhận frame mới nhất (chỉ giữ MỘT frame — frame cũ bị bỏ, không xếp hàng), chạy
               `engine.process`, trả kết quả kèm frame xám đã xử lý cho luồng chính.
    Lưu ý  : chỉ một luồng được gọi `engine.process` tại một thời điểm (engine không thread-safe).
             Frame gửi sang là bản do luồng chính đọc ra; luồng chính chỉ COPY để vẽ nên không tranh chấp.
    """

    def __init__(self, engine, on_result, on_error=None) -> None:
        super().__init__(name="vos", daemon=True)
        self._engine = engine
        self._on_result = on_result
        self._on_error = on_error
        self._lock = threading.Lock()
        self._pending = None
        self._wake = threading.Event()
        self._stopping = threading.Event()

    def submit(self, seq: int, frame, gray) -> None:
        with self._lock:
            self._pending = (seq, frame, gray)     # luôn là frame MỚI NHẤT
        self._wake.set()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()

    def run(self) -> None:
        while not self._stopping.is_set():
            self._wake.wait(0.2)
            if self._stopping.is_set():
                return
            with self._lock:
                item, self._pending = self._pending, None
            self._wake.clear()
            if item is None:
                continue
            seq, frame, gray = item
            try:
                # Bọc CẢ quá trình xử lý kết quả: lỗi trong `_store_vos`/`_smooth` (dữ liệu model
                # bất thường) cũng phải thành `state=error`, không được để thread chết im lặng.
                self._on_result(seq, self._engine.process(frame), gray)
            except Exception as exc:          # noqa: BLE001 — lỗi model phải thành trạng thái error
                if self._on_error is not None:
                    self._on_error(exc)
                return


class LiveTrackingSession:
    """Một phiên bám trực tiếp: đọc frame → (chờ bbox) → VOS (luồng riêng) + LK → ghi ảnh/trạng thái."""

    def __init__(self, engine, config: LiveTrackConfig, *, lk_tracker=None) -> None:
        self._engine = engine
        self._cfg = config
        self._lk = lk_tracker or LkBoxTracker()
        self._interp = LkBoxTracker()      # nội suy từ frame VOS gần nhất → frame hiện tại
        self._stats = LiveTrackStats(device=config.device)
        self._trail: deque = deque(maxlen=config.trajectory_len)
        self._display_stamps: deque = deque()
        self._vos_stamps: deque = deque()
        self._smoother = MaskSmoother(config.mask_smoothing) if config.mask_smoothing < 1.0 else None
        self._drift_window: deque = deque(maxlen=_STAT_WINDOW)   # đủ mẫu để lấy p05
        # Cửa sổ ĐẾM SỰ KIỆN cho mask rỗng. Để RIÊNG khỏi `_iou_window` (10 mẫu, dùng cho độ ổn
        # định): đây là đại lượng đếm, không phải phân vị, nên cửa sổ ngắn vẫn dùng được — tần suất
        # nền của "VOS trả mask rỗng" trên clip khoẻ đo được là 0/798 lần chạy (binh1).
        self._vos_lost_window: deque = deque(maxlen=_STAT_WINDOW)
        self._age_window: deque = deque(maxlen=_STAT_WINDOW)
        # Ô bao ĐÃ PHÁT theo từng frame: nhờ vậy đo drift đúng frame mà VOS đã thấy, không lệch
        # một khoảng bằng độ trễ suy luận (review 08-11 chỉ ra phép so cũ lệch ~3 frame).
        self._shown_by_frame: deque = deque(maxlen=_SHOWN_HISTORY)
        self._seq_frame: dict = {}       # seq → chỉ số frame đã phát lúc gửi cho VOS
        # (frame_idx, bbox VOS, seq, vos_ms, empty) chờ frame đó được phát để so
        self._pending_drift = None
        # Từng mẫu drift ra CSV (ticket 15): status.json chỉ có mean/p05 ⇒ không đo được độ trễ
        # phát hiện và tỉ lệ báo oan. Lock riêng của logger ⇒ KHÔNG ghi trong `_stats_lock`.
        self._drift_log = DriftSampleLog(Path(config.out_dir) / DRIFT_CSV_NAME)
        self._iou_window: deque = deque(maxlen=10)
        self._shown_iou_window: deque = deque(maxlen=10)
        self._prev_shown_mask = None
        self._prev_raw_mask = None
        self._prev_vos_bbox = None
        self._lock = threading.Lock()          # bảo vệ `_vos_state`
        # Bảo vệ `_stats` + mọi cửa sổ thống kê (luồng VOS ghi, luồng chính đọc). Lock LÁ, KHÔNG
        # tái nhập: đang giữ nó thì cấm gọi hàm có `with self._stats_lock` (dùng biến thể
        # `*_locked` cho phần dùng chung, như `_apply_drift_locked`).
        self._stats_lock = threading.Lock()
        self._vos_state = None          # (seq, result, gray, produced_at, vos_ms) lần VOS gần nhất
        self._mask = None               # mask lần VOS gần nhất (đường chạy đơn luồng)
        self._mask_bbox_xywh = None     # ô bao tại lần VOS đó (để tính độ dịch cho LK)
        self._seq = 0
        self._frame_index = 0
        self._source = None
        self._worker = None
        self._error = None              # lỗi từ luồng VOS (không được nuốt im lặng)
        # mốc an toàn: nếu vì lý do nào đó luồng chính đọc trước khi start() xong
        self._interp_base_result = _FrameResult(0, (0, 0, 0, 0), None, 0.0)
        self._use_lk = config.vos_every > 1

    # ------------------------------------------------------------------ API công khai

    def run(self, stop_event=None) -> LiveTrackStats:
        """Chạy tới khi hết nguồn (file không lặp), đủ frame, hoặc `stop_event` được set."""
        out_dir = Path(self._cfg.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        self._publish_status(out_dir)

        self._source = open_video_source(self._cfg.source).open()
        interval = 1.0 / max(1.0, float(self._cfg.display_fps))
        started = False
        try:
            while not (stop_event is not None and stop_event.is_set()):
                began = time.perf_counter()
                frame = self._source.read()
                if frame is None:
                    frame = self._rewind()
                    if frame is None:
                        break

                if not started:
                    # Trong lúc chờ, vẫn phát khung hình TRƠN để UI hiện luồng và người dùng chọn ô
                    bbox = read_bbox(out_dir / BBOX_NAME)
                    if bbox is None:
                        with self._stats_lock:
                            self._stats.state = STATE_WAITING
                        self._publish_frame(out_dir, frame)
                        self._sleep(interval, began)
                        continue
                    # bbox.json là (x, y, w, h); SAM 2 nhận box (x1, y1, x2, y2) — BUG thật 10-11:
                    # trước đây truyền thẳng nên hộp chọn trên live bị seed sai (w,h thành x2,y2)
                    result = self._engine.start(frame, xywh_to_xyxy(bbox))
                    self._after_vos(frame, result)
                    if self._use_lk:
                        self._start_worker(frame, self._gray(frame))
                    with self._stats_lock:
                        self._stats.state = STATE_TRACKING
                    started = True
                elif self._error is not None:
                    break                       # luồng VOS chết ⇒ dừng phiên, không phát mask cũ
                elif self._use_lk:
                    result = self._result_threaded(frame)
                else:
                    result = self._result_inline(frame)

                self._update_stats(result)
                self._publish_frame(out_dir, self._annotate(frame, result))
                self._publish_status(out_dir)

                if self._cfg.stop_after_frames and self._stats.frames >= self._cfg.stop_after_frames:
                    break
                self._sleep(interval, began)
        finally:
            # Hợp đồng: `stopped` phải có trong `status.json` TRƯỚC khi join luồng VOS (`_stop_worker()`
            # chờ tới 5 s). Hiện ngưỡng treo của watchdog là ≥ 15 s nên cửa sổ này chưa đủ để báo oan,
            # nhưng đặt đúng thứ tự là phòng thủ cho người đọc `status.json` khác (API/log) và rẻ.
            if self._error is None:             # giữ nguyên "error" nếu luồng VOS đã chết
                with self._stats_lock:
                    self._stats.state = STATE_STOPPED
            self._publish_status(out_dir)
            self._stop_worker()
            if self._source is not None:
                self._source.close()
            self._drift_log.close()
            # Ghi lại lần cuối: nếu luồng VOS báo lỗi trong lúc join thì state đã thành `error`.
            self._publish_status(out_dir)
        # Trả BẢN SAO: `join(5 s)` có thể timeout và luồng VOS còn ghi `_stats` sau đó ⇒ trả object
        # sống thì người đọc thấy số nửa cập nhật (review 09-11, P3).
        with self._stats_lock:
            return replace(self._stats)

    # ------------------------------------------------------------------ luồng VOS + nội suy LK

    def _start_worker(self, frame, gray) -> None:
        with self._lock:                      # mốc nội suy ban đầu = frame start(), đặt TRƯỚC submit
            self._vos_state = (0, self._interp_base_result, gray, time.perf_counter(),
                               float(getattr(self._interp_base_result, "elapsed_ms", 0.0)))
        self._worker = _VosWorker(self._engine, self._store_vos, self._on_worker_error)
        self._worker.start()
        self._seq += 1
        self._worker.submit(self._seq, frame, gray)

    def _stop_worker(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker.join(timeout=5.0)
            self._worker = None

    def _on_worker_error(self, exc) -> None:
        """Lỗi trong luồng VOS: ghi trạng thái error để API/UI biết, KHÔNG phát mask đứng yên."""
        self._error = exc
        with self._stats_lock:
            self._stats.state = STATE_ERROR
            self._stats.message = f"model lỗi trong luồng VOS: {exc}"

    def _store_vos(self, seq, result, gray) -> None:
        """Callback của luồng VOS: chỉ ghi kết quả mới nhất (không chặn, không vẽ)."""
        self._record_vos(result)
        frame_idx = self._seq_frame.pop(seq, None)
        # Nội suy LK lệch bao nhiêu ở ĐÚNG frame đó (`seq` để dòng CSV truy được về lần VOS nào)
        self._measure_drift(frame_idx, result, seq)
        self._smooth(result)          # làm mượt + đo độ ổn định NGAY khi mask mới về
        with self._lock:
            self._vos_state = (seq, result, gray, time.perf_counter(),
                               float(getattr(result, "elapsed_ms", 0.0)))

    def _result_threaded(self, frame):
        """Frame này: gửi cho VOS (nếu tới lượt) rồi vẽ bằng mask mới nhất + LK tới frame hiện tại."""
        gray = self._gray(frame)
        self._frame_index += 1
        every = max(1, self._cfg.vos_every)
        if self._frame_index % every == 0:
            self._seq += 1
            self._seq_frame[self._seq] = self._frame_index
            if len(self._seq_frame) > _SHOWN_HISTORY:      # chặn phình nếu VOS hỏng
                self._seq_frame.pop(min(self._seq_frame), None)
            self._worker.submit(self._seq, frame, gray)

        with self._lock:
            state = self._vos_state
        if state is None:
            return self._interp_base_result

        seq, base_result, base_gray, produced_at, vos_ms = state
        self._note_mask_age(time.perf_counter() - produced_at, vos_ms)
        base_bbox = xyxy_to_xywh(base_result.bbox)
        self._interp.reset(base_gray, base_bbox)      # mốc LUÔN là frame VOS → sai số không tích luỹ
        began = time.perf_counter()
        bbox, ok = self._interp.update(gray)
        lk_ms = round((time.perf_counter() - began) * 1000.0, 2)
        with self._stats_lock:            # `_stats` chỉ được ghi dưới lock (xem `__init__`)
            self._stats.lk_ms = lk_ms
        if not ok:
            # LK mất dấu: vẫn phát mask/ô bao của lần VOS gần nhất (không bịa vị trí mới)
            return base_result

        dx = bbox[0] - base_bbox[0]
        dy = bbox[1] - base_bbox[1]
        mask = getattr(base_result, "mask", None)
        return _FrameResult(
            frame_idx=self._frame_index,
            bbox=xywh_to_xyxy(bbox),
            mask=shift_mask(mask, dx, dy) if mask is not None else None,
            elapsed_ms=lk_ms,
        )

    # ------------------------------------------------------------------ đường đơn luồng

    def _result_inline(self, frame):
        """vos_every=1: chạy VOS ngay trong vòng lặp (không LK, không luồng phụ)."""
        self._frame_index += 1
        result = self._engine.process(frame)
        self._after_vos(frame, result)
        return result

    def _after_vos(self, frame, result) -> None:
        """Ghi nhận một lần VOS + đặt mốc LK (đường đơn luồng và frame start())."""
        self._record_vos(result)
        self._smooth(result)
        self._interp_base_result = result
        self._mask = getattr(result, "mask", None)
        self._mask_bbox_xywh = xyxy_to_xywh(result.bbox)
        self._lk.reset(self._gray(frame), self._mask_bbox_xywh)

    def _record_vos(self, result) -> None:
        with self._stats_lock:
            self._stats.vos_ms = round(float(getattr(result, "elapsed_ms", 0.0)), 1)
            self._stats.vos_runs += 1
            self._vos_stamps.append(time.perf_counter())
            self._trim(self._vos_stamps)
        self._measure_stability(result)

    def _shown_at(self, frame_idx):
        """Ô bao đã PHÁT ở frame `frame_idx` (tra ngược trong cửa sổ) — None nếu không có.

        `reversed()` PHẢI trong `_stats_lock`: đây là cấu trúc **thật sự có hai luồng** — luồng
        chính `append` (`_update_stats_locked`) còn luồng VOS duyệt (`_measure_drift`). `reversed()`
        của `deque` cũng kiểm `state` như iterator xuôi ⇒ sửa giữa lúc duyệt là
        `RuntimeError: deque mutated during iteration` ⇒ luồng VOS chết (review 10-11, P1).
        Lock ở đây là lock lá, và hàm này chỉ được gọi khi KHÔNG giữ lock (không tái nhập).
        """
        with self._stats_lock:
            return self._shown_at_locked(frame_idx)

    def _shown_at_locked(self, frame_idx):
        """Như `_shown_at` nhưng gọi khi ĐÃ giữ `_stats_lock` (hậu tố `_locked`, không acquire)."""
        for idx, bbox in reversed(self._shown_by_frame):
            if idx == frame_idx:
                return bbox
        return None

    def _measure_drift(self, frame_idx, result, seq=None) -> None:
        """Nội suy LK **sai bao nhiêu** ở đúng frame mà VOS vừa trả kết quả.

        Ý nghĩa: `drift_iou` = IoU giữa ô bao mà người xem đã thấy ở frame đó (do LK nội suy) và
        ô bao VOS vừa sửa lại. Đây là **độ tự nhất quán** của ô đang hiển thị, KHÔNG phải độ chính
        xác so với ground-truth (VOS bám lệch hệ thống mà vẫn ổn định thì drift vẫn cao) — đo độ
        chính xác phải dùng mIoU vs GT.

        Bỏ đo khi tắt LK (`vos_every=1`): lúc đó không có nội suy, thứ đo được chỉ là độ ổn định
        bbox của chính VOS — gọi nó là drift sẽ khiến "tắt LK" trông tốt hơn một cách vô nghĩa.
        """
        if not self._use_lk:
            return
        fresh = getattr(result, "bbox", None)
        if frame_idx is None or fresh is None or not _bbox_hop_le(fresh):
            return
        # Tra cứu + hẹn pending trong MỘT critical section: nếu tách hai khối thì luồng chính có thể
        # phát đúng frame này xen vào giữa (thấy `_pending_drift` còn cũ ⇒ bỏ) ⇒ mất một mẫu drift
        # (review 10-11 vòng 2, P3).
        with self._stats_lock:
            shown = self._shown_at_locked(frame_idx)
            if shown is None:
                # Kết quả về TRƯỚC khi frame đó được phát (engine rất nhanh) ⇒ hẹn so lúc phát
                # frame; nếu frame đó đã trôi qua thì BỎ, không lấy ô bao của frame khác (đo sai thứ).
                self._pending_drift = (frame_idx, tuple(fresh), seq,
                                       float(getattr(result, "elapsed_ms", 0.0)),
                                       self._mask_empty(result))
                return
        if not _bbox_hop_le(shown):
            return
        value = _bbox_iou(shown, fresh)
        self._record_drift(value)
        self._log_drift_sample(frame_idx=frame_idx, seq=seq, result=result, value=value)

    @staticmethod
    def _mask_empty(result):
        """Mask của kết quả VOS có RỖNG không — `None` khi engine không trả mask (chưa đo)."""
        mask = getattr(result, "mask", None)
        if mask is None:
            return None
        return not bool(mask.any())

    def _log_drift_sample(self, *, frame_idx, seq, value, result=None, vos_ms=None,
                          empty=None, bbox=None) -> None:
        """Ghi MỘT dòng CSV cho mẫu drift (ticket 15). PHẢI gọi khi KHÔNG giữ `_stats_lock`.

        `result` là kết quả VOS (có `elapsed_ms`/`mask`/`bbox`); nhánh `_pending_drift` tới hạn thì
        dữ liệu đã tách sẵn trong tuple hẹn (`vos_ms`/`empty`/`bbox`) → không truyền `result`.
        """
        self._drift_log.write(
            frame_idx=frame_idx, seq=seq,
            vos_ms=(float(getattr(result, "elapsed_ms", 0.0)) if vos_ms is None else vos_ms),
            empty=(self._mask_empty(result) if empty is None else empty),
            drift_iou=value,
            bbox=(getattr(result, "bbox", None) if bbox is None else bbox))

    def _record_drift(self, value) -> None:
        """Ghi một mẫu drift (bỏ mẫu `None` — ô suy biến thì không đủ tin để chấm).

        `append` PHẢI trong `_stats_lock`: `_apply_drift_locked()` duyệt deque bằng `np.fromiter`
        trong lúc giữ lock, còn `_update_stats_locked()` (luồng chính) cũng append trong lock ⇒ nếu
        nguồn ghi này ở ngoài lock thì deque bị sửa giữa lúc duyệt ⇒
        `RuntimeError: deque mutated during iteration` ⇒ luồng VOS chết ⇒ `state=error`
        (ticket 17; test stress bắt được trước khi sửa).
        """
        if value is None:
            return
        with self._stats_lock:
            self._drift_window.append(value)
            self._apply_drift_locked()

    def _apply_drift_locked(self) -> None:
        """Tính lại thống kê drift — gọi khi ĐÃ giữ `_stats_lock` (tên có hậu tố `_locked`)."""
        if not self._drift_window:
            return
        values = np.fromiter(self._drift_window, dtype=float)
        self._stats.drift_n = len(values)
        self._stats.drift_iou = round(float(values.mean()), 3)
        self._stats.drift_iou_p05 = (round(float(np.percentile(values, 5)), 3)
                                     if len(values) >= _STAT_MIN_SAMPLES else None)

    def _note_mask_age(self, seconds: float, vos_ms: float = 0.0) -> None:
        """Tuổi của mask đang hiển thị (ms) + p95; `mask_age_total_ms` tính cả thời gian suy luận.

        `seconds` đo từ lúc kết quả model **sẵn sàng** ⇒ chưa gồm `vos_ms`. Người xem thực tế thấy
        ảnh cũ hơn thế đúng bằng `vos_ms`, nên phải báo cả hai: `mask_age_ms` (tuổi mask) và
        `mask_age_total_ms` (tuổi dữ liệu ảnh). Ngân sách 150 ms dùng con số **total**.
        """
        age_ms = max(0.0, float(seconds) * 1000.0)
        vos_ms = max(0.0, float(vos_ms))
        # `append` + `np.fromiter` + `percentile` trong CÙNG `_stats_lock` (ticket 20): hôm nay chỉ
        # có một luồng ghi, nhưng đây đúng mẫu code mà ticket 17 vừa phải sửa cho `_drift_window`
        # (`RuntimeError: deque mutated during iteration` nếu một người sửa sau thêm luồng thứ hai).
        with self._stats_lock:
            self._age_window.append(age_ms)
            total_values = np.fromiter((v + vos_ms for v in self._age_window), dtype=float)
            self._stats.mask_age_ms = round(age_ms, 1)
            self._stats.mask_age_total_ms = round(age_ms + vos_ms, 1)
            self._stats.age_n = len(self._age_window)
            self._stats.mask_age_p95 = (round(float(np.percentile(total_values, 95)), 1)
                                        if len(self._age_window) >= _STAT_MIN_SAMPLES
                                        else None)

    def _measure_stability(self, result) -> None:
        """IoU giữa hai mask VOS liên tiếp — con số trung thực cho "mask có nhấp nháy không".

        Mask RỖNG không vào cửa sổ IoU (`mask_iou(rỗng, rỗng) = 1,0` sẽ biến "mất dấu hoàn toàn"
        thành "độ ổn định 100 %" trên UI — lỗi P2, review 08-11), nhưng chúng **ĐƯỢC ĐẾM** trong
        `_vos_lost_window` (⇒ `empty_frac_window`) và `empty_runs`.
        """
        raw = getattr(result, "mask", None)
        if raw is None:
            return
        # Đẩy ĐÚNG MỘT mẫu cho MỖI lần VOS trả kết quả: có vật (False) hay rỗng (True). Nếu chỉ
        # đẩy khi rỗng thì tỉ lệ không bao giờ giảm sau khi model bám lại (đúng lỗi mà đại lượng
        # này sinh ra để sửa).
        # MỘT khối lock cho cả cửa sổ + bộ đếm + stability: nếu tách hai khối thì một snapshot
        # `status.json` có thể thấy `empty_frac_window` đã tính mẫu rỗng MỚI trong khi `empty_runs`
        # còn là số cũ (review 09-11 vòng 2, P3).
        with self._stats_lock:
            # `append` PHẢI trong lock cùng với `sum()`: giữ bất biến "deque chỉ bị sửa khi giữ
            # `_stats_lock`" (hôm nay chỉ một luồng gọi, nhưng mẫu code sai sẽ bị copy).
            self._vos_lost_window.append(not raw.any())
            self._stats.empty_window_n = len(self._vos_lost_window)
            self._stats.empty_frac_window = (
                round(sum(self._vos_lost_window) / len(self._vos_lost_window), 3)
                if len(self._vos_lost_window) >= _EMPTY_WINDOW_MIN else None)
            if not raw.any():
                self._stats.empty_runs += 1
                # Mất dấu ⇒ KHÔNG có gì để nói về độ ổn định hiện tại: không giữ số cũ, không nối
                # IoU xuyên qua khoảng mất dấu (mask trước và sau là hai chuyện khác nhau).
                # Chưa có mẫu nào ⇒ `None` (CHƯA ĐO); đã có mẫu ⇒ `0,0` (số đo được: mask đang rỗng).
                self._stats.stability = 0.0 if self._iou_window else None
            self._stats.stability_n = len(self._iou_window)
        if not raw.any():
            self._prev_raw_mask = None
            return
        if self._prev_raw_mask is not None:
            # `mask_iou` tính NGOÀI lock (cùng lý do như `_smooth`): chỉ `append` + `sum()` cần lock.
            value = mask_iou(self._prev_raw_mask, raw)
            with self._stats_lock:
                self._iou_window.append(value)
                self._stats.stability = round(sum(self._iou_window) / len(self._iou_window), 3)
                self._stats.stability_n = len(self._iou_window)
        self._prev_raw_mask = raw

    def _smooth(self, result) -> None:
        """Làm mượt mask của kết quả VOS (nếu bật) và ĐO độ êm của mask HIỂN THỊ.

        `stability` = IoU của mask VOS thô (model ổn định không), `stability_shown` = IoU của mask
        đã làm mượt (mắt thấy êm không). Hai số tách nhau để không tự lừa mình: làm mượt làm IoU
        hiển thị TĂNG nhưng cái giá là mask trễ hình dạng thật.
        """
        raw = getattr(result, "mask", None)
        if raw is None:
            return

        shown = raw
        smoother = self._smoother
        if smoother is not None:
            bbox = xyxy_to_xywh(result.bbox)
            # CHỈ dịch bộ tích luỹ khi bbox MỚI hợp lệ. Khi model mất vật, engine trả mask rỗng
            # kèm bbox (0,0,0,0) (src/tracker_engine.py) ⇒ dịch theo nó sẽ "teleport" bộ tích luỹ
            # về góc khung: hold không bao giờ chạy và mask cũ hiện ở SAI vị trí (lỗi P1, review
            # 08-11). Không hợp lệ ⇒ coi là "model không thấy vật", giữ nguyên mốc cũ.
            if _bbox_hop_le(result.bbox):
                if self._prev_vos_bbox is not None:
                    smoother.shift(bbox[0] - self._prev_vos_bbox[0], bbox[1] - self._prev_vos_bbox[1])
                self._prev_vos_bbox = bbox
            shown = smoother.update(raw)
            result.mask = shown
            with self._stats_lock:
                self._stats.mask_holds = smoother.holds
                self._stats.mask_drops = smoother.drops

        if not shown.any():
            # Cùng lý do như `stability`: màn hình trống mà báo IoU = 1,0 là số liệu sai. Và `0,0`
            # chỉ có nghĩa "đo được" khi ĐÃ CÓ mẫu — cửa sổ rỗng ⇒ `None` = CHƯA ĐO (ticket 19).
            with self._stats_lock:
                self._stats.stability_shown = 0.0 if self._shown_iou_window else None
                self._stats.stability_shown_n = len(self._shown_iou_window)
            self._prev_shown_mask = None
            return
        if self._prev_shown_mask is not None:
            # `mask_iou` tính NGOÀI lock (không gian ảnh 480p/720p ⇒ ~0,2–1 ms, dài hơn hẳn
            # `np.percentile` 200 mẫu); chỉ `append` + `sum()` nằm trong lock (ticket 20).
            value = mask_iou(self._prev_shown_mask, shown)
            with self._stats_lock:
                self._shown_iou_window.append(value)
                self._stats.stability_shown = round(
                    sum(self._shown_iou_window) / len(self._shown_iou_window), 3)
                self._stats.stability_shown_n = len(self._shown_iou_window)
        self._prev_shown_mask = shown

    @staticmethod
    def _gray(frame):
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # ------------------------------------------------------------------ số liệu & vẽ

    def _update_stats(self, result) -> None:
        with self._stats_lock:
            row = self._update_stats_locked(result)
        # Ghi CSV NGOÀI lock: I/O trong `_stats_lock` sẽ chặn luồng VOS (nó cũng cần lock này).
        if row is not None:
            self._log_drift_sample(**row)

    def _update_stats_locked(self, result):
        """Cập nhật số liệu; TRẢ về dòng CSV cần ghi (mẫu `_pending_drift` tới hạn) hoặc `None`."""
        now = time.perf_counter()
        self._stats.frames += 1
        self._display_stamps.append(now)
        self._trim(self._display_stamps)
        self._stats.measured_fps = self._rate(self._display_stamps)
        self._stats.vos_fps = self._rate(self._vos_stamps)

        mask = getattr(result, "mask", None)
        # Ghi theo bộ đếm frame CỦA PHIÊN (không phải `result.frame_idx` của engine): `_seq_frame`
        # ánh xạ seq→bộ đếm này lúc submit, nên hai bên phải cùng một hệ.
        shown = tuple(result.bbox) if _bbox_hop_le(result.bbox) else None
        self._shown_by_frame.append((self._frame_index, shown))
        pending = self._pending_drift
        csv_row = None
        if pending is not None:
            self._pending_drift = None
            if pending[0] == self._frame_index and shown is not None:
                value = _bbox_iou(shown, pending[1])
                if value is not None:          # ở đây ĐANG giữ `_stats_lock` ⇒ không gọi _record_drift
                    self._drift_window.append(value)
                    self._apply_drift_locked()
                    csv_row = {"frame_idx": self._frame_index, "seq": pending[2],
                               "vos_ms": pending[3], "empty": pending[4],
                               "value": value, "bbox": pending[1]}
            # pending[0] < frame hiện tại ⇒ frame đó đã trôi qua, bỏ mẫu (không bịa)
        lost = mask is None or not mask.any()
        self._stats.lost_streak = self._stats.lost_streak + 1 if lost else 0
        self._stats.bbox = [int(v) for v in result.bbox]
        if not lost:
            x1, y1, x2, y2 = result.bbox
            self._trail.append((int((x1 + x2) / 2), int((y1 + y2) / 2)))
        return csv_row

    def _annotate(self, frame, result):
        """Tô mask + ô bao + quỹ đạo + HUD. Chữ HUD dùng ASCII vì font Hershey không có dấu."""
        img = frame.copy()
        mask = getattr(result, "mask", None)
        if mask is not None and mask.shape != frame.shape[:2]:
            # Nguồn đổi độ phân giải giữa phiên (relay /snapshot.jpg, điện thoại xoay máy) ⇒
            # `tint[mask]` sẽ IndexError. Bỏ mask frame này, không làm chết phiên.
            mask = None
        if mask is not None and mask.any():
            tint = img.copy()
            tint[mask] = _OVERLAY_COLOR_MASK
            img = cv2.addWeighted(img, 1.0 - _OVERLAY_ALPHA, tint, _OVERLAY_ALPHA, 0)

        x1, y1, x2, y2 = [int(v) for v in result.bbox]
        if x2 > x1 and y2 > y1:
            cv2.rectangle(img, (x1, y1), (x2, y2), _OVERLAY_COLOR_BOX, 2)

        points = list(self._trail)
        for index in range(1, len(points)):
            cv2.line(img, points[index - 1], points[index], (255, 0, 255), 2)  # BGR tím

        hud = (f"LIVE {self._stats.measured_fps:.1f}fps | VOS {self._stats.vos_fps:.1f}fps "
               f"{self._stats.vos_ms:.0f}ms | LK {self._stats.lk_ms:.1f}ms")
        if self._stats.lost_streak:
            hud += f" | LOST {self._stats.lost_streak}"
        # ASCII (không dấu) là BẮT BUỘC: cv2.putText/Hershey không render được dấu tiếng Việt
        cv2.putText(img, hud, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        return img

    # ------------------------------------------------------------------ ghi ra đĩa

    def _publish_frame(self, out_dir: Path, frame) -> None:
        ok, buffer = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self._cfg.jpeg_quality]
        )
        if ok:
            write_bytes_atomic(out_dir / FRAME_NAME, bytes(buffer))

    def _publish_status(self, out_dir: Path) -> None:
        """Ghi ảnh chụp NHẤT QUÁN của `_stats` (không trộn số của hai thế hệ)."""
        with self._stats_lock:
            snapshot = replace(self._stats)
        write_json_atomic(out_dir / STATUS_NAME, status_payload(snapshot))

    # ------------------------------------------------------------------ tiện ích

    @staticmethod
    def _trim(stamps: deque) -> None:
        cutoff = time.perf_counter() - _FPS_WINDOW_S
        while stamps and stamps[0] < cutoff:
            stamps.popleft()

    @staticmethod
    def _rate(stamps: deque) -> float:
        if len(stamps) < 2:
            return 0.0
        span = stamps[-1] - stamps[0]
        return round((len(stamps) - 1) / span, 1) if span > 0 else 0.0

    def _rewind(self):
        """Mở lại file từ đầu (demo live bằng video); nguồn thật hoặc lỗi → None."""
        if not self._cfg.loop_files:
            return None
        try:
            source, self._source = self._source, None
            if source is not None:
                source.close()
            self._source = open_video_source(self._cfg.source).open()
            return self._source.read()
        except (OSError, RuntimeError):
            return None

    @staticmethod
    def _sleep(interval: float, began: float) -> None:
        remaining = interval - (time.perf_counter() - began)
        if remaining > 0:
            time.sleep(remaining)
