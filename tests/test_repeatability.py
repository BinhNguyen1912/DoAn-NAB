"""Test `scripts/repeatability.py` — định mức nhiễu cho phép so A/B (thuần, headless)."""

import pytest

from scripts.repeatability import danh_gia, la_khac_biet, spread


class TestSpread:
    def test_ba_lan_chay_giong_nhau_thi_do_tan_bang_0(self):
        ket_qua = spread([29.3, 29.3, 29.3])
        assert ket_qua["spread"] == 0.0
        assert ket_qua["rel_spread"] == 0.0

    def test_do_tan_tuong_doi(self):
        # literal: min 28,9 max 29,9 ⇒ spread 1,0; mean 29,4 ⇒ rel 0,034
        ket_qua = spread([29.3, 28.9, 29.9])
        assert ket_qua["spread"] == pytest.approx(1.0)
        assert ket_qua["rel_spread"] == pytest.approx(1.0 / 29.3666666, abs=1e-3)
        assert ket_qua["n"] == 3

    def test_rong_thi_bao_loi(self):
        with pytest.raises(ValueError):
            spread([])


class TestKetLuan:
    def test_chenh_lech_nho_hon_nguong_la_inconclusive(self):
        # smoothing: 0,681 vs 0,706 (chênh 0,025) với ngưỡng nhiễu 0,03 ⇒ không phân biệt được
        cau = danh_gia({"a": "bật làm mượt", "b": "tắt", "a_mean": 0.681, "b_mean": 0.706,
                        "nguong": 0.03})
        assert cau.startswith("KHÔNG PHÂN BIỆT ĐƯỢC")
        assert "inconclusive" in cau

    def test_mot_lan_chay_thi_khong_ket_luan_duoc_gi(self):
        """n = 1 ⇒ chưa có ngưỡng nhiễu ⇒ phải nói "không phân biệt được", không được kết luận."""
        assert la_khac_biet(0.9, 0.5, nguong=0.0, n=1) is False
        assert la_khac_biet(0.9, 0.5, nguong=0.0, n=3) is True

    def test_chenh_lech_lon_hon_nguong_la_khac_that(self):
        assert la_khac_biet(0.93, 0.65, nguong=0.03) is True
        assert "vượt ngưỡng nhiễu" in danh_gia({"a": "binh1", "b": "binh2", "a_mean": 0.93,
                                                "b_mean": 0.65, "nguong": 0.03, "n": 3})
