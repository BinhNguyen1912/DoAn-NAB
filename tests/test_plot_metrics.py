"""Test phần đọc/tính của scripts/plot_metrics.py (không cần matplotlib/PNG)."""
import csv

import pytest

from scripts.plot_metrics import read_metrics, summarize


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame_idx", "latency_ms", "score", "center_x", "center_y", "lost"])
        w.writerows(rows)
    return str(path)


class TestReadMetrics:
    def test_doc_dung_cot_va_kieu(self, tmp_path):
        p = _write_csv(tmp_path / "m.csv", [
            [0, "100.0", "0.9", "10", "20", 0],
            [1, "200.0", "0.8", "", "", 1],     # frame mất dấu: tâm rỗng
        ])
        d = read_metrics(p)
        assert list(d["frame"]) == [0, 1]
        assert d["latency"].tolist() == [100.0, 200.0]
        assert d["lost"].tolist() == [0, 1]
        assert d["cx"][0] == 10.0 and d["cy"][0] == 20.0

    def test_csv_rong_bao_loi(self, tmp_path):
        p = tmp_path / "rong.csv"
        p.write_text("frame_idx,latency_ms,score,center_x,center_y,lost\n", encoding="utf-8")
        with pytest.raises(ValueError, match="rỗng"):
            read_metrics(str(p))


class TestSummarize:
    def test_mean_p95_fps_va_ty_le_mat_dau(self, tmp_path):
        p = _write_csv(tmp_path / "m.csv", [
            [0, "100.0", "0.9", "10", "20", 0],
            [1, "110.0", "0.9", "11", "21", 0],
            [2, "120.0", "0.9", "", "", 1],
        ])
        s = summarize("demo", read_metrics(p))
        assert s["n"] == 3
        assert s["mean_ms"] == pytest.approx(110.0)
        assert s["p95_ms"] == pytest.approx(119.0)   # nội suy tuyến tính
        assert s["fps"] == pytest.approx(1000 / 110)
        assert s["lost"] == 1 and s["lost_ratio"] == pytest.approx(1 / 3)


class TestP95KhongBiaSoKhiChuaDo:
    """Ticket #32: `p95` của bảng/biểu đồ cũng phải `None` khi KHÔNG có mẫu latency nào.

    Bản cũ rơi về `d["latency"]` (toàn 0 khi mọi frame đóng băng) ⇒ bảng in "p95 0 ms", đọc như
    "xử lý tức thì" — đúng bẫy `0/None` mà `AGENTS.md` §6 cấm.
    """

    def test_toan_bo_frame_dong_bang_thi_p95_None(self):
        import numpy as np

        from scripts import plot_metrics as pm

        s = pm.summarize("dongsong", {"latency": np.zeros(3), "lost": np.ones(3),
                                      "frame": np.arange(3), "frozen": np.ones(3, bool)})
        assert s["n"] == 3 and s["frozen"] == 3
        assert s["p95_ms"] is None and s["mean_ms"] is None and s["n_do_ms"] == 0
        assert s["fps"] is None

    def test_csv_rong_thi_khong_chia_cho_0(self):
        import numpy as np

        from scripts import plot_metrics as pm

        s = pm.summarize("rong", {"latency": np.array([]), "lost": np.array([]),
                                  "frame": np.array([])})
        assert s["p95_ms"] is None and s["lost_ratio"] is None


class TestPlotCompareKhongVeCot0:
    """Ticket #32 (P2 review 17-11): file toàn đóng băng KHÔNG được vẽ thành cột `0` trên thang log."""

    def _items(self):
        import numpy as np

        from scripts import plot_metrics as pm

        binh_thuong = pm.summarize("binh_thuong", {
            "latency": np.array([100.0, 110.0, 120.0]), "lost": np.zeros(3),
            "frame": np.arange(3), "frozen": np.zeros(3, bool)})
        dong_bang = pm.summarize("dong_bang", {
            "latency": np.zeros(3), "lost": np.ones(3),
            "frame": np.arange(3), "frozen": np.ones(3, bool)})
        return [({}, binh_thuong), ({}, dong_bang)]

    def test_it_hon_2_lan_co_mau_thi_khong_ve(self, tmp_path):
        from scripts import plot_metrics as pm

        assert pm.plot_compare(self._items(), str(tmp_path)) is None

    def test_2_lan_co_mau_thi_van_ve(self, tmp_path):
        import numpy as np

        from scripts import plot_metrics as pm

        items = self._items()
        them = pm.summarize("khac", {"latency": np.array([200.0]), "lost": np.zeros(1),
                                     "frame": np.arange(1), "frozen": np.zeros(1, bool)})
        p = pm.plot_compare([items[0], ({}, them)], str(tmp_path))
        assert p and p.endswith("so_sanh_latency.png")
