"""
Bộ lọc mask theo thời gian — giảm NHẤP NHÁY giữa các lần suy luận VOS.

Chức năng: trộn mask mới với mask cũ (EMA trên mặt nạ nhị phân) để đường bao không "giật" khi
           model trả về mask hơi khác ở mỗi lần; dịch bộ tích luỹ theo độ dịch ô bao trước mỗi lần
           trộn (nhờ vậy vật đang di chuyển không bị bóng mờ ở vị trí cũ).
Input  : mask bool (H, W) cho mỗi lần VOS; độ dịch (dx, dy) của ô bao giữa hai lần đó.
Output : mask bool (H, W) đã làm mượt (`acc ≥ 0,5`) để vẽ.
Lưu ý  : KHÔNG import torch. Đây là hậu xử lý hiển thị, **không** đổi vị trí đối tượng cũng như
         không thay VOS: nếu mask mới mất hẳn, bộ lọc chỉ giữ được ~1/alpha lần cập nhật rồi tắt.
         Đo trên máy này: chi phí ~2–4 ms cho 1280×720 (xem docs/task/10-11-2026-*).
"""

import numpy as np

import cv2


class MaskSmoother:
    """Giữ mask khi model "chớp" mất vật + EMA làm mượt đường bao.

    Hai cơ chế, cố ý tách rời để giải thích được trong báo cáo:
    1. **Giữ (hold)**: mask mới teo dưới `hold_ratio` diện tích mask đang hiển thị ⇒ coi là một lần
       "chớp" của model, giữ mask cũ (đã dịch theo ô bao). Giữ tối đa `max_hold` lần liên tiếp —
       quá số đó thì đó là **mất dấu thật**, phải tắt (không được giữ bóng ma).
    2. **EMA**: `acc = alpha*mới + (1-alpha)*cũ`, hiển thị `acc ≥ 0,5` — làm mượt đường bao.
    """

    def __init__(self, alpha: float = 0.6, hold_ratio: float = 0.4, max_hold: int = 2) -> None:
        if not 0.0 < float(alpha) <= 1.0:
            raise ValueError("alpha phải trong khoảng (0, 1]")
        self._alpha = float(alpha)
        self._hold_ratio = float(hold_ratio)
        self._max_hold = max(0, int(max_hold))
        self._hold = 0
        self._acc = None
        self._holds = 0      # số lần đã GIỮ mask cũ vì model "chớp"
        self._drops = 0      # số lần trả mask RỖNG (mất dấu thật)

    @property
    def alpha(self) -> float:
        return self._alpha

    @property
    def holds(self) -> int:
        """Số lần đã giữ mask cũ thay vì để nó chớp tắt."""
        return self._holds

    @property
    def drops(self) -> int:
        """Số lần mask hiển thị rỗng (mất dấu thật)."""
        return self._drops

    def reset(self) -> None:
        self._acc = None
        self._hold = 0

    def shift(self, dx: int, dy: int) -> None:
        """Dịch bộ tích luỹ theo chuyển động của đối tượng trước khi trộn mask mới."""
        if self._acc is None or (dx == 0 and dy == 0):
            return
        matrix = np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32)
        height, width = self._acc.shape[:2]
        self._acc = cv2.warpAffine(self._acc, matrix, (width, height),
                                   flags=cv2.INTER_NEAREST)

    def update(self, mask):
        """Nhận mask mới của VOS; trả mask bool để vẽ (đã giữ/làm mượt)."""
        if mask is None:
            return None
        current = mask.astype(np.float32)
        if self._acc is None or self._acc.shape != current.shape:
            self._acc = current
            self._hold = 0
            return self._acc >= 0.5

        shown = self._acc >= 0.5
        shown_area = float(np.count_nonzero(shown))
        new_area = float(np.count_nonzero(current))
        if shown_area > 0 and new_area < self._hold_ratio * shown_area:
            self._hold += 1
            if self._hold <= self._max_hold:
                self._holds += 1
                return shown.copy()          # giữ mask cũ: model "chớp", chưa phải mất dấu thật
            self._acc = current              # quá max_hold ⇒ mất dấu THẬT, chấp nhận mask rỗng
            self._hold = 0
            self._drops += 1
            return self._acc >= 0.5

        self._hold = 0
        self._acc = self._alpha * current + (1.0 - self._alpha) * self._acc
        return self._acc >= 0.5


def mask_iou(a, b) -> float:
    """IoU của hai mask bool — 1,0 = giống hệt, 0,0 = không giao nhau (đo độ ổn định)."""
    if a is None or b is None:
        return 0.0
    first = np.asarray(a, bool)
    second = np.asarray(b, bool)
    union = np.count_nonzero(first | second)
    if union == 0:
        return 1.0            # cả hai đều rỗng → coi như khớp (không có gì để lệch)
    return float(np.count_nonzero(first & second)) / float(union)
