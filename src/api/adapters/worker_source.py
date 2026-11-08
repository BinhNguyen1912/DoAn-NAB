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

import logging
import os
import shutil
import signal
import time
from pathlib import Path

from src.api.domain import LiveTelemetry, SourceUnavailable
from src.api.ports import FrameSource
from src.live_tracking import BBOX_NAME, FRAME_NAME, STATE_ERROR, STATUS_NAME
from src.worker import LOG_NAME, REPO_ROOT, build_live_worker_command, start as start_process

logger = logging.getLogger("doan.api.worker_source")

DEFAULT_LIVE_DIR = "/dev/shm/doan-live"
LIVE_DIR_ENV = "DOAN_LIVE_DIR"

# File do adapter quản lý trong thư mục live (dọn trước mỗi phiên để không đọc nhầm của phiên cũ)
PID_NAME = "worker.pid"
_OWNED_FILES = (FRAME_NAME, STATUS_NAME, BBOX_NAME, PID_NAME, "status.json.tmp",
                "frame.jpg.tmp", LOG_NAME)


def live_dir() -> Path:
    """Thư mục chia sẻ giữa worker và API (mặc định tmpfs, đổi bằng DOAN_LIVE_DIR)."""
    override = os.environ.get(LIVE_DIR_ENV)
    if override:
        return Path(override)
    return Path(DEFAULT_LIVE_DIR) if Path("/dev/shm").is_dir() else Path(REPO_ROOT) / "data" / "live"


class WorkerFrameSource(FrameSource):
    """Frame có bám đối tượng: worker chạy model, adapter chỉ đọc file mới nhất."""

    def __init__(self, source: str, *, bbox=None, image_size: int | None = None,
                 max_fps: float = 30.0, vos_every: int | None = None,
                 mask_smoothing: float | None = None, out_dir=None,
                 python_exe: str | None = None, startup_timeout: float = 240.0) -> None:
        self._source = str(source)
        self._bbox = tuple(int(v) for v in bbox) if bbox else None
        self._image_size = image_size
        self._max_fps = max_fps
        self._vos_every = vos_every
        self._mask_smoothing = mask_smoothing
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
            max_fps=self._max_fps, vos_every=self._vos_every,
            mask_smoothing=self._mask_smoothing,
            python_exe=self._python, repo_root=REPO_ROOT,
        )
        self._proc = start_process(argv, log_path=self._log, cwd=REPO_ROOT)
        try:
            (self._out / PID_NAME).write_text(str(self._proc.pid), encoding="utf-8")
        except OSError:                              # không ghi được pidfile thì vẫn chạy
            logger.warning("không ghi được %s", PID_NAME)
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
        finally:
            (self._out / PID_NAME).unlink(missing_ok=True)

    @property
    def label(self) -> str:
        return f"bám-đối-tượng:{self._source}"

    # ------------------------------------------------------------------ LiveTelemetrySource

    def telemetry(self) -> LiveTelemetry:
        """Số liệu worker ghi ra status.json: nhịp mask thật + độ ổn định + độ trễ.

        Vì sao cần: FPS phát (30) không nói gì về việc **mask có mới hay không** — worker chạy
        model ~8,5 lần/giây và nội suy phần còn lại. UI phải hiện đúng hai con số này.
        """
        status = _read_status(self._out / STATUS_NAME)
        return LiveTelemetry(
            display_fps=float(status.get("measured_fps") or 0.0),
            mask_fps=float(status.get("vos_fps") or 0.0),
            stability=float(status.get("stability") or 0.0),
            latency_ms=float(status.get("vos_ms") or 0.0),
            lk_ms=float(status.get("lk_ms") or 0.0),
            empty_runs=int(status.get("empty_runs") or 0),
        )

    # ------------------------------------------------------------------ nội bộ

    def _prepare_dir(self) -> None:
        """Reap worker của phiên TRƯỚC rồi mới dọn file.

        Vì sao: `./run api` chạy uvicorn `--reload`, mỗi lần lưu file API chết nhưng worker SAM 2
        (start_new_session) sống tiếp và **ghi đè frame.jpg** — phiên mới sẽ `_wait_first_frame`
        thấy frame của worker cũ, báo "running" bằng ảnh của phiên trước, và hai worker cùng ghi
        một file. Đã xác nhận bằng đọc mã (review độc lập 08-11).
        """
        self._out.mkdir(parents=True, exist_ok=True)
        self._reap_stale_worker()
        for name in _OWNED_FILES:
            (self._out / name).unlink(missing_ok=True)

    def _reap_stale_worker(self) -> None:
        """Kill worker cũ nếu pidfile còn sống và ĐÚNG là worker live của CHÍNH thư mục này.

        Chốt an toàn (review độc lập 08-11 chỉ ra bản đầu quá lỏng — `killpg` có thể giết cả
        nhóm tiến trình của API):
        1. bỏ qua pidfile hỏng/pid <= 0/pid của chính mình;
        2. `/proc/<pid>/cmdline` phải có **một phần tử argv** đúng tên `live_worker.py`
           (không dùng substring: `grep live_worker`, `vim tools/live_worker.py` cũng khớp);
        3. argv phải chứa `--out-dir <self._out>` ⇒ không giết worker của instance khác;
        4. pid phải là **session leader** (`getsid(pid) == pid`, nhờ `start_new_session=True`)
           và **không** cùng process group với API ⇒ `killpg` không bao giờ chạm nhóm của mình.
        """
        pid = _read_pid(self._out / PID_NAME)
        if pid is None or pid == os.getpid():
            return
        argv = _read_cmdline(pid)
        if not argv or not _is_our_live_worker(argv, self._out):
            return
        try:
            if os.getsid(pid) != pid or os.getpgid(pid) == os.getpgid(0):
                return                              # không phải session leader của riêng nó
        except OSError:
            return
        logger.warning("dọn worker live còn sót của phiên trước: pid=%s", pid)
        self._terminate_process(pid)

    @staticmethod
    def _terminate_process(pid: int) -> None:
        """SIGTERM rồi SIGKILL sau 2 s (không chờ quá lâu: zombie cũng tính là đã chết)."""
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                return
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if not _pid_alive(pid):
                return
            time.sleep(0.05)
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

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


def _read_pid(path: Path):
    """Đọc pidfile; None nếu chưa có/hỏng."""
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None


def _read_cmdline(pid: int) -> list[str]:
    """argv của tiến trình (tách theo NUL); [] nếu không đọc được."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [part for part in raw.decode("utf-8", "replace").split("\0") if part]


def _is_our_live_worker(argv, out_dir: Path) -> bool:
    """Đúng worker live của thư mục `out_dir`? (so khớp argv, KHÔNG dùng substring)."""
    names = {Path(arg).name for arg in argv}
    if "live_worker.py" not in names:
        return False
    for index, arg in enumerate(argv):
        if arg == "--out-dir" and index + 1 < len(argv):
            try:
                return Path(argv[index + 1]).resolve() == Path(out_dir).resolve()
            except OSError:
                return False
    return False


def _pid_alive(pid: int) -> bool:
    """Còn sống thật? Zombie (`/proc` vẫn tồn tại) phải tính là ĐÃ CHẾT."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return False
    return state != "Z"


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
