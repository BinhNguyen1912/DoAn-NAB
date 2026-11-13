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
         `timeout_s`. Lần dò đầu ~1,5 s trong trường hợp xấu nhất; sau đó lấy từ cache `CACHE_TTL_S`.
         KHÔNG dò webcam khi đang có phiên live (mở thêm sẽ tranh thiết bị với phiên đang chạy).
"""

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
# Video demo trong `data/` được ưu tiên theo thứ tự này (clip đã đo nhiều trong báo cáo)
_PREFERRED_VIDEOS = ("binh1.mp4", "binh2.mp4", "simloss.mp4")


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


def http_snapshot_ok(url: str, timeout_s: float = 1.5) -> bool:
    """URL có trả ảnh JPEG thật không (relay sống + camera Windows đang mở)."""
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:   # noqa: S310 — URL nội bộ
            data = resp.read(4)
        return data[:2] == b"\xff\xd8"                                  # SOI của JPEG
    except Exception:                     # noqa: BLE001 — mọi lỗi mạng đều là "không dùng được"
        return False


def camera_ok(index: int) -> bool:
    """Webcam index này mở được và đọc được 1 frame không (mở rồi ĐÓNG ngay)."""
    try:
        import cv2
    except Exception:                     # noqa: BLE001 — thiếu cv2/HAL hỏng đều là "không có camera"
        return False
    cap = None
    try:
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            return False
        ok, frame = cap.read()
        return bool(ok) and frame is not None
    except Exception:                     # noqa: BLE001 — driver ném lỗi là "không có camera"
        return False
    finally:
        if cap is not None:
            cap.release()


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
            ok = self._safe(self._camera_ok, index)
            candidates.append(_candidate(str(index), f"Webcam {index} (cắm ở máy chủ)", "camera", ok))
            if ok:
                break                     # máy chỉ có 1 webcam — không dò tiếp 1, 2

        # 2) Relay camera Windows → WSL (đường demo khi WSL không thấy webcam)
        for url in self._relay_urls():
            ok = self._safe(self._http_ok, url)
            candidates.append(_candidate(url, "Relay webcam Windows (snapshot JPEG)", "relay", ok))

        # 3) Video demo có sẵn trong repo (luôn "available": file tồn tại, backend tự lặp lại)
        for path in self._demo_videos():
            candidates.append(_candidate(str(path), f"Video demo {path.name}", "file", True))

        available = [c for c in candidates if c["available"]]
        return {
            "suggested": available[0]["source"] if available else "",
            "candidates": candidates,
        }

    def _relay_urls(self) -> list[str]:
        urls: list[str] = []
        env = self._env if self._env is not None else os.environ
        explicit = (env.get("CAM_RELAY_URL") or "").strip()
        if explicit:
            urls.append(explicit)
        host = self._safe(self._gateway)
        if host and not explicit:
            urls.extend(f"http://{host}:{port}/snapshot.jpg" for port in _RELAY_PORTS)
        return urls

    def _demo_videos(self) -> list[Path]:
        data = self._root / "data"
        if not data.is_dir():
            return []
        found = [p for p in data.iterdir() if p.suffix.lower() in _VIDEO_SUFFIXES and p.is_file()]
        order = {name: i for i, name in enumerate(_PREFERRED_VIDEOS)}
        found.sort(key=lambda p: (order.get(p.name, len(order)), p.name))
        return found[:3]

    @staticmethod
    def _safe(func, *args):
        try:
            return func(*args)
        except Exception:                 # noqa: BLE001 — dò nguồn KHÔNG được ném ra HTTP
            logger.debug("dò nguồn lỗi", exc_info=True)
            return None


def _candidate(source: str, label: str, kind: str, available: bool, note: str = "") -> dict:
    return {"source": source, "label": label, "kind": kind, "available": bool(available),
            "note": note}
