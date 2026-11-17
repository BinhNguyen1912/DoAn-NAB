"""Test `SessionSummary.p95_ms`/`p95_n`/`mean_n` + `_p95_txt` (ticket #32, P2 review 17-11).

Trước test này, revert `p95_ms` về `0,0` hoặc bỏ nhánh "chưa đo" của `_p95_txt` mà **toàn bộ suite
vẫn xanh** — đúng loại "test không có răng" mà AGENTS §9.1 cấm.
"""

import pytest

from src.live_pipeline import SessionSummary
from tools.run_live import _p95_txt


class TestP95CuaSessionSummary:
    def test_rong_thi_p95_None_va_n_0(self):
        s = SessionSummary(total_frames=0)
        assert s.p95_ms is None
        assert s.p95_n == 0 and s.mean_n == 0

    def test_co_mau_thi_p95_kem_n(self):
        s = SessionSummary(total_frames=2, latencies_ms=[100.0, 200.0])
        assert s.p95_ms == pytest.approx(195.0)      # nội suy tuyến tính của numpy
        assert s.p95_n == 2 and s.mean_n == 2


class TestP95Txt:
    def test_None_thi_in_chua_do(self):
        assert "chưa đo" in _p95_txt({"p95_latency_ms": None, "p95_latency_ms_n": 0})

    def test_co_so_thi_in_kem_n(self):
        chu = _p95_txt({"p95_latency_ms": 120.0, "p95_latency_ms_n": 600})
        assert "120" in chu and "n=600" in chu

    def test_artifact_cu_khong_co_khoa_n_thi_khong_in_None(self):
        """`*_summary.json` sinh TRƯỚC PR này không có `p95_latency_ms_n` ⇒ không được in "n=None"."""
        chu = _p95_txt({"p95_latency_ms": 120.0})
        assert "n=?" in chu and "None" not in chu
