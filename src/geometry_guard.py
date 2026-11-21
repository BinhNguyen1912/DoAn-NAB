"""
GeometryGuard — bảo vệ hình học đối tượng khi bám bắt và tái nhận diện (ticket 03).

Chức năng:
1. Lưu trữ lịch sử hình học (diện tích và aspect ratio = w/h) của đối tượng trong các frame ổn định.
2. Kiểm tra tính tương thích hình học của ứng viên trước khi tái nhận diện (loại bỏ mảng tường,
   bóng đèn, công tắc, cánh cửa có cùng màu nhưng khác tỉ lệ hình học).
3. Tự động sinh điểm prompt tương phản (positive ở tâm, negative ở rìa ngoài) cho ứng viên hợp lệ.
"""
from collections import deque
from dataclasses import dataclass


@dataclass
class GeometricStats:
    mean_w: float
    mean_h: float
    mean_area: float
    mean_aspect_ratio: float
    samples: int


class GeometricProfile:
    """Lịch sử hình học đối tượng (kích thước, diện tích, aspect ratio)."""

    def __init__(self, maxlen: int = 30, min_samples: int = 3):
        self._history: deque[tuple[int, int, int, int]] = deque(maxlen=maxlen)
        self.min_samples = int(min_samples)

    def reset(self) -> None:
        self._history.clear()

    def update(self, bbox: tuple[int, int, int, int] | None) -> None:
        """Cập nhật một ô bao hợp lệ vào lịch sử."""
        if bbox is None:
            return
        x1, y1, x2, y2 = bbox
        w, h = abs(x2 - x1), abs(y2 - y1)
        if w > 0 and h > 0:
            self._history.append((int(x1), int(y1), int(x2), int(y2)))

    @property
    def is_ready(self) -> bool:
        """True nếu đã có đủ số mẫu ổn định tối thiểu."""
        return len(self._history) >= self.min_samples

    def stats(self) -> GeometricStats | None:
        if not self.is_ready:
            return None
        widths = [abs(b[2] - b[0]) for b in self._history]
        heights = [abs(b[3] - b[1]) for b in self._history]
        areas = [w * h for w, h in zip(widths, heights)]
        ars = [w / h for w, h in zip(widths, heights)]
        return GeometricStats(
            mean_w=float(sum(widths) / len(widths)),
            mean_h=float(sum(heights) / len(heights)),
            mean_area=float(sum(areas) / len(areas)),
            mean_aspect_ratio=float(sum(ars) / len(ars)),
            samples=len(self._history),
        )

    def is_compatible(self, cand_bbox: tuple[int, int, int, int],
                      area_tol: float = 0.60,
                      aspect_tol: float = 0.45) -> bool:
        """Kiểm tra ứng viên có khớp hình học với lịch sử đối tượng không.

        area_tol: sai lệch diện tích tối đa (0.60 = 60%).
        aspect_tol: sai lệch tỷ lệ w/h tối đa (0.45 = 45%).
        """
        st = self.stats()
        if st is None:
            # Chưa đủ mẫu lịch sử ⇒ cho qua (fail-open)
            return True

        x1, y1, x2, y2 = cand_bbox
        cw = abs(x2 - x1)
        ch = abs(y2 - y1)
        if cw <= 0 or ch <= 0:
            return False

        c_area = cw * ch
        c_ar = cw / ch

        # Kiểm tra sai số diện tích
        area_diff = abs(c_area - st.mean_area) / st.mean_area
        if area_diff > area_tol:
            return False

        # Kiểm tra sai số tỷ lệ khung hình
        ar_diff = abs(c_ar - st.mean_aspect_ratio) / st.mean_aspect_ratio
        if ar_diff > aspect_tol:
            return False

        return True


def generate_contrast_points(
    bbox: tuple[int, int, int, int],
    frame_shape: tuple[int, int],
    margin: int | None = None,
) -> tuple[list[tuple[float, float]], list[int]]:
    """Tự động sinh điểm positive (tâm) và negative (4 cạnh ngoài) cho bbox.

    Dùng khi tái bắt đối tượng đơn sắc để SAM 2 không bị tràn mask ra ngoài nền sáng.
    """
    x1, y1, x2, y2 = bbox
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    w = abs(x2 - x1)
    h = abs(y2 - y1)
    h_max, w_max = frame_shape[0], frame_shape[1]

    if margin is None:
        margin = max(4, int(min(w, h) * 0.15))

    points = [(cx, cy)]
    labels = [1]

    # 4 điểm negative ngoài 4 cạnh (có clip trong khung hình)
    candidates_neg = [
        (cx, max(0.0, y1 - margin)),               # trên
        (cx, min(float(h_max - 1), y2 + margin)), # dưới
        (max(0.0, x1 - margin), cy),               # trái
        (min(float(w_max - 1), x2 + margin), cy), # phải
    ]
    for px, py in candidates_neg:
        # Chỉ nhận điểm negative nếu nó thật sự nằm NGOÀI bbox
        if px < x1 or px > x2 or py < y1 or py > y2:
            points.append((float(px), float(py)))
            labels.append(0)

    return points, labels
