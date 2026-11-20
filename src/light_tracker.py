"""
LK tracker nhẹ — nội suy ô bao giữa các lần chạy VOS (giây phút model "nghỉ").

Chức năng: theo dõi dịch chuyển của đối tượng bằng `cv2.calcOpticalFlowPyrLK` trên lưới điểm
           trong ô bao; lấy **trung vị** độ dịch (bền với điểm nhiễu) rồi tịnh tiến ô bao.
Input  : frame xám (gray) hiện tại; ô bao ban đầu (x, y, w, h).
Output : ô bao mới (x, y, w, h) hoặc None khi không đủ điểm theo dõi (vật bị che/mất).
Lưu ý  : LK mặc định chỉ **tịnh tiến** — không bắt được xoay/co giãn; vì vậy nó KHÔNG thay VOS, chỉ lấp
         các frame giữa hai lần suy luận. Số đo trên máy này: 2,22 ms (rảnh) / 3,19 ms (dưới tải)
         — `docs/research/09`. Không import torch.
         Từ 20-11 có chế độ `scale=True` (tùy chọn): khớp **similarity** (dịch + tỉ lệ + xoay) trên
         chính lưới điểm đó. Lý do: đo trên GT người tô cho thấy ô hiển thị lệch kích thước tới
         −132 px, mà tịnh tiến **không thể** chữa lệch kích thước (`docs/task/20-11-2026-cai-gia-do-
         chinh-xac-cua-hybrid.md`). Mặc định vẫn TẮT để không đổi số đã công bố.
"""

import numpy as np

import cv2

# Tham số LK — giữ mặc định của OpenCV cho ổn định, chỉ chỉnh lưới điểm
DEFAULT_GRID = 8          # số điểm mỗi chiều trong ô bao (8×8 = 64 điểm)
DEFAULT_MIN_POINTS = 6   # dưới ngưỡng này coi như mất dấu (không đủ điểm để tin)
DEFAULT_WIN = 21          # cửa sổ tìm kiếm (px)
DEFAULT_MAX_MAD = 1.5     # độ tản (px) tối đa của vector dịch; lớn hơn ⇒ coi là mất dấu
# Chế độ `scale=True`: giới hạn DÙNG ĐƯỢC của tỉ lệ/xoay trong MỘT bước LK (giữa hai frame). Vượt
# ngưỡng ⇒ coi như khớp nhiễu và quay về tịnh tiến thuần (không bịa co giãn). Hai frame liên tiếp
# cách nhau ~33 ms nên tỉ lệ thật hiếm khi ra ngoài ±25 %; cửa hẹp để chặn "LK bám nền rồi phóng ô".
DEFAULT_SCALE_MIN = 0.80
DEFAULT_SCALE_MAX = 1.25
DEFAULT_MAX_ANGLE_DEG = 15.0


class LkBoxTracker:
    """Theo dõi ô bao bằng optical flow thưa (Lucas–Kanade).

    `scale=False` (mặc định): chỉ **tịnh tiến** (hành vi cũ, số đo cũ giữ nguyên).
    `scale=True`: khớp similarity (dịch + tỉ lệ + xoay) trên cùng lưới điểm; tỉ lệ/góc bị **cổng**
    (`scale_min/scale_max/max_angle_deg`) — ra ngoài cổng thì quay về tịnh tiến thuần chứ không bịa.
    """

    def __init__(self, *, grid: int = DEFAULT_GRID, min_points: int = DEFAULT_MIN_POINTS,
                 win: int = DEFAULT_WIN, max_mad: float = DEFAULT_MAX_MAD,
                 scale: bool = False, scale_min: float = DEFAULT_SCALE_MIN,
                 scale_max: float = DEFAULT_SCALE_MAX,
                 max_angle_deg: float = DEFAULT_MAX_ANGLE_DEG) -> None:
        self._grid = max(2, int(grid))
        self._min_points = max(1, int(min_points))
        self._win = int(win)
        self._max_mad = float(max_mad)
        self._scale = bool(scale)
        self._scale_min = float(scale_min)
        self._scale_max = float(scale_max)
        self._max_angle = float(max_angle_deg)
        self._prev_gray = None
        self._prev_bbox = None
        self._points = None
        # Chẩn đoán cho phép đo: bước gần nhất có dùng similarity không, tỉ lệ/góc nó ước lượng được.
        # Có mặt để artifact/CSV giải thích được vì sao ô bao đổi kích thước, không phải để điều khiển.
        self.last_scale: float = 1.0
        self.last_angle_deg: float = 0.0
        self.last_khop_similarity: bool = False
        # Ma trận 2×3 đã DÙNG để biến đổi mốc→frame hiện tại (tịnh tiến: `[[1,0,dx],[0,1,dy]]`).
        # Có mặt để mask cũ được biến đổi CÙNG phép với ô bao — nếu chỉ dịch mask khi ô bao co giãn
        # thì mask và ô bao lệch nhau ngay trên hình người xem.
        self.last_matrix = None
        # LÝ DO của bước gần nhất — cần cho việc ĐO: không có nó thì "LK từ chối" không phân biệt được
        # "cổng mad chặn" với "gieo điểm rỗng" / "không đủ điểm" (review #65 vòng 3: một frame không có
        # ô hiển thị bị hiểu sai thành "LK mất dấu" khi thực ra `_seed` rỗng vì bbox VOS suy biến).
        self.last_ly_do = "chua_chay"

    # ------------------------------------------------------------------ API

    def reset(self, gray, bbox) -> None:
        """Đặt lại mốc theo dõi tại frame hiện tại với ô bao (x, y, w, h)."""
        self._prev_gray = gray
        self._prev_bbox = tuple(int(v) for v in bbox)
        self._points = self._seed(self._prev_bbox, gray.shape)

    def update(self, gray):
        """Ước lượng ô bao mới. Trả (bbox, True) hoặc (None, False) khi mất dấu."""
        # Chẩn đoán phải reset ở ĐẦU mỗi bước: trước đây chỉ reset sau khi đã có ≥ `min_points`, nên các
        # `return None, False` sớm (mất dấu) để lại `last_khop_similarity = True` của bước TRƯỚC ⇒ đọc
        # CSV hiểu sai bước vừa rồi đã dùng similarity (P3 review #65 vòng 2).
        self.last_scale, self.last_angle_deg, self.last_khop_similarity = 1.0, 0.0, False
        if self._prev_gray is None or self._points is None or self._prev_bbox is None:
            self.last_ly_do = "chua_reset"
            return None, False
        if self._points.size == 0:
            self.last_ly_do = "seed_rong"          # ô < 4 px (vd bbox VOS suy biến) ⇒ LK CHƯA chạy
            return None, False

        moved, status, _err = cv2.calcOpticalFlowPyrLK(
            self._prev_gray, gray, self._points, None,
            winSize=(self._win, self._win), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
        )
        if moved is None or status is None:
            self.last_ly_do = "lk_hong"
            return None, False

        keep = status.reshape(-1) == 1
        if int(keep.sum()) < self._min_points:
            self.last_ly_do = "thieu_diem"
            return None, False

        prev = self._points.reshape(-1, 2)[keep]
        moved_ok = moved.reshape(-1, 2)[keep]
        delta = moved_ok - prev
        # TRUNG VỊ chứ không trung bình: vài điểm trôi theo nền không được kéo cả ô bao đi
        dx = float(np.median(delta[:, 0]))
        dy = float(np.median(delta[:, 1]))

        # Kiểm tra ĐỘ TẢN: LK luôn trả về một vector cho mỗi điểm, kể cả khi vật đã biến mất
        # (nó khớp với nhiễu). Vector dịch thật thì rất đồng nhất; khớp nhiễu thì tản mát.
        # Không có chốt này, tracker sẽ "bám" vào nền và báo ô bao sai — tệ hơn là báo mất dấu.
        #
        # Ở chế độ `scale=True`, độ tản phải đo trên **PHẦN DƯ của mô hình similarity**, không phải
        # trên vector dịch thô: vật co giãn thì trường dịch KHÔNG đều (điểm giữa gần như đứng yên,
        # điểm rìa đi ra) nên đo thô sẽ chặn đúng chuyển động thật. Đo trên phần dư trả lời đúng câu
        # hỏi "mô hình có giải thích được chuyển động không". (Lần chạy thử 20-11: đo thô ⇒ mọi ca
        # phóng to/thu nhỏ/xoay đều `ok=False`.)
        if self._scale:
            khop = self._khop_similarity(prev, moved_ok)
            matrix = khop[0] if khop else None
            if matrix is not None:
                du = moved_ok - self._ap_dung(matrix, prev)
                mad_du = max(float(np.median(np.abs(du[:, 0] - np.median(du[:, 0])))),
                             float(np.median(np.abs(du[:, 1] - np.median(du[:, 1])))))
                if mad_du > self._max_mad:
                    self.last_ly_do = "mad_du"
                    return None, False
                bbox = self._bbox_tu_matrix(matrix, gray.shape)
                if bbox is not None:
                    # Chỉ ghi chẩn đoán khi phép similarity THẬT SỰ được dùng: trước đây gán trong
                    # `_khop_similarity` nên ca "khớp qua cổng nhưng bbox bị từ chối" để lại
                    # `last_scale = 1.6` cho một bước ĐI TỊNH TIẾN ⇒ đọc chẩn đoán bị sai (P3 review #65).
                    self.last_scale, self.last_angle_deg = khop[1], khop[2]
                    self.last_khop_similarity = True
                    self.last_matrix = matrix
                    self.last_ly_do = "ok_scale"
                    self.reset(gray, bbox)    # gieo lại điểm → không tích luỹ sai số
                    return bbox, True
            # Không dùng được similarity (cổng tỉ lệ/góc chặn, hoặc bbox suy ra hỏng) ⇒ rơi về tịnh
            # tiến, vẫn kiểm tản thô. `last_ly_do` phân biệt được ba ca: cổng, bbox, và cổng mad.
        mad_x = float(np.median(np.abs(delta[:, 0] - dx)))
        mad_y = float(np.median(np.abs(delta[:, 1] - dy)))
        if max(mad_x, mad_y) > self._max_mad:
            self.last_ly_do = "mad_du"
            return None, False

        x, y, w, h = self._prev_bbox
        bbox = (int(round(x + dx)), int(round(y + dy)), int(w), int(h))
        self.last_matrix = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy]], np.float32)
        self.last_ly_do = "ok_shift"
        self.reset(gray, bbox)          # gieo lại điểm trong ô mới → không tích luỹ sai số
        return bbox, True

    # ------------------------------------------------------------------ nội bộ

    @staticmethod
    def _ap_dung(matrix, points):
        """Áp affine 2×3 lên mảng (N, 2)."""
        return points @ matrix[:, :2].T + matrix[:, 2]

    def _khop_similarity(self, prev, moved):
        """Khớp similarity (dịch + tỉ lệ + xoay) giữa hai lưới điểm.

        Trả `(matrix, ti_le, goc)` khi dùng được, `None` khi cổng chặn. KHÔNG ghi `last_scale` ở đây:
        bước chỉ "dùng similarity" nếu bbox suy ra cũng được chấp nhận (xem `update`).

        Cổng an toàn (ra ngoài ⇒ `None` ⇒ rơi về tịnh tiến, KHÔNG bịa co giãn):
          - ít hơn `min_points` điểm;
          - tỉ lệ ngoài `[scale_min, scale_max]`;
          - |góc| > `max_angle_deg`.
        Tỉ lệ thật giữa hai frame liên tiếp (~33 ms) hiếm khi ra ngoài ±25 %; cửa hẹp để chặn ca
        "LK bám nền rồi phóng to ô bao".
        """
        if len(prev) < self._min_points:
            return None
        matrix, _inliers = cv2.estimateAffinePartial2D(
            prev.astype(np.float32), moved.astype(np.float32), method=cv2.LMEDS)
        if matrix is None:
            return None
        a, b = float(matrix[0, 0]), float(matrix[1, 0])     # cột 1 = ảnh của (1, 0) ⇒ (a, b)
        ti_le = float(np.hypot(a, b))
        goc = float(np.degrees(np.arctan2(b, a)))
        if not (self._scale_min <= ti_le <= self._scale_max) or abs(goc) > self._max_angle:
            return None
        return matrix, ti_le, goc

    def _bbox_tu_matrix(self, matrix, shape):
        """Ô bao bao ngoài 4 góc ĐÃ biến đổi. `None` nếu ra khỏi giới hạn dùng được."""
        x, y, w, h = self._prev_bbox
        goc = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], np.float32)
        bien = self._ap_dung(matrix, goc)
        chieu_cao, chieu_rong = shape[:2]
        x1, y1 = float(bien[:, 0].min()), float(bien[:, 1].min())
        x2, y2 = float(bien[:, 0].max()), float(bien[:, 1].max())
        # Cắt vào khung: ô ra ngoài khung thì `warp`/chấm IoU sẽ méo; kẹp về [0, kích thước - 1].
        x1, x2 = max(0.0, min(x1, chieu_rong - 1)), max(0.0, min(x2, chieu_rong - 1))
        y1, y2 = max(0.0, min(y1, chieu_cao - 1)), max(0.0, min(y2, chieu_cao - 1))
        rong_moi, cao_moi = x2 - x1, y2 - y1
        if rong_moi < 4 or cao_moi < 4:
            return None
        return (int(round(x1)), int(round(y1)), int(round(rong_moi)), int(round(cao_moi)))

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


def warp_mask(mask, matrix):
    """Biến đổi mask bằng ma trận affine 2×3 (`LkBoxTracker.last_matrix`). Mask bool giữ bool.

    Dùng cho chế độ `scale=True`: mask cũ phải co giãn/xoay **cùng phép** với ô bao, nếu không thì
    mask và ô bao lệch nhau ngay trên hình. `INTER_NEAREST` để mask vẫn là 0/1.
    """
    if matrix is None:
        return mask
    if (np.allclose(matrix[:, :2], np.eye(2)) and np.allclose(matrix[:, 2], 0)):
        return mask
    source = np.ascontiguousarray(mask.astype(np.uint8))
    height, width = source.shape[:2]
    moved = cv2.warpAffine(source, np.asarray(matrix, np.float32), (width, height),
                           flags=cv2.INTER_NEAREST)
    return moved.astype(bool)


def shift_mask(mask, dx: int, dy: int):
    """Dịch mask theo (dx, dy) — dùng để mask VOS cũ bám theo ô bao LK giữa hai lần suy luận.

    Input : mask (H, W) bool/uint8; dx, dy (int, pixel).
    Output: mask bool cùng kích thước (phần ra ngoài khung bị cắt).
    Lưu ý : tịnh tiến thuần — vẫn giữ cho tương thích; chế độ `scale=True` dùng `warp_mask`.
    """
    if dx == 0 and dy == 0:
        return mask
    return warp_mask(mask, np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32))
