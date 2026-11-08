"""
LK tracker nhẹ — nội suy ô bao giữa các lần chạy VOS (giây phút model "nghỉ").

Chức năng: theo dõi dịch chuyển của đối tượng bằng `cv2.calcOpticalFlowPyrLK` trên lưới điểm
           trong ô bao; lấy **trung vị** độ dịch (bền với điểm nhiễu) rồi tịnh tiến ô bao.
Input  : frame xám (gray) hiện tại; ô bao ban đầu (x, y, w, h).
Output : ô bao mới (x, y, w, h) hoặc None khi không đủ điểm theo dõi (vật bị che/mất).
Lưu ý  : LK chỉ **tịnh tiến** — không bắt được xoay/co giãn; vì vậy nó KHÔNG thay VOS, chỉ lấp
         các frame giữa hai lần suy luận. Số đo trên máy này: 2,22 ms (rảnh) / 3,19 ms (dưới tải)
         — `docs/research/09`. Không import torch.
"""

import numpy as np

import cv2

# Tham số LK — giữ mặc định của OpenCV cho ổn định, chỉ chỉnh lưới điểm
DEFAULT_GRID = 8          # số điểm mỗi chiều trong ô bao (8×8 = 64 điểm)
DEFAULT_MIN_POINTS = 6   # dưới ngưỡng này coi như mất dấu (không đủ điểm để tin)
DEFAULT_WIN = 21          # cửa sổ tìm kiếm (px)
DEFAULT_MAX_MAD = 1.5     # độ tản (px) tối đa của vector dịch; lớn hơn ⇒ coi là mất dấu


class LkBoxTracker:
    """Theo dõi tịnh tiến ô bao bằng optical flow thưa (Lucas–Kanade)."""

    def __init__(self, *, grid: int = DEFAULT_GRID, min_points: int = DEFAULT_MIN_POINTS,
                 win: int = DEFAULT_WIN, max_mad: float = DEFAULT_MAX_MAD) -> None:
        self._grid = max(2, int(grid))
        self._min_points = max(1, int(min_points))
        self._win = int(win)
        self._max_mad = float(max_mad)
        self._prev_gray = None
        self._prev_bbox = None
        self._points = None

    # ------------------------------------------------------------------ API

    def reset(self, gray, bbox) -> None:
        """Đặt lại mốc theo dõi tại frame hiện tại với ô bao (x, y, w, h)."""
        self._prev_gray = gray
        self._prev_bbox = tuple(int(v) for v in bbox)
        self._points = self._seed(self._prev_bbox, gray.shape)

    def update(self, gray):
        """Ước lượng ô bao mới. Trả (bbox, True) hoặc (None, False) khi mất dấu."""
        if self._prev_gray is None or self._points is None or self._prev_bbox is None:
            return None, False
        if self._points.size == 0:
            return None, False

        moved, status, _err = cv2.calcOpticalFlowPyrLK(
            self._prev_gray, gray, self._points, None,
            winSize=(self._win, self._win), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
        )
        if moved is None or status is None:
            return None, False

        keep = status.reshape(-1) == 1
        if int(keep.sum()) < self._min_points:
            return None, False

        delta = (moved.reshape(-1, 2)[keep] - self._points.reshape(-1, 2)[keep])
        # TRUNG VỊ chứ không trung bình: vài điểm trôi theo nền không được kéo cả ô bao đi
        dx = float(np.median(delta[:, 0]))
        dy = float(np.median(delta[:, 1]))

        # Kiểm tra ĐỘ TẢN: LK luôn trả về một vector cho mỗi điểm, kể cả khi vật đã biến mất
        # (nó khớp với nhiễu). Vector dịch thật thì rất đồng nhất; khớp nhiễu thì tản mát.
        # Không có chốt này, tracker sẽ "bám" vào nền và báo ô bao sai — tệ hơn là báo mất dấu.
        mad_x = float(np.median(np.abs(delta[:, 0] - dx)))
        mad_y = float(np.median(np.abs(delta[:, 1] - dy)))
        if max(mad_x, mad_y) > self._max_mad:
            return None, False

        x, y, w, h = self._prev_bbox
        bbox = (int(round(x + dx)), int(round(y + dy)), int(w), int(h))
        self.reset(gray, bbox)          # gieo lại điểm trong ô mới → không tích luỹ sai số
        return bbox, True

    # ------------------------------------------------------------------ nội bộ

    def _seed(self, bbox, shape):
        """Sinh lưới điểm bên trong ô bao (bỏ 10% viền để điểm không rơi ra nền)."""
        x, y, w, h = bbox
        height, width = shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(width - 1, x + w), min(height - 1, y + h)
        if x1 - x0 < 4 or y1 - y0 < 4:
            return np.empty((0, 1, 2), np.float32)

        margin_x = max(1, int((x1 - x0) * 0.1))
        margin_y = max(1, int((y1 - y0) * 0.1))
        xs = np.linspace(x0 + margin_x, x1 - margin_x, self._grid)
        ys = np.linspace(y0 + margin_y, y1 - margin_y, self._grid)
        grid = np.array([[px, py] for py in ys for px in xs], dtype=np.float32)
        return grid.reshape(-1, 1, 2)


def shift_mask(mask, dx: int, dy: int):
    """Dịch mask theo (dx, dy) — dùng để mask VOS cũ bám theo ô bao LK giữa hai lần suy luận.

    Input : mask (H, W) bool/uint8; dx, dy (int, pixel).
    Output: mask bool cùng kích thước (phần ra ngoài khung bị cắt).
    Lưu ý : tịnh tiến thuần (warpAffine) — không xoay/co giãn, đúng với giả định của LK.
    """
    if dx == 0 and dy == 0:
        return mask
    source = np.ascontiguousarray(mask.astype(np.uint8))
    matrix = np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32)
    height, width = source.shape[:2]
    moved = cv2.warpAffine(source, matrix, (width, height), flags=cv2.INTER_NEAREST)
    return moved.astype(bool)
