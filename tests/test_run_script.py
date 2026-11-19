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
                    "reid", "demobase"):
            assert cmd in r.stdout, f"thiếu lệnh '{cmd}' trong help"

    def test_reid_thieu_tham_so_bao_loi_ro_rang(self):
        """`./run reid` cần video + bbox; thiếu thì báo lỗi dễ hiểu, mã thoát 2."""
        r = _run("reid", "data/khong-co.mp4")
        assert r.returncode == 2
        assert "x,y,w,h" in r.stdout

    def test_fast_nhan_co_thay_vi_lam_nguon(self):
        """Bug thật 27-10: `./run fast --reid-cue object` ăn "--reid-cue" làm nguồn → argparse báo lỗi.

        Dùng `--help` để kiểm headless (argparse thoát trước khi mở cửa sổ).
        """
        r = _run("fast", "--help")
        assert r.returncode == 0
        assert "unrecognized arguments" not in (r.stdout + r.stderr)
        assert "--reid-cue" in r.stdout          # cờ được chuyển tiếp nguyên vẹn

    def test_view_nhan_co_thay_vi_lam_nguon(self):
        r = _run("view", "--help")
        assert r.returncode == 0
        assert "unrecognized arguments" not in (r.stdout + r.stderr)

    def test_video_nhan_co_thay_vi_lam_nguon(self):
        """Bug 27-10 còn sót ở `video`: `./run video --device cuda` từng ăn "--device" làm nguồn
        ⇒ argparse lỗi. Review độc lập 10-11 bắt đúng lúc viết tài liệu chạy GPU."""
        r = _run("video", "--help")
        assert r.returncode == 0
        assert "unrecognized arguments" not in (r.stdout + r.stderr)

    def test_fast_tu_ghi_video_co_moc_thoi_gian(self):
        """Bug thật 29-10: `./run fast` không ghi file → người dùng tưởng đã lưu video."""
        r = _run("fast", "--help")          # --help thoát trước khi mở cửa sổ
        assert r.returncode == 0
        assert "[fast] ghi: data/fast_" in r.stdout

    def test_fast_mac_dinh_bam_VAT_khong_phai_mat(self):
        """Bug thật 01-11: `./run fast` để cue=face → test bằng VẬT thì re-ID có 0 mẫu mặt,
        không bao giờ nhận lại (đo: 201 frame, 180 mất dấu, reid_score = -1 suốt phiên).
        `fast` là lệnh test nhanh nên mặc định phải bám VẬT; `--reid-cue` của người dùng vẫn đè được."""
        r = _run("fast", "--help")
        assert r.returncode == 0
        assert "cue=object" in r.stdout

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

    def test_summary_p95_null_khong_crash(self, tmp_path, monkeypatch):
        """Ticket #32 (P1 review 17-11): summary có `p95_latency_ms: null` từng làm `./run summary`
        ném `TypeError: unsupported format string passed to NoneType.__format__` — `.get(k, 0)` chỉ
        cứu khi THIẾU khoá, không cứu `null`. Chết giữa vòng lặp ⇒ các file sau không được in.
        """
        import json

        # `./run` tự `cd "$ROOT"` nên `monkeypatch.chdir` KHÔNG đủ ⇒ dùng `DOAN_DATA_DIR` trỏ vào
        # `tmp_path`: trước đây test ghi file vào `data/` của repo, để lại rác nếu bị kill (timeout 120 s)
        # và không an toàn với `pytest-xdist` (P3 audit sau merge 17-11).
        d = tmp_path / "data"
        d.mkdir()
        (d / "zz_test_null_summary.json").write_text(json.dumps(
            {"total_frames": 3, "mean_latency_ms": 100.0, "p95_latency_ms": None,
             "p95_latency_ms_n": 0, "effective_fps": 10.0, "lost_count": 3}), encoding="utf-8")
        monkeypatch.setenv("DOAN_DATA_DIR", str(d))

        r = _run("summary")
        assert r.returncode == 0, r.stderr
        assert "chưa đo" in r.stdout
        assert sorted(p.name for p in d.glob("*")) == ["zz_test_null_summary.json"], (
            "test không được ghi gì vào `data/` của repo")

    def test_aliases_in_khoi_lenh_tat(self):
        r = _run("aliases")
        assert r.returncode == 0
        assert "alias demo=" in r.stdout and "/.bashrc" in r.stdout


class TestDemobase:
    """`./run demobase` — chạy bản demo cũ trong worktree .baseline/ (dự phòng khi web lỗi).

    Dùng `CAM_BASELINE_DIR` + `CAM_BASELINE_TAG` để test hermetic: không tạo worktree thật,
    không đụng `.baseline/` của máy dev.
    """

    @staticmethod
    def _fake_baseline(tmp_path, tag="fake-tag"):
        """Dựng 'bản cũ' giả: thư mục có `run` in ra lệnh con + tham số nó nhận."""
        base = tmp_path / "baseline"
        base.mkdir()
        run = base / "run"
        run.write_text('#!/usr/bin/env bash\necho "SUB=$1"\nshift || true\nfor a in "$@"; do echo "ARG=$a"; done\n')
        run.chmod(0o755)
        (base / ".demobase-tag").write_text(tag)
        return base

    def _run_env(self, *args, **env_extra):
        import os
        env = {**os.environ, **env_extra}
        return subprocess.run(["bash", ROOT_RUN, *args], capture_output=True, text=True,
                              timeout=60, env=env)

    def test_mac_dinh_lay_demoip(self, tmp_path):
        base = self._fake_baseline(tmp_path)
        r = self._run_env("demobase", CAM_BASELINE_DIR=str(base), CAM_BASELINE_TAG="fake-tag")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "SUB=demoip" in r.stdout

    def test_tham_so_di_nguyen_vao_lenh_con(self, tmp_path):
        base = self._fake_baseline(tmp_path, tag="fake-tag")
        r = self._run_env("demobase", "demoip", "--max-frames", "5",
                          CAM_BASELINE_DIR=str(base), CAM_BASELINE_TAG="fake-tag")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "SUB=demoip" in r.stdout
        assert "ARG=--max-frames" in r.stdout and "ARG=5" in r.stdout

    def test_lenh_con_tu_chon(self, tmp_path):
        base = self._fake_baseline(tmp_path, tag="fake-tag")
        r = self._run_env("demobase", "video", "data/binh1.mp4",
                          CAM_BASELINE_DIR=str(base), CAM_BASELINE_TAG="fake-tag")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "SUB=video" in r.stdout and "ARG=data/binh1.mp4" in r.stdout

    def test_help_cua_ban_cu_khong_bat_relay(self, tmp_path):
        """`./run demobase -h` phải in help của bản cũ, KHÔNG chạy demoip (không bật relay)."""
        base = self._fake_baseline(tmp_path, tag="fake-tag")
        r = self._run_env("demobase", "-h", CAM_BASELINE_DIR=str(base),
                          CAM_BASELINE_TAG="fake-tag")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "SUB=help" in r.stdout

    def test_tag_khong_ton_tai_bao_loi_ma_1(self, tmp_path):
        """Review độc lập 14-11 (P1): tag lạ + thư mục .baseline rỗng từng bị hai `rev-parse`
        cùng rỗng coi là 'khớp' → chạy code cũ và ghi mark cho tag không tồn tại, thoát 0."""
        base = tmp_path / "baseline"          # CHƯA có code → nhánh dựng mới
        r = self._run_env("demobase", "help", CAM_BASELINE_DIR=str(base),
                          CAM_BASELINE_TAG="khong-co-tag-nay")
        assert r.returncode == 1
        assert "không thấy tag khong-co-tag-nay" in r.stdout, r.stdout
        assert not (base / ".demobase-tag").exists()


class TestRunGt:
    """`./run gt` — lệnh tắt để gán GT thật.

    Vì sao có test: người dùng dán `python scripts/gt_gan_nhanh.py …` vào PowerShell (máy Windows
    KHÔNG có `python`, chỉ alias Microsoft Store) và nhận "Python was not found" — gặp thật 19-11.
    Test này khoá 3 thứ: lệnh tồn tại trong help, chuyển tiếp cờ nguyên vẹn, và có mặt trong danh
    sách lệnh của `run` (nếu ai xoá nhánh xử lý thì đỏ ngay).
    """

    def test_gt_co_trong_help(self):
        r = _run("help")
        assert r.returncode == 0
        assert "gt " in r.stdout or "gt\n" in r.stdout
        assert "bình" in r.stdout.lower() or "tô gt" in r.stdout.lower() or "trình tô" in r.stdout.lower()

    def test_gt_chuyen_tiep_co_nguyen_ven(self):
        """`--clip` đứng trước phải KHÔNG bị ăn làm tham số của `run` (bẫy đã gặp ở `fast`/`view`)."""
        r = _run("gt", "--help")
        assert r.returncode == 0, r.stderr
        assert "unrecognized arguments" not in (r.stdout + r.stderr)
        assert "--nguoi-gan" in r.stdout and "--frames" in r.stdout

    def test_gt_thieu_tham_so_thi_argparse_bao_loi(self):
        r = _run("gt")
        assert r.returncode != 0
        assert "--clip" in (r.stdout + r.stderr)
