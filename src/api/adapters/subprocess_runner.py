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
    OUT_NAME,
    artifact_path,
    build_command,
    is_running,
    load_summary,
    notify_on_exit,
    read_progress,
    start,
    transcode_for_web,
)


class SubprocessPipelineRunner(PipelineRunner):
    """Chạy `tools/run_live.py` trong conda env bằng subprocess (CPU, không cần GPU)."""

    def __init__(self, repo_root: Path, *, python_exe: str | None = None) -> None:
        self._repo_root = Path(repo_root)
        self._python = python_exe
        self._procs: dict = {}
        # Job đã hết tiến trình nhưng còn đang xuất bản H.264 → vẫn coi là ĐANG CHẠY.
        # Nếu không tách cờ này, UI thấy summary.json là báo "done" khi chưa có out_web.mp4
        # → Chrome không phát được video (bug thật bắt bởi E2E 08-11).
        self._finalizing: set = set()
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
            self._finalizing.discard(job_id)
        if on_exit is not None:
            notify_on_exit(proc, lambda code: self._finish(job_id, Path(job_dir), on_exit, code))
        return proc

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._finalizing:
                return True          # còn xuất bản H.264 → job CHƯA xong
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

    def _finish(self, job_id: str, job_dir: Path, on_exit, code: int) -> None:
        """Quên tiến trình, xuất bản H.264 cho web, rồi mới báo cho tầng trên.

        Lưu ý: bản ghi của OpenCV là mp4v — Chrome KHÔNG giải mã được (đo 08-11: canPlayType
        trả "", videoWidth=0). Chuyển mã thất bại chỉ ghi log, KHÔNG làm job thất bại: frontend
        sẽ lùi về cho tải `out.mp4` về xem bằng VLC.
        """
        with self._lock:
            self._finalizing.add(job_id)
        if code == 0:
            self._export_web(job_dir)
        with self._lock:
            self._finalizing.discard(job_id)
            self._procs.pop(job_id, None)
        on_exit(code)

    @staticmethod
    def _export_web(job_dir: Path) -> None:
        """Tạo `out_web.mp4` (H.264) từ `out.mp4`; lỗi được ghi vào worker.log."""
        source = job_dir / OUT_NAME
        if not source.is_file():
            return
        result = transcode_for_web(source)
        try:
            with open(job_dir / LOG_NAME, "a", encoding="utf-8") as log:
                if result:
                    log.write("[web] đã tạo bản H.264 cho trình duyệt: out_web.mp4\n")
                else:
                    log.write("[web] KHÔNG tạo được bản H.264 (thiếu ffmpeg?) — "
                              "trình duyệt có thể không phát được out.mp4 (codec mp4v)\n")
        except OSError:
            pass
