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


def find_live_workers(proc_root="/proc", exclude_pid: int | None = None) -> list[tuple[int, list[str]]]:
    """Mọi tiến trình `live_worker.py` đang sống (trừ `exclude_pid`), kèm argv.

    Vì sao cần: 21-11 người dùng chạy `./run demoip` và thấy "không mượt bằng lúc nảy" — đo ra
    **1484 ms/frame thay vì 158 ms**. Nguyên nhân: một worker của **phiên web trước** (đóng tab mà
    không bấm Dừng) vẫn chạy, ăn **461 % CPU** và **giữ luôn webcam**. API chỉ reap worker cũ khi
    `_prepare_dir()` của một phiên MỚI chạy (`src/api/adapters/worker_source.py`), còn CLI thì không
    biết gì ⇒ phải CẢNH BÁO được từ CLI, kèm pid để người dùng tự quyết.

    Trả `[(pid, argv)]`; lỗi đọc `/proc` ⇒ bỏ qua tiến trình đó (không ném — chỉ là cảnh báo).
    """
    ket_qua: list[tuple[int, list[str]]] = []
    try:
        entries = list(Path(proc_root).iterdir())
    except OSError:
        return ket_qua
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == exclude_pid:
            continue
        argv = read_cmdline(pid) if proc_root == "/proc" else []
        if proc_root != "/proc":
            # Đường test: đọc file `cmdline` trong thư mục giả (không đụng tiến trình thật).
            try:
                raw = (entry / "cmdline").read_bytes()
            except OSError:
                continue
            argv = [part for part in raw.decode("utf-8", "replace").split("\0") if part]
        if argv and "live_worker.py" in {Path(arg).name for arg in argv}:
            ket_qua.append((pid, argv))
    return ket_qua
