"""
Nguồn frame LIVE có BÁM ĐỐI TƯỢNG: chạy worker model ở tiến trình riêng, đọc frame qua /dev/shm.

Chức năng: hiện thực `FrameSource` nhưng frame do `tools/live_worker.py` sinh ra (đã vẽ mask +
           ô bao + quỹ đạo). API chỉ đọc file `frame.jpg` mới nhất → **không cần import torch**.
Input  : source (0 | rtsp:// | http://snapshot | đường dẫn video), bbox (tuỳ chọn), image_size.
Output : bytes JPEG của frame đã overlay; file trạng thái nằm cùng thư mục.
Lưu ý  : thư mục mặc định là `/dev/shm/doan-live` (tmpfs) — ghi 15–30 ảnh/giây lên /mnt/d (9p)
         sẽ chậm và tạo rác; đổi bằng biến môi trường DOAN_LIVE_DIR.
         Worker nạp model 20–60 s trước khi có frame đầu ⇒ `start()` phải chờ (startup_timeout)
         và kiểm tra `status.json` để báo lỗi sớm thay vì treo.
"""

import os
import shutil
import signal
import time
from pathlib import Path

from src.api.domain import SourceUnavailable
from src.api.ports import FrameSource
from src.live_tracking import BBOX_NAME, FRAME_NAME, STATE_ERROR, STATUS_NAME
from src.worker import LOG_NAME, REPO_ROOT, build_live_worker_command, start as start_process

DEFAULT_LIVE_DIR = "/dev/shm/doan-live"
LIVE_DIR_ENV = "DOAN_LIVE_DIR"

# File do adapter quản lý trong thư mục live (dọn trước mỗi phiên để không đọc nhầm của phiên cũ)
_OWNED_FILES = (FRAME_NAME, STATUS_NAME, BBOX_NAME, "status.json.tmp", "frame.jpg.tmp", LOG_NAME)


def live_dir() -> Path:
    """Thư mục chia sẻ giữa worker và API (mặc định tmpfs, đổi bằng DOAN_LIVE_DIR)."""
    override = os.environ.get(LIVE_DIR_ENV)
    if override:
        return Path(override)
    return Path(DEFAULT_LIVE_DIR) if Path("/dev/shm").is_dir() else Path(REPO_ROOT) / "data" / "live"


class WorkerFrameSource(FrameSource):
    """Frame có bám đối tượng: worker chạy model, adapter chỉ đọc file mới nhất."""

    def __init__(self, source: str, *, bbox=None, image_size: int | None = None,
                 max_fps: float = 15.0, out_dir=None, python_exe: str | None = None,
                 startup_timeout: float = 240.0) -> None:
        self._source = str(source)
        self._bbox = tuple(int(v) for v in bbox) if bbox else None
        self._image_size = image_size
        self._max_fps = max_fps
        self._out = Path(out_dir) if out_dir is not None else live_dir()
        self._python = python_exe
        self._startup_timeout = startup_timeout
        self._proc = None
        self._log = self._out / LOG_NAME

    # ------------------------------------------------------------------ FrameSource

    def start(self) -> None:
        self._prepare_dir()
        if self._bbox is not None:
            self._write_bbox(self._bbox)

        argv = build_live_worker_command(
            self._source, self._out, image_size=self._image_size,
            max_fps=self._max_fps, python_exe=self._python, repo_root=REPO_ROOT,
        )
        self._proc = start_process(argv, log_path=self._log, cwd=REPO_ROOT)
        self._wait_first_frame()

    def read_jpeg(self):
        try:
            return (self._out / FRAME_NAME).read_bytes()
        except OSError:
            return None

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:                              # worker chạy trong session riêng → dừng cả nhóm
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:                 # noqa: BLE001 — không được treo khi dọn dẹp
            proc.kill()

    @property
    def label(self) -> str:
        return f"bám-đối-tượng:{self._source}"

    # ------------------------------------------------------------------ nội bộ

    def _prepare_dir(self) -> None:
        self._out.mkdir(parents=True, exist_ok=True)
        for name in _OWNED_FILES:
            (self._out / name).unlink(missing_ok=True)

    def _write_bbox(self, bbox) -> None:
        import json

        x, y, w, h = bbox
        (self._out / BBOX_NAME).write_text(
            json.dumps({"x": x, "y": y, "w": w, "h": h}), encoding="utf-8"
        )

    def _wait_first_frame(self) -> None:
        """Chờ frame đầu tiên; báo lỗi sớm nếu worker chết hoặc ghi status lỗi."""
        deadline = time.time() + self._startup_timeout
        while time.time() < deadline:
            if (self._out / FRAME_NAME).is_file():
                return
            status = _read_status(self._out / STATUS_NAME)
            if status.get("state") == STATE_ERROR:
                raise SourceUnavailable(str(status.get("message") or "worker báo lỗi"))
            if self._proc is not None and self._proc.poll() is not None:
                raise SourceUnavailable(
                    f"worker dừng khi khởi động (mã {self._proc.returncode}) — xem {self._log}"
                )
            time.sleep(0.1)
        raise SourceUnavailable(
            f"worker không đưa được frame trong {self._startup_timeout:.0f}s — xem {self._log}"
        )


def _read_status(path: Path) -> dict:
    import json

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def reset_live_dir(out_dir=None) -> None:
    """Xoá thư mục live (dùng cho test và khi cần dọn tay)."""
    target = Path(out_dir) if out_dir is not None else live_dir()
    shutil.rmtree(target, ignore_errors=True)
