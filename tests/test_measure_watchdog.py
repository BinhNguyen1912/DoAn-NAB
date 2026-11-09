"""Test hàm thuần của `scripts/measure_watchdog.py` — phần provenance của artifact số đo.

Vì sao có: nhánh "git lỗi" từng làm `git_dirty_code` không được gán ⇒ `UnboundLocalError` **sau khi
đã chạy xong 3 lần đo**, tức là nuốt mất toàn bộ số vừa đo (review độc lập 09-11, P2). Hàm thuần nên
test được headless, không cần API/worker.
"""

import subprocess

import pytest

import scripts.measure_watchdog as measure


class TestDirtyOutsideData:
    def test_sua_file_code_la_ban(self):
        assert measure._is_dirty_outside_data(" M src/api/live.py\n") is True

    def test_sua_file_du_lieu_khong_tinh_la_code_ban(self):
        """Chính file artifact là thứ đang được ghi lại ⇒ không được coi là 'code bẩn'."""
        assert measure._is_dirty_outside_data(" M data/watchdog_2026-11-09_metrics.json\n") is False

    def test_file_code_moi_chua_track_van_tinh(self):
        """`??` (chưa track) mà là code thì phải tính — nếu không, số đo trên code chưa commit lọt."""
        assert measure._is_dirty_outside_data("?? src/api/adapters/moi.py\n") is True

    def test_sach_thi_false(self):
        assert measure._is_dirty_outside_data("") is False


class TestGitProvenance:
    def test_thieu_git_thi_tra_rong_chu_khong_nem(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise FileNotFoundError("git không có trên máy")

        monkeypatch.setattr(measure.subprocess, "run", _boom)

        assert measure._git_provenance() == ("", None, None)

    def test_git_tra_ma_loi_cung_khong_nem(self, monkeypatch):
        def _fail(*args, **kwargs):
            raise subprocess.CalledProcessError(128, "git")

        monkeypatch.setattr(measure.subprocess, "run", _fail)

        assert measure._git_provenance() == ("", None, None)

    def test_doc_duoc_rev_va_co_tach_data(self, monkeypatch):
        calls = []

        def _run(cmd, **kwargs):
            calls.append(cmd)

            class _Result:
                stdout = "abc123\n" if "rev-parse" in cmd else " M src/x.py\n M data/y.json\n"

            return _Result()

        monkeypatch.setattr(measure.subprocess, "run", _run)

        assert measure._git_provenance() == ("abc123", True, True)
        assert calls and calls[0][:2] == ["git", "rev-parse"]


@pytest.mark.parametrize("porcelain, expected", [
    (" M src/a.py\n M data/b.json\n", True),
    (" M data/b.json\n", False),
])
def test_ket_hop_voi_artifact(porcelain, expected):
    assert measure._is_dirty_outside_data(porcelain) is expected
