"""Test `scripts/calibrate_reid.py` — hiệu chỉnh cổng nhận lại offline từ CSV có nhãn.

Vì sao có file này (retro 01-11): ngưỡng `reid_obj_threshold` / `reid_obj_ncc_min` đã bị
chỉnh tay **6 lần trong 3 ngày** (xem log 27-10), mỗi lần bằng cảm nhận rồi số đo thật
phản bác. Công cụ này cho ngưỡng một NHÀ ĐO: quét lưới trên số liệu đã ghi, không chạy model.

Hai điều quan trọng được khoá ở đây:
1. Phép quyết định trong sweep PHẢI là `accept_candidate` thật của `src/reid.py`.
2. Không có ca SAI nào có nhãn → **KHÔNG được đề xuất ngưỡng** (cận trên chưa xác định).
"""
import csv

import pytest

from scripts.calibrate_reid import (_parse_labels, boundary, label_events,
                                    read_reacquire_events, suggest)

HEADER = ["frame_idx", "latency_ms", "score", "center_x", "center_y", "lost",
          "state", "reid_score", "reacquired", "ncc"]


def _write_metrics(path, rows):
    """rows: list[(frame_idx, reid_score, ncc, reacquired)] → CSV đúng schema MetricsLogger."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for frame, cos, ncc, reacq in rows:
            w.writerow([frame, "100.0", "5.0", "10", "10", "0", "tracking",
                        cos, reacq, ncc])
    return str(path)


class TestDocSuKienNhanLai:
    def test_chi_lay_dong_reacquired_1(self, tmp_path):
        p = _write_metrics(tmp_path / "m.csv", [
            (0, "", 0, 0),                     # frame tracking bình thường
            (99, "0.819812", "0.711833", 1),   # sự kiện nhận lại
            (150, "0.86018", "0.720977", 1),
        ])
        ev = read_reacquire_events(p)
        assert [e.frame_idx for e in ev] == [99, 150]
        assert ev[0].cosine == pytest.approx(0.819812)
        assert ev[0].ncc == pytest.approx(0.711833)
        assert all(e.label is None for e in ev)

    def test_csv_khong_co_su_kien(self, tmp_path):
        p = _write_metrics(tmp_path / "m.csv", [(0, "", 0, 0), (1, "-1", "-1", 0)])
        assert read_reacquire_events(p) == []


class TestGanNhan:
    def test_gan_good_va_bad(self, tmp_path):
        p = _write_metrics(tmp_path / "m.csv", [
            (10, "0.9", "0.8", 1), (20, "0.9", "0.4", 1), (30, "0.8", "0.7", 1),
        ])
        ev = label_events(read_reacquire_events(p), good=[10], bad=[20])
        assert [e.label for e in ev] == ["good", "bad", None]   # 30 chưa gán nhãn

    def test_cung_frame_vua_good_vua_bad_bao_loi(self, tmp_path):
        p = _write_metrics(tmp_path / "m.csv", [(10, "0.9", "0.8", 1)])
        with pytest.raises(ValueError):
            label_events(read_reacquire_events(p), good=[10], bad=[10])


class TestCanTachNguong:
    def test_tach_duoc_thi_bao_diem_giua(self, tmp_path):
        # cosine chồng lấn (sai 0,92 > đúng 0,90) nhưng ncc tách được (sai 0,42 < đúng 0,86)
        p = _write_metrics(tmp_path / "m.csv", [
            (10, "0.90", "0.86", 1), (20, "0.92", "0.42", 1),
        ])
        ev = label_events(read_reacquire_events(p), good=[10], bad=[20])
        b = boundary(ev)
        assert b["cosine"]["separable"] is False
        assert b["cosine"]["midpoint"] is None
        assert b["ncc"]["separable"] is True
        assert b["ncc"]["max_bad"] == pytest.approx(0.42)
        assert b["ncc"]["min_good"] == pytest.approx(0.86)
        assert b["ncc"]["midpoint"] == pytest.approx(0.64)

    def test_chua_co_ca_sai_thi_can_tren_chua_xac_dinh(self, tmp_path):
        p = _write_metrics(tmp_path / "m.csv", [
            (10, "0.82", "0.71", 1), (20, "0.97", "0.42", 1),
        ])
        ev = label_events(read_reacquire_events(p), good=[10, 20])
        b = boundary(ev)
        assert b["ncc"]["max_bad"] is None
        assert b["ncc"]["separable"] is False
        assert b["ncc"]["min_good"] == pytest.approx(0.42)   # chỉ biết cận dưới


class TestGopNhieuCsv:
    """Ngưỡng phải hiệu chỉnh trên TẤT CẢ clip có nhãn, không phải từng clip rời."""

    def _two_csv(self, tmp_path):
        a = _write_metrics(tmp_path / "a_metrics.csv", [(10, "0.95", "0.80", 1)])
        b = _write_metrics(tmp_path / "b_metrics.csv", [(41, "0.90", "0.28", 1)])
        return a, b

    def test_doc_va_gan_nhan_theo_chi_so_csv(self, tmp_path):
        a, b = self._two_csv(tmp_path)
        ev = label_events(read_reacquire_events([a, b]),
                          good=[(0, 10)], bad=[(1, 41)])
        assert [(e.frame_idx, e.label) for e in ev] == [(10, "good"), (41, "bad")]

    def test_tach_duoc_ncc_khi_gop_hai_clip(self, tmp_path):
        a, b = self._two_csv(tmp_path)
        ev = label_events(read_reacquire_events([a, b]), good=[(0, 10)], bad=[(1, 41)])
        s = suggest(ev)
        assert s["ncc_min"] == pytest.approx(0.54)      # giữa 0,28 và 0,80
        assert s["cos_min"] == pytest.approx(0.93)      # giữa 0,90 và 0,95 = 0,925 → 0,93

    def test_nhieu_csv_ma_nhan_khong_co_tien_to_thi_bao_loi(self, tmp_path):
        a, b = self._two_csv(tmp_path)
        with pytest.raises(ValueError, match="chỉ số CSV"):
            _parse_labels("10", n_csv=2)

    def test_chi_so_csv_vuot_qua_so_file_thi_bao_loi(self, tmp_path):
        with pytest.raises(ValueError, match="chỉ số CSV"):
            _parse_labels("5:10", n_csv=2)


class TestDeXuat:
    def test_de_xuat_midpoint_khi_tach_duoc_ca_hai_cue(self, tmp_path):
        p = _write_metrics(tmp_path / "m.csv", [
            (10, "0.93", "0.86", 1), (20, "0.88", "0.40", 1),
        ])
        ev = label_events(read_reacquire_events(p), good=[10], bad=[20])
        s = suggest(ev)
        assert s["cos_min"] == pytest.approx(0.91)    # giữa 0,88 và 0,93 = 0,905 → 0,91
        assert s["ncc_min"] == pytest.approx(0.63)    # giữa 0,40 và 0,86

    def test_khong_co_ca_sai_thi_KHONG_de_xuat_nguong(self, tmp_path):
        p = _write_metrics(tmp_path / "m.csv", [(10, "0.82", "0.71", 1)])
        ev = label_events(read_reacquire_events(p), good=[10])
        assert suggest(ev) is None

    def test_chi_co_ca_sai_thi_cung_KHONG_de_xuat_nguong(self, tmp_path):
        """Bug thật 01-11: chỉ có ca SAI → công cụ báo nhầm 'hai cue không tách được'.
        Thật ra thiếu ca ĐÚNG nên cận DƯỚI chưa biết — không đề xuất gì."""
        p = _write_metrics(tmp_path / "m.csv", [(41, "0.899365", "0.279373", 1)])
        ev = label_events(read_reacquire_events(p), bad=[41])
        assert suggest(ev) is None

    def test_co_ca_sai_nhung_khong_tach_duoc_thi_de_xuat_None(self, tmp_path):
        # sai có cosine VÀ ncc đều cao hơn đúng → không cue nào tách được
        p = _write_metrics(tmp_path / "m.csv", [
            (10, "0.80", "0.50", 1), (20, "0.95", "0.99", 1),
        ])
        ev = label_events(read_reacquire_events(p), good=[10], bad=[20])
        s = suggest(ev)
        assert s["cos_min"] is None and s["ncc_min"] is None
