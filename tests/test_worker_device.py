"""
Test đường `device` (cpu | cuda) đi qua ĐƯỜNG LIVE — worker + adapter web.

Vì sao có: 11-11 phát hiện `tools/live_worker.py` gọi `TrackerEngine.build_default(image_size=...)`
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
        """Mặc định repo là CPU: không đặt `$CAMERA_AI_DEVICE` thì argv không có `--device`."""
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
    """Cái lỗ 11-11: `build_default()` được gọi mà THIẾU `device` ⇒ máy GPU vẫn chạy CPU.

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
        assert ghi.get("device") == "cuda", "thiếu `device` ⇒ máy GPU vẫn chạy CPU (lỗi 11-11)"

    def test_mac_dinh_la_cpu(self, monkeypatch, tmp_path):
        ghi = self._chay(monkeypatch, tmp_path)
        assert ghi.get("device") == "cpu"


@pytest.mark.skipif(subprocess.run([sys.executable, "-c",
                                    "import torch,sys; sys.exit(0 if torch.cuda.is_available() "
                                    "else 1)"], capture_output=True).returncode == 0,
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
