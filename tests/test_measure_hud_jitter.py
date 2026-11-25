"""Test cho `scripts/measure_hud_jitter.py` — đo jitter trên KHUNG HÌNH vẽ ra (dò màu).

Vì sao phải test phần dò màu (25-11): bản đầu lấy hộp màu đỏ lớn nhất làm "ô" ⇒ **banner "MẤT DẤU"**
(khối đỏ đặc có chữ trắng) bị đọc thành ô ⇒ báo "bước nhảy" 336 px mà thật ra là banner hiện/ẩn. Đo lại
trên phiên `demoip_1125-100334`: nếu lọt banner thì max 336,77 px; lọc đúng thì max 188,12 px.
"""
import cv2
import numpy as np
import pytest

from scripts.measure_hud_jitter import (  # noqa: N812 — tên module theo repo
    _dai_nhay,
    dem_vang,
    do_video,
    hop_tu_frame,
)

DO = (0, 0, 255)        # BGR
VANG = (0, 215, 255)


def _nen(h=240, w=320):
    return np.full((h, w, 3), 40, dtype=np.uint8)


class TestHopTuFrame:
    def test_o_vien_mong_duoc_nhan(self):
        fr = _nen()
        fr[100:180, 100:200] = 40
        fr[100:102, 100:200] = DO          # viền trên
        fr[178:180, 100:200] = DO          # viền dưới
        fr[100:180, 100:102] = DO          # viền trái
        fr[100:180, 198:200] = DO          # viền phải
        hop, n = hop_tu_frame(fr)
        assert hop == (100, 100, 199, 179) and n > 400

    def test_banner_khoi_dac_co_chu_KHONG_bi_coi_la_o(self):
        """Ca thật: banner "MẤT DẤU" = khối đỏ đặc 285×19 có chữ trắng ⇒ KHÔNG phải ô."""
        fr = _nen()
        fr[226:245, 174:459] = DO                      # khối đặc
        for x in range(180, 450, 12):                  # chữ trắng
            fr[230:241, x:x + 7] = (255, 255, 255)
        hop, _ = hop_tu_frame(fr)
        assert hop is None, f"banner bị đọc thành ô: {hop}"

    def test_khoi_dac_vuong_thi_van_la_o_neu_khong_det(self):
        """Khối đặc nhưng KHÔNG dẹt (rộng/cao ≤ 5) ⇒ giữ, để không loại oan ô thật có vật đỏ."""
        fr = _nen()
        fr[100:180, 100:200] = DO
        hop, _ = hop_tu_frame(fr)
        assert hop is not None

    def test_qua_it_pixel_thi_khong_co_o(self):
        fr = _nen()
        fr[10:14, 10:14] = DO
        hop, n = hop_tu_frame(fr)
        assert hop is None and n < 80

    def test_anh_khong_co_mau_do(self):
        assert hop_tu_frame(_nen()) == (None, 0)


class TestDemVang:
    def test_dem_pixel_net_dut(self):
        fr = _nen()
        fr[50:52, 50:200] = VANG
        assert dem_vang(fr) == 300
        assert dem_vang(_nen()) == 0


class TestDaiNhay:
    @pytest.mark.parametrize("px,dai", [(0.0, "<20px"), (19.9, "<20px"), (20.0, "20-50px"),
                                        (49.0, "20-50px"), (99.0, "50-100px"),
                                        (150.0, "100-200px"), (500.0, ">=200px")])
    def test_chia_dai(self, px, dai):
        assert _dai_nhay(px) == dai


class TestDoVideo:  # noqa: D101 - nhóm test cho `do_video`
    def test_khong_co_video_thi_khong_do_duoc(self, tmp_path):
        """0 mẫu ≠ 'đã đo' (AGENTS §6)."""
        p = tmp_path / "rong.mp4"
        vw = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
        for _ in range(5):
            vw.write(_nen())
        vw.release()
        r = do_video(p)
        assert r["so_frame"] == 5
        assert r["dich_chuyen_frame_med"] is None, "video không có ô ⇒ phải None, không phải 0"
        assert r["pct_o_do"] == 0.0

    def test_o_dung_yen_roi_nhay_cho_med_giu_lon(self, tmp_path):
        """Đúng hiện tượng 25-11: 6 frame cùng chỗ rồi nhảy ⇒ `giu_frame_med` ~6 và "
        `dich_chuyen_frame_med` = 0."""
        p = tmp_path / "o.mp4"
        vw = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
        for i in range(24):
            fr = _nen()
            x = 40 + 60 * (i // 6)            # đứng yên 6 frame rồi nhảy
            # Nét dày 3 px: mp4v (4:2:0) XOÁ SẠCH nét đỏ 1 px — đo 25-11: nét 1 px còn 5 pixel đỏ,
            # nét 2 px còn 449, nét 4 px còn 880 ⇒ test vẽ 1 px sẽ "không có ô" (bẫy của chính phép đo).
            cv2.rectangle(fr, (x, 100), (x + 50, 160), DO, 3)
            vw.write(fr)
        vw.release()
        r = do_video(p)
        assert r["giu_frame_med"] is not None
        assert r["dich_chuyen_frame_med"] == 0.0
        assert r["nhay_tam_med"] == pytest.approx(60.0, abs=2.0)
        assert r["dai_buoc_nhay"].get("20-50px", 0) + r["dai_buoc_nhay"].get("50-100px", 0) == 3
