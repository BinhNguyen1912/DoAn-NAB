"""
PromptSelector — máy trạng thái chọn ô đối tượng bằng kéo chuột trên cửa sổ OpenCV.

Chức năng: ở frame đầu (hoặc frame hiện tại khi chọn lại), người dùng kéo chuột vẽ ô
chọn đối tượng; thả chuột → ô được chuẩn hoá thành bbox (x1, y1, x2, y2). Phần điều
khiển vòng lặp (track → r chọn lại → q/ESC thoát) nằm trong `live_pipeline.run_interactive`;
module này chỉ sở hữu phần tương tác chuột + vẽ khung trực quan (rubber-band).

Input  : sự kiện chuột OpenCV (event, x, y) qua `on_mouse` (gắn bằng cv2.setMouseCallback),
         và frame gốc qua `bind(frame)` để biết kích thước + clip toạ độ.
Output : `bbox` (x1, y1, x2, y2) đã chuẩn hoá (x1<x2, y1<y2, nằm trong frame);
         `draw(frame)` trả ảnh có khung kéo/xác nhận để hiển thị.
Lưu ý  : máy trạng thái thuần — test headless qua sự kiện chuột tổng hợp (không cần GUI);
         phần kéo chuột thật trên cửa sổ kiểm thủ công (WSL không GUI/camera).
"""
import cv2

# Kích thước ô tối thiểu để chấp nhận.
# Trước đây 5 px → một cú click/rê chuột nhỏ cũng được nhận làm "đối tượng": đo thật 27-10
# thấy ô rác 42×60 làm SAM 2 bám loạn rồi mất dấu. Nâng lên 16 px (vẫn nhỏ hơn mặt/vật thật)
# và in cảnh báo để người dùng biết phải kéo lại.
MIN_BOX = 16
HINT_TOO_SMALL = "[chọn] ô quá nhỏ — kéo rộng hơn quanh đối tượng rồi thả chuột"

_COLOR_DRAG = (0, 255, 0)    # xanh lá — đang kéo
_COLOR_DONE = (0, 200, 255)  # cam — đã xác nhận


class PromptSelector:
    """Máy trạng thái kéo-thả chọn ô (idle → dragging → done)."""

    IDLE = "idle"
    DRAGGING = "dragging"
    DONE = "done"

    def __init__(self, frame_shape):
        """frame_shape: (H, W) hoặc (H, W, 3) — kích thước frame sẽ chọn lên."""
        self._h, self._w = int(frame_shape[0]), int(frame_shape[1])
        self.reset()

    # ---------- API công khai ----------

    def bind(self, frame):
        """Gắn selector vào frame mới (khi chọn lại trên frame hiện tại): cập nhật kích thước + reset."""
        self._h, self._w = int(frame.shape[0]), int(frame.shape[1])
        self.reset()

    def reset(self):
        """Xóa ô đang chọn, về idle sẵn sàng chọn lại."""
        self.state = self.IDLE
        self._start = None
        self._end = None
        self.bbox = None

    def has_bbox(self):
        """True khi đã thả chuột và ô đủ lớn — sẵn sàng lấy ra khởi động track."""
        return self.state == self.DONE and self.bbox is not None

    def take_bbox(self):
        """Lấy bbox đã chọn rồi reset về idle (sẵn sàng cho lần chọn kế tiếp)."""
        bbox = self.bbox
        self.reset()
        return bbox

    def on_mouse(self, event, x, y, flags, param):
        """Mouse callback OpenCV — gắn bằng cv2.setMouseCallback(window, selector.on_mouse)."""
        x = max(0, min(self._w - 1, int(x)))
        y = max(0, min(self._h - 1, int(y)))
        if event == cv2.EVENT_LBUTTONDOWN:
            self.state = self.DRAGGING
            self._start = (x, y)
            self._end = (x, y)
            self.bbox = None
        elif event == cv2.EVENT_MOUSEMOVE and self.state == self.DRAGGING:
            self._end = (x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            if self.state == self.DRAGGING:
                self._end = (x, y)
                bbox = self._normalized_bbox()
                if self._is_valid(bbox):
                    self.bbox = bbox
                    self.state = self.DONE
                else:
                    # ô quá nhỏ (click nhầm) — huỷ, về idle + nói rõ để người dùng biết
                    print(HINT_TOO_SMALL)
                    self.reset()
        elif event == cv2.EVENT_RBUTTONDOWN:
            # click phải huỷ chọn đang dở
            self.reset()

    def draw(self, frame):
        """Vẽ khung trực quan lên bản sao frame: xanh lá khi đang kéo, cam khi đã xác nhận."""
        img = frame.copy()
        if self.state == self.DRAGGING and self._start and self._end:
            x1, y1, x2, y2 = self._normalized_bbox()
            cv2.rectangle(img, (x1, y1), (x2, y2), _COLOR_DRAG, 2)
        elif self.state == self.DONE and self.bbox is not None:
            x1, y1, x2, y2 = self.bbox
            cv2.rectangle(img, (x1, y1), (x2, y2), _COLOR_DONE, 2)
        return img

    # ---------- nội bộ ----------

    def _normalized_bbox(self):
        x1, y1 = self._start
        x2, y2 = self._end
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    @staticmethod
    def _is_valid(bbox):
        x1, y1, x2, y2 = bbox
        return (x2 - x1) >= MIN_BOX and (y2 - y1) >= MIN_BOX