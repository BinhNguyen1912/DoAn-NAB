"""
OpenVocabDetector — tìm vật thể bằng MÔ TẢ VĂN BẢN (YOLO-World), không cần chấm điểm tay.

Vì sao có: SAM 2 là mô hình **promptable** — nó chỉ bám được thứ người dùng TRỎ vào. Với vật
đơn sắc cùng tông nền (remote trắng trước tường trắng) mọi thứ dựa vào *màu/đặc trưng thị giác*
đều mù, còn người thì vẫn nhận ra vì hiểu **ngữ nghĩa** ("vật này là cái điều khiển"). YOLO-World
đóng đúng lỗ hổng đó: nó biết hình thái của lớp `remote control`, nên tách được vật khỏi mảng
tường cùng màu, và **tự tìm lại khi vật quay vào khung** (re-ID không cần mẫu đặc trưng).

ĐO TRÊN MÁY NÀY (CPU Iris Xe, `yolov8s-worldv2.pt` 25 MB, 22-11-2026):
    imgsz=320 → 38–52 ms/frame (19–26 FPS)     imgsz=640 → 160–242 ms/frame (4–6 FPS)
⇒ 320 là mức dùng được cho live; 640 chỉ dùng để chấm offline.

GIỚI HẠN ĐÃ ĐO — phải đọc trước khi hứa:
  - Trên clip tổng hợp `data/remote_trang.mp4` (hình chữ nhật trắng trơn) detector trả **0 box**
    ở cả 320 và 640. Đó là kỳ vọng: hình chữ nhật trơn KHÔNG phải "cái điều khiển" về mặt ngữ
    nghĩa ⇒ **clip tổng hợp KHÔNG dùng được để nghiệm thu hướng này**, cần footage thật.
  - `binh1.mp4` (chai nước) cho 0,38 box/frame với `conf` 0,29–0,30 = **dương tính giả**, dưới
    `DEFAULT_CONF` 0,25 thì lọt, trên 0,35 thì sạch. Vì vậy ngưỡng mặc định để 0,30 và mọi lần
    nhận lại phải qua thêm cổng hình học (`src/geometry_guard.py`) chứ không tin detector một mình.

Fail-open: thiếu weights / thiếu `ultralytics` / model lỗi ⇒ `available = False`,
`detect()` trả `[]` và ghi `last_error`. Không bao giờ ném — một phụ thuộc TUỲ CHỌN không được
làm chết phiên demo.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

# Trọng số mặc định (git-ignored: 25 MB). Tải bằng:
#   curl -L -o models/yolo-world/yolov8s-worldv2.pt \
#     https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s-worldv2.pt
DEFAULT_WEIGHTS = os.path.join("models", "yolo-world", "yolov8s-worldv2.pt")
# 320 đo được 19–26 FPS trên CPU ⇒ đủ để chạy mỗi khi mất dấu mà không ăn hết nhịp phát.
DEFAULT_IMGSZ = 320
# 0,30: đo trên `binh1` cho dương tính giả ở conf 0,29–0,30 ⇒ 0,25 là quá thấp.
DEFAULT_CONF = 0.30


@dataclass
class Detection:
    """Một vật thể detector tìm được. `bbox` theo (x1, y1, x2, y2) toạ độ frame gốc."""

    bbox: tuple[int, int, int, int]
    conf: float
    label: str


@dataclass
class OpenVocabDetector:
    """Bọc YOLO-World. `available = False` khi thiếu weights/thư viện — gọi `detect()` vẫn an toàn."""

    weights: str = DEFAULT_WEIGHTS
    classes: tuple[str, ...] = ()
    conf: float = DEFAULT_CONF
    imgsz: int = DEFAULT_IMGSZ
    device: str = "cpu"
    _model: object = None
    _loaded: bool = False
    last_error: str | None = None
    last_ms: float | None = None
    # số lần gọi THẬT (để báo cáo "đã đo hay chưa" thay vì đọc `0` thành "chạy không ra gì")
    calls: int = field(default=0)

    # ---------------------------------------------------------------- trạng thái

    @property
    def weights_path(self) -> str:
        """Đường dẫn tuyệt đối tới weights (chấp nhận đường dẫn tương đối theo repo root)."""
        if os.path.isabs(self.weights):
            return self.weights
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(root, self.weights)

    @property
    def available(self) -> bool:
        """True khi có file weights. KHÔNG kiểm `ultralytics` (import nặng) — `load()` làm việc đó."""
        return os.path.isfile(self.weights_path)

    def load(self) -> bool:
        """Nạp model (lần đầu ~1–3 s). Trả False + `last_error` thay vì ném."""
        if self._loaded:
            return True
        if not self.available:
            self.last_error = f"không thấy weights: {self.weights_path}"
            return False
        try:
            from ultralytics import YOLO            # phụ thuộc TUỲ CHỌN
            self._model = YOLO(self.weights_path)
            if self.classes:
                self._model.set_classes(list(self.classes))
        except Exception as exc:                    # noqa: BLE001 — phụ thuộc tuỳ chọn phải fail-open
            self.last_error = f"không nạp được YOLO-World: {exc}"
            self._model = None
            return False
        self._loaded = True
        self.last_error = None
        return True

    # ---------------------------------------------------------------- suy luận

    def detect(self, frame) -> list[Detection]:
        """Trả danh sách vật thể (rỗng nếu chưa nạp được hoặc không thấy gì). Không ném."""
        if not self.load():
            return []
        t0 = time.perf_counter()
        try:
            result = self._model.predict(frame, imgsz=self.imgsz, conf=self.conf,
                                         device=self.device, verbose=False)[0]
        except Exception as exc:                    # noqa: BLE001
            self.last_error = f"predict lỗi: {exc}"
            return []
        self.calls += 1
        self.last_ms = (time.perf_counter() - t0) * 1000.0
        names = getattr(result, "names", {}) or {}
        out: list[Detection] = []
        for box in getattr(result, "boxes", []):
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
            idx = int(box.cls[0]) if box.cls is not None else 0
            out.append(Detection(
                bbox=(int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))),
                conf=float(box.conf[0]),
                label=str(names.get(idx, self.classes[idx] if idx < len(self.classes) else idx)),
            ))
        # Cao nhất trước — chỗ gọi chỉ cần "ứng viên tốt nhất" là lấy phần tử đầu.
        out.sort(key=lambda d: d.conf, reverse=True)
        return out

    def best(self, frame) -> Detection | None:
        """Ứng viên tin cậy nhất, hoặc None."""
        found = self.detect(frame)
        return found[0] if found else None
