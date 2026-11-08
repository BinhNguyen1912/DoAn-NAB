"""Test package `src.worker` — dựng lệnh, đọc artifact, quản lý tiến trình.

Không cần model SAM 2, không cần checkpoint, không chạy pipeline thật.
"""

import json
import subprocess

import numpy as np
import pytest

from src.worker import ARTIFACT_NAMES, artifacts, command, is_running, process

BBOX = (10, 20, 30, 40)


def _job(tmp_path):
    job = tmp_path / "20261108-120000-abcdef"
    job.mkdir()
    (job / "source.mp4").write_bytes(b"\x00")
    return job


class TestBuildCommand:
    """Lệnh phải chứa đúng flag mà tools/run_live.py hiểu."""

    def test_co_du_duong_dan_vao_ra(self, tmp_path):
        argv = command.build_command(_job(tmp_path), params={}, bbox=BBOX, repo_root=tmp_path)

        assert argv[0] == "bash" and argv[1] == "-lc"
        cmd = argv[2]
        assert "conda activate samurai" in cmd
        assert "tools/run_live.py" in cmd
        for flag, name in (
            ("--source", "source.mp4"),
            ("--record", "out.mp4"),
            ("--metrics-csv", "metrics.csv"),
            ("--metrics-summary", "summary.json"),
            ("--progress-json", "progress.json"),
        ):
            assert flag in cmd and name in cmd
        assert "--bbox" in cmd and "10,20,30,40" in cmd

    def test_mac_dinh_khong_bat_reid_va_khong_ep_image_size(self, tmp_path):
        cmd = command.build_command(_job(tmp_path), params={}, bbox=BBOX, repo_root=tmp_path)[2]
        assert "--reid" not in cmd
        assert "--image-size" not in cmd
        assert "--max-frames" not in cmd

    def test_reid_cue_object_phai_truyen_ro_vi_mac_dinh_repo_la_face(self, tmp_path):
        cmd = command.build_command(
            _job(tmp_path), params={"reid": True, "cue": "object"}, bbox=BBOX, repo_root=tmp_path
        )[2]
        assert "--reid" in cmd
        assert "--reid-cue object" in cmd

    def test_tham_so_so_duoc_truyen_khi_co(self, tmp_path):
        cmd = command.build_command(
            _job(tmp_path),
            params={"image_size": 256, "max_frames": 40, "max_trajectory": 55},
            bbox=BBOX, repo_root=tmp_path,
        )[2]
        assert "--image-size 256" in cmd
        assert "--max-frames 40" in cmd
        assert "--max-trajectory 55" in cmd

    def test_tham_so_la_bi_bo_qua(self, tmp_path):
        """Khoá lạ không được lọt vào dòng lệnh (chống chèn cờ tuỳ ý)."""
        cmd = command.build_command(
            _job(tmp_path), params={"device": "cuda", "rm": "-rf /"}, bbox=BBOX, repo_root=tmp_path
        )[2]
        assert "cuda" not in cmd
        assert "rm -rf" not in cmd

    def test_duong_dan_co_dau_cach_duoc_quote(self, tmp_path):
        job = tmp_path / "thu muc co dau cach"
        job.mkdir()
        cmd = command.build_command(job, params={}, bbox=BBOX, repo_root=tmp_path)[2]
        assert "'" in cmd              # shlex.quote đã bọc đường dẫn

    def test_python_exe_tuy_chinh(self, tmp_path):
        cmd = command.build_command(
            _job(tmp_path), params={}, bbox=BBOX, python_exe="/usr/bin/python3.11",
            repo_root=tmp_path,
        )[2]
        assert "/usr/bin/python3.11" in cmd


class TestArtifactsDoc:
    def test_progress_chua_co_tra_none(self, tmp_path):
        assert artifacts.read_progress(_job(tmp_path)) is None

    def test_progress_json_hong_tra_none(self, tmp_path):
        job = _job(tmp_path)
        (job / "progress.json").write_text("{ khong phai json", encoding="utf-8")
        assert artifacts.read_progress(job) is None

    def test_progress_thieu_khoa_frames_tra_none(self, tmp_path):
        job = _job(tmp_path)
        (job / "progress.json").write_text(json.dumps({"total": 10}), encoding="utf-8")
        assert artifacts.read_progress(job) is None

    def test_progress_doc_dung_gia_tri(self, tmp_path):
        job = _job(tmp_path)
        (job / "progress.json").write_text(
            json.dumps({"frames": 12, "total": 30, "updated_at": 1.5}), encoding="utf-8"
        )
        prog = artifacts.read_progress(job)
        assert prog["frames"] == 12
        assert prog["total"] == 30

    def test_summary_chua_co_tra_none(self, tmp_path):
        assert artifacts.load_summary(_job(tmp_path)) is None

    def test_summary_doc_duoc(self, tmp_path):
        job = _job(tmp_path)
        (job / "summary.json").write_text(
            json.dumps({"total_frames": 3, "mean_latency_ms": 175.0}), encoding="utf-8"
        )
        assert artifacts.load_summary(job)["total_frames"] == 3

    def test_metrics_chua_co_tra_list_rong(self, tmp_path):
        assert artifacts.load_metrics(_job(tmp_path)) == []

    def test_metrics_doi_kieu_so_va_bool(self, tmp_path):
        job = _job(tmp_path)
        (job / "metrics.csv").write_text(
            "frame_idx,latency_ms,lost\n"
            "0,175.5,false\n"
            "1,180,true\n",
            encoding="utf-8",
        )
        rows = artifacts.load_metrics(job)
        # literal tính tay: 2 dòng dữ liệu
        assert len(rows) == 2
        assert rows[0]["frame_idx"] == 0
        assert rows[0]["latency_ms"] == 175.5
        assert rows[0]["lost"] is False
        assert rows[1]["lost"] is True


class TestArtifactPath:
    def test_chi_cho_ten_trong_whitelist(self, tmp_path):
        job = _job(tmp_path)
        (job / "out.mp4").write_bytes(b"x")
        assert artifacts.artifact_path(job, "out.mp4") is not None
        assert artifacts.artifact_path(job, "bi_mat.txt") is None
        assert artifacts.artifact_path(job, "../job.json") is None
        assert artifacts.artifact_path(job, "sub/out.mp4") is None

    def test_whitelist_gom_6_file_hop_dong(self):
        assert ARTIFACT_NAMES == (
            "out.mp4", "out_web.mp4", "metrics.csv", "summary.json", "run_info.json",
            "worker.log",
        )


class TestProcess:
    def test_proc_none_la_false(self):
        assert is_running(None) is False

    def test_proc_da_ket_thuc_la_false(self):
        proc = subprocess.Popen(["true"])
        proc.wait()
        assert is_running(proc) is False

    def test_doi_tuong_khong_co_poll_la_false(self):
        # CompletedProcess của subprocess.run không có .poll → không được ném AttributeError
        assert is_running(subprocess.run(["true"], check=False)) is False

    def test_start_ghi_log_va_tra_popen(self, tmp_path):
        log = tmp_path / "worker.log"
        proc = process.start(["bash", "-lc", "echo xin-chao"], log_path=log, cwd=tmp_path)
        proc.wait()

        assert proc.returncode == 0
        assert "xin-chao" in log.read_text(encoding="utf-8")

    def test_on_exit_duoc_goi_trong_thread_rieng(self, tmp_path):
        import threading
        import time

        seen = []
        done = threading.Event()

        proc = process.start(["bash", "-lc", "exit 3"], log_path=tmp_path / "l.log")
        process.notify_on_exit(proc, lambda code: (seen.append(code), done.set()))
        assert done.wait(timeout=10) is True
        time.sleep(0.05)
        assert seen == [3]

    def test_loi_trong_callback_khong_lam_chet_thread(self, tmp_path):
        import threading

        done = threading.Event()

        def _boom(_code):
            done.set()
            raise RuntimeError("lỗi cố ý trong callback")

        proc = process.start(["bash", "-lc", "exit 0"], log_path=tmp_path / "l.log")
        process.notify_on_exit(proc, _boom)
        assert done.wait(timeout=10) is True


class TestProgressHookTrongRunLive:
    """Flag --progress-json của CLI dùng hàm ghi atomic."""

    def test_ghi_file_va_doc_lai(self, tmp_path):
        from tools.run_live import _write_progress

        path = tmp_path / "progress.json"
        _write_progress(str(path), 7, 20)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["frames"] == 7
        assert data["total"] == 20
        assert "updated_at" in data
        assert not (tmp_path / "progress.json.tmp").exists()

    def test_path_none_thi_khong_lam_gi(self, tmp_path):
        from tools.run_live import _write_progress

        _write_progress(None, 1, 1)  # không được ném lỗi
        assert list(tmp_path.iterdir()) == []

    def test_khong_truyen_path_thi_khong_can_callback(self):
        from tools.run_live import _progress_callback

        assert _progress_callback(None, 10) is None

    def test_callback_ghi_moi_5_frame_va_luon_tra_true(self, tmp_path):
        from tools.run_live import _progress_callback

        path = tmp_path / "progress.json"
        cb = _progress_callback(str(path), 30)

        class _R:
            def __init__(self, i):
                self.frame_idx = i

        for i in range(4):
            assert cb(np.zeros((2, 2, 3), np.uint8), _R(i)) is True
        assert not path.exists()          # 4 frame chưa tới mốc 5
        assert cb(np.zeros((2, 2, 3), np.uint8), _R(4)) is True
        assert json.loads(path.read_text(encoding="utf-8"))["frames"] == 5


@pytest.mark.parametrize("source", [0, "rtsp://cam/stream", "khong/ton/tai.mp4"])
def test_total_frames_hint_chi_tin_file_that(source):
    """Webcam/RTSP/đường dẫn không tồn tại → không được đoán tổng số frame."""
    from tools.run_live import _total_frames_hint

    assert _total_frames_hint(source) is None


class TestWebExport:
    """Bản ghi mp4v của OpenCV không phát được trên Chrome → phải xuất thêm bản H.264."""

    def test_ten_artifact_co_ban_web(self):
        assert "out_web.mp4" in ARTIFACT_NAMES

    def test_find_ffmpeg_uu_tien_bien_moi_truong(self, tmp_path, monkeypatch):
        from src.worker import web_export

        fake = tmp_path / "ffmpeg-gia"
        fake.write_text("#!/bin/sh\n", encoding="utf-8")
        monkeypatch.setenv(web_export.FFMPEG_ENV, str(fake))
        assert web_export.find_ffmpeg() == str(fake)

    def test_lenh_chuyen_ma_dung_h264_cho_web(self, tmp_path):
        from src.worker import web_export

        cmd = web_export.build_transcode_command("ffmpeg", tmp_path / "a.mp4", tmp_path / "b.mp4")
        assert cmd[0] == "ffmpeg"
        assert "libx264" in cmd
        assert "yuv420p" in cmd          # Chrome/Safari không giải mã yuv444p
        assert "+faststart" in cmd       # phát được ngay, không cần tải hết file

    def test_src_khong_ton_tai_tra_none(self, tmp_path):
        from src.worker import web_export

        assert web_export.transcode_for_web(tmp_path / "khong-co.mp4") is None

    def test_thieu_ffmpeg_thi_tra_none_khong_no(self, tmp_path, monkeypatch):
        from src.worker import web_export

        monkeypatch.setattr(web_export, "find_ffmpeg", lambda: None)
        src = tmp_path / "out.mp4"
        src.write_bytes(b"x")
        assert web_export.transcode_for_web(src) is None

    def test_chuyen_ma_that_tao_ra_file_h264(self, tmp_path, write_video):
        """Chuyển mã thật (mp4v → H.264) — bỏ qua nếu máy không có ffmpeg."""
        from src.worker import web_export

        if web_export.find_ffmpeg() is None:
            pytest.skip("máy không có ffmpeg (imageio-ffmpeg/PATH)")

        frames = np.full((6, 48, 64, 3), 90, np.uint8)
        src = write_video(tmp_path / "out.mp4", frames, fps=10)
        result = web_export.transcode_for_web(src, ffmpeg=web_export.find_ffmpeg())

        assert result is not None
        import cv2

        cap = cv2.VideoCapture(result)
        try:
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, "little")
            # ffmpeg ghi tag 'avc1' hoặc 'h264' tuỳ bản; cả hai đều là H.264.
            # Bằng chứng thật sự là Chrome giải mã được — xem scripts/e2e_web.js.
            assert fourcc in (b"avc1", b"h264"), f"phải là H.264, nhận {fourcc!r}"
        finally:
            cap.release()


class TestAdapterDangHoanTat:
    """Adapter thật: trong lúc xuất H.264, job phải được coi là ĐANG CHẠY."""

    def test_xuat_ban_h264_van_tinh_la_dang_chay(self, tmp_path, monkeypatch):
        import threading
        import time

        from src.api.adapters import subprocess_runner as adapter

        gate = threading.Event()
        finished = []

        class _Proc:
            def wait(self):
                return 0

            def poll(self):
                return 0

        monkeypatch.setattr(adapter, "start", lambda *a, **k: _Proc())
        monkeypatch.setattr(adapter, "transcode_for_web", lambda src: (gate.wait(5), str(src))[1])

        runner = adapter.SubprocessPipelineRunner(tmp_path)
        job_dir = tmp_path / "20261108-120000-abcdef"
        job_dir.mkdir()
        (job_dir / "out.mp4").write_bytes(b"x")

        runner.start("job-1", job_dir, params={}, bbox=(0, 0, 4, 4),
                     on_exit=lambda code: finished.append(code))

        # chờ tới khi luồng nền đã vào bước xuất bản (đang chặn ở gate)
        deadline = time.time() + 5
        while time.time() < deadline and runner._finalizing.__len__() == 0:  # noqa: SLF001
            time.sleep(0.01)
        assert runner.is_running("job-1") is True     # đang xuất H.264

        gate.set()
        deadline = time.time() + 5
        while time.time() < deadline and not finished:
            time.sleep(0.01)
        assert finished == [0]
        assert runner.is_running("job-1") is False     # xong hẳn
