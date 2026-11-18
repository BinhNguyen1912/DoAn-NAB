"""Đọc thông tin tiến trình từ `/proc` — một bản duy nhất cho cả adapter API và CLI worker.

Vì sao có module riêng: `tools/live_worker.py` cần biết "thư mục live này đang bị một phiên khác giữ"
(ticket #37), nhưng **không được** import `src.api.adapters.*` (kéo `fastapi`/port vào tiến trình
worker). Ba hàm dưới đây vốn nằm trong `src/api/adapters/worker_source.py`; chuyển ra đây rồi adapter
import lại ⇒ không có bản thứ hai để lệch nhau.

**Chỉ Linux** (`/proc`): trên macOS/Windows `pid_con_song` trả `False` và `read_cmdline` trả `[]`; mọi
guard dựa trên chúng **fail-open** (không chặn). Đừng "sửa" bằng `os.kill(pid, 0)`: trên Windows tín
hiệu 0 = `TerminateProcess` ⇒ **giết** tiến trình đang kiểm (đã ghi ở `scripts/demo_preflight.py`).
"""

from pathlib import Path


def pid_con_song(pid: int) -> bool:
    """Còn sống thật? Zombie (`/proc` vẫn tồn tại) phải tính là ĐÃ CHẾT (ticket #34)."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return False
    return state != "Z"


def read_pid(path) -> int | None:
    """Đọc pidfile; `None` nếu chưa có/hỏng/không phải số dương (KHÔNG ném)."""
    try:
        pid = int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None


def read_cmdline(pid: int) -> list[str]:
    """argv của tiến trình (tách theo NUL); `[]` nếu không đọc được (kể cả không có `/proc`)."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [part for part in raw.decode("utf-8", "replace").split("\0") if part]


def is_live_worker_for(argv, out_dir) -> bool:
    """Đúng worker live của thư mục `out_dir`? (so khớp argv theo PHẦN TỬ, không dùng substring).

    Dùng để chống **PID tái chế**: pidfile cũ trỏ một tiến trình khác đang sống thì không được coi là
    "phiên live đang giữ thư mục" (nếu không, CLI bị chặn vĩnh viễn mà lối thoát duy nhất là tự xoá
    pidfile — `scripts/demo_preflight.py` đã ghi đúng lý do này).
    """
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
