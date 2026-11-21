"""Test `src/track_identity.py` — NEO danh tính + `cos` (plan 21-11-2026, PR-1 LOG-ONLY).

Vì sao module này tồn tại: phiên `demoip_1121-103854` bám sang MÁY LẠNH 9 s mà không cổng nào kêu
(`score` còn tăng lên 5,85–6,02; hai cổng nhảy cần 200/451 px trong khi cú nhảy thật là 114 px).
PR-1 chỉ ĐO; ngưỡng θ phải chốt bằng phân bố thật (≥200 mẫu/clip), không đoán.
"""
import numpy as np
import pytest

from src.appearance import object_signature
from src.reid import best_match
from src.track_identity import MAX_ANCHORS, MIN_ANCHORS, NeoDanhTinh, cos_voi_neo, dem_neo


def _frame(box=(20, 20, 80, 140), shape=(200, 300), color=(40, 180, 220)):
    f = np.full((shape[0], shape[1], 3), (35, 37, 32), np.uint8)
    x1, y1, x2, y2 = box
    f[y1:y2, x1:x2] = color
    return f


def _mask(box=(20, 20, 80, 140), shape=(200, 300)):
    m = np.zeros(shape, bool)
    x1, y1, x2, y2 = box
    m[y1:y2, x1:x2] = True
    return m


class TestNeoDanhTinh:
    def test_nap_neo_va_cham_cos(self):
        neo = NeoDanhTinh()
        f, m = _frame(), _mask()
        assert [neo.thu(f, m) for _ in range(MIN_ANCHORS)] == [True] * MIN_ANCHORS
        assert neo.co_neo is True
        assert neo.cos(f, m) == pytest.approx(1.0, abs=1e-6)   # cùng vùng ⇒ cos 1,0

    def test_chua_du_neo_thi_tra_None_chu_khong_phai_0(self):
        """Bẫy `0/None ≠ đã đo` (AGENTS §6): chưa đủ neo ⇒ `None`, KHÔNG được ghi 0."""
        neo = NeoDanhTinh()
        assert neo.cos(_frame(), _mask()) is None
        assert neo.n_cham == 1 and neo.n_none == 1

    def test_mask_rong_thi_None(self):
        neo = NeoDanhTinh()
        f, m = _frame(), _mask()
        for _ in range(MIN_ANCHORS):
            neo.thu(f, m)
        assert neo.cos(f, np.zeros((200, 300), bool)) is None

    def test_khong_nhan_neo_rac_qua_cong_chat_luong(self):
        """Mask 1 pixel (dưới `DEFAULT_MIN_AREA`) ⇒ KHÔNG được thành neo (nếu nhận, `cos` sẽ pass-giả)."""
        neo = NeoDanhTinh()
        m = np.zeros((200, 300), bool)
        m[100, 100] = True
        assert neo.thu(_frame(), m) is False
        assert dem_neo(neo) == 0

    def test_dung_o_MAX_ANCHORS(self):
        neo = NeoDanhTinh(max_anchors=3)
        f, m = _frame(), _mask()
        assert [neo.thu(f, m) for _ in range(5)] == [True, True, True, False, False]
        assert dem_neo(neo) == 3

    def test_vat_di_cho_khac_van_cos_cao(self):
        """Đặc trưng `object_signature` bất biến vị trí (toạ độ chuẩn hoá theo ô) ⇒ neo dùng được."""
        neo = NeoDanhTinh()
        for _ in range(MIN_ANCHORS):
            neo.thu(_frame(), _mask())
        f2 = _frame(box=(120, 40, 180, 160))     # cùng vật, chỗ khác
        m2 = _mask(box=(120, 40, 180, 160))
        assert neo.cos(f2, m2) > 0.9

    def test_neo_khong_khop_vat_khac_thi_cos_thap(self):
        neo = NeoDanhTinh()
        m = _mask()
        for _ in range(MIN_ANCHORS):
            neo.thu(_frame(color=(40, 180, 220)), m)
        # "vật" khác: cùng hình nhưng màu rất khác
        assert neo.cos(_frame(color=(30, 30, 30)), m) < 0.9

    def test_xoa_neo_khi_chon_lai(self):
        neo = NeoDanhTinh()
        f, m = _frame(), _mask()
        for _ in range(MIN_ANCHORS):
            neo.thu(f, m)
        neo.xoa()
        assert neo.co_neo is False and dem_neo(neo) == 0

    def test_cos_khop_dung_cong_thuc_best_match(self):
        """Chống import VÒNG: module này tự tính max tích vô hướng (KHÔNG import `reid.best_match`).

        Hai cách phải cho cùng kết quả, nếu không `track_cos` sẽ lệch nghĩa với `reid_score`.
        """
        neo = NeoDanhTinh()
        f, m = _frame(), _mask()
        # 2 neo là 2 tư thế khác nhau một chút (đổi màu nhẹ) để `max` có ý nghĩa
        neo.thu(_frame(color=(40, 180, 220)), m)
        neo.thu(_frame(color=(60, 170, 210)), m)
        neo.thu(_frame(color=(50, 175, 215)), m)
        assert neo.co_neo is True
        c = neo.cos(f, m)
        sig = object_signature(f, m)
        assert c == pytest.approx(float(best_match(list(neo._refs), sig)), abs=1e-6)

    def test_cos_voi_neo_fail_open(self):
        assert cos_voi_neo(None, _frame(), _mask()) is None
        class Hong:
            def cos(self, *_a):
                raise RuntimeError("hỏng")
        assert cos_voi_neo(Hong(), _frame(), _mask()) is None

    def test_mac_dinh_can_3_neo(self):
        """P2 review 21-11: docstring/plan nói "3 là mức tối thiểu" nhưng hằng số là 2.

        `cos` lấy MAX trên các neo ⇒ 2 neo mà 1 cái hỏng thì còn 1 ⇒ cổng pass-giả. Test khoá hằng số
        VÀ hành vi (2 neo ⇒ chưa chấm).
        """
        assert MIN_ANCHORS == 3 and MAX_ANCHORS >= MIN_ANCHORS
        neo = NeoDanhTinh()
        f, m = _frame(), _mask()
        assert neo.thu(f, m) and neo.thu(f, m)
        assert neo.co_neo is False
        assert neo.cos(f, m) is None
        assert neo.thu(f, m) is True
        assert neo.co_neo is True

    def test_khong_nhan_neo_la_dai_rac_sat_mep_khung(self):
        """P2 review 21-11: bản đầu chỉ lọc `signature_quality_ok` ⇒ dải rác sát mép (vd 71×10)

        vẫn được nhận làm NEO ⇒ **khoá cái sai cho cả phiên**. Nay phải cắt dải mép rồi mới chấm.
        """
        neo = NeoDanhTinh()
        f = _frame()
        m = np.zeros((200, 300), bool)
        m[0:10, 0:71] = True                     # dải mỏng dính MÉP TRÊN-TRÁI (như mask rác SAM 2)
        assert neo.thu(f, m) is False
        assert dem_neo(neo) == 0
