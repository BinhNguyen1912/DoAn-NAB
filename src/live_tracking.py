"""
LiveTrackingSession — vòng lặp bám đối tượng cho LUỒNG TRỰC TIẾP (chạy trong tiến trình worker).

Chức năng: mở nguồn frame, chờ ô chọn đối tượng (hoặc nhận sẵn), bám bằng engine VOS **cách quãng**
           (mỗi `vos_every` frame) và dùng **LK optical flow** cho các frame còn lại; vẽ overlay và
           ghi **frame mới nhất** + **trạng thái** ra thư mục chia sẻ để API đọc và phát.
Input  : engine (TrackerEngine hoặc engine giả trong test), LiveTrackConfig.
Output : `<out_dir>/frame.jpg` (JPEG mới nhất), `<out_dir>/status.json`, `<out_dir>/worker.log`,
         và `<out_dir>/drift_samples.csv` (từng mẫu drift — xem `src/drift_samples.py`; file chỉ
         sinh ra khi phiên thật sự đo được mẫu nào).
         `<out_dir>/bbox.json` và `<out_dir>/worker.pid` do **phía API** ghi (người chọn ô / adapter
         `WorkerFrameSource`); module này chỉ **đọc** `bbox.json`. Vì thế CLI và API **không** được dùng
         chung `--out-dir` — xem `phien_live_dang_giu()` (ticket #37).
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
from src import tracking_health
from src.light_tracker import DEFAULT_MAX_MAD, LkBoxTracker, shift_mask, warp_mask
from src.mask_filter import MaskSmoother, mask_iou
from src.live_pipeline import _OVERLAY_ALPHA, _OVERLAY_COLOR_BOX, _OVERLAY_COLOR_MASK
from src.video_source import looks_like_file, open_video_source
from src.url_safe import an_userinfo

FRAME_NAME = "frame.jpg"
STATUS_NAME = "status.json"
BBOX_NAME = "bbox.json"
# PID của worker đang giữ thư mục live (adapter API ghi). Khai ở ĐÂY để CLI (`tools/live_worker.py`)
# kiểm được "thư mục này đang có phiên khác dùng" mà không phải import module API (ticket #37).
PID_NAME = "worker.pid"

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
# Định nghĩa tuổi mask đi kèm MỌI `status.json`: repo có HAI định nghĩa (AGENTS §6) nên file phải tự
# khai nó đang dùng cái nào — người trích số không phải đi đọc mã để biết `mask_age_p95` là tuổi thật
# hay định nghĩa cũ (thiếu `vos_ms`).
DINH_NGHIA_TUOI_MASK = (
    "mask_age_total_ms = queue + pre + vos + post + age (tuổi dữ liệu thật, từ 14-11); "
    "mask_age_cu_ms = age + vos (định nghĩa CŨ, chỉ để so với số trước 14-11). "
    "Mỗi frame PHÁT ghi ĐÚNG MỘT mẫu (kể cả frame đầu của engine.start()); vos_every=1 (đơn luồng) "
    "⇒ age = 0 và total = pre + vos + post, vì frame vừa được VOS xử lý chính là frame đang phát. "
    "Pha chưa đo được tính 0; riêng vos_every=1 KHÔNG có drift_iou (không nội suy LK)"
)
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
    # Xuất mask THẬT tại đúng những `frame_idx` này để chấm mIoU so với GT gán tay (việc #6).
    # Chuỗi "0,50,120" hoặc bộ int. Rỗng = không xuất (mặc định: chấm điểm là việc CHỦ ĐỘNG, không
    # phải việc âm thầm ghi hàng trăm MB mask mỗi phiên).
    dump_mask_frames: tuple = ()
    dump_mask_dir: str = ""
    # Cửa chống-trôi của LK (px, độ tản trung vị vector dịch). Mặc định = `light_tracker.DEFAULT_MAX_MAD`
    # (1,5). Có mặt ở đây **chỉ để ĐO** (ticket #38): đo offline 19-11 cho thấy 1,5 px chặn LK quá mức
    # (ok_frac trong khung 0,227; nới 6,0 ⇒ 0,568 mà IoU khi-ok chỉ giảm 0,031). Đổi GIÁ TRỊ MẶC ĐỊNH
    # phải chờ A/B live 2 clip + kiểm ảnh ô bao không bị kéo vào nền — xem ticket #38.
    lk_max_mad: float = DEFAULT_MAX_MAD
    # Nội suy CẢ TỈ LỆ (+ xoay) trong LK, không chỉ dịch (mặc định TẮT: giữ nguyên số đã công bố).
    # Lý do tồn tại: đo trên GT người tô 20-11, ô hiển thị lệch kích thước tới −132 px và tịnh tiến
    # KHÔNG THỂ chữa được lệch kích thước (`docs/task/20-11-2026-cai-gia-do-chinh-xac-cua-hybrid.md`).
    # Bật/tắt được để A/B được chèn kẽ (không đổi mặc định khi chưa có số chứng minh tốt hơn).
    lk_scale: bool = False
    # DỤNG CỤ ĐO (ticket #38): ghi ô bao ĐANG HIỂN THỊ ở **mọi frame đã phát** ra CSV
    # (`frame_idx,x1,y1,x2,y2,lk_ok,ly_do,ly_do_khop,scale,angle_deg,n_diem` — 5 cột cuối từ ticket
    # #39; `scale`/`angle_deg` TRỐNG khi similarity không được dùng). Vì sao cần: CSV drift chỉ có dòng ở các lần VOS (mỗi N frame),
    # nên không chấm được ô người xem thấy ở các frame GT lẻ (`binh1`: 91/181/211/241 không chia hết
    # cho 3). Chuỗi rỗng = TẮT (mặc định) — không ghi gì thêm.
    dump_shown_csv: str = ""

    def __post_init__(self) -> None:
        """Kiểm tra tham số ở MỘT chỗ — trước đây schema API cho 0.0 còn worker clamp 0.05,
        hai bên hiểu khác nhau (lỗi P2, review 08-11)."""
        # Cùng hàm chuẩn hoá với CLI/API/worker ⇒ `--device CUDA ` cũng thành `cuda`.
        self.device = normalize_device(self.device)
        self.dump_mask_frames = _parse_frame_list(self.dump_mask_frames)
        if not 0.0 < float(self.mask_smoothing) <= 1.0:
            raise ValueError(
                f"mask_smoothing phải trong khoảng (0, 1]; nhận {self.mask_smoothing!r} "
                "(1.0 = tắt làm mượt)"
            )
        if int(self.vos_every) < 1:
            raise ValueError(f"vos_every phải >= 1; nhận {self.vos_every!r}")
        if float(self.display_fps) <= 0:
            raise ValueError(f"display_fps phải > 0; nhận {self.display_fps!r}")
        if not float(self.lk_max_mad) > 0:
            raise ValueError(f"lk_max_mad phải > 0; nhận {self.lk_max_mad!r}")


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
    # Cấu hình phiên: phần ĐƯỢC YÊU CẦU (CLI/API) + `image_size_hieu_luc` đọc từ engine
    # (`cau_hinh_hieu_luc`). `status.json` echo NGUYÊN khối ⇒ artifact tự kiểm được "cấu hình chạy ==
    # cấu hình yêu cầu" thay vì tin CLI (Next steps 14-11, góc "độ bền & hiệu năng").
    # Rỗng = worker bản cũ không ghi (KHÔNG phải "đã kiểm và khớp").
    cau_hinh: dict = field(default_factory=dict)
    # Khoá LỆCH giữa yêu cầu và hiệu lực, vd `["image_size"]`. Rỗng = khớp, HOẶC chưa kiểm được
    # (`image_size_hieu_luc` là None) — người đọc phải xem `cau_hinh.image_size_hieu_luc` để phân biệt.
    cau_hinh_lech: list = field(default_factory=list)
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
    # Cờ phán quyết chất lượng bám (ticket #14): `ok | model_lost | drift_trend | not_measured`
    # + lý do + p05 + `n` + `empty_frac` của CÙNG cửa sổ mẫu. Rỗng = worker bản cũ không ghi
    # (KHÔNG phải "đã kiểm và ổn"). Tính trong `_apply_drift_locked` bằng hàm thuần
    # `src/tracking_health.py` (không phụ thuộc torch ⇒ test được headless).
    suc_khoe: dict = field(default_factory=dict)
    dump_shown_loi: str = ""
    # Chẩn đoán LK của **frame GẦN NHẤT** (ticket #39): `ly_do`/`ly_do_khop`/`scale`/`angle_deg`/
    # `n_diem` của bước nội suy vừa rồi. Đây là **một frame**, KHÔNG phải trung bình — muốn phân bố thì
    # đọc cột trong `--dump-shown-csv`. Rỗng = không có LK (vos_every=1) hoặc worker bản cũ.
    chan_doan_lk: dict = field(default_factory=dict)
    mask_age_ms: float | None = None      # tuổi mask đang hiện (từ lúc kết quả model sẵn sàng)
    # `mask_age_cu_ms` = age + vos_ms — ĐỊNH NGHĨA CŨ, chỉ còn để so với số trước 14-11.
    mask_age_cu_ms: float | None = None
    # `mask_age_total_ms` = **tuổi dữ liệu thật**: chờ trong worker (queue) + tiền xử lý (pre) +
    # suy luận (vos) + từ lúc có kết quả tới lúc vẽ (age). Trước 14-11 nó chỉ là age + vos ⇒ thấp
    # hơn thực tế tới ~1 chu kỳ submit (0–100 ms) + 5,65 ms tiền xử lý (AGENTS §6).
    mask_age_total_ms: float | None = None
    mask_age_p95: float | None = None     # phân vị 95 % của mask_age_total_ms
    age_n: int = 0                        # số mẫu tuổi mask (0 ⇒ CHƯA ĐO)
    # Chu kỳ VOS tách theo pha (đo 14-11 để biết 32 ms "thừa" của chu kỳ 156 ms nằm ở đâu —
    # `docs/task/14-11-2026-do-lai-bbox-dung-ket-luan-khong-can-train-lai.md`). `None` = chưa đo.
    queue_ms: float | None = None   # từ lúc gửi frame cho tới lúc luồng VOS bắt đầu xử lý
    pre_ms: float | None = None     # tiền xử lý (resize + tensor) của lần VOS gần nhất
    post_ms: float | None = None    # đo drift (nếu có LK) + làm mượt mask sau khi có kết quả
    # Thời gian GHI mask ra PNG cho `--dump-mask-frames`, tách RIÊNG khỏi `post_ms` (ticket #26):
    # trước đây `_dump_mask` chạy bên trong cửa sổ `post_ms` ⇒ `post_ms`/`mask_age_total_ms` bị chính
    # dụng cụ đo làm bẩn (~1–3 ms @640×480, 5–15 ms @1080p, hơn nữa khi dump nhiều frame). `None` =
    # **không có file nào được ghi** ở lần VOS này (khác `0,0` = đã ghi, ghi cực nhanh).
    dump_ms: float | None = None
    # `cycle_ms`/`queue_ms` **vẫn** chứa thời gian dump của lần VOS TRƯỚC (`_dump_mask` chạy trong
    # callback `_store_vos`, tức bên trong khoảng `bat_dau_i − bat_dau_{i−1}` của worker) ⇒ đo bằng
    # `--dump-mask-frames` thì `cycle_ms`/`queue_ms` bị phình, chỉ `post_ms` là đã sạch (ticket #26,
    # P2 review 17-11 — đừng trích `cycle_ms` của phiên có dump làm "chu kỳ VOS").
    cycle_ms: float | None = None   # khoảng cách giữa 2 lần VOS bắt đầu liên tiếp (= 1/vos_fps)
    idle_ms: float | None = None    # luồng VOS chờ frame mới (không phải thời gian tính toán)
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


def _parse_frame_list(value) -> tuple:
    """`"0, 50,120"` / `(0,50)` / `[]` → tuple int dương, sắp tăng, bỏ trùng.

    Chấp nhận cả chuỗi vì CLI truyền chuỗi; từ chối giá trị âm ngay tại đây thay vì lặng lẽ không
    khớp frame nào (im lặng bỏ qua = "chấm 0 mẫu mà tưởng đã chấm").
    """
    if value is None or value == "" or value == ():
        return ()
    if isinstance(value, str):
        parts = [p for p in value.replace(";", ",").split(",") if p.strip()]
        nums = []
        for part in parts:
            try:
                nums.append(int(part))
            except ValueError as exc:
                raise ValueError(f"dump_mask_frames: {part!r} không phải số nguyên") from exc
    else:
        nums = [int(v) for v in value]
    am = [n for n in nums if n < 0]
    if am:
        raise ValueError(f"dump_mask_frames: frame_idx không âm; nhận {am}")
    return tuple(sorted(set(nums)))


def session_exit_code(stats: "LiveTrackStats") -> int:
    """Mã thoát của tiến trình worker cho một phiên đã kết thúc: `0` bình thường, `1` nếu lỗi.

    Vì sao không để `main()` tự quyết: `worker_source.health()` phân biệt "người dùng bấm Dừng" với
    "chết vì lỗi" bằng **mã thoát** (mã ≠ 0 ⇒ `error`). Một chỗ định nghĩa + test được ⇒ không có
    chuyện nhánh nào đó quên trả 1 (điều đã xảy ra tới 14-11: mọi phiên, kể cả crash, đều trả 0).
    """
    return 1 if stats.state == STATE_ERROR else 0


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


# Ba hàm đọc tiến trình nằm ở `src/proc_pid.py` (dùng chung với adapter API); re-export để chỗ đang
# import từ module này không phải đổi.
from src.proc_pid import is_live_worker_for, pid_con_song, read_cmdline, read_pid  # noqa: E402


def phien_live_dang_giu(out_dir) -> int | None:
    """`pid` của một phiên live KHÁC đang giữ `out_dir` (`None` = không ai giữ).

    Vì sao cần: `live_worker --bbox` ghi `<out-dir>/bbox.json`, mà thư mục đó có thể là của một phiên
    web đang `waiting_selection` ⇒ ghi vào là **cướp ô chọn** của phiên đó, không cảnh báo (ticket #37).
    Đường API tự dọn `bbox.json` khi bắt đầu phiên; đây là chốt cho ca operator chạy CLI tay.
    """
    pid = read_pid(Path(out_dir) / PID_NAME)
    if pid is None or pid == os.getpid():
        return None
    if not pid_con_song(pid):
        return None
    # CHỐNG PID TÁI CHẾ (P2 review độc lập 18-11): pidfile cũ trỏ một tiến trình KHÁC đang sống (không
    # phải worker) thì **không** được coi là "phiên live đang giữ" — nếu không CLI bị chặn vĩnh viễn mà
    # câu báo lại sai sự thật, lối thoát duy nhất là tự xoá pidfile. Cùng tiền lệ
    # `scripts/demo_preflight._is_our_live_worker` (đã có 3 test).
    if not is_live_worker_for(read_cmdline(pid), out_dir):
        return None
    return pid


def cau_hinh_yeu_cau(*, source="", image_size=None, vos_every=3, display_fps=30.0,
                     mask_smoothing=1.0, device="", dump_mask_frames=(),
                     lk_max_mad=DEFAULT_MAX_MAD, lk_scale=False) -> dict:
    """Cấu hình **được yêu cầu** (từ CLI/API) ở dạng ghi được vào `status.json`.

    Tách khỏi `LiveTrackStats` để giai đoạn `loading` (chưa có engine, 20–240 s) cũng ghi được cấu
    hình ĐỊNH chạy — trước đây file chỉ có `device`, ai đọc sớm cũng không biết phiên sẽ chạy
    `image_size`/`vos_every` nào.
    `image_size=None` = KHÔNG override (dùng mặc định của `model_cfg`, hiện là 1024).
    `image_size_hieu_luc` luôn có mặt và luôn `None` ở đây (chưa nạp model ⇒ **chưa kiểm được**:
    `image_size_kiem_duoc = False`): giữ cùng bộ khoá ở cả hai giai đoạn để người đọc `status.json`
    không phải phân biệt schema.
    """
    return {
        # Che `user:pass@` (ticket 29): chuỗi này đi vào `status.json` → artifact đã commit (+ HTTP).
        # Chỉ che khi IN RA; nguồn thật mà worker mở vẫn dùng chuỗi gốc.
        "source": an_userinfo(str(source)),
        "image_size_yeu_cau": None if image_size is None else int(image_size),
        "image_size_hieu_luc": None,
        # Cờ tường minh thay cho suy luận "`cau_hinh_lech` rỗng ⇒ khớp": rỗng có thể là CHƯA KIỂM
        # ĐƯỢC (predictor không khai báo). False thì cấm đọc là "đã khớp" (review độc lập 15-11, P2).
        "image_size_kiem_duoc": False,
        "vos_every": int(vos_every),
        "display_fps": float(display_fps),
        "mask_smoothing": float(mask_smoothing),
        "device": str(device),
        # Bật `--dump-mask-frames` hay không: là DỤNG CỤ ĐO (có thể làm phình `dump_ms`), nên artifact
        # phải tự khai — không có khoá này thì không ai biết số của phiên có bị dump làm bẩn không
        # (ticket #26, P3 review 17-11).
        "dump_mask_frames": list(dump_mask_frames or ()),
        # Cửa chống-trôi của LK: `LiveTrackConfig` thi hành trực tiếp (không có bản "hiệu lực" riêng)
        # nên không thể lệch âm thầm — nhưng PHẢI echo, nếu không thì không ai biết artifact được đo ở
        # 1,5 hay 6,0 (đúng lý do `cau_hinh` tồn tại, review 15-11).
        "lk_max_mad": float(lk_max_mad),
        # Echo cả chế độ nội suy: artifact phải tự khai ô bao được đo ở "chỉ dịch" hay "dịch+tỉ lệ",
        # nếu không thì hai phiên khác chế độ đọc như cùng cấu hình (đúng lý do `cau_hinh` tồn tại).
        "lk_scale": bool(lk_scale),
        "mask_age_dinh_nghia": DINH_NGHIA_TUOI_MASK,
    }


def cau_hinh_hieu_luc(yeu_cau: dict, engine) -> dict:
    """Ghép cấu hình yêu cầu với `image_size` mà ENGINE THẬT SỰ chạy (đọc từ predictor).

    `image_size_hieu_luc = None` = **chưa kiểm được** (engine giả trong test, hoặc predictor không
    khai báo) — KHÔNG phải "khớp".
    """
    ra = dict(yeu_cau)
    thuc = getattr(engine, "image_size_hieu_luc", None) if engine is not None else None
    ra["image_size_hieu_luc"] = thuc
    ra["image_size_kiem_duoc"] = thuc is not None
    return ra


def so_khop_cau_hinh(cau_hinh: dict) -> list:
    """Danh sách khoá LỆCH giữa yêu cầu và hiệu lực; `[]` = khớp hoặc chưa kiểm được.

    Chỉ `image_size` có bản "hiệu lực" tách khỏi yêu cầu (`vos_every`/`display_fps`/
    `mask_smoothing` do chính `LiveTrackConfig` thi hành nên không thể lệch âm thầm). Bỏ qua khi
    một bên `None`: yêu cầu `None` = dùng mặc định (không có gì để so), hiệu lực `None` = chưa đo.
    """
    yeu_cau = cau_hinh.get("image_size_yeu_cau")
    thuc = cau_hinh.get("image_size_hieu_luc")
    if yeu_cau is None or thuc is None:
        return []
    try:
        return [] if int(yeu_cau) == int(thuc) else ["image_size"]
    except (TypeError, ValueError):
        return ["image_size"]


def status_payload(stats: "LiveTrackStats") -> dict:
    """Payload `status.json` — MỘT nguồn duy nhất cho cả trạng thái "loading" lẫn phiên đang chạy.

    Trước đây `tools/live_worker.py` tự viết một dict 7 khoá, phiên chạy ghi 14 khoá ⇒ người đọc
    file trong 20–60 s nạp model thấy schema khác (P3, review 08-11).
    """
    return {
        "state": stats.state,
        "device": stats.device,
        # Cấu hình yêu cầu + hiệu lực: artifact đọc THẲNG file này để tự kiểm "chạy đúng cấu hình
        # đã yêu cầu" (xem `cau_hinh_yeu_cau`/`so_khop_cau_hinh`).
        "cau_hinh": dict(stats.cau_hinh),
        "cau_hinh_lech": list(stats.cau_hinh_lech),
        "frames": stats.frames,
        "vos_runs": stats.vos_runs,
        "measured_fps": stats.measured_fps,
        "vos_fps": stats.vos_fps,
        "vos_ms": stats.vos_ms,
        "pre_ms": stats.pre_ms,
        "queue_ms": stats.queue_ms,
        "post_ms": stats.post_ms,
        "dump_ms": stats.dump_ms,
        "cycle_ms": stats.cycle_ms,
        "idle_ms": stats.idle_ms,
        "lk_ms": stats.lk_ms,
        "drift_iou": stats.drift_iou,
        "drift_iou_p05": stats.drift_iou_p05,
        # Rỗng ⇒ worker bản cũ (chưa có cờ #14) — KHÔNG đọc thành "ok".
        "suc_khoe": stats.suc_khoe or None,
        # Lỗi ghi CSV ô-hiển-thị (`--dump-shown-csv`): `""` = không lỗi. `cau_hinh` vẫn khai ĐÃ YÊU CẦU
        # ghi, nên cần khoá này để không ai đọc "không có file" thành "không ai yêu cầu ghi".
        "dump_shown_loi": getattr(stats, "dump_shown_loi", "") or None,
        # Chẩn đoán LK của frame gần nhất (ticket #39) — `None` = chưa có bước LK nào để đọc.
        "chan_doan_lk": dict(stats.chan_doan_lk) or None,
        "suc_khoe_cau": tracking_health.cau_co(stats.suc_khoe),
        "drift_n": stats.drift_n,
        "mask_age_ms": stats.mask_age_ms,
        "mask_age_cu_ms": stats.mask_age_cu_ms,
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


def _tach_pha(bat_dau: float, submitted_at, last_start, last_done) -> dict:
    """Tách chu kỳ VOS thành `queue_ms` / `cycle_ms` / `idle_ms` — hàm THUẦN, test được.

    Vì sao: chu kỳ 156 ms (đo 14-11) lớn hơn `vos_ms` 124 ms đúng 32 ms mà **chưa ai đo** nằm ở đâu;
    không tách thì mọi đề xuất "đổi cadence cho nhanh hơn" đều là đoán. Ba khoản:
      - `queue_ms`: frame gửi lúc `submitted_at` nhưng luồng còn bận ⇒ frame chờ (mask cũ đi);
      - `cycle_ms`: khoảng cách giữa hai lần bắt đầu xử lý liên tiếp = `1/vos_fps` thực;
      - `idle_ms` : luồng ngồi chờ frame mới (không phải thời gian tính toán).
    `None` khi chưa có mốc trước đó (lần đầu) — KHÔNG phải 0.
    """
    def _ms(a, b):
        return None if (a is None or b is None) else round((a - b) * 1000.0, 2)

    return {
        "queue_ms": _ms(bat_dau, submitted_at),
        "cycle_ms": _ms(bat_dau, last_start),
        "idle_ms": _ms(bat_dau, last_done),
    }


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
        self._timing: dict = {}
        self._last_start = None    # lúc bắt đầu xử lý lần trước (⇒ `cycle_ms`)
        self._last_done = None     # lúc xong lần trước (⇒ `idle_ms`)

    def submit(self, seq: int, frame, gray) -> None:
        with self._lock:
            # `submitted_at` để đo `queue_ms`: thời gian frame nằm chờ vì model còn bận frame trước.
            # Đây chính là khoản "mask cũ đi" mà `mask_age` cũ bỏ sót.
            self._pending = (seq, frame, gray, time.perf_counter())   # luôn là frame MỚI NHẤT
        self._wake.set()

    @property
    def timing(self) -> dict:
        """Số đo pha của lần xử lý GẦN NHẤT (`None` = chưa đo). Đọc từ luồng đã gọi `_on_result`."""
        return dict(self._timing)

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
            seq, frame, gray, submitted_at = item
            bat_dau = time.perf_counter()
            self._timing = _tach_pha(bat_dau, submitted_at, self._last_start, self._last_done)
            self._last_start = bat_dau
            try:
                # Bọc CẢ quá trình xử lý kết quả: lỗi trong `_store_vos`/`_smooth` (dữ liệu model
                # bất thường) cũng phải thành `state=error`, không được để thread chết im lặng.
                self._on_result(seq, self._engine.process(frame), gray)
            except Exception as exc:          # noqa: BLE001 — lỗi model phải thành trạng thái error
                if self._on_error is not None:
                    self._on_error(exc)
                return
            finally:
                self._last_done = time.perf_counter()


class LiveTrackingSession:
    """Một phiên bám trực tiếp: đọc frame → (chờ bbox) → VOS (luồng riêng) + LK → ghi ảnh/trạng thái."""

    def __init__(self, engine, config: LiveTrackConfig, *, lk_tracker=None) -> None:
        self._engine = engine
        self._cfg = config
        # Cả hai tracker dùng CÙNG cửa MAD của phiên: `_lk` (bám từ frame trước) và `_interp` (nội suy
        # từ frame VOS gần nhất) cùng sinh ra ô hiển thị, lệch ngưỡng thì số đo không nói được gì.
        self._lk = lk_tracker or LkBoxTracker(max_mad=config.lk_max_mad, scale=config.lk_scale)
        self._interp = LkBoxTracker(max_mad=config.lk_max_mad, scale=config.lk_scale)
        self._stats = LiveTrackStats(device=config.device)
        # Echo cấu hình NGAY khi dựng phiên (engine đã nạp ⇒ `image_size` hiệu lực đã biết): từ đây
        # `status.json` trả lời được "phiên này chạy cấu hình nào" mà không cần đọc `worker.log`.
        self._stats.cau_hinh = cau_hinh_hieu_luc(
            cau_hinh_yeu_cau(source=config.source, lk_max_mad=config.lk_max_mad,
                             lk_scale=config.lk_scale,
                             image_size=getattr(engine, "image_size", None),
                             vos_every=config.vos_every, display_fps=config.display_fps,
                             mask_smoothing=config.mask_smoothing, device=config.device,
                             dump_mask_frames=config.dump_mask_frames),
            engine,
        )
        self._stats.cau_hinh_lech = so_khop_cau_hinh(self._stats.cau_hinh)
        if self._stats.cau_hinh_lech:
            print(f"[canh-bao] cấu hình YÊU CẦU khác HIỆU LỰC ở {self._stats.cau_hinh_lech}: "
                  f"image_size yêu cầu {self._stats.cau_hinh['image_size_yeu_cau']}, model chạy "
                  f"{self._stats.cau_hinh['image_size_hieu_luc']} — số đo của phiên này KHÔNG gắn "
                  "được với cấu hình đã yêu cầu (override không có tác dụng?)", flush=True)
        self._trail: deque = deque(maxlen=config.trajectory_len)
        self._display_stamps: deque = deque()
        self._vos_stamps: deque = deque()
        self._smoother = MaskSmoother(config.mask_smoothing) if config.mask_smoothing < 1.0 else None
        self._drift_window: deque = deque(maxlen=_STAT_WINDOW)   # đủ mẫu để lấy p05
        # Cùng cửa sổ, cùng thứ tự với `_drift_window`: cờ #14 cần biết mẫu drift đó có kèm mask
        # RỖNG hay không (rỗng nhiều ⇒ `model_lost`, rỗng ít ⇒ `drift_trend`). Hai deque phải append
        # cạnh nhau ở MỌI chỗ, nếu lệch nhịp thì `empty_frac` không còn ứng với `p05` nào.
        self._drift_empty_window: deque = deque(maxlen=_STAT_WINDOW)
        # Ghi ô hiển thị từng frame (dụng cụ đo): file mở LƯỜI ở frame đầu, đóng trong `run()`.
        # KHÔNG ghi trong `_stats_lock` (I/O dưới lock sẽ chặn luồng VOS — cùng lý do với CSV drift):
        # `_update_stats_locked` chỉ để lại `_last_shown`, `_update_stats` mới ghi ra đĩa.
        self._shown_fh = None
        self._last_shown = None
        self._shown_loi = ""       # lý do GHI HỎNG (khác "không yêu cầu ghi") — vào `status.json`
        # Cửa sổ ĐẾM SỰ KIỆN cho mask rỗng. Để RIÊNG khỏi `_iou_window` (10 mẫu, dùng cho độ ổn
        # định): đây là đại lượng đếm, không phải phân vị, nên cửa sổ ngắn vẫn dùng được — tần suất
        # nền của "VOS trả mask rỗng" trên clip khoẻ đo được là 0/798 lần chạy (binh1).
        self._vos_lost_window: deque = deque(maxlen=_STAT_WINDOW)
        self._age_window: deque = deque(maxlen=_STAT_WINDOW)
        # Ô bao ĐÃ PHÁT theo từng frame: nhờ vậy đo drift đúng frame mà VOS đã thấy, không lệch
        # một khoảng bằng độ trễ suy luận (review 08-11 chỉ ra phép so cũ lệch ~3 frame).
        self._shown_by_frame: deque = deque(maxlen=_SHOWN_HISTORY)
        # `(frame_idx, lk_ok)` song song `_shown_by_frame`: `lk_ok = None` khi không có LK
        # (`vos_every=1`), `False` khi `update()` trả `not-ok` (pipeline phát ô BASE), `True` khi LK ok.
        # Ghi vào CSV drift (ticket 14): thiếu nó thì `drift_iou = 0` không phân biệt được "LK trượt"
        # với "ô VOS nhảy" — 19-11 phải dựng cả script phát lại để suy ra, và chỉ khớp 3/6 cặp.
        self._lk_by_frame: deque = deque(maxlen=_SHOWN_HISTORY)
        self._lk_ok_frame = None
        # Chẩn đoán của bước LK vừa rồi (ticket #39). `None` = chưa có / không có LK.
        self._chan_doan_frame = None
        self._seq_frame: dict = {}       # seq → chỉ số frame đã phát lúc gửi cho VOS
        self._dumped: set = set()        # các frame VIDEO đã ghi mask (để báo frame yêu cầu mà thiếu)
        # Số file mask bị GHI ĐÈ vì tên file trùng (chọn lại ô giữa phiên / out_dir của phiên
        # trước). Đếm để `manifest.json` tự khai — ghi đè là chuyện CÓ THỂ chấp nhận, ghi đè
        # IM LẶNG thì không (ticket #26).
        self._so_file_ghi_de = 0
        # (frame_idx, bbox VOS, seq, vos_ms, empty) chờ frame đó được phát để so
        self._pending_drift = None
        # Từng mẫu drift ra CSV (ticket 15): status.json chỉ có mean/p05 ⇒ không đo được độ trễ
        # phát hiện và tỉ lệ báo oan. Lock riêng của logger ⇒ KHÔNG ghi trong `_stats_lock`.
        self._drift_log = DriftSampleLog(Path(config.out_dir) / DRIFT_CSV_NAME)
        self._iou_window: deque = deque(maxlen=10)
        self._shown_iou_window: deque = deque(maxlen=10)
        self._prev_shown_mask = None
        self._prev_raw_mask = None
        self._prev_vos_frame = None      # frame video của mẫu stability gần nhất (ticket #35)
        self._prev_vos_bbox = None
        self._lock = threading.Lock()          # bảo vệ `_vos_state`
        # Bảo vệ `_stats` + mọi cửa sổ thống kê (luồng VOS ghi, luồng chính đọc). Lock LÁ, KHÔNG
        # tái nhập: đang giữ nó thì cấm gọi hàm có `with self._stats_lock` (dùng biến thể
        # `*_locked` cho phần dùng chung, như `_apply_drift_locked`).
        self._stats_lock = threading.Lock()
        # (seq, result, gray, produced_at, vos_ms, pre_ms, queue_ms, post_ms) — lần VOS gần nhất;
        # 3 khoản cuối đi CÙNG snapshot để tuổi mask không trộn pha của lần chạy khác.
        self._vos_state = None
        self._mask = None               # mask lần VOS gần nhất (đường chạy đơn luồng)
        self._mask_bbox_xywh = None     # ô bao tại lần VOS đó (để tính độ dịch cho LK)
        self._seq = 0
        self._frame_index = 0
        # Số frame đã ĐỌC từ nguồn trước khi bắt đầu bám (chọn ô GIỮA phiên ⇒ > 0). Tên file mask đi
        # theo `_frame_index` của PHIÊN, nên khi offset > 0 thì `mask_000042.png` KHÔNG phải frame 42
        # của clip ⇒ ghép GT theo số frame sẽ SAI (ticket #36). Khai ra để chỗ CHẤM biết.
        self._frame_goc = 0
        self._da_canh_bao_offset = False   # chỉ cảnh báo "TỪ CHỐI dump" một lần/phiên
        self._da_canh_bao_quay_vong = False
        self._tu_choi_offset: set[int] = set()   # frame bị TỪ CHỐI ghi vì offset ≠ 0
        self._tu_choi_quay_vong: set[int] = set()   # frame bị TỪ CHỐI vì nguồn đã quay vòng
        self._so_lan_quay_vong = 0               # > 0 ⇒ tên file mask không còn là frame của clip
        self._da_chay = False
        self._source = None
        self._worker = None
        self._error = None              # lỗi từ luồng VOS (không được nuốt im lặng)
        # mốc an toàn: nếu vì lý do nào đó luồng chính đọc trước khi start() xong
        self._interp_base_result = _FrameResult(0, (0, 0, 0, 0), None, 0.0)
        self._use_lk = config.vos_every > 1

    # ------------------------------------------------------------------ API công khai

    def run(self, stop_event=None) -> LiveTrackStats:
        """Chạy tới khi hết nguồn (file không lặp), đủ frame, hoặc `stop_event` được set."""
        if self._da_chay:
            # Gọi `run()` lần hai trên CÙNG session: `_frame_index`/`_frame_goc`/`_dumped` KHÔNG reset
            # ⇒ nguồn mở lại từ frame 0 của clip nhưng tên file tiếp tục từ `_frame_index` của lần
            # trước (mask lệch frame) và `_da_canh_bao_offset` đã True nên guard offset mất tác dụng
            # (P3 vòng review 2). Chặn thay vì âm thầm sinh số sai.
            raise RuntimeError("LiveTrackingSession.run() chỉ được gọi MỘT lần — dựng session mới "
                              "cho mỗi phiên (bộ đếm frame/dump không reset)")
        self._da_chay = True
        out_dir = Path(self._cfg.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        self._publish_status(out_dir)

        interval = 1.0 / max(1.0, float(self._cfg.display_fps))
        started = False
        try:
            # Mở nguồn TRONG `try`: bản cũ để ngoài nên `.open()` ném ⇒ `status.json` kẹt ở
            # `loading` trong khi tiến trình đã chết, người đọc tưởng model còn đang nạp.
            self._source = open_video_source(self._cfg.source).open()
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
                        # Frame này bị đọc trong GIAI ĐOẠN CHỜ CHỌN Ô ⇒ nó KHÔNG được bám. Đếm để
                        # `manifest.json` khai `frame_goc_cua_phien` (ticket #36).
                        self._frame_goc += 1
                        self._publish_frame(out_dir, frame)
                        self._sleep(interval, began)
                        continue
                    # bbox.json là (x, y, w, h); SAM 2 nhận box (x1, y1, x2, y2) — BUG thật 10-11:
                    # trước đây truyền thẳng nên hộp chọn trên live bị seed sai (w,h thành x2,y2)
                    self._chon_bbox = tuple(bbox)      # vào manifest.json của mask dump
                    result = self._engine.start(frame, xywh_to_xyxy(bbox))
                    # Đường CÓ luồng: frame `start()` cũng sẽ được worker `process()` lại và
                    # `_store_vos` ghi mask của nó ⇒ dump Ở ĐÂY nữa là ghi đè chính file đó trong cùng
                    # phiên (P1 review 17-11: `so_file_ghi_de` sẽ báo oan, hoặc tệ hơn là bị guard cũ
                    # che mất). Đường đơn luồng không có worker ⇒ dump tại đây.
                    self._after_vos(frame, result, dump=not self._use_lk)
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
        except Exception as exc:                 # noqa: BLE001 — lỗi phải THÀNH TRẠNG THÁI, không im
            # Bản cũ: ngoại lệ ở luồng chính (mở nguồn, `engine.start` với ô chọn xấu, `read()` ném,
            # `_annotate`) thoát khỏi vòng lặp rồi `finally` ghi `stopped` ⇒ đầu kia API báo "worker đã
            # kết thúc phiên" và người xem không phân biệt được với việc bấm Dừng (review vòng 1/3).
            self._on_loop_error(exc)
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
            # Thứ tự `stop_worker → flush → close`: nếu `join(5 s)` timeout mà worker còn sống thì nó
            # có thể ghi thêm dòng giữa flush và close (được), hoặc sau close (bị `_closed` bỏ — mất
            # mẫu cuối, nhưng KHÔNG được mở lại file vì mode `w` sẽ xoá sạch dãy đã ghi).
            self._canh_bao_mask_thieu()
            self._flush_pending_csv()
            self._drift_log.close()
            if self._shown_fh is not None:      # dụng cụ đo #38: đóng sau cùng để không mất frame cuối
                self._shown_fh.close()
                self._shown_fh = None
            # Ghi lại lần cuối: nếu luồng VOS báo lỗi trong lúc join thì state đã thành `error`.
            self._publish_status(out_dir)
        # Trả BẢN SAO: `join(5 s)` có thể timeout và luồng VOS còn ghi `_stats` sau đó ⇒ trả object
        # sống thì người đọc thấy số nửa cập nhật (review 09-11, P3).
        with self._stats_lock:
            return replace(self._stats)

    # ------------------------------------------------------------------ luồng VOS + nội suy LK

    def _start_worker(self, frame, gray) -> None:
        with self._lock:                      # mốc nội suy ban đầu = frame start(), đặt TRƯỚC submit
            # 8 phần tử: 5 phần tử cũ + (pre_ms, queue_ms, post_ms) — `None` = chưa có lần VOS nào.
            self._vos_state = (0, self._interp_base_result, gray, time.perf_counter(),
                               float(getattr(self._interp_base_result, "elapsed_ms", 0.0)),
                               None, None, None)
        self._worker = _VosWorker(self._engine, self._store_vos, self._on_worker_error)
        self._worker.start()
        self._seq += 1
        # Đăng ký `seq → frame` cho CẢ lần `start()`: nếu thiếu, mẫu VOS đầu tiên không có
        # `frame_idx` ⇒ không chấm được drift và dòng CSV của nó không truy về frame nào
        # (ticket 15: mỗi dòng phải có `frame_idx` để đối chiếu với video).
        self._seq_frame[self._seq] = self._frame_index
        self._worker.submit(self._seq, frame, gray)

    def _flush_pending_csv(self) -> None:
        """Ghi dòng CSV cho mẫu còn treo trong `_pending_drift` khi phiên dừng.

        Ca thật: kết quả VOS cuối cùng về SAU frame cuối ⇒ không bao giờ có lần phát nào để chấm.
        Không flush thì CSV mất đúng mẫu cuối (đo 13-11: cảnh tĩnh 358 lần VOS nhưng 357 dòng).
        Không chấm drift vì không có ô bao đã phát — ghi `drift_iou` trống, KHÔNG bịa 0.
        """
        with self._stats_lock:
            pending, self._pending_drift = self._pending_drift, None
        if pending is None:
            return
        # `lk_ok` để TRỐNG (chưa đo): mẫu này bị flush vì frame chưa từng được phát ⇒ chưa có lần LK nào
        # cho nó (review thay thế PR #50, P3: `pending[5]` gần như luôn `None`, đừng để đọc thành "LK hỏng").
        self._log_drift_sample(frame_idx=pending[0], seq=pending[2], vos_ms=pending[3],
                               empty=pending[4], value=None, bbox=pending[1], lk_ok=None)

    def _stop_worker(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker.join(timeout=5.0)
            self._worker = None

    def _on_worker_error(self, exc) -> None:
        """Lỗi trong luồng VOS: ghi trạng thái error để API/UI biết, KHÔNG phát mask đứng yên."""
        self._set_error(exc, "model lỗi trong luồng VOS")

    def _on_loop_error(self, exc) -> None:
        """Ngoại lệ ở luồng chính (mở nguồn, `engine.start`, `read()`, vẽ): phải thành `error`.

        Thông điệp cố ý KHÁC nhánh luồng VOS để người đọc `status.json` biết lỗi đến từ đâu; cả hai
        đều đi qua `_set_error` nên chỉ có MỘT nơi ghi `state = error`.
        """
        self._set_error(exc, "lỗi trong vòng lặp chính")

    def _set_error(self, exc, where: str) -> None:
        """Lỗi ĐẦU TIÊN thắng: luồng chính và luồng VOS có thể cùng chết, và nếu lỗi sau ghi đè thì
        `status.json` nêu sai nguồn gốc (ca thật: VOS chết vì OOM sau khi nguồn đã mất)."""
        with self._stats_lock:
            if self._error is None:
                self._error = exc
                self._stats.message = f"{where}: {exc}"
            self._stats.state = STATE_ERROR

    def _store_vos(self, seq, result, gray) -> None:
        """Callback của luồng VOS: chỉ ghi kết quả mới nhất (không chặn, không vẽ)."""
        # `post_ms` bắt đầu TRƯỚC `_record_vos` (bên trong có `_measure_stability` ⇒ `mask_iou`
        # mask thô ~0,2–1 ms); nếu đo sau nó thì `post_ms` thiếu đúng khoản đó và chuỗi pha không
        # khép được (review vòng 3, P3).
        bat_dau_post = time.perf_counter()
        pha = self._worker.timing if self._worker is not None else {}
        pre = getattr(result, "pre_ms", None)      # engine không có `pre_ms` ⇒ None (CHƯA ĐO), không 0
        pre_ms = None if pre is None else round(float(pre), 2)
        # PHẢI lấy chỉ số frame VIDEO của phiên TRƯỚC khi pop — `_dump_mask` cần nó để đặt tên file.
        # `result.frame_idx` là bộ đếm NỘI BỘ của engine (số lần gọi `process()`), KHÔNG phải chỉ số
        # frame video: với `vos_every=3`, lần VOS thứ 14 là frame video ~42 ⇒ đặt tên theo engine làm
        # `mask_000013.png` chứa mask của frame 42, ghép với `gt_000013.png` ⇒ mIoU SAI mà không cảnh
        # báo (P0, review độc lập 14-11). Cùng lý do đã ghi cho CSV drift ở `_measure_drift`.
        frame_idx = self._seq_frame.pop(seq, None)
        dump_ms, da_ghi = self._record_vos(result, frame_video=frame_idx)
        # Nội suy LK lệch bao nhiêu ở ĐÚNG frame đó (`seq` để dòng CSV truy được về lần VOS nào)
        self._measure_drift(frame_idx, result, seq)
        self._smooth(result)          # làm mượt + đo độ ổn định NGAY khi mask mới về
        # TRỪ thời gian ghi PNG: `--dump-mask-frames` là DỤNG CỤ ĐO, không được làm bẩn `post_ms`
        # (rồi `mask_age_total_ms`/p95 của đúng mẫu đó — ticket #26). `cycle_ms`/`queue_ms` lấy từ
        # worker nên VẪN chứa dump của lần trước; đừng nói chúng "đã sạch".
        post_ms = round((time.perf_counter() - bat_dau_post) * 1000.0 - dump_ms, 2)
        queue_ms = pha.get("queue_ms")
        with self._stats_lock:
            self._stats.cycle_ms = pha.get("cycle_ms")
            self._stats.queue_ms = queue_ms
            self._stats.idle_ms = pha.get("idle_ms")
            self._stats.pre_ms = pre_ms
            self._stats.post_ms = post_ms
            # `None` = **không có file nào được ghi** (không yêu cầu dump / `mask is None` /
            # `imwrite` fail) — khác `0,0` = đã ghi, ghi cực nhanh. Gán CÙNG lock với `post_ms` để
            # `status.json` không ghép hai lần VOS khác nhau (P3 review 17-11).
            self._stats.dump_ms = dump_ms if da_ghi else None
        with self._lock:
            # Gom pha của CHÍNH lần VOS này vào snapshot: `_result_threaded` chỉ đọc tuple này nên
            # không trộn pha của lần chạy khác vào mẫu tuổi mask (review vòng 3, P3).
            self._vos_state = (seq, result, gray, time.perf_counter(),
                               float(getattr(result, "elapsed_ms", 0.0)),
                               pre_ms, queue_ms, post_ms)

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
            # Hiện KHÔNG reachable (review PR #66, Q1), nhưng nếu reachable thì `chan_doan_lk` sẽ mang
            # chẩn đoán của frame TRƯỚC với `frame_idx` của frame này ⇒ bịt bằng 1 dòng.
            self._chan_doan_frame = None
            return self._interp_base_result

        seq, base_result, base_gray, produced_at, vos_ms, pre_ms, queue_ms, post_ms = state
        # Truyền ĐỦ các khoản của ĐÚNG lần VOS này (lấy từ snapshot, không đọc `_stats` — tránh lệch
        # thế hệ khi một VOS mới vừa xong).
        self._note_mask_age(time.perf_counter() - produced_at, vos_ms,
                            pre_ms=pre_ms or 0.0, queue_ms=queue_ms or 0.0,
                            post_ms=post_ms or 0.0)
        base_bbox = xyxy_to_xywh(base_result.bbox)
        self._interp.reset(base_gray, base_bbox)      # mốc LUÔN là frame VOS → sai số không tích luỹ
        began = time.perf_counter()
        bbox, ok = self._interp.update(gray)
        self._lk_ok_frame = bool(ok)
        # Snapshot NGAY sau `update()` (ticket #39): đọc lại sau đó sẽ dính giá trị của bước khác.
        self._chan_doan_frame = {
            "ly_do": getattr(self._interp, "last_ly_do", None),
            "ly_do_khop": getattr(self._interp, "last_ly_do_khop", None),
            "scale": round(float(getattr(self._interp, "last_scale", 1.0)), 4),
            "angle_deg": round(float(getattr(self._interp, "last_angle_deg", 0.0)), 2),
            "n_diem": getattr(self._interp, "last_n_diem", None),
            # Similarity có THẬT SỰ được dùng không — `scale`/`angle_deg` chỉ có nghĩa khi True.
            "khop": bool(getattr(self._interp, "last_khop_similarity", False)),
            "lk_ok": bool(ok),
        }
        lk_ms = round((time.perf_counter() - began) * 1000.0, 2)
        with self._stats_lock:            # `_stats` chỉ được ghi dưới lock (xem `__init__`)
            self._stats.lk_ms = lk_ms
        if not ok:
            # LK mất dấu: vẫn phát mask/ô bao của lần VOS gần nhất (không bịa vị trí mới)
            return base_result

        dx = bbox[0] - base_bbox[0]
        dy = bbox[1] - base_bbox[1]
        mask = getattr(base_result, "mask", None)
        # Mask phải biến đổi CÙNG PHÉP với ô bao. Chế độ `lk_scale` dùng ma trận similarity của LK;
        # chế độ cũ vẫn là dịch thuần (giữ nguyên hành vi và số đo đã công bố).
        matrix = getattr(self._interp, "last_matrix", None)
        if mask is None:
            mask_moi = None
        elif self._cfg.lk_scale:
            # Ở chế độ `scale` TUYỆT ĐỐI không dùng `shift_mask(mask, dx, dy)`: `dx,dy` chỉ là delta
            # góc trên-trái của ô bao ĐÃ đổi kích thước, không phải phép biến đổi mask ⇒ mask lệch pha.
            # `last_matrix` luôn có sau một bước `ok=True`; phòng hờ `None` thì giữ mask nguyên.
            mask_moi = warp_mask(mask, matrix) if matrix is not None else mask
        else:
            mask_moi = shift_mask(mask, dx, dy)
        return _FrameResult(
            frame_idx=self._frame_index,
            bbox=xywh_to_xyxy(bbox),
            mask=mask_moi,
            elapsed_ms=lk_ms,
        )

    # ------------------------------------------------------------------ đường đơn luồng

    def _result_inline(self, frame):
        """vos_every=1: chạy VOS ngay trong vòng lặp (không LK, không luồng phụ)."""
        # Không có nội suy ⇒ `lk_ok = None`; khi ghi CSV, `_update_stats_locked` bọc `bool(...)` nên cột
        # ra **`0`** (KHÔNG trống) — đọc đúng bằng `lk_khong_ap_dung` trong artifact; cấm đọc "0" thành
        # "LK từ chối 100 %" (P3 review PR #66 vòng 2).
        self._lk_ok_frame = None
        self._chan_doan_frame = None      # ... và chẩn đoán LK cũng không áp dụng được
        self._frame_index += 1
        result = self._engine.process(frame)
        self._after_vos(frame, result)
        return result

    def _after_vos(self, frame, result, dump: bool = True) -> None:
        """Ghi nhận một lần VOS + đặt mốc LK (đường đơn luồng và frame start()).

        `dump=False` khi đường CÓ luồng VOS: chính frame này sẽ được worker xử lý lại và dump ở
        `_store_vos` ⇒ dump ở đây là ghi đè file của cùng một frame.

        Tuổi mask: `age = 0` ở đường này (frame vừa VOS CHÍNH LÀ frame đang phát) và `post_ms` đo
        cùng CÁCH ĐO với `_store_vos`, TRỪ `_measure_drift` — đường đơn luồng không có nội suy LK nên
        không có cặp VOS ↔ nội suy để so ⇒ `post_ms` ở đây hệ thống NHỎ HƠN đường LK đúng phần drift +
        I/O CSV; đừng so `post_ms` giữa hai đường. KHÔNG đo drift ở đây: bịa một mẫu drift là làm sai
        số (ticket #24).
        """
        bat_dau_post = time.perf_counter()
        # `frame_video` = chỉ số frame VIDEO của phiên (không phải bộ đếm của engine) — xem P0 review
        # 14-11: đường `vos_every=1` chạy inline ở đây, thiếu tham số này thì mask KHÔNG được dump.
        dump_ms, da_ghi = self._record_vos(
            result, frame_video=self._frame_index, dump=dump)
        self._smooth(result)
        # Trừ thời gian ghi PNG (ticket #26): `post_ms` chỉ còn phần XỬ LÝ KẾT QUẢ.
        post_ms = round((time.perf_counter() - bat_dau_post) * 1000.0 - dump_ms, 2)
        self._interp_base_result = result
        self._mask = getattr(result, "mask", None)
        self._mask_bbox_xywh = xyxy_to_xywh(result.bbox)
        self._lk.reset(self._gray(frame), self._mask_bbox_xywh)
        pre = getattr(result, "pre_ms", None)      # engine không có `pre_ms` ⇒ None (CHƯA ĐO), không 0
        with self._stats_lock:
            self._stats.post_ms = post_ms
            self._stats.dump_ms = dump_ms if da_ghi else None
            # Ghi `pre_ms` cả ở đường đơn luồng: thiếu nó thì `mask_age_total_ms` (đã gồm pre) không
            # tách được khoản nào — artifact `bangcau --every 1` có `pre_ms.n = 0` và tuổi mask cao
            # hơn `vos_ms` ~10 ms mà không cột nào giải thích (P2 review độc lập 17-11).
            self._stats.pre_ms = None if pre is None else round(float(pre), 2)
        # Tuổi của mask đang hiển thị = **0** ở đường đơn luồng: frame vừa được VOS xử lý CHÍNH LÀ
        # frame đang phát (không có frame nào chen giữa như đường có LK). Các khoản còn lại lấy từ
        # chính kết quả này (pre/vos), `queue_ms = 0` vì không có hàng đợi worker.
        self._note_mask_age(0.0, float(getattr(result, "elapsed_ms", 0.0) or 0.0),
                           pre_ms=float(getattr(result, "pre_ms", 0.0) or 0.0),
                           queue_ms=0.0, post_ms=post_ms)

    def _canh_bao_mask_thieu(self) -> None:
        """Frame được yêu cầu dump mà KHÔNG có lần VOS nào ⇒ nói ra, đừng để người dùng tưởng đã đo.

        Với `vos_every > 1`, chỉ frame chia hết cho N mới có mask thật; đòi frame 40 khi `vos_every=3`
        là chuyện có thật và nếu im lặng thì lần chấm mIoU chỉ còn vài frame mà không ai biết vì sao.
        """
        thieu = [f for f in self._cfg.dump_mask_frames if f not in self._dumped]
        if not thieu:
            return
        # MỖI lý do một câu, đọc từ set RIÊNG (P2 vòng review 4): gộp chung `_tu_choi_offset` thì ca
        # quay vòng in "(phiên bắt đầu sau 0 frame) — chạy lại với ô chọn có sẵn từ frame đầu", vừa sai
        # sự thật vừa khuyên đúng thứ không chữa được nguyên nhân (nguồn lặp).
        bi_tu_choi = sorted(self._tu_choi_offset)
        if bi_tu_choi:
            print(f"[canh-bao] TỪ CHỐI dump {len(bi_tu_choi)} frame {bi_tu_choi} (phiên bắt đầu sau "
                  f"{self._frame_goc} frame) — chạy lại với ô chọn có sẵn từ frame đầu", flush=True)
            thieu = [f for f in thieu if f not in self._tu_choi_offset]
        bi_tu_choi_qv = sorted(self._tu_choi_quay_vong)
        if bi_tu_choi_qv:
            print(f"[canh-bao] TỪ CHỐI dump {len(bi_tu_choi_qv)} frame {bi_tu_choi_qv} — nguồn đã quay "
                  f"vòng {self._so_lan_quay_vong} lần nên chỉ số frame của phiên không còn là frame của "
                  "clip; dùng `--stop-after-frames` <= độ dài clip (hoặc tắt lặp)", flush=True)
            thieu = [f for f in thieu if f not in self._tu_choi_quay_vong]
        if not thieu:
            return
        da_chay = int(getattr(self._stats, "frames", 0) or 0)
        if self._cfg.vos_every == 1:
            # `vos_every` đã đúng: khuyên "dùng --vos-every 1" là câu SAI (P3 vòng review 3). Nêu
            # đúng nguyên nhân còn lại: phiên kết thúc trước frame được yêu cầu.
            print(f"[canh-bao] không có mask cho frame {thieu} — phiên chỉ chạy tới frame "
                  f"{da_chay} (nguồn hết/`--stop-after-frames` nhỏ hơn frame cuối). Với vos_every=1 "
                  "thì frame nào chạy qua cũng có mask", flush=True)
            return
        print(f"[canh-bao] không có mask cho frame {thieu} — với vos_every="
              f"{self._cfg.vos_every} chỉ frame chia hết cho {self._cfg.vos_every} mới có lần VOS "
              "(dùng --vos-every 1 khi chấm mIoU)", flush=True)

    def _dump_mask(self, result, frame_video=None) -> bool:
        """Ghi mask của frame `result.frame_idx` ra PNG nếu frame đó nằm trong danh sách yêu cầu.

        Vì sao chỉ những frame ĐƯỢC CHỌN: chấm mIoU cần GT gán tay, mà gán tay vài chục frame là
        ngưỡng chịu được của con người. Ghi mask mọi frame sẽ ngốn hàng trăm MB và không ai dùng.

        Mask RỖNG vẫn phải ghi (file toàn 0): "model trả rỗng" là kết quả ĐO ĐƯỢC, và khi GT có vật
        thì nó phải chấm 0,0 — không có file sẽ bị đọc thành "chưa đo" (AGENTS §6).

        Lỗi ghi file KHÔNG được làm chết phiên bám (đây là dụng cụ đo, không phải đường demo) nhưng
        phải in cảnh báo, không im lặng (bài học "nuốt lỗi trong adapter" 08-11).

        Trả `True` ⇔ **đã ghi ra file**. `status.json["dump_ms"]` chỉ được khác `None` khi hàm này trả
        `True`: frame nằm trong danh sách yêu cầu mà `mask is None`/`imwrite` thất bại/hỏng thì KHÔNG
        có file nào, nên khai `dump_ms = 0,02` sẽ đọc thành "đã dump, ghi cực nhanh" (P1 review 17-11).
        """
        frames = self._cfg.dump_mask_frames
        # CHỈ số frame VIDEO của phiên mới khớp được với GT (`score_miou.py label` cắt theo số frame
        # của clip). `result.frame_idx` (bộ đếm engine) chỉ dùng để suy ra frame video cho CSV drift.
        frame_idx = frame_video
        if not frames or frame_idx is None or int(frame_idx) not in frames:
            return False
        out_dir = self._cfg.dump_mask_dir or str(Path(self._cfg.out_dir) / "masks")
        mask = getattr(result, "mask", None)
        try:
            target = Path(out_dir)
            target.mkdir(parents=True, exist_ok=True)
            if mask is None:
                # KHÔNG ghi file 1×1: nó trông như "đã đo" nhưng khi chấm sẽ lệch kích thước GT và
                # biến một ca "không có mask" thành lỗi khó hiểu ở khâu chấm điểm. Bỏ qua + cảnh báo.
                print(f"[canh-bao] frame {frame_idx}: model không trả mask ⇒ không ghi file "
                      "(chấm điểm sẽ đếm là 'thiếu mask', KHÔNG phải 0,0)", flush=True)
                return False
            arr = (np.asarray(mask) > 0).astype(np.uint8)
            # `imwrite` KHÔNG ném khi ghi hỏng (đĩa đầy/quyền) — nó trả False ⇒ file không có, và khâu
            # chấm sẽ báo "thiếu mask của model" = "chưa chạy", đúng cái bẫy docstring này nói phải
            # tránh (P3 review hẹp 14-11).
            dich = target / f"mask_{int(frame_idx):06d}.png"
            # GHI ĐÈ KHÔNG ĐƯỢC IM LẶNG: tên file đi theo chỉ số frame VIDEO của PHIÊN, nên nếu ai
            # thêm "chọn lại ô giữa phiên" mà reset `_frame_index` thì mask của hai lần chọn sẽ
            # trùng tên — không có cảnh báo thì mask của lần chọn cũ bị thay mà `GT` vẫn ghép theo
            # số frame ⇒ mIoU SAI mà không ai biết (ticket #26).
            # Điều kiện: file ĐÃ TỒN TẠI trên đĩa. KHÔNG loại trừ "frame này phiên này đã ghi" —
            # chính ca "chọn lại ô giữa phiên" (ticket #26) làm frame đó được ghi LẦN HAI trong cùng
            # phiên; guard cũ (`... and int(frame_idx) not in self._dumped`) bỏ cảnh báo đúng ca cần
            # canh (P1 review 17-11). Tên file đi theo chỉ số frame VIDEO của phiên ⇒ ghi đè nghĩa là
            # mask của lần chọn trước bị thay, mà GT vẫn ghép theo số frame.
            if self._so_lan_quay_vong:
                # Tên file = chỉ số frame của PHIÊN, mà nguồn đã quay vòng ⇒ nó không còn là frame của
                # clip (clip 12 frame: `mask_000015.png` = frame 3). Cùng cơ chế "từ chối" như offset.
                self._tu_choi_quay_vong.add(int(frame_idx))
                if not self._da_canh_bao_quay_vong:
                    self._da_canh_bao_quay_vong = True
                    print(f"[canh-bao] TỪ CHỐI dump mask: nguồn đã quay vòng {self._so_lan_quay_vong} "
                          "lần (loop_files) ⇒ chỉ số frame của phiên không còn là frame của clip, "
                          "tên `mask_NNNNNN.png` sẽ sai. Dùng `--stop-after-frames` <= độ dài clip "
                          "(hoặc tắt lặp) — xem ticket #36", flush=True)
                return False
            if self._frame_goc:
                # TỪ CHỐI GHI **MỌI** frame (ticket #36; P1 vòng review 2): tên file đi theo chỉ số
                # frame của PHIÊN, mà phiên đã bỏ `_frame_goc` frame lúc chờ chọn ô. Nguồn
                # `loop_files` còn QUAY VÒNG nên `offset + idx` **không** phải frame của clip (phải
                # mod độ dài clip) ⇒ không đoán. Không có file = "chưa chạy", đúng hơn một file mang
                # tên sai frame.
                # Cảnh báo MỘT lần, nhưng `return False` cho **mọi** lần: guard cũ đặt cả hai trong
                # `not self._da_canh_bao_offset` ⇒ từ frame yêu cầu thứ hai trở đi nó rơi xuống
                # `cv2.imwrite` và ghi đúng thứ file mà ticket này cấm.
                self._tu_choi_offset.add(int(frame_idx))
                if not self._da_canh_bao_offset:
                    self._da_canh_bao_offset = True
                    print(f"[canh-bao] TỪ CHỐI dump mask: phiên bắt đầu sau {self._frame_goc} frame "
                          "đọc từ nguồn (chờ chọn ô) ⇒ tên `mask_NNNNNN.png` không phải frame NNNNNN "
                          "của clip, nhất là khi nguồn quay vòng. Chạy lại với ô chọn có sẵn từ frame "
                          "đầu (`--bbox`/bbox.json) — xem ticket #36", flush=True)
                return False
            se_ghi_de = dich.exists()
            if not cv2.imwrite(str(dich), arr * 255):
                print(f"[canh-bao] cv2.imwrite trả False cho frame {frame_idx} (đĩa/quyền?) — file "
                      "KHÔNG được ghi", flush=True)
                return False
            if se_ghi_de:
                # Đếm SAU khi ghi thành công (nếu `imwrite` fail thì không có lần ghi đè nào xảy ra).
                self._so_file_ghi_de += 1
                print(f"[canh-bao] GHI ĐÈ {dich.name}: file đã có trong thư mục này (đếm "
                      f"{self._so_file_ghi_de} lần). Mask của lần chọn/phiên trước bị thay ⇒ dùng "
                      "`--dump-mask-dir` khác cho mỗi lần chọn nếu cần chấm cả hai", flush=True)
            self._dumped.add(int(frame_idx))
            self._write_mask_manifest(target)
            return True
        except Exception as exc:                 # noqa: BLE001 — dụng cụ đo không giết phiên
            print(f"[canh-bao] không ghi được mask frame {frame_idx}: {exc}", flush=True)
            return False

    def _write_mask_manifest(self, target: Path) -> None:
        """Ghi `manifest.json` cạnh các file mask: **mask sinh ra trong điều kiện nào**.

        Không có nó thì artifact mIoU không tự kiểm được là mask tới từ `image_size`/`vos_every`/ô chọn
        nào — đúng loại "số không truy được về cấu hình" mà repo đã gặp (P0/P2 review 14-11).
        """
        import json

        payload = {
            "nguon": an_userinfo(str(self._cfg.source)),
            # `image_size` thuộc ENGINE (hydra override), không phải session config. Ghi CẢ hai: giá trị
            # yêu cầu và giá trị predictor thật sự dùng (`None` = chưa kiểm được).
            "image_size": getattr(self._engine, "image_size", None),
            "image_size_hieu_luc": getattr(self._engine, "image_size_hieu_luc", None),
            "vos_every": self._cfg.vos_every, "mask_smoothing": self._cfg.mask_smoothing,
            "bbox_xywh": list(self._chon_bbox) if getattr(self, "_chon_bbox", None) else None,
            "frames_yeu_cau": list(self._cfg.dump_mask_frames),
            # > 0 = phiên đã bỏ N frame lúc chờ chọn ô ⇒ `_dump_mask` TỪ CHỐI ghi, nên khi có file thì
            # giá trị này luôn 0. Giữ khoá để chỗ CHẤM phát hiện manifest do tool khác/viết tay sinh.
            # `getattr`: hàm này còn được gọi từ test dựng session bằng `object.__new__` (không `__init__`).
            "frame_goc_cua_phien": getattr(self, "_frame_goc", 0),
            # Danh sách ĐÃ GHI (khác "yêu cầu"): không có nó thì không phân biệt được "chấm 12 frame"
            # với "đã ghi 7/12" (P3 review 17-11).
            "frames_da_ghi": sorted(getattr(self, "_dumped", set())),
            # > 0 ⇒ có file bị ghi đè (tên trùng giữa hai lần chọn/phiên) — đọc kèm khi chấm.
            "so_file_ghi_de": getattr(self, "_so_file_ghi_de", 0),
            "ghi_chu": "mask THÔ của model (trước bước làm mượt); tên file = chỉ số frame VIDEO",
        }
        try:
            (target / "manifest.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"[canh-bao] không ghi được manifest.json: {exc}", flush=True)

    def _record_vos(self, result, frame_video=None, dump: bool = True) -> tuple:
        """Ghi nhận một lần VOS. Trả `(dump_ms, da_ghi)`: thời gian ĐÃ THỬ ghi mask + có file thật không.

        Trả `(dump_ms, da_ghi)` thay vì tự gán `post_ms`/`dump_ms`: người gọi đang đo `post_ms` bao
        trọn cả lần gọi này, nên phải **trừ** phần ghi file ra — nếu không, dụng cụ đo
        (`--dump-mask-frames`) làm bẩn đúng `post_ms`/`mask_age_total_ms` mà nó định đo (ticket #26).

        `dump_ms` = thời gian **thử** ghi; `da_ghi` = có file thật. Hai giá trị này phải được gán vào
        `_stats` **cùng lúc với `post_ms`** ở người gọi: gán `dump_ms` ở đây rồi `post_ms` ở ngoài kia
        thì một lần VOS chen giữa sẽ khiến `status.json` ghép `post_ms` của lần N với `dump_ms` của
        lần N+1 (P3 review độc lập 17-11).
        """
        bat_dau_dump = time.perf_counter()
        # `dump=False`: đường CÓ luồng, frame `start()` sẽ được worker xử lý lại và dump ở `_store_vos`
        # ⇒ dump ở đây là ghi đè chính file đó. `frame_video` vẫn được truyền vì nó còn dùng để
        # `_measure_stability` nhận ra "cùng một frame, hai kết quả VOS" (ticket #35).
        da_ghi = self._dump_mask(result, frame_video) if dump else False
        dump_ms = round((time.perf_counter() - bat_dau_dump) * 1000.0, 2)
        with self._stats_lock:
            self._stats.vos_ms = round(float(getattr(result, "elapsed_ms", 0.0)), 1)
            self._stats.vos_runs += 1
            self._vos_stamps.append(time.perf_counter())
            self._trim(self._vos_stamps)
        # `frame_video`: để `_measure_stability` bỏ mẫu cặp khi worker xử lý LẠI đúng frame `start()`
        # (ticket #35). `None` chỉ xảy ra khi `_seq_frame` đã bị prune (worker gộp frame, giữ 90 seq):
        # khi đó KHÔNG biết frame ⇒ **đo bình thường** (thà thừa một mẫu cặp hơn bỏ mẫu thật).
        self._measure_stability(result, frame_video=frame_video)
        # Trả thời gian ĐÃ THỬ ghi (kể cả khi fail) để `post_ms` không bao gồm công việc dump; người
        # đọc `status.json` chỉ thấy con số khi CÓ file (`da_ghi`). Không dump frame này ⇒ 0,0 (không
        # có gì để trừ).
        return (dump_ms, da_ghi) if dump and self._co_dump(frame_video) else (0.0, False)

    def _co_dump(self, frame_video) -> bool:
        """Frame này có nằm trong `--dump-mask-frames` không (⇒ có THỬ ghi file)."""
        frames = self._cfg.dump_mask_frames
        return bool(frames) and frame_video is not None and int(frame_video) in frames

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
        found, bbox = self._shown_state_locked(frame_idx)
        return bbox if found else None

    def _shown_state_locked(self, frame_idx):
        """`(đã phát frame này chưa?, ô bao lúc phát hoặc None)`.

        Phải phân biệt hai ca mà `None` gộp làm một (review độc lập 13-11, P1): (a) frame **chưa**
        được phát — chờ phát rồi mới chấm, và (b) frame **đã** phát nhưng không có ô bao hiển thị
        (`_update_stats_locked` lưu `None`). Nếu gộp, ca (b) bị hẹn `_pending_drift` cho một frame
        ĐÃ TRÔI QUA ⇒ mẫu bị bỏ im lặng ⇒ CSV thiếu dòng (đo được: binh1 379 lần VOS nhưng 368
        dòng; binh2 359 vs 339).
        """
        for idx, bbox in reversed(self._shown_by_frame):
            if idx == frame_idx:
                return True, bbox
        return False, None

    def _lk_ok_of(self, frame_idx):
        """Trạng thái LK của frame đã phát `frame_idx` (`None` = chưa đo/không có LK)."""
        for idx, ok in reversed(self._lk_by_frame):
            if idx == frame_idx:
                return ok
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
            # VOS không thấy vật (mask rỗng ⇒ bbox (0,0,0,0)): KHÔNG chấm drift nhưng VẪN ghi dòng —
            # đây chính là bằng chứng "VOS mất dấu", thứ phải TÁCH khỏi "LK trôi". Bỏ dòng này thì
            # cột `empty` luôn 0 và `empty_frac` nói dối (binh2 12-11: 81 lần mask rỗng trong
            # status.json nhưng CSV ghi 0,0 — bắt được khi đo thật).
            self._log_drift_sample(frame_idx=frame_idx, seq=seq, value=None, result=result)
            return
        # Tra cứu + hẹn pending trong MỘT critical section: nếu tách hai khối thì luồng chính có thể
        # phát đúng frame này xen vào giữa (thấy `_pending_drift` còn cũ ⇒ bỏ) ⇒ mất một mẫu drift
        # (review 10-11 vòng 2, P3).
        da_hen = False
        cu = None
        with self._stats_lock:
            found, shown = self._shown_state_locked(frame_idx)
            # `_lk_ok_of` lặp `_lk_by_frame`, mà luồng phát APPEND deque đó dưới `_stats_lock` ⇒ phải
            # gọi TRONG lock này. Gọi ngoài lock từng là đường mới của PR #50 và có thể ném
            # `RuntimeError: deque mutated during iteration` ⇒ `_VosWorker` bắt `Exception` ⇒ **cả
            # phiên live thành `error`** (review độc lập bắt P1 ngay sau khi merge).
            lk_ok = self._lk_ok_of(frame_idx) if found else None
            if not found:
                # Kết quả về TRƯỚC khi frame đó được phát (engine rất nhanh) ⇒ hẹn so lúc phát
                # frame; nếu frame đó đã trôi qua thật thì `_update_stats_locked`/`_flush_pending`
                # vẫn ghi được dòng (drift trống), không bỏ mẫu.
                # Pending là MỘT slot: nếu kết quả VOS trước đó còn treo thì ghi nó thành dòng ngay
                # (sau khi nhả lock) thay vì ghi đè ⇒ không mất mẫu khi VOS nhanh hơn nhịp phát
                # (review độc lập vòng 2, P3).
                cu, da_hen = self._pending_drift, True
                # 5 phần tử: (frame, bbox VOS, seq, vos_ms, empty). `lk_ok` KHÔNG nằm trong tuple —
                # frame này chưa được phát nên chưa biết LK, và phải TRA LẠI trong lock lúc drain
                # (nhồi `None` vào tuple từng làm mẫu bị mất khỏi mẫu số của `lk_ok_frac` — P2 review #51).
                self._pending_drift = (frame_idx, tuple(fresh), seq,
                                       float(getattr(result, "elapsed_ms", 0.0)),
                                       self._mask_empty(result))
        if da_hen:
            if cu is not None:
                with self._stats_lock:
                    lk_ok_cu = self._lk_ok_of(cu[0])
                self._log_drift_sample(frame_idx=cu[0], seq=cu[2], vos_ms=cu[3],
                                       empty=cu[4], value=None, bbox=cu[1], lk_ok=lk_ok_cu)
            return
        if shown is None:
            # Frame đã phát nhưng KHÔNG có ô bao hiển thị ⇒ không có gì để so (ghi dòng, drift trống).
            self._log_drift_sample(frame_idx=frame_idx, seq=seq, value=None, result=result)
            return
        value = _bbox_iou(shown, fresh)
        self._record_drift(value, self._mask_empty(result))
        self._log_drift_sample(frame_idx=frame_idx, seq=seq, result=result, value=value,
                               hien_thi=shown, lk_ok=lk_ok)

    @staticmethod
    def _mask_empty(result):
        """Mask của kết quả VOS có RỖNG không — `None` khi engine không trả mask (chưa đo)."""
        mask = getattr(result, "mask", None)
        if mask is None:
            return None
        return not bool(mask.any())

    def _log_drift_sample(self, *, frame_idx, seq, value, result=None, vos_ms=None,
                          empty=None, bbox=None, hien_thi=None, lk_ok=None) -> None:
        """Ghi MỘT dòng CSV cho mẫu drift (ticket 15). PHẢI gọi khi KHÔNG giữ `_stats_lock`.

        `result` là kết quả VOS (có `elapsed_ms`/`mask`/`bbox`); nhánh `_pending_drift` tới hạn thì
        dữ liệu đã tách sẵn trong tuple hẹn (`vos_ms`/`empty`/`bbox`) → không truyền `result`.
        """
        self._drift_log.write(
            frame_idx=frame_idx, seq=seq,
            vos_ms=(float(getattr(result, "elapsed_ms", 0.0)) if vos_ms is None else vos_ms),
            empty=(self._mask_empty(result) if empty is None else empty),
            drift_iou=value,
            bbox=(getattr(result, "bbox", None) if bbox is None else bbox),
            hien_thi=hien_thi, lk_ok=lk_ok)

    def _record_drift(self, value, empty=None) -> None:
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
            self._drift_empty_window.append(empty)
            self._apply_drift_locked()

    def _apply_drift_locked(self) -> None:
        """Tính lại thống kê drift — gọi khi ĐÃ giữ `_stats_lock` (tên có hậu tố `_locked`)."""
        if not self._drift_window:
            # Chưa có mẫu nào: vẫn phải khai cờ khi phiên KHÔNG THỂ đo (`vos_every < 2`), nếu không
            # `status.json` để `null` và người đọc không biết là "không có gì để đo" hay "worker bản
            # cũ" (review độc lập PR #54, P3).
            if getattr(self._cfg, "vos_every", 3) < 2:
                self._stats.suc_khoe = tracking_health.phan_quyet(
                    [], [], vos_every=self._cfg.vos_every,
                    truoc=(self._stats.suc_khoe or {}).get("co", tracking_health.OK))
            return
        values = np.fromiter(self._drift_window, dtype=float)
        self._stats.drift_n = len(values)
        self._stats.drift_iou = round(float(values.mean()), 3)
        self._stats.drift_iou_p05 = (round(float(np.percentile(values, 5)), 3)
                                     if len(values) >= _STAT_MIN_SAMPLES else None)
        # Cờ #14 — `truoc` tạo găng tay Schmitt (đang bật thì chỉ tắt khi p05 > ngưỡng ra). Đọc
        # `self._cfg` ở đây an toàn: chỉ để biết `vos_every`, không đụng trạng thái dùng chung.
        self._stats.suc_khoe = tracking_health.phan_quyet(
            list(self._drift_window), list(self._drift_empty_window),
            vos_every=getattr(self._cfg, "vos_every", 3),
            truoc=(self._stats.suc_khoe or {}).get("co", tracking_health.OK),
        )

    def _note_mask_age(self, seconds: float, vos_ms: float = 0.0, pre_ms: float = 0.0,
                       queue_ms: float = 0.0, post_ms: float = 0.0) -> None:
        """Tuổi của mask đang hiển thị (ms) + p95, tách 2 định nghĩa.

        `seconds` đo từ lúc kết quả model **sẵn sàng** ⇒ chưa gồm: chờ trong worker (`queue_ms`),
        tiền xử lý (`pre_ms`), suy luận (`vos_ms`), đo drift + làm mượt (`post_ms`). Người xem thực
        tế thấy dữ liệu cũ hơn đúng bằng tổng các khoản đó, nên báo cả hai:
          - `mask_age_cu_ms` = age + vos (**định nghĩa cũ**, giữ để so với số trước 14-11);
          - `mask_age_total_ms` = queue + pre + vos + post + age (**tuổi dữ liệu thật**).
        p95 tính **theo từng mẫu** trên `mask_age_total_ms`, không cộng một `vos_ms` hiện tại cho
        mọi mẫu lịch sử (cách cũ làm số của cả cửa sổ nhảy theo lần đo mới nhất).
        """
        age_ms = max(0.0, float(seconds) * 1000.0)
        vos_ms = max(0.0, float(vos_ms))
        phu_ms = (max(0.0, float(pre_ms)) + max(0.0, float(queue_ms))
                  + max(0.0, float(post_ms)))
        # `append` + `np.fromiter` + `percentile` trong CÙNG `_stats_lock` (ticket 20): hôm nay chỉ
        # có một luồng ghi, nhưng đây đúng mẫu code mà ticket 17 vừa phải sửa cho `_drift_window`
        # (`RuntimeError: deque mutated during iteration` nếu một người sửa sau thêm luồng thứ hai).
        with self._stats_lock:
            # Lưu TỪNG mẫu kèm phụ phí của chính lần VOS đó (queue+pre+post) — không dùng lại
            # `vos_ms` hiện tại cho toàn cửa sổ.
            tong = age_ms + vos_ms + phu_ms
            self._age_window.append((tong, age_ms + vos_ms))
            total_values = np.fromiter((v[0] for v in self._age_window), dtype=float)
            self._stats.mask_age_ms = round(age_ms, 1)
            self._stats.mask_age_cu_ms = round(age_ms + vos_ms, 1)
            self._stats.mask_age_total_ms = round(tong, 1)
            self._stats.age_n = len(self._age_window)
            self._stats.mask_age_p95 = (round(float(np.percentile(total_values, 95)), 1)
                                        if len(self._age_window) >= _STAT_MIN_SAMPLES
                                        else None)

    def _measure_stability(self, result, frame_video=None) -> None:
        """IoU giữa hai mask VOS liên tiếp — con số trung thực cho "mask có nhấp nháy không".

        Mask RỖNG không vào cửa sổ IoU (`mask_iou(rỗng, rỗng) = 1,0` sẽ biến "mất dấu hoàn toàn"
        thành "độ ổn định 100 %" trên UI — lỗi P2, review 08-11), nhưng chúng **ĐƯỢC ĐẾM** trong
        `_vos_lost_window` (⇒ `empty_frac_window`) và `empty_runs`.

        `frame_video` (ticket #35): frame `engine.start()` được worker `process()` LẠI ⇒ có **hai** kết
        quả VOS cho **cùng một frame video**. Cặp đó không phải "hai mask liên tiếp" — đo IoU của chúng
        gần như luôn ≈ 1,0 và làm `stability` bị thổi lên ở đầu phiên. Vì thế: vẫn ĐẾM vào cửa sổ mất
        dấu (mỗi lần VOS là một lần thật, giữ `empty_window_n == vos_runs`), nhưng **không đẩy mẫu cặp**
        khi `frame_video` trùng lần trước — chỉ cập nhật mốc.
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
        # CÙNG frame video (frame `start()` được worker xử lý lại) không phải cặp "liên tiếp" — xem
        # docstring. Không đẩy mẫu, chỉ cập nhật mốc.
        if frame_video is not None and frame_video == self._prev_vos_frame:
            self._prev_raw_mask = raw
            return
        self._prev_vos_frame = frame_video
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
            shown_row = self._last_shown
            self._last_shown = None
        # Ghi CSV NGOÀI lock: I/O trong `_stats_lock` sẽ chặn luồng VOS (nó cũng cần lock này).
        if row is not None:
            self._log_drift_sample(**row)
        if shown_row is not None:
            self._ghi_o_hien_thi(*shown_row)

    def _ghi_o_hien_thi(self, frame_idx: int, shown, lk_ok: bool, chan_doan=None) -> None:
        """Ghi một dòng ô-bao-đang-hiển-thị (dụng cụ đo #38). Ô không hợp lệ ⇒ để trống, KHÔNG ghi 0.

        Bốn cột toạ độ trống nghĩa là "frame này không có ô nào hiển thị" (chưa có model / mất dấu) —
        khác `0,0,0,0` là một ô suy biến, và khác "chưa đo" (không có file).
        """
        try:
            if self._shown_fh is None:
                path = Path(self._cfg.dump_shown_csv)
                path.parent.mkdir(parents=True, exist_ok=True)
                self._shown_fh = path.open("w", encoding="utf-8", newline="")
                # 5 cột chẩn đoán ở CUỐI (ticket #39): CSV cũ (6 cột) vẫn đọc được, chỉ thiếu cột ⇒
                # `doc_shown` của script A/B trả None chứ không bịa 0.
                self._shown_fh.write(
                    "frame_idx,x1,y1,x2,y2,lk_ok,ly_do,ly_do_khop,scale,angle_deg,n_diem\n")
            d = chan_doan or {}
            # Mỗi dòng LUÔN đủ 11 field. Bản trước nội suy `o = ""` khi không có ô ⇒ dòng chỉ còn 8 field
            # ⇒ `DictReader` đọc `ly_do` thành giá trị của cột `angle_deg`, mất `n_diem` — đúng ca
            # `seed_rong` (f62: bbox VOS suy biến ⇒ không có ô) mà ticket #39 sinh ra để chẩn đoán
            # (P1 review PR #66).
            o = ([""] * 4 if shown is None
                 else [int(shown[0]), int(shown[1]), int(shown[2]), int(shown[3])])
            # `scale`/`angle_deg` chỉ có nghĩa khi similarity THẬT SỰ được dùng; chế độ `shift` luôn
            # reset 1.0/0.0 ⇒ ghi ra sẽ là số CHƯA ĐO (P2 review PR #66) ⇒ để TRỐNG.
            dung_khop = bool(d.get("khop"))
            o += ["" if lk_ok is None else int(bool(lk_ok))]
            o += ["" if d.get("ly_do") is None else str(d["ly_do"]),
                  "" if d.get("ly_do_khop") is None else str(d["ly_do_khop"]),
                  "" if not dung_khop or d.get("scale") is None else f"{float(d['scale']):.4f}",
                  "" if not dung_khop or d.get("angle_deg") is None else f"{float(d['angle_deg']):.2f}",
                  "" if d.get("n_diem") is None else str(int(d["n_diem"]))]
            self._shown_fh.write(",".join(str(x) for x in [int(frame_idx), *o]) + "\n")
        except OSError as exc:                     # không được làm chết phiên vì lỗi ghi file đo
            print(f"[canh-bao] không ghi được CSV ô hiển thị ({exc}) — tắt ghi", flush=True)
            # KHÔNG sửa `_cfg`: `cau_hinh` trong `status.json` phải giữ nguyên "đã YÊU CẦU ghi" (để
            # đọc được provenance), còn lý do hỏng ghi ở cờ riêng bên dưới.
            self._shown_fh = None
            self._shown_loi = f"{type(exc).__name__}: {exc}"
            with self._stats_lock:
                self._stats.dump_shown_loi = self._shown_loi
            self._cfg.dump_shown_csv = ""      # thôi thử ghi lại mỗi frame

    def _update_stats_locked(self, result):
        """Cập nhật số liệu; TRẢ về dòng CSV cần ghi (mẫu `_pending_drift` tới hạn) hoặc `None`."""
        now = time.perf_counter()
        self._stats.frames += 1
        self._display_stamps.append(now)
        self._trim(self._display_stamps)
        self._stats.measured_fps = self._rate(self._display_stamps)
        # Chẩn đoán LK của frame NÀY (ticket #39). Ghi cả `frame_idx` để người đọc biết mẫu nào —
        # không có nó thì không đối chiếu được với dòng trong `--dump-shown-csv`.
        if self._chan_doan_frame is not None:
            self._stats.chan_doan_lk = dict(self._chan_doan_frame, frame_idx=self._frame_index)
        self._stats.vos_fps = self._rate(self._vos_stamps)

        mask = getattr(result, "mask", None)
        # Ghi theo bộ đếm frame CỦA PHIÊN (không phải `result.frame_idx` của engine): `_seq_frame`
        # ánh xạ seq→bộ đếm này lúc submit, nên hai bên phải cùng một hệ.
        shown = tuple(result.bbox) if _bbox_hop_le(result.bbox) else None
        self._shown_by_frame.append((self._frame_index, shown))
        # Dụng cụ đo (#38): nhớ ô HIỂN THỊ của frame này để ghi ra CSV ngoài lock.
        if self._cfg.dump_shown_csv:
            self._last_shown = (self._frame_index, shown, bool(self._lk_ok_frame),
                                self._chan_doan_frame)
        self._lk_by_frame.append((self._frame_index, self._lk_ok_frame))
        pending = self._pending_drift
        csv_row = None
        if pending is not None:
            self._pending_drift = None
            if pending[0] == self._frame_index and shown is not None:
                value = _bbox_iou(shown, pending[1])
                if value is not None:          # ở đây ĐANG giữ `_stats_lock` ⇒ không gọi _record_drift
                    self._drift_window.append(value)
                    self._drift_empty_window.append(pending[4])
                    self._apply_drift_locked()
                csv_row = {"frame_idx": self._frame_index, "seq": pending[2],
                           "vos_ms": pending[3], "empty": pending[4],
                           "value": value, "bbox": pending[1],
                           "hien_thi": shown, "lk_ok": self._lk_ok_of(self._frame_index)}
            else:
                # Frame đã phát mà KHÔNG có ô bao hiển thị (hoặc frame đó không bao giờ tới lượt
                # phát): KHÔNG chấm drift nhưng VẪN ghi dòng — bỏ im lặng là mất mẫu, và đúng
                # những mẫu đó là ca "VOS thấy vật / màn hình không có hộp" cần tách khỏi "LK trôi"
                # (review độc lập 13-11, P1).
                csv_row = {"frame_idx": pending[0], "seq": pending[2], "vos_ms": pending[3],
                           "empty": pending[4], "value": None, "bbox": pending[1]}
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
        """Mở lại file từ đầu (demo live bằng video); nguồn thật hoặc lỗi → None.

        `loop_files=True` (mặc định) chỉ có nghĩa với nguồn **có điểm kết thúc**: file video hoặc
        thư mục ảnh. Với webcam/RTSP/snapshot HTTP, một lần `read()` trả `None` mà mở lại thiết bị
        là tự bắn vào chân: relay/`usbipd` còn đang giữ thiết bị ⇒ "Device busy" và phiên đang khoẻ
        chết theo (AGENTS §6; đường `raw` đã có guard này từ trước — `opencv_source._looks_like_file`).
        """
        if not self._cfg.loop_files or not looks_like_file(self._cfg.source):
            return None
        try:
            source, self._source = self._source, None
            if source is not None:
                source.close()
            self._source = open_video_source(self._cfg.source).open()
            # Đếm lần quay vòng: sau đó `_frame_index` tiếp tục tăng nên tên `mask_NNNNNN.png` KHÔNG
            # còn là frame NNNNNN của clip (clip 12 frame + quay vòng ⇒ `mask_000015.png` = frame 3).
            # `_dump_mask` từ chối ghi từ đây (P3 vòng review 3).
            self._so_lan_quay_vong += 1
            return self._source.read()
        except (OSError, RuntimeError):
            return None

    @staticmethod
    def _sleep(interval: float, began: float) -> None:
        remaining = interval - (time.perf_counter() - began)
        if remaining > 0:
            time.sleep(remaining)
