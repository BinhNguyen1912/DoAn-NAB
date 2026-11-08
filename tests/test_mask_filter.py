"""Test `src/mask_filter.py` — EMA mask + IoU (không cần model, không cần video)."""

import numpy as np
import pytest

from src.mask_filter import MaskSmoother, mask_iou


def _mask(*boxes, shape=(40, 60)):
    out = np.zeros(shape, bool)
    for x0, y0, x1, y1 in boxes:
        out[y0:y1, x0:x1] = True
    return out


class TestMaskSmoother:
    def test_lan_dau_tra_ve_chinh_mask_do(self):
        smoother = MaskSmoother(alpha=0.5)
        mask = _mask((10, 10, 20, 20))
        assert (smoother.update(mask) == mask).all()

    def test_mask_bien_mat_mot_lan_khong_bien_mat_ngay(self):
        """Nhấp nháy 1 lần: alpha=0,5 → acc = 0,5 < ngưỡng 0,5 ⇒ … phải giữ được."""
        smoother = MaskSmoother(alpha=0.4)
        mask = _mask((10, 10, 20, 20))
        smoother.update(mask)
        smoother.update(mask)
        empty = np.zeros_like(mask)

        kept = smoother.update(empty)
        assert kept.any(), "một lần mask rỗng không được làm đối tượng biến mất (nhấp nháy)"

    def test_mask_bien_mat_lien_tuc_thi_tat_han(self):
        smoother = MaskSmoother(alpha=0.5)
        mask = _mask((10, 10, 20, 20))
        for _ in range(4):
            smoother.update(mask)
        empty = np.zeros_like(mask)

        for _ in range(5):          # 0,5^5 < 0,5^1 … sau vài lần acc tụt dưới ngưỡng
            kept = smoother.update(empty)
        assert not kept.any(), "mất dấu thật thì phải tắt, không được giữ bóng ma"

    def test_shift_dich_bo_tich_luy(self):
        smoother = MaskSmoother(alpha=1.0)      # alpha=1: kết quả = mask mới (dễ kiểm)
        smoother.update(_mask((10, 10, 20, 20)))
        smoother.shift(5, 3)                     # dịch bộ tích luỹ 5 px phải, 3 px xuống
        kept = smoother.update(_mask((15, 13, 25, 23)))
        assert kept[13:23, 15:25].all() and kept.sum() == 100

    def test_reset_xoa_trang_thai(self):
        smoother = MaskSmoother()
        smoother.update(_mask((1, 1, 5, 5)))
        smoother.reset()
        empty = np.zeros((40, 60), bool)
        assert not smoother.update(empty).any()   # không còn gì để trộn

    def test_giu_mask_khi_dien_tich_teo_dot_ngot(self):
        """Cơ chế hold: mask teo còn 10 % ⇒ coi là "chớp", giữ mask cũ."""
        smoother = MaskSmoother(alpha=0.6, hold_ratio=0.4, max_hold=2)
        full = _mask((10, 10, 30, 30))          # 400 px
        smoother.update(full)
        tiny = _mask((10, 10, 13, 13))          # 9 px ≪ 40 % của 400

        kept = smoother.update(tiny)
        assert kept.sum() == 400, "một lần chớp không được làm mask teo theo"

    def test_gia_tri_max_hold_roi_moi_chap_nhan_mat_dau(self):
        smoother = MaskSmoother(alpha=0.6, hold_ratio=0.4, max_hold=2)
        full = _mask((10, 10, 30, 30))
        smoother.update(full)
        empty = np.zeros_like(full)

        assert smoother.update(empty).sum() == 400      # hold 1
        assert smoother.update(empty).sum() == 400      # hold 2
        assert not smoother.update(empty).any()         # quá max_hold ⇒ mất dấu thật

    def test_mat_dau_that_roi_co_lai_thi_giu_lai_duoc(self):
        smoother = MaskSmoother(alpha=0.6, hold_ratio=0.4, max_hold=1)
        full = _mask((10, 10, 30, 30))
        empty = np.zeros_like(full)
        smoother.update(full)
        smoother.update(empty)
        smoother.update(empty)                          # đã tắt
        assert smoother.update(full).sum() == 400       # có lại → bật lại

    def test_mask_none_tra_ve_none(self):
        assert MaskSmoother().update(None) is None

    def test_alpha_ngoai_khoang_bao_loi(self):
        with pytest.raises(ValueError):
            MaskSmoother(alpha=0.0)
        with pytest.raises(ValueError):
            MaskSmoother(alpha=1.5)

    def test_doi_kich_thuoc_frame_thi_lam_lai_tu_dau(self):
        smoother = MaskSmoother(alpha=0.5)
        smoother.update(_mask((1, 1, 5, 5), shape=(40, 60)))
        bigger = _mask((1, 1, 5, 5), shape=(80, 120))
        assert smoother.update(bigger).shape == bigger.shape


class TestMaskIou:
    def test_giong_het(self):
        mask = _mask((5, 5, 15, 15))
        assert mask_iou(mask, mask) == 1.0

    def test_khong_giao(self):
        assert mask_iou(_mask((1, 1, 5, 5)), _mask((20, 20, 25, 25))) == 0.0

    def test_mot_nua(self):
        # a = 4×4 = 16 px; b = dải trái 2×4 ∪ dải trên 4×2 = 8 + 8 − 4 = 12 px (nằm trong a)
        # → giao 12, hợp 16 ⇒ IoU = 0,75
        a = _mask((0, 0, 4, 4))
        b = _mask((0, 0, 2, 4), (0, 0, 4, 2))
        assert mask_iou(a, b) == pytest.approx(0.75)

    def test_hai_mask_rong_coi_nhu_khop(self):
        empty = np.zeros((10, 10), bool)
        assert mask_iou(empty, empty) == 1.0

    def test_mask_none(self):
        assert mask_iou(None, _mask((1, 1, 2, 2))) == 0.0
