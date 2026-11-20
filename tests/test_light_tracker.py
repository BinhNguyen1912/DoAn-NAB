"""Test LK tracker (`src/light_tracker.py`) — không cần model, dùng frame tổng hợp."""

import time

import cv2
import numpy as np
import pytest

from src.light_tracker import LkBoxTracker, shift_mask


def _frame_with_square(offset_x, offset_y, size=(120, 160), side=30):
    """Ảnh xám: nền nhiễu nhẹ + hình vuông sáng ở (offset) — để LK có texture mà bám."""
    rng = np.random.default_rng(7)
    frame = rng.integers(40, 60, size=size, dtype=np.uint8)
    x, y = 20 + offset_x, 20 + offset_y
    frame[y:y + side, x:x + side] = 220
    return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)


class TestLkBoxTracker:
    def test_bam_dung_do_dich_theo_truc_x(self):
        tracker = LkBoxTracker()
        first = _frame_with_square(0, 0)
        tracker.reset(cv2.cvtColor(first, cv2.COLOR_BGR2GRAY), (20, 20, 30, 30))

        bbox = None
        for step in range(1, 6):                 # dịch 3 px/frame
            gray = cv2.cvtColor(_frame_with_square(3 * step, 0), cv2.COLOR_BGR2GRAY)
            bbox, ok = tracker.update(gray)
            assert ok, f"mất dấu ở bước {step}"

        # literal tính tay: 5 bước × 3 px = 15 px
        assert abs(bbox[0] - (20 + 15)) <= 2
        assert abs(bbox[1] - 20) <= 2
        assert bbox[2] == 30 and bbox[3] == 30     # LK chỉ TỊNH TIẾN, không đổi kích thước

    def test_bam_dung_do_dich_theo_truc_y(self):
        tracker = LkBoxTracker()
        tracker.reset(cv2.cvtColor(_frame_with_square(0, 0), cv2.COLOR_BGR2GRAY), (20, 20, 30, 30))

        for step in range(1, 5):                 # dịch 2 px/frame
            gray = cv2.cvtColor(_frame_with_square(0, 2 * step), cv2.COLOR_BGR2GRAY)
            bbox, ok = tracker.update(gray)

        assert ok
        assert abs(bbox[1] - (20 + 8)) <= 2

    def test_chua_reset_thi_tra_false(self):
        tracker = LkBoxTracker()
        bbox, ok = tracker.update(np.zeros((48, 64), np.uint8))
        assert (bbox, ok) == (None, False)

    def test_khung_hinh_qua_nho_khong_gieo_duoc_diem(self):
        tracker = LkBoxTracker()
        tracker.reset(np.zeros((48, 64), np.uint8), (10, 10, 2, 2))
        assert tracker.update(np.zeros((48, 64), np.uint8)) == (None, False)

    def test_khong_theo_duoc_khi_frame_sau_doi_hoan_toan(self):
        """Nhiễu ngẫu nhiên hoàn toàn → không đủ điểm tin cậy, phải báo mất dấu (không bịa)."""
        tracker = LkBoxTracker()          # tham số mặc định: chốt chặn là độ tản, không phải số điểm
        rng = np.random.default_rng(3)
        tracker.reset(rng.integers(0, 255, (120, 160), dtype=np.uint8), (20, 20, 30, 30))

        noisy = rng.integers(0, 255, (120, 160), dtype=np.uint8)
        bbox, ok = tracker.update(noisy)
        assert ok is False
        assert bbox is None

    def test_chi_phi_duoi_nguong_33ms(self):
        """LK phải RẺ (mục tiêu < 10 ms/frame trên ảnh 160×120) để dùng 30 FPS."""
        tracker = LkBoxTracker()
        frames = [_frame_with_square(step, 0) for step in range(20)]
        tracker.reset(cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY), (20, 20, 30, 30))

        began = time.perf_counter()
        for frame in frames[1:]:
            tracker.update(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        per_frame_ms = (time.perf_counter() - began) * 1000 / (len(frames) - 1)

        assert per_frame_ms < 10.0, f"LK chậm bất thường: {per_frame_ms:.1f} ms/frame"


class TestShiftMask:
    def test_dich_dung_vi_tri(self):
        mask = np.zeros((40, 40), bool)
        mask[5:10, 5:10] = True

        moved = shift_mask(mask, 4, 3)
        assert moved[8:13, 9:14].all()
        assert moved.sum() == mask.sum()

    def test_dich_ra_ngoai_khung_bi_cat(self):
        mask = np.zeros((20, 20), bool)
        mask[0:5, 0:5] = True

        moved = shift_mask(mask, -10, -10)
        assert moved.sum() == 0                 # ra ngoài hết

    def test_dich_0_khong_doi_gi(self):
        mask = np.zeros((20, 20), bool)
        mask[2:6, 3:9] = True
        assert (shift_mask(mask, 0, 0) == mask).all()

    def test_khong_lam_thay_doi_mask_goc(self):
        mask = np.zeros((20, 20), bool)
        mask[2:6, 3:9] = True
        before = mask.copy()
        shift_mask(mask, 3, 3)
        assert (mask == before).all()


@pytest.mark.parametrize("bbox,expected", [
    ((10, 20, 30, 40), (10, 20, 40, 60)),
    ((0, 0, 5, 5), (0, 0, 5, 5)),
])
def test_chuyen_doi_bbox_giua_hai_quy_uoc(bbox, expected):
    from src.live_tracking import xywh_to_xyxy, xyxy_to_xywh

    assert xywh_to_xyxy(bbox) == expected
    assert xyxy_to_xywh(expected) == bbox


# --- chế độ `scale=True`: nội suy cả TỈ LỆ + xoay (20-11) -------------------------------------
def _khung_vat(patch, *, ti_le=1.0, xoay=0.0, dx=0, dy=0, hinh=(240, 320), tam=(160, 120), seed=1):
    """Ảnh tổng hợp: nền nhiễu nhẹ CỐ ĐỊNH + một "vật" có texture, phóng to/xoay/dịch theo yêu cầu.

    Texture gắn vào vật (không phải nền ngẫu nhiên) — nếu nền ngẫu nhiên thì LK không khớp được gì và
    mọi ca đều "mất dấu", đúng cái bẫy đã gặp khi thử lần đầu.
    """
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    img = np.full(hinh, 128, np.uint8)
    img = (img + rng.normal(0, 2, img.shape)).clip(0, 255).astype(np.uint8)
    p = patch if ti_le == 1.0 else cv2.resize(patch, None, fx=ti_le, fy=ti_le)
    if xoay:
        m = cv2.getRotationMatrix2D((p.shape[1] / 2, p.shape[0] / 2), xoay, 1.0)
        p = cv2.warpAffine(p, m, (p.shape[1], p.shape[0]))
    ph, pw = p.shape
    x0, y0 = int(tam[0] - pw / 2 + dx), int(tam[1] - ph / 2 + dy)
    img[y0:y0 + ph, x0:x0 + pw] = p
    return img


def _patch_texture(seed=1):
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    return cv2.GaussianBlur((rng.random((90, 60)) * 255).astype(np.uint8), (3, 3), 0)


def test_scale_bat_duoc_vat_PHONG_TO_va_THU_NHO():
    """Tịnh tiến thuần KHÔNG THỂ chữa lệch kích thước (đo trên GT 20-11: ΔW/ΔH tới −132 px).

    Nghiệm thu: vật to 1,2× ⇒ ô bao phải to ~72×108; nhỏ 0,85× ⇒ ~51×77. Chế độ `shift` phải
    `ok=False` ở cả hai ca (đúng lý do phải thêm chế độ này).
    """
    from src.light_tracker import LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    b = (130, 75, 60, 90)
    for ti_le, rong_mong, cao_mong in ((1.2, 72, 108), (0.85, 51, 77)):
        f2 = _khung_vat(patch, ti_le=ti_le)
        t = LkBoxTracker(scale=False)
        t.reset(f1, b)
        assert t.update(f2)[0] is None, f"shift phải KHÔNG bám được khi vật co giãn {ti_le}"
        t = LkBoxTracker(scale=True)
        t.reset(f1, b)
        bbox, ok = t.update(f2)
        assert ok and abs(bbox[2] - rong_mong) <= 3 and abs(bbox[3] - cao_mong) <= 3, (ti_le, bbox)
        assert abs(t.last_scale - ti_le) < 0.06
        assert t.last_khop_similarity is True


def test_scale_bat_duoc_XOAY_va_van_tinh_dich_chuyen():
    from src.light_tracker import LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    # xoay 10°: ô bao bao ngoài 60×90 xoay 10° ≈ 74×99
    t = LkBoxTracker(scale=True)
    t.reset(f1, (130, 75, 60, 90))
    bbox, ok = t.update(_khung_vat(patch, xoay=10))
    assert ok and abs(bbox[2] - 74) <= 4 and abs(bbox[3] - 99) <= 4, bbox
    assert t.last_angle_deg < 0 and abs(abs(t.last_angle_deg) - 10) < 2      # xoay âm = cùng chiều
    # dịch thuần: cả hai chế độ phải ra CÙNG kết quả (không thêm sai số khi tỉ lệ = 1)
    for sc in (False, True):
        t = LkBoxTracker(scale=sc)
        t.reset(f1, (130, 75, 60, 90))
        assert t.update(_khung_vat(patch, dx=5, dy=3))[0] == (135, 78, 60, 90), sc


def test_scale_CONG_an_toan_tu_choi_bien_doi_qua_lon():
    """Vật "phóng" 1,6× trong một bước (> `scale_max` 1,25) là dấu hiệu khớp rác ⇒ KHÔNG được bịa
    ô bao to gấp rưỡi; phải rơi về tịnh tiến (và ở ca này tịnh tiến cũng mất dấu)."""
    from src.light_tracker import DEFAULT_SCALE_MAX, LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    t = LkBoxTracker(scale=True)
    t.reset(f1, (130, 75, 60, 90))
    bbox, ok = t.update(_khung_vat(patch, ti_le=1.6))
    assert ok is False and bbox is None
    assert DEFAULT_SCALE_MAX == 1.25          # nếu ai nới cổng, test các ca "quá lớn" phải xem lại
    assert t.last_khop_similarity is False


def test_scale_mat_dau_khi_vat_bien_mat():
    """Cổng `mad` phải còn hiệu lực: vật biến mất ⇒ không bám vào nền rồi báo ô bao sai."""
    import numpy as np
    from src.light_tracker import LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    rng = np.random.default_rng(7)
    nen = (rng.random(f1.shape) * 255).astype(np.uint8)      # đổi hẳn nội dung: không còn vật
    t = LkBoxTracker(scale=True, max_mad=1.5)
    t.reset(f1, (130, 75, 60, 90))
    bbox, ok = t.update(nen)
    assert ok is False and bbox is None


def test_warp_mask_bien_doi_cung_phep_voi_o_bao():
    """Mask phải co giãn CÙNG phép với ô bao, nếu không thì mask và ô lệch nhau trên hình."""
    import numpy as np
    from src.light_tracker import warp_mask
    mask = np.zeros((100, 100), bool)
    mask[40:60, 40:60] = True                               # khối 20×20 ở giữa
    # phóng 1,5× quanh tâm (50, 50) ⇒ khối 30×30
    m = np.array([[1.5, 0, -25.0], [0, 1.5, -25.0]], np.float32)
    ra = warp_mask(mask, m)
    assert ra.dtype == bool and ra.shape == mask.shape
    assert ra.sum() > mask.sum()                            # to ra
    ys, xs = np.where(ra)
    assert abs((ys.max() - ys.min() + 1) - 30) <= 2 and abs((xs.max() - xs.min() + 1) - 30) <= 2
    # ma trận None / identity ⇒ trả NGUYÊN mask (không tạo bản sao biến dạng)
    assert warp_mask(mask, None) is mask
    assert warp_mask(mask, np.array([[1, 0, 0], [0, 1, 0]], np.float32)) is mask
