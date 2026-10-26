"""Test module đặc trưng vật thể (ticket 10) — hàm thuần, KHÔNG cần model/checkpoint.

Seam test (giao diện công khai của `src/appearance.py`):
  - `object_signature(frame, mask)`  → vector đặc trưng (hoặc None khi mask rỗng)
  - `signature_quality_ok(bbox, mask)` → cổng chất lượng (to nhỏ + tỉ lệ mask)
  - `candidate_boxes(frame_shape, size)` → danh sách ô ứng viên khi mất dấu
  - `mask_to_bbox(mask)` → ô bao của mask

Nguồn số kỳ vọng (nguồn độc lập, KHÔNG tính lại bằng code đang test):
  - "Cùng vật ≥ 0,9" / "khác màu < 0,6" lấy từ đo thật trên fixture tổng hợp ở
    `docs/research/06` §4.2: covariance tách "khác màu" = 0,166; HSV hist "khác màu" = 0,382;
    cùng vật dịch vài pixel ≈ 1,0.
  - Hàm IoU dưới đây viết tay trong test, không import từ `src`.
"""
import numpy as np

from src.appearance import (
    candidate_boxes,
    mask_to_bbox,
    object_signature,
    signature_quality_ok,
)

ORANGE = (0, 140, 255)   # BGR — "vật" cam
BLUE = (200, 90, 20)     # BGR — vật khác màu
BG = (35, 37, 32)        # nền tối
SHAPE = (480, 640)


def _frame(box, color=ORANGE):
    """Frame nền tối + một ô màu đặc tại `box`."""
    f = np.full((SHAPE[0], SHAPE[1], 3), BG, np.uint8)
    x1, y1, x2, y2 = box
    f[y1:y2, x1:x2] = color
    return f


def _striped_frame(box, color=ORANGE):
    """Frame có ô kẻ sọc — dùng cho ca 'cùng màu nhưng khác hoa văn'."""
    f = _frame(box, color)
    x1, y1, x2, y2 = box
    for x in range(x1, x2, 12):
        f[y1:y2, x:x + 5] = (255, 255, 255)
    return f


def _mask(box):
    m = np.zeros(SHAPE, np.uint8)
    x1, y1, x2, y2 = box
    m[y1:y2, x1:x2] = 255
    return m


def _cos(a, b):
    a = np.asarray(a, np.float64).ravel()
    b = np.asarray(b, np.float64).ravel()
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def _iou(a, b):
    """IoU viết tay trong test (nguồn độc lập với code đang test)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


BOX = (60, 60, 160, 160)          # vật 100x100


class TestMaskToBbox:
    def test_bbox_dung_bien_mask(self):
        assert mask_to_bbox(_mask(BOX)) == BOX

    def test_mask_rong_tra_none(self):
        assert mask_to_bbox(np.zeros(SHAPE, np.uint8)) is None


class TestObjectSignature:
    def test_tat_dinh_voi_cung_dau_vao(self):
        sig1 = object_signature(_striped_frame(BOX), _mask(BOX))
        sig2 = object_signature(_striped_frame(BOX), _mask(BOX))
        assert np.array_equal(sig1, sig2)

    def test_vector_chuan_hoa_l2_bang_1(self):
        sig = object_signature(_striped_frame(BOX), _mask(BOX))
        assert abs(float(np.linalg.norm(sig)) - 1.0) < 1e-6

    def test_mask_rong_tra_none(self):
        assert object_signature(_frame(BOX), np.zeros(SHAPE, np.uint8)) is None

    def test_cung_vat_dich_nhe_cosine_cao(self):
        """Vật chỉ dịch 3 pixel → phải gần như trùng (ngưỡng 0,9 lấy từ đo thật §4.2)."""
        sig_a = object_signature(_striped_frame(BOX), _mask(BOX))
        moved = (63, 66, 163, 166)
        sig_b = object_signature(_striped_frame(moved), _mask(moved))
        assert _cos(sig_a, sig_b) >= 0.9

    def test_khac_mau_cosine_thap(self):
        """Cùng hình, khác màu → cosine phải dưới 0,6 (đo: 0,166–0,382 với từng khối riêng)."""
        sig_a = object_signature(_frame(BOX, ORANGE), _mask(BOX))
        sig_b = object_signature(_frame(BOX, BLUE), _mask(BOX))
        assert _cos(sig_a, sig_b) < 0.6

    def test_cung_mau_khac_hoa_van_thap_hon_truong_hop_giong_nhau(self):
        """Cùng màu nhưng 'trơn' vs 'có sọc' phải tách được — đây là ca HSV hist một mình bó tay."""
        base = object_signature(_striped_frame(BOX), _mask(BOX))
        plain = object_signature(_frame(BOX, ORANGE), _mask(BOX))
        assert _cos(base, plain) < 0.95


class TestSignatureQuality:
    def test_o_du_lon_va_mask_day_du_thi_dat(self):
        assert signature_quality_ok(BOX, _mask(BOX)) is True

    def test_o_qua_nho_bi_loai(self):
        small = (10, 10, 25, 25)
        assert signature_quality_ok(small, _mask(small)) is False

    def test_mask_bi_che_gan_het_bi_loai(self):
        """Che 90% diện tích ô → không đủ tin để làm mẫu tham chiếu."""
        m = np.zeros(SHAPE, np.uint8)
        m[60:160, 60:70] = 255          # chỉ 10/100 cột còn thấy
        assert signature_quality_ok(BOX, m) is False


class TestCandidateBoxes:
    def test_co_o_phu_dung_vat(self):
        """Quét lưới phải có ít nhất một ô chồng lên vị trí thật (IoU ≥ 0,5)."""
        boxes = candidate_boxes(SHAPE, (100, 100), stride_frac=0.5, scales=(1.0,))
        assert max(_iou(b, BOX) for b in boxes) >= 0.5

    def test_moi_o_nam_trong_khung(self):
        boxes = candidate_boxes(SHAPE, (100, 100), stride_frac=0.5, scales=(0.75, 1.0, 1.5))
        assert len(boxes) > 0
        for x1, y1, x2, y2 in boxes:
            assert 0 <= x1 < x2 <= SHAPE[1]
            assert 0 <= y1 < y2 <= SHAPE[0]

    def test_co_du_cac_ti_le_yeu_cau(self):
        boxes = candidate_boxes(SHAPE, (100, 100), stride_frac=0.5, scales=(0.75, 1.0, 1.5))
        widths = {x2 - x1 for x1, _, x2, _ in boxes}
        assert {75, 100, 150} <= widths
