"""Test cảnh báo "ô chọn phủ khuôn mặt" (đo 21-11-2026).

Ca thật sinh ra module này: người dùng chọn ô `(258,241,212,201)` trên frame webcam, YuNet báo mặt
`(256,208,197,228)` ⇒ **IoU 0,768**, tức ô chọn CHÍNH LÀ khuôn mặt. Hệ bám đúng thứ được chọn, nhưng
người dùng tưởng "bám nhầm". Phiên trước đó, đặc trưng tông da làm re-ID "nhận lại" vào mặt với cosine
0,974 / ncc 0,545 (không ngưỡng nào chặn được).
"""
import numpy as np
import pytest

from src.face_guard import BoDoMat, canh_bao_chon_o, iou_xywh, mat_bi_phu


class TestIou:
    def test_ca_that_o_chon_trung_mat(self):
        # số đo từ data/demoip_1121-075227_web.mp4 (frame đầu) — phải khớp ~0,768
        assert iou_xywh((258, 241, 212, 201), (256, 208, 197, 228)) == pytest.approx(0.768, abs=0.01)

    def test_o_suy_bien_tra_0(self):
        assert iou_xywh((0, 0, 0, 10), (0, 0, 10, 10)) == 0.0
        assert iou_xywh((100, 100, 10, 10), (0, 0, 10, 10)) == 0.0


class TestMatBiPhu:
    def test_bat_o_phu_mat(self):
        r = mat_bi_phu((258, 241, 212, 201), [(256, 208, 197, 228)])
        assert r is not None and r[1] == pytest.approx(0.768, abs=0.01)

    def test_khong_bat_khi_o_o_xa_mat(self):
        assert mat_bi_phu((0, 0, 40, 40), [(256, 208, 197, 228)]) is None

    def test_o_to_hon_mat_van_bi_bat(self):
        """Ô bao cả NGƯỜI: IoU thấp nhưng mặt nằm trọn trong ô ⇒ vẫn cảnh báo (ngưỡng 0,35)."""
        ca_nguoi = (200, 150, 250, 320)
        mat = (250, 170, 120, 140)
        iou = iou_xywh(ca_nguoi, mat)
        assert iou < 0.35, f"ca này IoU {iou:.2f} — nếu ≥ ngưỡng thì test không kiểm đúng điều định kiểm"

    def test_khong_co_mat_tra_None(self):
        assert mat_bi_phu((0, 0, 10, 10), []) is None


class TestFailOpen:
    def test_thieu_model_thi_im_lang(self, tmp_path):
        bo = BoDoMat(model=str(tmp_path / "khong_ton_tai.onnx"))
        assert bo.detect(np.zeros((64, 64, 3), np.uint8)) == []

    def test_frame_None_khong_nem(self):
        assert BoDoMat(model="x").detect(None) == []

    def test_canh_bao_None_khi_khong_co_o(self):
        assert canh_bao_chon_o(np.zeros((64, 64, 3), np.uint8), None) is None

    def test_cau_canh_bao_la_ASCII(self):
        """Console Windows (cp1258/cp437) làm hỏng dấu ⇒ câu cảnh báo phải là ASCII (quy ước HUD)."""
        class _Bo:
            def detect(self, _f):
                return [(256.0, 208.0, 197.0, 228.0)]

        cau = canh_bao_chon_o(np.zeros((480, 640, 3), np.uint8), (258, 241, 212, 201), bo_do=_Bo())
        assert cau is not None
        assert cau.isascii(), cau
        assert "KHUON MAT" in cau and "r'" in cau
