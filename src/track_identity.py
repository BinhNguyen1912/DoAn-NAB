"""Cổng DANH TÍNH cho vùng đang bám — dùng CHUNG cho đường CLI (`src/reid.py`) và đường web
(`src/live_tracking.py`), vì đường web **không có re-ID** (nên mọi thứ nằm trong `reid.py` là
"cổng mù trên sân khấu web"; plan 21-11-2026 §Tranh chấp).

Vì sao cần: phiên thật 21-11 (`data/demoip_1121-103854_*`) bám **remote máy lạnh TRẮNG** trên nền
**tường be + máy lạnh trắng**; ô trượt sang **máy lạnh ~9 s** (f110–f173) mà **không cổng nào kêu**:

- `score` (object_score_logits) **TĂNG** lên 5,85–6,02 khi bám máy lạnh — cao nhất phiên ⇒ lọc theo
  score là sai chiều.
- cú nhảy f109→f110 = **114 px**, trong khi `identity_guard.is_suspect_switch` cần **200 px** và
  `reid._is_suspicious_jump` cần **451 px** (1,5 × đường chéo ô 301 px) ⇒ cả hai im lặng.

**PR-1 là LOG-ONLY**: module này chỉ ĐO (`cos` giữa mask đang bám và 3–5 mẫu neo đầu tiên) và trả
`cos` để ghi ra CSV/`status.json`. Nó **không** đổi trạng thái, không ẩn ô, không reset engine. Việc
chốt ngưỡng θ phải dựa trên phân bố đo được (≥200 mẫu/clip), không phải đoán — xem plan §Quyết định.

Tại sao NEO chứ không phải bộ nhớ cuốn: `ReIdSession._collect_reference` append một mẫu **mỗi frame
TRACKING** (`src/reid.py:478`) vào `deque(maxlen=8)` ⇒ chỉ **8 frame (~0,4 s)** là "ký ức" đã là khung
cửa/máy lạnh; chấm `cos` với bộ nhớ đó sẽ nói "vẫn đúng" trong khi đang bám sai. Neo lấy từ **mask**
(không phải bbox: bbox chứa nền) của những frame đầu, qua `signature_quality_ok`.

Fail-open 2 lớp (để không bao giờ giết phiên demo):
1. < `MIN_ANCHORS` neo ⇒ `cos = None` (ghi ô trống = "chưa đo", KHÔNG phải 0).
2. Không chấm được (mask rỗng/None/lỗi) ⇒ `None`, không ném.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from src.appearance import mask_to_bbox, object_signature, signature_quality_ok

# Số mẫu neo. 3 là mức tối thiểu để `best_match` (lấy max) không bị MỘT mẫu hỏng làm pass-giả;
# 5 là mức trần để neo vẫn là "vật lúc chọn" chứ không trôi theo vật.
MIN_ANCHORS = 2
MAX_ANCHORS = 5


class NeoDanhTinh:
    """3–5 đặc trưng NEO của vùng được chọn lúc đầu + `cos` của vùng đang bám so với neo.

    Dùng:
        neo = NeoDanhTinh()
        neo.thu(frame, mask)          # mỗi frame đầu, tự lọc qua signature_quality_ok
        c = neo.cos(frame, mask)      # mỗi frame TRACKING; None = chưa đo được
    """

    def __init__(self, min_anchors: int = MIN_ANCHORS, max_anchors: int = MAX_ANCHORS):
        self.min_anchors = max(1, int(min_anchors))
        self.max_anchors = max(self.min_anchors, int(max_anchors))
        self._refs: deque = deque(maxlen=self.max_anchors)
        self.n_cham = 0            # số lần đã chấm cos (để báo "chưa đo" ≠ "đo được 0")
        self.n_none = 0            # số lần không chấm được (mask rỗng/None)

    # -- nạp neo --
    def thu(self, frame, mask, bbox=None) -> bool:
        """Thử lưu 1 mẫu neo từ MASK. Trả True nếu đã lưu.

        Lọc bằng `signature_quality_ok` (diện tích + tỉ lệ mask/ô + không phải ô rác) — cùng cổng
        với `_collect_reference`, để neo không nhận mẫu rác sát mép khung.
        """
        if frame is None or mask is None or not np.any(mask):
            return False
        if len(self._refs) >= self.max_anchors:
            return False
        box = bbox if bbox is not None else mask_to_bbox(mask)
        if box is None:
            return False
        if not signature_quality_ok(box, mask):
            return False
        sig = object_signature(frame, mask)
        if sig is None:
            return False
        self._refs.append(sig)
        return True

    # -- chấm --
    @property
    def co_neo(self) -> bool:
        """Đã đủ neo để chấm chưa (fail-open: chưa đủ ⇒ không chấm, không báo)."""
        return len(self._refs) >= self.min_anchors

    def cos(self, frame, mask) -> Optional[float]:
        """`cos` LỚN NHẤT giữa mask đang bám và các neo; `None` = chưa đo được.

        `None` KHÔNG được ghi thành 0: "chưa đo" và "đo được 0" là hai chuyện khác nhau (AGENTS §6).
        """
        self.n_cham += 1
        if not self.co_neo or frame is None or mask is None or not np.any(mask):
            self.n_none += 1
            return None
        sig = object_signature(frame, mask)
        if sig is None:
            self.n_none += 1
            return None
        # Cố ý KHÔNG import `reid.best_match`: `src/reid.py` import module này ⇒ sẽ thành import
        # VÒNG (đã suýt gặp). `object_signature` đã chuẩn hoá L2 nên cosine = tích vô hướng; lấy max
        # như `best_match`. Test `test_track_identity.py` khoá hai cách tính cho cùng kết quả.
        return float(max(float(np.dot(ref, sig)) for ref in self._refs))

    def xoa(self) -> None:
        """Quên neo (khi người dùng chọn lại đối tượng). Bộ đếm **giữ nguyên** để tổng hợp phiên."""
        self._refs.clear()


def cos_voi_neo(neo: Optional[NeoDanhTinh], frame, mask) -> Optional[float]:
    """Gọi an toàn: `neo=None` hoặc neo lỗi ⇒ `None` (không ném)."""
    if neo is None:
        return None
    try:
        return neo.cos(frame, mask)
    except Exception:            # fail-open: đo đạc không được giết phiên
        return None


def dem_neo(neo: Optional[NeoDanhTinh]) -> int:
    """Số neo hiện có (ghi vào status/CSV để biết cổng có hiệu lực hay không)."""
    return len(getattr(neo, "_refs", ()) or ()) if neo is not None else 0


__all__ = ["NeoDanhTinh", "cos_voi_neo", "dem_neo", "MIN_ANCHORS", "MAX_ANCHORS"]
