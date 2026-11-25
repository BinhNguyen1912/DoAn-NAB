"""Test cho `src/box_smoother.py` — làm mượt ô VẼ RA trên đường CLI.

Số liệu dùng trong test lấy từ phiên thật 25-11 (`data/demoip_1125-100334`): ô nhảy med 22,7 px mỗi
~9 frame hiển thị, max 118 px. Test ở đây chỉ dùng số học (không cần model/khung hình).
"""
import math

import pytest

from src.box_smoother import DEFAULT_SNAP_RATIO, DEFAULT_TAU_MS, BoxSmoother

HINH = (480, 640)          # (H, W) — khung 640×480 của demo
DUONG_CHEO = math.hypot(640, 480)


class TestCoBan:
    def test_o_dau_tien_ve_nguyen(self):
        s = BoxSmoother()
        assert s.update((100, 100, 200, 300), HINH) == (100, 100, 200, 300)

    def test_o_rong_hoac_none_thi_reset(self):
        s = BoxSmoother()
        s.update((100, 100, 200, 300), HINH)
        assert s.update((0, 0, 0, 0)) == (0, 0, 0, 0)
        assert s.o_dang_ve is None
        assert s.update((5, 5, 5, 5)) == (0, 0, 0, 0), "ô cao/rộng 0 không phải ô hợp lệ"
        assert s.update(None) == (0, 0, 0, 0)

    def test_di_chuyen_nho_thi_khong_snap(self):
        s = BoxSmoother()
        s.update((100, 100, 200, 300), HINH)
        s.update((122, 100, 222, 300), HINH)          # +22,7 px = cú nhảy med của phiên thật
        assert s.so_lan_snap == 0

    def test_mot_frame_khong_nhay_het_quang_duong(self):
        """EMA nghĩa là frame kế tiếp CHỈ đi một phần — nếu đi hết thì không có tác dụng gì."""
        s = BoxSmoother(tau_ms=DEFAULT_TAU_MS, snap_ratio=0.0)
        s.update((100, 100, 200, 300), HINH)
        ra = s.update((130, 100, 230, 300), HINH)     # đích +30 px
        assert 100 < ra[0] < 130, f"phải ở giữa, ra {ra}"

    def test_hoi_tu_sau_vai_frame(self):
        """τ=125 ms ở nhịp 18,7 FPS (~53 ms/frame): sau ~8 frame (một chu kỳ VOS) phải gần đích."""
        s = BoxSmoother(tau_ms=125.0, snap_ratio=0.0)
        s.update((100, 100, 200, 300), HINH)
        ra = None
        for _ in range(8):
            ra = s.update((200, 100, 300, 300), HINH, dt_s=0.053)
        assert abs(ra[0] - 200) <= 8, f"sau 8 frame còn lệch {abs(ra[0] - 200)} px (>8)"


class TestSnap:
    def test_cu_nhay_lon_thi_snap_ngay(self):
        """Ca 21-11 (bám sang cửa/tường): cú nhảy 229 px. Tráng nó = vệt quét ngang khung."""
        s = BoxSmoother()
        s.update((340, 200, 480, 320), HINH)
        ra = s.update((207, 383, 313, 479), HINH)     # ô của phiên 1125 f114 (lệch 229 px)
        assert ra == (207, 383, 313, 479)
        assert s.so_lan_snap == 1

    def test_nguong_snap_dung_25_phan_tram_duong_cheo(self):
        s = BoxSmoother()
        s.update((100, 100, 200, 300), HINH)
        gan = DEFAULT_SNAP_RATIO * DUONG_CHEO
        # ngay dưới ngưỡng ⇒ KHÔNG snap
        s2 = BoxSmoother()
        s2.update((100, 100, 200, 300), HINH)
        s2.update((100 + gan - 5, 100, 200 + gan - 5, 300), HINH)
        assert s2.so_lan_snap == 0
        # ngay trên ngưỡng ⇒ snap
        s3 = BoxSmoother()
        s3.update((100, 100, 200, 300), HINH)
        s3.update((100 + gan + 5, 100, 200 + gan + 5, 300), HINH)
        assert s3.so_lan_snap == 1

    def test_khong_truyen_frame_shape_thi_snap_tat(self):
        """Không biết khung ⇒ không đoán ngưỡng (nhưng vẫn EMA, không văng lỗi)."""
        s = BoxSmoother()
        s.update((100, 100, 200, 300))
        ra = s.update((500, 400, 600, 470))
        assert s.so_lan_snap == 0
        assert ra != (500, 400, 600, 470)


class TestBen:
    def test_o_co_lai_cuc_nhanh_khong_bi_dao_canh(self):
        """EMA 4 toạ độ độc lập có thể đảo cạnh ⇒ hình chữ nhật ngược (vẽ ra đường kẻ lạ)."""
        s = BoxSmoother(tau_ms=1000.0, snap_ratio=0.0)
        s.update((100, 100, 400, 400))
        x1, y1, x2, y2 = s.update((390, 390, 400, 400))   # co mạnh
        assert x2 > x1 and y2 > y1, f"cạnh bị đảo: {(x1, y1, x2, y2)}"

    def test_dt_lon_hon_thi_muot_nhanh_hon(self):
        """Cùng đích, cùng τ: frame có dt lớn hơn phải đi được xa hơn (không phụ thuộc FPS)."""
        a = BoxSmoother(tau_ms=125.0, snap_ratio=0.0)
        a.update((100, 100, 200, 300))
        ra_a = a.update((200, 100, 300, 300), HINH, dt_s=0.033)
        b = BoxSmoother(tau_ms=125.0, snap_ratio=0.0)
        b.update((100, 100, 200, 300))
        ra_b = b.update((200, 100, 300, 300), HINH, dt_s=0.1)
        assert ra_b[0] > ra_a[0]

    def test_reset_roi_ve_dung_cho_moi(self):
        """Sau reset (vật hiện lại) ô phải xuất hiện ĐÚNG chỗ mới, không bò từ chỗ cũ."""
        s = BoxSmoother()
        s.update((100, 100, 200, 300), HINH)
        s.reset()
        assert s.update((500, 300, 600, 460), HINH) == (500, 300, 600, 460)

    @pytest.mark.parametrize("bbox", [(1, 1, 2, 2), (0, 0, 640, 480), (300, 100, 640, 479)])
    def test_khong_bao_gio_tra_o_rong(self, bbox):
        s = BoxSmoother(snap_ratio=0.0)
        s.update((100, 100, 200, 300), HINH)
        x1, y1, x2, y2 = s.update(bbox, HINH)
        assert x2 > x1 and y2 > y1

    def test_tau_nho_hon_0_khong_no(self):
        s = BoxSmoother(tau_ms=0.0, snap_ratio=0.0)
        s.update((100, 100, 200, 300), HINH)
        assert s.update((130, 100, 230, 300), HINH) == (130, 100, 230, 300)
