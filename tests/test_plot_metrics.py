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
