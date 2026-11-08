"""
Quản lý tiến trình con — chỉ biết subprocess, không biết pipeline là gì.

Chức năng: khởi chạy argv ở nền, ghi log ra file, báo returncode qua callback trong thread riêng.
Input  : argv (từ src.worker.command), đường dẫn log, cwd.
Output : subprocess.Popen; hàm kiểm tra còn chạy hay không.
Lưu ý  : dùng start_new_session để dừng server không kéo theo việc kill oan tiến trình con.
"""

import subprocess
import threading
from pathlib import Path


def start(argv: list[str], *, log_path, cwd=None) -> subprocess.Popen:
    """Chạy argv ở nền; stdout+stderr gộp vào `log_path` (chế độ append)."""
    log_file = open(Path(log_path), "ab")
    try:
        return subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd is not None else None,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        # Popen đã dup file descriptor → đóng bản của cha để không giữ khoá file
        log_file.close()


def notify_on_exit(proc: subprocess.Popen, on_exit) -> None:
    """Gọi `on_exit(returncode)` trong thread riêng sau khi tiến trình kết thúc.

    Lưu ý: lỗi bên trong callback bị nuốt — callback của tầng trên không được làm chết thread.
    """
    if on_exit is None:
        return

    def _wait() -> None:
        rc = proc.wait()
        try:
            on_exit(rc)
        except Exception:  # noqa: BLE001 — cố ý: không để callback làm chết thread nền
            pass

    threading.Thread(target=_wait, daemon=True).start()


def is_running(proc) -> bool:
    """True nếu tiến trình còn chạy; None hoặc đối tượng không có `poll` → False."""
    if proc is None:
        return False
    poll = getattr(proc, "poll", None)
    if not callable(poll):
        return False
    return poll() is None
