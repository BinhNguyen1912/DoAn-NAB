"""
Adapter chạy pipeline bằng subprocess — hiện thực `PipelineRunner`.

Chức năng: dựng lệnh (src.worker.command), chạy nền, giữ bảng tiến trình đang sống (thread-safe),
           đọc progress/summary/artifact qua src.worker.artifacts.
Input  : job_id, job_dir, params, bbox, on_exit.
Output : trạng thái chạy + dữ liệu kết quả.
Lưu ý  : bảng tiến trình là THUỘC TÍNH CỦA INSTANCE (không phải biến global) — nhờ vậy test
         tiêm được, và nhiều runner độc lập không giẫm lên nhau.
         Đổi sang GPU worker (Modal/RunPod) = viết class khác cùng chữ ký, không sửa service.
"""

import threading
from pathlib import Path

from src.api.ports import PipelineRunner
from src.worker import (
    ARTIFACT_NAMES,
    LOG_NAME,
    artifact_path,
    build_command,
    is_running,
    load_summary,
    notify_on_exit,
    read_progress,
    start,
)


class SubprocessPipelineRunner(PipelineRunner):
    """Chạy `tools/run_live.py` trong conda env bằng subprocess (CPU, không cần GPU)."""

    def __init__(self, repo_root: Path, *, python_exe: str | None = None) -> None:
        self._repo_root = Path(repo_root)
        self._python = python_exe
        self._procs: dict = {}
        self._lock = threading.Lock()

    def start(self, job_id: str, job_dir: Path, *, params: dict, bbox,
              on_exit=None):
        argv = build_command(
            job_dir, params=params, bbox=bbox,
            python_exe=self._python, repo_root=self._repo_root,
        )
        proc = start(argv, log_path=Path(job_dir) / LOG_NAME, cwd=self._repo_root)
        with self._lock:
            self._procs[job_id] = proc
        if on_exit is not None:
            notify_on_exit(proc, lambda code: self._finish(job_id, on_exit, code))
        return proc

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            proc = self._procs.get(job_id)
        return is_running(proc)

    def artifact_names(self) -> tuple:
        return tuple(ARTIFACT_NAMES)

    def read_progress(self, job_dir: Path):
        return read_progress(job_dir)

    def load_summary(self, job_dir: Path):
        return load_summary(job_dir)

    def artifact_path(self, job_dir: Path, name: str):
        return artifact_path(job_dir, name)

    def _finish(self, job_id: str, on_exit, code: int) -> None:
        """Quên tiến trình rồi mới báo cho tầng trên (tránh is_running trả True trong callback)."""
        with self._lock:
            self._procs.pop(job_id, None)
        on_exit(code)
