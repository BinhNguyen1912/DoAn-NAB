"""Test script `run` (lệnh tắt) — đảm bảo help/exit code đúng và không lệch tài liệu."""
import subprocess

ROOT_RUN = "run"


def _run(*args):
    return subprocess.run(["bash", ROOT_RUN, *args], capture_output=True, text=True, timeout=60)


class TestRunHelp:
    def test_help_lists_main_commands(self):
        r = _run("help")
        assert r.returncode == 0
        for cmd in ("demo", "demo5", "check", "phone", "test", "lint", "charts", "gpu", "env",
                    "reid"):
            assert cmd in r.stdout, f"thiếu lệnh '{cmd}' trong help"

    def test_reid_thieu_tham_so_bao_loi_ro_rang(self):
        """`./run reid` cần video + bbox; thiếu thì báo lỗi dễ hiểu, mã thoát 2."""
        r = _run("reid", "data/khong-co.mp4")
        assert r.returncode == 2
        assert "x,y,w,h" in r.stdout

    def test_khong_truyen_gi_cung_in_help(self):
        r = _run()
        assert r.returncode == 0 and "DEMO" in r.stdout

    def test_lenh_sai_bao_loi_va_ma_thoat_2(self):
        r = _run("khong-co-lenh-nay")
        assert r.returncode == 2
        assert "không có lệnh" in r.stdout


class TestRunSubcommands:
    def test_env_in_du_thong_tin(self):
        r = _run("env")
        assert r.returncode == 0
        for key in ("repo", "env", "python", "torch", "opencv", "webcam", "GUI"):
            assert key in r.stdout

    def test_cam_la_huong_dan_khong_can_moi_truong(self):
        r = _run("cam")
        assert r.returncode == 0 and "usbipd" in r.stdout

    def test_gpu_in_link_colab(self):
        r = _run("gpu")
        assert r.returncode == 0 and "colab" in r.stdout.lower()

    def test_summary_khong_crash(self):
        assert _run("summary").returncode == 0

    def test_aliases_in_khoi_lenh_tat(self):
        r = _run("aliases")
        assert r.returncode == 0
        assert "alias demo=" in r.stdout and "/.bashrc" in r.stdout
