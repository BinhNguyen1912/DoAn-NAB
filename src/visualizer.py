"""
Visualizer — lớp vẽ HUD trình bày hoàn chỉnh cho demo bảo vệ (ticket 06).

Chức năng: nhận frame gốc + TrackingResult từng frame → trả ảnh HUD gồm:
  - Segmentation Mask tô màu bán trong suốt (alpha blend, giống `draw_overlay_minimal`);
  - ô bao (bbox) quanh đối tượng;
  - quỹ đạo: đường polyline nối tâm đối tượng qua thời gian — deque giới hạn số điểm
    (`max_trajectory`) để không tràn bộ nhớ khi live dài;
  - text HUD FPS hiệu dụng + độ trễ ms/frame, nhãn tiếng Việt vẽ qua PIL + font TTF
    (cv2.putText dùng font Hershey ASCII — không render nổi chữ có dấu; fallback ASCII
    khi máy không có font TTF);
  - tuỳ chọn ghi video mp4 bản đã overlay (`open_recorder` — bật/tắt qua config/CLI).

Input  : frame (H, W, 3) uint8 BGR + TrackingResult (mask, bbox, score, elapsed_ms).
Output : ảnh HUD cùng kích thước frame; ảnh ghi ra file mp4 nếu recorder đã mở.
Lưu ý  : `reset()` xoá quỹ đạo + số liệu trượt khi người dùng chọn lại đối tượng
         (phím r — ticket 05); recorder giữ nguyên để ghi liền mạch cả 2 phiên.
"""
import os
from collections import deque

import cv2
import numpy as np

# ---------- cấu hình vẽ (đổi qua tham số __init__, config YAML đầy đủ là ticket 08) ----------

_COLOR_MASK = (0, 140, 255)      # BGR cam — cùng màu fixture/ticket 04
_COLOR_BOX = (0, 0, 255)         # BGR đỏ
_COLOR_TRAJECTORY = (255, 0, 255)  # BGR tím
_COLOR_TEXT = (255, 255, 255)    # BGR trắng
_MASK_ALPHA = 0.35
_LINE_THICKNESS = 2
_LATENCY_WINDOW = 30             # cửa sổ trượt để tính FPS/độ trễ trên HUD

# Danh sách font TTF phổ biến hỗ trợ tiếng Việt (Linux/windows/macOS) — thử lần lượt
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
)
# Cho phép override bằng biến môi trường (máy nào font khác)
_FONT_ENV = "CAMAI_FONT_PATH"


def find_vietnamese_font():
    """Trả đường dẫn font TTF hỗ trợ tiếng Việt đầu tiên tìm thấy, hoặc None.

    Ưu tiên biến môi trường CAMAI_FONT_PATH nếu người dùng chỉ định.
    """
    env = os.environ.get(_FONT_ENV)
    if env and os.path.isfile(env):
        return env
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


class Visualizer:
    """Lớp vẽ HUD mỗi frame + quản lý quỹ đạo (deque) + ghi video mp4."""

    def __init__(self, max_trajectory=100, font_path=None, font_size=16):
        """
        max_trajectory: số điểm quỹ đạo tối đa giữ trong deque (điểm cũ tự rơi ra).
        font_path      : đè font tìm tự động (None → find_vietnamese_font()).
        font_size      : cỡ chữ HUD (px).
        """
        self.max_trajectory = int(max_trajectory)
        self._trajectory = deque(maxlen=self.max_trajectory)  # (cx, cy) tâm đối tượng
        self._latencies = deque(maxlen=_LATENCY_WINDOW)       # ms, cửa sổ trượt
        self._font_path = font_path or find_vietnamese_font()
        self._font_size = int(font_size)
        self._writer = None      # cv2.VideoWriter khi ghi video
        self._pending_recorder = None  # (path, fps) chờ frame đầu để biết kích thước

    # ---------- API công khai ----------

    def update(self, frame, result):
        """Vẽ HUD lên bản sao frame; trả ảnh (H, W, 3) uint8; ghi ra mp4 nếu recorder mở."""
        img = frame.copy()

        # 1) tô mask bán trong suốt
        if result.mask is not None and result.mask.any():
            tint = img.copy()
            tint[result.mask] = _COLOR_MASK
            img = cv2.addWeighted(img, 1.0 - _MASK_ALPHA, tint, _MASK_ALPHA, 0)

        # 2) ô bao
        x1, y1, x2, y2 = [int(v) for v in result.bbox]
        if x2 > x1 and y2 > y1:
            cv2.rectangle(img, (x1, y1), (x2, y2), _COLOR_BOX, _LINE_THICKNESS)

        # 3) quỹ đạo — thêm tâm (bỏ frame mask rỗng để không thêm điểm rác (0,0)),
        #    rồi vẽ polyline nối các điểm + chấm hiện tại
        if result.bbox != (0, 0, 0, 0):
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
            self._trajectory.append((cx, cy))
        if len(self._trajectory) >= 2:
            pts = np.array(self._trajectory, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(img, [pts], isClosed=False, color=_COLOR_TRAJECTORY,
                          thickness=_LINE_THICKNESS)
            cv2.circle(img, self._trajectory[-1], 3, _COLOR_TRAJECTORY, -1)

        # 4) HUD text FPS + độ trễ + điểm tin cậy
        self._latencies.append(result.elapsed_ms)
        self._draw_hud(img, result.score)

        # 5) ghi nếu recorder đang mở
        self._write(img)
        return img

    def reset(self):
        """Xoá quỹ đạo + số liệu trượt (khi chọn lại đối tượng — phím r)."""
        self._trajectory.clear()
        self._latencies.clear()

    @property
    def trajectory_points(self):
        return tuple(self._trajectory)

    @property
    def effective_fps(self):
        """FPS hiệu dụng theo độ trễ trung bình trong cửa sổ trượt (trung thực ADR-0002)."""
        if not self._latencies:
            return 0.0
        mean_ms = float(np.mean(self._latencies))
        return 1000.0 / mean_ms if mean_ms > 0 else 0.0

    @property
    def mean_latency_ms(self):
        return float(np.mean(self._latencies)) if self._latencies else 0.0

    # ---------- ghi video ----------

    def open_recorder(self, path, fps=30.0, frame_size=None):
        """Bật ghi mp4.

        frame_size=(W, H): mở ngay, trả True/False theo VideoWriter mở được.
        frame_size=None  : trả True và trì hoãn mở tận update() đầu tiên (khi mới biết
                           kích thước frame) — hợp hữu dụng với live/cam lạ.
        """
        self.close_recorder()
        if frame_size is not None:
            return self._open_writer(path, fps, frame_size)
        self._pending_recorder = (str(path), float(fps))
        return True

    def close_recorder(self):
        """Đóng recorder nếu đang mở (an toàn khi chưa mở)."""
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        self._pending_recorder = None

    def _open_writer(self, path, fps, frame_size):
        w, h = int(frame_size[0]), int(frame_size[1])
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        if not writer.isOpened():
            writer.release()
            print(f"[visualizer] KHONG ghi duoc video: {path} (codec/thu muc khong hop le)")
            return False
        self._writer = writer
        return True

    def _write(self, img):
        if self._writer is None and self._pending_recorder is not None:
            path, fps = self._pending_recorder
            self._pending_recorder = None
            self._open_writer(path, fps, (img.shape[1], img.shape[0]))
        if self._writer is not None:
            self._writer.write(img)

    # ---------- HUD text ----------

    def _draw_hud(self, img, score):
        """Vẽ HUD 3 dòng: FPS, độ trễ, điểm tin cậy (tiếng Việt qua PIL nếu có font)."""
        for i, text in enumerate(self.hud_lines(score, self.effective_fps,
                                               self.mean_latency_ms)):
            self._put_text(img, text, (8, 20 + 20 * i))

    def hud_lines(self, score, fps, ms):
        """Nội dung 3 dòng HUD — hàm thuần để test không cần pixel.

        Điểm tin cậy (`object_score_logits` của SAM 2) giúp người dùng so sánh các lần
        chọn đối tượng: ô chứa đối tượng thật thường có điểm cao hơn vùng nền.
        """
        if self._font_path is not None:
            return [f"FPS: {fps:.1f}",
                    f"Độ trễ: {ms:.0f} ms/frame",
                    f"Điểm tin cậy: {score:.1f}"]
        return [f"FPS: {fps:.1f}",
                f"Tre: {ms:.0f} ms/frame",
                f"Diem tin cay: {score:.1f}"]

    def _put_text(self, img, text, org):
        """Vẽ 1 dòng text: PIL (đủ tiếng Việt) nếu có font, cv2.putText nếu không."""
        if self._font_path is not None:
            _pil_put_text(img, text, org, self._font_path, self._font_size, _COLOR_TEXT)
        else:
            cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        _COLOR_TEXT, 2, cv2.LINE_AA)


def _pil_put_text(img_bgr, text, org, font_path, size, color_bgr):
    """Vẽ text tiếng Việt bằng PIL lên ndarray BGR tại chỗ (in-place)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:  # không có PIL — hạ xuống cv2.putText ASCII
        cv2.putText(img_bgr, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    color_bgr, 2, cv2.LINE_AA)
        return
    pil_img = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    font = ImageFont.truetype(font_path, size)
    x, y = org
    # BGR → RGB cho fill (PIL dùng RGB)
    draw.text((x, y), text, font=font, fill=(color_bgr[2], color_bgr[1], color_bgr[0]))
    img_bgr[:] = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)