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


def test_clip_khong_khai_ky_vong_thi_khong_bi_cham():
    """Chạy không khai `--expect-lost`: `_verdict(per_clip, {})` phải rỗng (đo xong là đạt) —
    trước đây mọi clip bị mặc định `False` nên clip mất dấu thật vẫn thoát mã 1 (review vòng 2, P2)."""
    per_clip = measure.summarize([
        {"clip": "xau", "empty_runs": 41, "empty_frac_window": 0.205, "empty_window_n": 200},
    ])
    assert measure._verdict(per_clip, {}) == []


def test_ket_luan_phan_biet_chi_do_voi_dat():
    """Không khai `--expect-lost` ⇒ artifact phải ghi **"CHỈ ĐO"**, không phải "đạt" — để không ai
    trích một lần đo làm bằng chứng "đã đạt tiêu chí" (review 09-11 vòng 3, P1)."""
    assert measure._ket_luan([], {}) .startswith("CHỈ ĐO")
    assert measure._ket_luan([], {"binh2": True}) == "đạt"
    assert measure._ket_luan(["binh2: chưa đủ mẫu"], {"binh2": True}).startswith("KHÔNG ĐẠT")


def test_co_truong_empty_window_lay_tu_status_tho():
    """`co_truong_empty_window` phải phản ánh `status.json` THÔ: nếu tính từ dòng đã `update` thì khoá
    luôn tồn tại (giá trị None) và nhánh "worker bản cũ không ghi khoá" không bao giờ chạy."""
    for status, want in (({}, False),
                         ({"empty_frac_window": None}, True),
                         ({"empty_frac_window": 0.0}, True)):
        row = measure._row_from_status(status, "x", "p.mp4", (1, 2, 3, 4))
        assert measure.summarize([row])["x"]["co_truong_empty_window"] is want, status


def test_moi_clip_deu_co_truong_ky_vong():
    """Hình dạng `tom_tat` phải ỔN ĐỊNH: clip nào cũng có `ky_vong` (`True` nếu được khai, chuỗi
    `"không đặt"` nếu không) — trước đây clip ĐƯỢC KHAI thiếu hẳn khoá, script đọc artifact sẽ
    `KeyError` (review 09-11 vòng 3, P2)."""
    per_clip = measure.summarize([{"clip": "a"}, {"clip": "b"}])
    measure._gan_ky_vong(per_clip, {"a": True})
    assert {k: v["ky_vong"] for k, v in per_clip.items()} == {"a": True, "b": "không đặt"}
