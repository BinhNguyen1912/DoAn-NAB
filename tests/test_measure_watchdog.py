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
    def test_thieu_git_thi_tra_rong_kem_ly_do_chu_khong_nem(self, monkeypatch):
        """Không có provenance ⇒ phải NÓI RA (`git_loi`), không trả `("", None, None)` im lặng."""

        def _boom(*args, **kwargs):
            raise FileNotFoundError("git không có trên máy")

        monkeypatch.setattr(measure.subprocess, "run", _boom)

        rev, dirty, dirty_code, loi = measure._git_provenance()
        assert rev is None and dirty is None and dirty_code is None
        assert loi and "FileNotFoundError" in loi

    def test_git_tra_ma_loi_cung_khong_nem(self, monkeypatch):
        def _fail(*args, **kwargs):
            raise subprocess.CalledProcessError(128, "git")

        monkeypatch.setattr(measure.subprocess, "run", _fail)

        rev, _, _, loi = measure._git_provenance()
        assert rev is None and loi and "CalledProcessError" in loi

    def test_loi_giai_ma_utf8_cung_khong_nem(self, monkeypatch):
        """`git` in tiếng Việt sai locale có thể ném `UnicodeDecodeError` — ném ở đây là mất cả 3 lần đo."""

        def _bad_decode(*args, **kwargs):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")

        monkeypatch.setattr(measure.subprocess, "run", _bad_decode)

        rev, _, _, loi = measure._git_provenance()
        assert rev is None and loi and "UnicodeDecodeError" in loi

    def test_rev_rong_cung_la_loi_provenance(self, monkeypatch):
        class _Empty:
            stdout = ""

        monkeypatch.setattr(measure.subprocess, "run", lambda *a, **k: _Empty())

        rev, _, _, loi = measure._git_provenance()
        assert rev is None and loi

    def test_doc_duoc_rev_va_co_tach_data(self, monkeypatch):
        calls = []

        def _run(cmd, **kwargs):
            calls.append(cmd)

            class _Result:
                stdout = "abc123\n" if "rev-parse" in cmd else " M src/x.py\n M data/y.json\n"

            return _Result()

        monkeypatch.setattr(measure.subprocess, "run", _run)

        assert measure._git_provenance() == ("abc123", True, True, None)
        assert calls and calls[0][:2] == ["git", "rev-parse"]


class TestVerdict:
    """P2 vòng 2: "không phát hiện được lỗi" từng bị ghi là "không vượt ngưỡng" (0/None ≠ đã đo)."""

    def test_khong_phat_hien_duoc_la_that_bai(self):
        that_bai, vuot = measure._verdict(None, 100.0, 5.0)
        assert that_bai is True and vuot is True

    def test_trong_nguong_la_dat(self):
        assert measure._verdict(103.0, 100.0, 5.0) == (False, False)

    def test_cham_nhung_co_ket_luan_la_vuot_nguong(self):
        that_bai, vuot = measure._verdict(112.0, 100.0, 5.0)
        assert that_bai is False and vuot is True


class TestExitCode:
    def test_phat_hien_that_bai_thi_thoat_1(self):
        runs = [{"that_bai": True, "vuot_nguong": True}]
        assert measure._exit_code(runs, None, None) == 1

    def test_vuot_nguong_thi_thoat_1(self):
        runs = [{"that_bai": False, "vuot_nguong": True}]
        assert measure._exit_code(runs, None, None) == 1

    def test_du_dat_va_co_provenance_thi_thoat_0(self):
        runs = [{"that_bai": False, "vuot_nguong": False}]
        assert measure._exit_code(runs, None, None) == 0

    def test_git_loi_thi_thoat_1_du_so_dat(self):
        runs = [{"that_bai": False, "vuot_nguong": False}]
        assert measure._exit_code(runs, None, "git hỏng") == 1

    def test_loi_do_dac_thi_thoat_1(self):
        assert measure._exit_code([], "RuntimeError: API chết", None) == 1


@pytest.mark.parametrize("porcelain, expected", [
    (" M src/a.py\n M data/b.json\n", True),
    (" M data/b.json\n", False),
])
def test_ket_hop_voi_artifact(porcelain, expected):
    assert measure._is_dirty_outside_data(porcelain) is expected
