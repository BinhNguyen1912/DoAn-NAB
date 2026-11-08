"""
LiveTrackingSession — vòng lặp bám đối tượng cho LUỒNG TRỰC TIẾP (chạy trong tiến trình worker).

Chức năng: mở nguồn frame, chờ ô chọn đối tượng (hoặc nhận sẵn), bám bằng engine VOS **cách quãng**
           (mỗi `vos_every` frame) và dùng **LK optical flow** cho các frame còn lại; vẽ overlay và
           ghi **frame mới nhất** + **trạng thái** ra thư mục chia sẻ để API đọc và phát.
Input  : engine (TrackerEngine hoặc engine giả trong test), LiveTrackConfig.
Output : `<out_dir>/frame.jpg` (JPEG mới nhất), `<out_dir>/status.json`, `<out_dir>/worker.log`.
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

    def __post_init__(self) -> None:
        """Kiểm tra tham số ở MỘT chỗ — trước đây schema API cho 0.0 còn worker clamp 0.05,
        hai bên hiểu khác nhau (lỗi P2, review 08-11)."""
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
    frames: int = 0               # số frame ĐÃ PHÁT (nhịp display)
    vos_runs: int = 0             # số lần CHẠY MODEL (mask mới)
    measured_fps: float = 0.0     # FPS phát thực đo
    vos_fps: float = 0.0          # FPS của VOS (nhịp mask thật)
    vos_ms: float = 0.0           # độ trễ suy luận gần nhất
    lk_ms: float = 0.0            # độ trễ LK gần nhất
    stability: float = 0.0        # IoU trung bình giữa hai mask VOS liên tiếp (1,0 = không nhấp nháy)
    stability_shown: float = 0.0  # IoU giữa hai mask ĐÃ LÀM MƯỢT (càng cao càng êm mắt)
    drift_iou: float = 0.0        # IoU giữa ô bao ĐANG HIỂN THỊ và ô bao của lần VOS kế tiếp
    drift_iou_p05: float = 0.0    # phân vị 5 % của drift (đuôi xấu: lúc nội suy lệch nhất)
    mask_age_ms: float = 0.0      # tuổi của mask đang hiển thị (ms) — mask cũ bao lâu
    mask_age_p95: float = 0.0     # phân vị 95 % của tuổi mask trong cửa sổ gần nhất
    empty_runs: int = 0           # số lần VOS trả mask RỖNG (mất dấu thật)
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
        "frames": stats.frames,
        "vos_runs": stats.vos_runs,
        "measured_fps": stats.measured_fps,
        "vos_fps": stats.vos_fps,
        "vos_ms": stats.vos_ms,
        "lk_ms": stats.lk_ms,
        "drift_iou": stats.drift_iou,
        "drift_iou_p05": stats.drift_iou_p05,
        "mask_age_ms": stats.mask_age_ms,
        "mask_age_p95": stats.mask_age_p95,
        "stability": stats.stability,
        "stability_shown": stats.stability_shown,
        "empty_runs": stats.empty_runs,
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


def _bbox_iou(a, b) -> float:
    """IoU hai ô bao (x1,y1,x2,y2) — dùng để đo độ lệch của nội suy LK."""
    ax1, ay1, ax2, ay2 = (float(v) for v in a)
    bx1, by1, bx2, by2 = (float(v) for v in b)
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


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
        self._stats = LiveTrackStats()
        self._trail: deque = deque(maxlen=config.trajectory_len)
        self._display_stamps: deque = deque()
        self._vos_stamps: deque = deque()
        self._smoother = MaskSmoother(config.mask_smoothing) if config.mask_smoothing < 1.0 else None
        self._drift_window: deque = deque(maxlen=200)   # đủ mẫu để lấy p05
        self._age_window: deque = deque(maxlen=200)
        self._last_display_bbox = None   # ô bao đã phát ở frame gần nhất (để đo drift)
        self._iou_window: deque = deque(maxlen=10)
        self._shown_iou_window: deque = deque(maxlen=10)
        self._prev_shown_mask = None
        self._prev_raw_mask = None
        self._prev_vos_bbox = None
        self._lock = threading.Lock()          # bảo vệ `_vos_state`
        self._stats_lock = threading.Lock()    # bảo vệ `_stats` (luồng VOS ghi, luồng chính đọc)
        self._vos_state = None          # (seq, result, gray) của lần VOS gần nhất
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
            self._stop_worker()
            if self._source is not None:
                self._source.close()
            if self._error is None:             # giữ nguyên "error" nếu luồng VOS đã chết
                with self._stats_lock:
                    self._stats.state = STATE_STOPPED
            self._publish_status(out_dir)
        return self._stats

    # ------------------------------------------------------------------ luồng VOS + nội suy LK

    def _start_worker(self, frame, gray) -> None:
        with self._lock:                      # mốc nội suy ban đầu = frame start(), đặt TRƯỚC submit
            self._vos_state = (0, self._interp_base_result, gray, time.perf_counter())
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
        self._measure_drift(result)    # nội suy LK đã lệch bao nhiêu so với lần VOS này
        self._smooth(result)          # làm mượt + đo độ ổn định NGAY khi mask mới về
        with self._lock:
            self._vos_state = (seq, result, gray, time.perf_counter())

    def _result_threaded(self, frame):
        """Frame này: gửi cho VOS (nếu tới lượt) rồi vẽ bằng mask mới nhất + LK tới frame hiện tại."""
        gray = self._gray(frame)
        self._frame_index += 1
        every = max(1, self._cfg.vos_every)
        if self._frame_index % every == 0:
            self._seq += 1
            self._worker.submit(self._seq, frame, gray)

        with self._lock:
            state = self._vos_state
        if state is None:
            return self._interp_base_result

        seq, base_result, base_gray, produced_at = state
        self._note_mask_age(time.perf_counter() - produced_at)
        base_bbox = xyxy_to_xywh(base_result.bbox)
        self._interp.reset(base_gray, base_bbox)      # mốc LUÔN là frame VOS → sai số không tích luỹ
        began = time.perf_counter()
        bbox, ok = self._interp.update(gray)
        self._stats.lk_ms = round((time.perf_counter() - began) * 1000.0, 2)
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
            elapsed_ms=self._stats.lk_ms,
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
        self._measure_drift(result)
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

    def _measure_drift(self, result) -> None:
        """LK nội suy lệch bao nhiêu so với ô bao của lần VOS **kế tiếp**?

        Đây là câu hỏi mà cả kiến trúc hybrid đứng trên, và trước đây repo **chưa đo lần nào**:
        `stability` chỉ nói mask có nhấp nháy không, không nói nội suy có bám đúng không.
        Chỉ so khi cả hai ô bao đều hợp lệ (mask rỗng ⇒ bbox `(0,0,0,0)` ⇒ không có gì để so).
        """
        shown = self._last_display_bbox
        fresh = getattr(result, "bbox", None)
        if shown is None or fresh is None:
            return
        if not (_bbox_hop_le(shown) and _bbox_hop_le(fresh)):
            return
        self._drift_window.append(_bbox_iou(shown, fresh))
        values = np.fromiter(self._drift_window, dtype=float)
        with self._stats_lock:
            self._stats.drift_iou = round(float(values.mean()), 3)
            self._stats.drift_iou_p05 = round(float(np.percentile(values, 5)), 3)

    def _note_mask_age(self, seconds: float) -> None:
        """Ghi tuổi mask đang hiển thị (ms) + p95 trong cửa sổ gần nhất."""
        age_ms = max(0.0, float(seconds) * 1000.0)
        self._age_window.append(age_ms)
        if len(self._age_window) < 5:              # chưa đủ mẫu: chỉ báo giá trị tức thời
            with self._stats_lock:
                self._stats.mask_age_ms = round(age_ms, 1)
            return
        values = np.fromiter(self._age_window, dtype=float)
        with self._stats_lock:
            self._stats.mask_age_ms = round(age_ms, 1)
            self._stats.mask_age_p95 = round(float(np.percentile(values, 95)), 1)

    def _measure_stability(self, result) -> None:
        """IoU giữa hai mask VOS liên tiếp — con số trung thực cho "mask có nhấp nháy không".

        Mask RỖNG không vào mẫu: `mask_iou(rỗng, rỗng) = 1,0` sẽ biến "mất dấu hoàn toàn" thành
        "độ ổn định 100 %" trên UI (lỗi P2, review 08-11). Mất dấu được đếm riêng ở `empty_runs`.
        """
        raw = getattr(result, "mask", None)
        if raw is None:
            return
        if not raw.any():
            with self._stats_lock:
                self._stats.empty_runs += 1
                # Mất dấu ⇒ KHÔNG có gì để nói về độ ổn định: đặt 0 (không giữ số cũ, không
                # nối IoU xuyên qua khoảng mất dấu — mask trước và sau là hai chuyện khác nhau).
                self._stats.stability = 0.0
            self._prev_raw_mask = None
            return
        if self._prev_raw_mask is not None:
            self._iou_window.append(mask_iou(self._prev_raw_mask, raw))
            with self._stats_lock:
                self._stats.stability = round(sum(self._iou_window) / len(self._iou_window), 3)
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
            # Cùng lý do như `stability`: màn hình trống mà báo IoU = 1,0 là số liệu sai.
            with self._stats_lock:
                self._stats.stability_shown = 0.0
            self._prev_shown_mask = None
            return
        if self._prev_shown_mask is not None:
            self._shown_iou_window.append(mask_iou(self._prev_shown_mask, shown))
            with self._stats_lock:
                self._stats.stability_shown = round(
                    sum(self._shown_iou_window) / len(self._shown_iou_window), 3)
        self._prev_shown_mask = shown

    @staticmethod
    def _gray(frame):
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # ------------------------------------------------------------------ số liệu & vẽ

    def _update_stats(self, result) -> None:
        with self._stats_lock:
            self._update_stats_locked(result)

    def _update_stats_locked(self, result) -> None:
        now = time.perf_counter()
        self._stats.frames += 1
        self._display_stamps.append(now)
        self._trim(self._display_stamps)
        self._stats.measured_fps = self._rate(self._display_stamps)
        self._stats.vos_fps = self._rate(self._vos_stamps)

        mask = getattr(result, "mask", None)
        self._last_display_bbox = tuple(result.bbox) if _bbox_hop_le(result.bbox) else None
        lost = mask is None or not mask.any()
        self._stats.lost_streak = self._stats.lost_streak + 1 if lost else 0
        self._stats.bbox = [int(v) for v in result.bbox]
        if not lost:
            x1, y1, x2, y2 = result.bbox
            self._trail.append((int((x1 + x2) / 2), int((y1 + y2) / 2)))

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
