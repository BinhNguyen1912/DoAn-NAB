"""
Dò nguồn frame KHẢ DỤNG để UI tự điền nguồn (không bắt người dùng dán URL mỗi lần).

Chức năng: trả danh sách nguồn mà backend thật sự dùng được — webcam index, relay camera Windows
           (`http://<IP-Windows>:8090/snapshot.jpg`), các video demo có sẵn — kèm cờ `available`
           đã KIỂM bằng thử thật (mở webcam / GET ảnh JPEG), và một nguồn gợi ý.
Input  : repo_root (để tìm video demo), biến môi trường (tuỳ chọn `CAM_RELAY_URL`), các hàm dò
         được tiêm vào (test không cần webcam/mạng thật).
Output : dict `{"suggested": str, "candidates": [{source,label,kind,available}]}`.
Lưu ý  : đây là ADAPTER ngoài cùng (chạm cv2 + HTTP). Endpoint gọi nó chạy trong threadpool của
         FastAPI, nên phải CACHE: mỗi lần dò có thể mở webcam (giữ thiết bị) và chờ HTTP tới
         `timeout_s`. Ngân sách thời gian: HTTP 0,8 s/URL, webcam bị BỎ QUA nếu máy không có
         `/dev/video*` ⇒ lần dò chậm nhất ~1,6 s (2 URL); sau đó lấy từ cache `CACHE_TTL_S`.
         `suggest()` giữ lock trong suốt lần dò ⇒ 10 tab gọi cùng lúc vẫn chỉ 1 lần mở thiết bị
         (single-flight bằng cách xếp hàng, chấp nhận được vì ai cũng nhận cache mới ngay sau đó).
         KHÔNG dò webcam khi đang có phiên live (mở thêm sẽ tranh thiết bị với phiên đang chạy).
"""

import glob
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger("doan.api.source_probe")

CACHE_TTL_S = 5.0
# Port mặc định của relay trong repo (`scripts/cam_relay.sh`), và vài port hay dùng khác
_RELAY_PORTS = (8090,)
_VIDEO_SUFFIXES = (".mp4", ".avi", ".mov", ".mkv")
_MAX_CAMERA_INDEX = 2
# Ngân sách thời gian mỗi lần dò. Không tin driver: `cv2.VideoCapture` (DSHOW trên Windows) có thể
# block 1–3 s/thiết bị khi camera bận, còn HTTP tới IP "black-hole" chờ hết timeout.
CAMERA_BUDGET_S = 0.6
HTTP_BUDGET_S = 0.8
# Video demo trong `data/` được ưu tiên theo thứ tự này (clip đã đo nhiều trong báo cáo)
_PREFERRED_VIDEOS = ("binh1.mp4", "binh2.mp4", "binh1_simloss.mp4")
# Clip nhỏ hơn mức này là clip test (160×120 vài chục KB) — gợi ý nó làm demo trông "hỏng".
_MIN_VIDEO_BYTES = 100 * 1024


def default_gateway_ip(route_table: Path = Path("/proc/net/route")) -> str | None:
    """IP gateway mặc định (Windows host trong WSL2) — đọc `/proc/net/route`, không cần thư viện.

    Dòng khớp: Destination `00000000` (mặc định), Gateway là hex little-endian.
    Không phải Linux/WSL (không có file) ⇒ None, im lặng: máy Windows/Colab tự có webcam riêng.
    """
    try:
        lines = route_table.read_text().splitlines()[1:]
    except OSError:
        return None
    for line in lines:
        parts = line.split()
        if len(parts) < 3 or parts[1] != "00000000":
            continue
        try:
            raw = int(parts[2], 16)
        except ValueError:
            continue
        ip = ".".join(str((raw >> shift) & 0xFF) for shift in (0, 8, 16, 24))
        if ip not in ("0.0.0.0", ""):
            return ip
    return None


def http_snapshot_ok(url: str, timeout_s: float = 0.8) -> bool:
    """URL có trả ảnh JPEG thật không (relay sống + camera Windows đang mở)."""
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:   # noqa: S310 — URL nội bộ
            data = resp.read(4)
        return data[:2] == b"\xff\xd8"                                  # SOI của JPEG
    except Exception:                     # noqa: BLE001 — mọi lỗi mạng đều là "không dùng được"
        return False


def camera_ok(index: int) -> bool:
    """Webcam index này mở được và đọc được 1 frame không (mở rồi ĐÓNG ngay).

    Dùng ĐÚNG đường mở của phiên live (`open_video_source(str(index))` → V4L2 + MJPG + 640×480),
    không gọi `cv2.VideoCapture` trần: webcam UVC-qua-usbipd đã đo được `isOpened()=True` nhưng
    `read()` luôn False ⇒ dò bằng đường khác sẽ báo "dùng được" trong khi bấm "Bật phát" lại hỏng.

    Trên Linux KHÔNG có `/dev/video*` (WSL khi usbipd kẹt, runner CI) thì trả False NGAY: thử mở
    ở đó chỉ tốn ~30 ms/index kèm một tràng WARN của OpenCV — đo 13-11: 3 index = ~90 ms tiếng ồn
    mà kết quả luôn là False.
    """
    if os.name == "posix" and not glob.glob("/dev/video*"):
        return False
    from src.video_source import open_video_source

    source = None
    try:
        source = open_video_source(str(index)).open()      # ném RuntimeError nếu không mở được
        return source.read() is not None
    except Exception:                     # noqa: BLE001 — driver/thiết bị lỗi đều là "không dùng được"
        return False
    finally:
        if source is not None:
            source.close()


class SourceProbe:
    """Dò nguồn có cache — endpoint `/api/live/sources` dùng instance này.

    Các hàm dò được TIÊM vào (`http_probe`, `camera_probe`) để test không cần camera/mạng thật.
    `live_busy` (callable) cho biết đang có phiên live: khi đó BỎ QUA dò webcam để không tranh
    thiết bị với phiên đang chạy (dò webcam là tự mở thiết bị).
    """

    def __init__(self, repo_root, *, http_probe=http_snapshot_ok, camera_probe=camera_ok,
                 live_busy=None, gateway_probe=default_gateway_ip, env=None) -> None:
        self._root = Path(repo_root)
        self._http_ok = http_probe
        self._camera_ok = camera_probe
        self._live_busy = live_busy or (lambda: False)
        self._gateway = gateway_probe
        self._env = env
        self._lock = threading.Lock()
        self._cache: dict | None = None
        self._cache_at = 0.0

    # ------------------------------------------------------------------ API công khai

    def suggest(self) -> dict:
        """Trả nguồn gợi ý + danh sách ứng viên (cache `CACHE_TTL_S` giây)."""
        with self._lock:
            if self._cache is not None and time.monotonic() - self._cache_at < CACHE_TTL_S:
                return self._cache
            result = self._probe()
            self._cache, self._cache_at = result, time.monotonic()
            return result

    # ------------------------------------------------------------------ nội bộ

    def _probe(self) -> dict:
        candidates: list[dict] = []
        busy = False
        try:
            busy = bool(self._live_busy())
        except Exception:                 # noqa: BLE001 — không để lỗi dò làm hỏng endpoint
            busy = False

        # 1) Webcam của CHÍNH máy chạy API — chỉ dò khi không có phiên live (xem docstring).
        for index in range(_MAX_CAMERA_INDEX + 1):
            if busy:
                candidates.append(_candidate(str(index), f"Webcam {index} (cắm ở máy chủ)", "camera",
                                             available=False, note="đang có phiên live"))
                continue
            ok, elapsed_ms, detail = self._timed(self._camera_ok, CAMERA_BUDGET_S, index)
            candidates.append(_candidate(
                str(index), f"Webcam {index} (cắm ở máy chủ)", "camera", bool(ok),
                check=detail if detail else ("mở được camera + đọc được 1 frame" if ok
                                             else "không mở được camera"), latency_ms=elapsed_ms))
            if ok:
                break                     # máy chỉ có 1 webcam — không dò tiếp 1, 2

        # 2) Relay camera Windows → WSL (đường demo khi WSL không thấy webcam)
        for url in self._relay_urls():
            ok, elapsed_ms, detail = self._timed(self._http_ok, HTTP_BUDGET_S + 0.2, url)
            candidates.append(_candidate(
                url, "Relay webcam Windows (snapshot JPEG)", "relay", bool(ok),
                check=detail if detail else ("nhận được ảnh JPEG" if ok else "không lấy được ảnh JPEG"),
                latency_ms=elapsed_ms))

        # 3) Video demo có sẵn trong repo (luôn "available": file tồn tại, backend tự lặp lại)
        for path in self._demo_videos():
            candidates.append(_candidate(
                str(path), f"Video demo {path.name}", "file", True,
                check=f"có sẵn · {path.stat().st_size // 1024} KB (chưa mở thử)"))

        available = [c for c in candidates if c["available"]]
        return {
            "suggested": available[0]["source"] if available else "",
            # UI cần biết gợi ý là CAMERA hay VIDEO: gợi ý video mà UI ghi "đã kiểm camera" là nói dối.
            "suggested_kind": available[0]["kind"] if available else "",
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "budget_ms": int((CAMERA_BUDGET_S + HTTP_BUDGET_S) * 1000),
            "candidates": candidates,
        }

    def _relay_urls(self) -> list[str]:
        urls: list[str] = []
        env = self._env if self._env is not None else os.environ
        explicit = (env.get("CAM_RELAY_URL") or "").strip()
        if explicit:
            urls.append(explicit)
        # LUÔN thử cả IP gateway: IP WSL2 đổi sau mỗi lần restart, còn `CAM_RELAY_URL` trong env thì
        # kẹt IP cũ ⇒ nếu chỉ dùng env thì dò hỏng câm đúng lúc người dùng đã "cấu hình đúng".
        host = self._safe(self._gateway)
        if host:
            for port in _RELAY_PORTS:
                url = f"http://{host}:{port}/snapshot.jpg"
                if url not in urls:
                    urls.append(url)
        return urls

    def _demo_videos(self) -> list[Path]:
        """Video demo đáng đem ra gợi ý: bỏ clip tạm (`_*`), clip test E2E, và clip quá nhỏ.

        Vì sao: `data/` có `_gui_test.mp4` (160×120, 14 KB) và `e2e_web.mp4` — gợi ý những clip đó
        làm demo trông "hỏng" dù hệ thống chạy đúng (review 13-11, góc nhìn chất lượng).
        """
        data = self._root / "data"
        if not data.is_dir():
            return []
        found = [
            p for p in data.iterdir()
            if p.suffix.lower() in _VIDEO_SUFFIXES
            and p.is_file()
            and not p.name.startswith(("_", "e2e_"))
            and p.stat().st_size > _MIN_VIDEO_BYTES
        ]
        order = {name: i for i, name in enumerate(_PREFERRED_VIDEOS)}
        found.sort(key=lambda p: (order.get(p.name, len(order)), p.name))
        return found[:3]

    @staticmethod
    def _timed(func, budget_s: float, *args):
        """Chạy `func` với DEADLINE cứng: quá `budget_s` thì coi như không dùng được.

        Vì sao phải có: `cv2.VideoCapture` trên Windows (DSHOW) có thể block 1–3 s/thiết bị khi
        camera đang bị app khác giữ — không được để một request HTTP treo theo nó. Thread bị bỏ rơi
        là daemon và `camera_ok`/`http_snapshot_ok` đều đóng tài nguyên trong `finally`.
        """
        box: list = []

        def run():
            box.append(SourceProbe._safe(func, *args))

        thread = threading.Thread(target=run, daemon=True)
        started = time.monotonic()
        thread.start()
        thread.join(budget_s)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if thread.is_alive():
            return None, elapsed_ms, f"quá hạn {int(budget_s * 1000)} ms"
        return box[0] if box else None, elapsed_ms, ""

    @staticmethod
    def _safe(func, *args):
        try:
            return func(*args)
        except Exception:                 # noqa: BLE001 — dò nguồn KHÔNG được ném ra HTTP
            logger.debug("dò nguồn lỗi", exc_info=True)
            return None


def _candidate(source: str, label: str, kind: str, available: bool, *, check: str = "",
               latency_ms: int = 0, note: str = "") -> dict:
    """Một ứng viên + BẰNG CHỨNG đã kiểm (`check`) và thời gian kiểm — để UI không nói quá.

    `available` chỉ có nghĩa "thử được lúc `checked_at`", KHÔNG phải "đang chạy": chỉ phiên live
    mới chứng minh được điều đó, bằng `state`/`frames`/`measured_fps` của chính nó.
    """
    return {"source": source, "label": label, "kind": kind, "available": bool(available),
            "check": check, "latency_ms": int(latency_ms), "note": note}
