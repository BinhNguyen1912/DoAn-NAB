"""
Test đường `device` (cpu | cuda) đi qua ĐƯỜNG LIVE — worker + adapter web.

Vì sao có: 10-11 phát hiện `tools/live_worker.py` gọi `TrackerEngine.build_default(image_size=...)`
**không** truyền `device` ⇒ dù máy có GPU, phiên live qua web vẫn chạy model trên CPU. Ba chỗ phải
khớp nhau, nếu lệch thì im lặng chạy CPU (số FPS trong báo cáo bị gán sai thiết bị):
  CLI worker (`--device`) ← `src/worker/command.py` ← `WorkerFrameSource` ← `$CAMERA_AI_DEVICE`.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.api.adapters import worker_source as ws
from src.worker import build_live_worker_command

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestLenhWorker:
    def test_truyen_device_cuda(self, tmp_path):
        joined = " ".join(build_live_worker_command("0", tmp_path, device="cuda",
                                                    repo_root=tmp_path))
        assert "--device cuda" in joined

    def test_khong_truyen_thi_de_cli_mac_dinh(self, tmp_path):
        """`None` = không ghi cờ ⇒ worker dùng mặc định cpu (không ghi đè bằng chuỗi rỗng)."""
        joined = " ".join(build_live_worker_command("0", tmp_path, repo_root=tmp_path))
        assert "--device" not in joined

    def test_ten_la_bi_tu_choi_truoc_khi_dung_lenh(self, tmp_path):
        """Typo phải nổ ngay ở đây, KHÔNG lọt xuống worker rồi chết giữa lúc nạp model."""
        with pytest.raises(ValueError, match="device phải là"):
            build_live_worker_command("0", tmp_path, device="gpu", repo_root=tmp_path)


class TestAdapterChuyenTiep:
    """`WorkerFrameSource` phải đưa `device` vào đúng argv của worker (không rơi mất trên đường)."""

    @pytest.fixture
    def bat_lenh(self, monkeypatch):
        """Chặn việc chạy tiến trình thật; trả về list argv đã dựng + không chờ frame đầu."""
        da_dung = []

        class _ProcGia:
            pid = 4242

            def poll(self):
                return None

        def _start(argv, **_kw):
            da_dung.append(argv)
            return _ProcGia()

        monkeypatch.setattr(ws, "start_process", _start)
        monkeypatch.setattr(ws.WorkerFrameSource, "_wait_first_frame", lambda self: None)
        return da_dung

    def test_cuda_vao_argv(self, tmp_path, bat_lenh):
        source = ws.WorkerFrameSource("0", bbox=(1, 2, 3, 4), device="cuda", out_dir=tmp_path,
                                      python_exe=sys.executable)
        source.start()
        joined = " ".join(bat_lenh[0])
        assert "--device cuda" in joined

    def test_mac_dinh_khong_ghi_co_device(self, tmp_path, bat_lenh):
        """Constructor nhận `None` = KHÔNG ghi cờ (worker tự dùng mặc định cpu).

        Nhánh production thì `device_from_env()` trả `"cpu"` (có cờ) — xem
        `TestCompositionRoot::test_env_trong_van_ghi_device_cpu`.
        """
        source = ws.WorkerFrameSource("0", bbox=(1, 2, 3, 4), out_dir=tmp_path,
                                      python_exe=sys.executable)
        source.start()
        assert "--device" not in " ".join(bat_lenh[0])

    def test_ten_la_no_truoc_khi_chay_tien_trinh(self, tmp_path, bat_lenh):
        source = ws.WorkerFrameSource("0", bbox=(1, 2, 3, 4), device="gpu", out_dir=tmp_path,
                                      python_exe=sys.executable)
        with pytest.raises(ValueError, match="device phải là"):
            source.start()
        assert bat_lenh == [], "không được chạy worker khi tham số đã sai"


class TestWiringEngine:
    """Cái lỗ 10-11: `build_default()` được gọi mà THIẾU `device` ⇒ máy GPU vẫn chạy CPU.

    Chặn `TrackerEngine.build_default` để bắt đúng kwargs rồi dừng `main()` ngay (không nạp
    checkpoint), nhờ vậy test chạy được trên máy không có GPU mà vẫn kiểm được nhánh `cuda`.
    """

    def _bat_kwargs(self, monkeypatch):
        import src.tracker_engine as te
        import tools.live_worker as lw

        ghi = {}

        def build_default(**kwargs):
            ghi.update(kwargs)
            raise SystemExit(0)          # dừng trước khi chạy phiên (không cần checkpoint)

        monkeypatch.setattr(te.TrackerEngine, "build_default", staticmethod(build_default))
        monkeypatch.setattr(lw, "_cuda_available", lambda: True)   # giả lập máy có GPU
        return lw, ghi

    def _chay(self, monkeypatch, tmp_path, *extra):
        lw, ghi = self._bat_kwargs(monkeypatch)
        monkeypatch.setattr(sys, "argv", [
            "live_worker.py", "--source", "data/_gui_test.mp4",
            "--out-dir", str(tmp_path / "live"), *extra])
        with pytest.raises(SystemExit):
            lw.main()
        return ghi

    def test_truyen_device_xuong_engine(self, monkeypatch, tmp_path):
        ghi = self._chay(monkeypatch, tmp_path, "--device", "cuda")
        assert ghi.get("device") == "cuda", "thiếu `device` ⇒ máy GPU vẫn chạy CPU (lỗi 10-11)"

    def test_mac_dinh_la_cpu(self, monkeypatch, tmp_path):
        ghi = self._chay(monkeypatch, tmp_path)
        assert ghi.get("device") == "cpu"


class TestCompositionRoot:
    """Hop DUY NHẤT không có test trước review 10-11: `build_default_live()` đọc env rồi truyền
    xuống `WorkerFrameSource`. Xoá `device=device` ở đó ⇒ 782 test vẫn xanh và đường live quay lại
    chạy CPU (đúng lỗi gốc tái phát), nên phải khoá bằng test ở chính composition root.
    """

    def _bat_source(self, monkeypatch):
        import src.api.main as main

        ghi = {}

        class _SourceGia:
            label = "giả"

            def __init__(self, source, **kwargs):
                ghi.update(kwargs, source=source)

        monkeypatch.setattr(main, "WorkerFrameSource", _SourceGia)
        return main, ghi

    def test_env_cuda_duoc_truyen_xuong_worker(self, monkeypatch):
        main, ghi = self._bat_source(monkeypatch)
        monkeypatch.setenv("CAMERA_AI_DEVICE", "cuda")
        live = main.build_default_live()
        live._make_source("0", "track", (1, 2, 3, 4), 192, 3, None)
        assert ghi["device"] == "cuda", "env không tới được worker ⇒ GPU bị bỏ qua im lặng"

    def test_mac_dinh_la_cpu(self, monkeypatch):
        main, ghi = self._bat_source(monkeypatch)
        monkeypatch.delenv("CAMERA_AI_DEVICE", raising=False)
        live = main.build_default_live()
        live._make_source("0", "track", (1, 2, 3, 4), 192, 3, None)
        assert ghi["device"] == "cpu"

    def test_env_go_sai_no_ngay_luc_khoi_dong(self, monkeypatch):
        main, _ghi = self._bat_source(monkeypatch)
        monkeypatch.setenv("CAMERA_AI_DEVICE", "gpu")
        with pytest.raises(ValueError, match="device phải là"):
            main.build_default_live()

    def test_env_trong_van_ghi_device_cpu(self, monkeypatch, tmp_path):
        """Env trống ⇒ `device_from_env()` trả `"cpu"` ⇒ lệnh job **có** `--device cpu`.

        Câu cũ trong docstring một test khác ("không đặt env thì argv không có `--device`") chỉ đúng
        cho nhánh constructor nhận `None` — nhánh production không đi qua đó (P2 review 10-11).
        Giá trị `cpu` trùng mặc định `configs/default.yaml` nên hành vi không đổi.
        """
        import src.api.main as main

        ghi = {}

        class _RunnerGia:
            def __init__(self, repo_root, **kwargs):
                ghi.update(kwargs)

        monkeypatch.setattr(main, "SubprocessPipelineRunner", _RunnerGia)
        monkeypatch.delenv("CAMERA_AI_DEVICE", raising=False)
        main.build_default_service(main.ApiSettings(jobs_root=tmp_path))
        assert ghi["device"] == "cpu"

    def test_job_upload_cung_theo_thiet_bi(self, monkeypatch, tmp_path):
        """`build_default_service()` cũng phải truyền thiết bị (job tải video lên)."""
        import src.api.main as main

        ghi = {}

        class _RunnerGia:
            def __init__(self, repo_root, **kwargs):
                ghi.update(kwargs)

        monkeypatch.setattr(main, "SubprocessPipelineRunner", _RunnerGia)
        monkeypatch.setenv("CAMERA_AI_DEVICE", "cuda")
        main.build_default_service(main.ApiSettings(jobs_root=tmp_path))
        assert ghi["device"] == "cuda"


class TestJobTaiVideoLen:
    """Job `POST /api/jobs` (tải video lên → track → trả mp4) cũng phải chạy được trên GPU.

    Trước 10-11 `SubprocessPipelineRunner` dựng lệnh mà không có `--device` ⇒ trên máy GPU, job
    xuất video vẫn chạy CPU (155 ms/frame @256) trong khi người dùng tưởng đang dùng GPU.
    """

    def test_runner_truyen_device_vao_lenh(self, tmp_path, monkeypatch):
        from src.api.adapters import subprocess_runner as sr

        da_dung = []

        class _ProcGia:
            pid = 4242

            def poll(self):
                return None

        monkeypatch.setattr(sr, "start", lambda argv, **_kw: (da_dung.append(argv), _ProcGia())[1])
        runner = sr.SubprocessPipelineRunner(tmp_path, device="cuda", python_exe=sys.executable)
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        runner.start("j1", job_dir, params={}, bbox=(1, 2, 3, 4))
        assert "--device cuda" in " ".join(da_dung[0])

    def test_mac_dinh_khong_ghi_co_device(self, tmp_path, monkeypatch):
        from src.api.adapters import subprocess_runner as sr

        class _ProcGia:
            pid = 4242

            def poll(self):
                return None

        da_dung = []
        monkeypatch.setattr(sr, "start",
                            lambda argv, **_kw: (da_dung.append(argv), _ProcGia())[1])
        runner = sr.SubprocessPipelineRunner(tmp_path, python_exe=sys.executable)
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        runner.start("j1", job_dir, params={}, bbox=(1, 2, 3, 4))
        assert "--device" not in " ".join(da_dung[0])


def _cuda_co_san() -> bool:
    """Có CUDA không — tính MỘT lần (import torch ~1–3 s; đừng chạy ở mỗi lần collect)."""
    cache = getattr(_cuda_co_san, "_cache", None)
    if cache is None:
        try:
            proc = subprocess.run(
                [sys.executable, "-c",
                 "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)"],
                capture_output=True, timeout=60)
            cache = proc.returncode == 0
        except (subprocess.SubprocessError, OSError):
            # Không để pha COLLECT nổ (TimeoutExpired ⇒ cả module 15 test error thay vì skip gọn).
            cache = False
        _cuda_co_san._cache = cache
    return cache


@pytest.mark.skipif(_cuda_co_san(),
                    reason="máy CÓ CUDA — ca 'xin cuda mà không có GPU' không tái hiện được")
class TestWorkerKhongCoCuda:
    """Xin `cuda` trên máy không có GPU: phải báo lỗi RÕ và KHÔNG nạp checkpoint 156 MB."""

    def test_bao_loi_va_ghi_status_error(self, tmp_path):
        out = tmp_path / "live"
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "live_worker.py"),
             "--source", "0", "--out-dir", str(out), "--device", "cuda"],
            capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT))
        assert proc.returncode == 2, proc.stderr
        assert "GPU CUDA" in (proc.stdout + proc.stderr)
        status = json.loads((out / "status.json").read_text(encoding="utf-8"))
        assert status["state"] == "error"
        assert "GPU CUDA" in status["message"], \
            "lý do phải tới được UI/watchdog, không chỉ nằm trong console"
