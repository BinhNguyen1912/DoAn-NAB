"""Test hàm thuần của `scripts/measure_empty_window.py` — đọc `--clip` và tóm tắt/kiểm kỳ vọng."""

import pytest

import scripts.measure_empty_window as measure


class TestParseClip:
    def test_doc_dung_dinh_dang(self):
        assert measure.parse_clip("binh1=data/binh1.mp4:104,308,209,287") == (
            "binh1", "data/binh1.mp4", (104, 308, 209, 287))

    def test_sai_dinh_dang_thi_nem_loi_co_huong_dan(self):
        with pytest.raises(ValueError, match="tên=đường_dẫn:x,y,w,h"):
            measure.parse_clip("binh1-data/binh1.mp4")


class TestSummarize:
    def test_none_chua_du_mau_khong_phai_0(self):
        rows = [{"clip": "a", "empty_runs": 2, "empty_frac_window": None, "empty_window_n": 3}]
        out = measure.summarize(rows)
        assert out["a"]["empty_frac_window"] is None
        assert out["a"]["dang_mat_dau"] is None

    def test_0_0_la_da_do_va_khong_mat_dau(self):
        rows = [{"clip": "a", "empty_runs": 0, "empty_frac_window": 0.0, "empty_window_n": 200}]
        assert measure.summarize(rows)["a"]["dang_mat_dau"] is False

    def test_ti_le_duong_la_dang_mat_dau(self):
        rows = [{"clip": "a", "empty_runs": 34, "empty_frac_window": 0.17, "empty_window_n": 200}]
        assert measure.summarize(rows)["a"]["dang_mat_dau"] is True


class TestVerdict:
    @staticmethod
    def _per_clip(a, b):
        return measure.summarize([
            {"clip": "khoe", "empty_runs": 0, "empty_frac_window": 0.0, "empty_window_n": 200},
            {"clip": "xau", "empty_runs": 34, "empty_frac_window": b, "empty_window_n": 200},
        ])

    def test_dung_ky_vong_thi_khong_co_van_de(self):
        assert measure._verdict(self._per_clip("xau", 0.17), {"khoe": False, "xau": True}) == []

    def test_sai_ky_vong_thi_bao(self):
        problems = measure._verdict(self._per_clip("xau", 0.17), {"khoe": False, "xau": False})
        assert problems and "xau" in problems[0]

    def test_chua_du_mau_cung_la_van_de(self):
        per_clip = measure.summarize([{"clip": "a", "empty_frac_window": None, "empty_window_n": 2}])
        problems = measure._verdict(per_clip, {"a": False})
        assert problems and "chưa đủ mẫu" in problems[0]

    def test_thieu_clip_cung_la_van_de(self):
        assert measure._verdict({}, {"a": False})


def test_thieu_han_truong_khac_voi_chua_du_mau():
    """Worker bản cũ không ghi `empty_frac_window` ⇒ chẩn đoán phải nói "thiếu khoá", không phải
    "chưa đủ mẫu" (hai nguyên nhân khác nhau, review 09-11 P3)."""
    per_clip = measure.summarize([{"clip": "a", "empty_runs": 0, "empty_window_n": 0}])
    assert per_clip["a"]["co_truong_empty_window"] is False
    problems = measure._verdict(per_clip, {"a": False})
    assert problems and "KHÔNG ghi" in problems[0]
