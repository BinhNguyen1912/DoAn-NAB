"""
LiveStreamService — phiên phát trực tiếp: giữ nguồn frame, phát frame mới nhất cho client.

Chức năng: mở nguồn (webcam/RTSP/ảnh relay/file lặp), chạy một thread đọc frame theo nhịp
           `target_fps`, giữ **frame mới nhất** trong bộ đệm 1 phần tử (client chậm thì bỏ
           frame cũ, không bao giờ chậm dần), và cung cấp luồng JPEG cho endpoint MJPEG.
Input  : `make_source(source: str) -> FrameSource` (nhà máy được tiêm vào), target_fps.
Output : LiveStatus (trạng thái + số frame + FPS đo được) và luồng bytes JPEG.
Lưu ý  : chỉ giữ frame MỚI NHẤT (không hàng đợi) — đây là quyết định thiết kế cho live:
         độ trễ thấp quan trọng hơn việc phát đủ mọi frame. Đừng đổi thành queue trừ khi
         có số đo chứng minh cần.
         Service không import cv2 — nguồn frame là adapter được tiêm (xem ports.FrameSource).
"""

import logging
import threading
import time
from collections import deque
from typing import Callable, Iterator

from src.api.domain import LiveState, LiveStatus, SourceUnavailable
from src.api.ports import FrameSource

logger = logging.getLogger("doan.api.live")

_TICK_S = 0.01          # nhịp chờ nhỏ khi nguồn chưa có frame / khi client chậm
_FPS_WINDOW_S = 2.0     # cửa sổ đo FPS thực
_JPEG_BOUNDARY = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
_MAX_OPEN_ERROR = "Không mở được {label}: {error}"


class LiveStreamService:
    """Một phiên live tại một thời điểm (đủ cho đồ án; đa phiên sẽ cần kho theo id)."""

    def __init__(self, make_source: Callable[[str], FrameSource], *, target_fps: int = 15) -> None:
        self._make_source = make_source
        self._interval = 1.0 / max(1, int(target_fps))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._source: FrameSource | None = None
        self._latest: bytes | None = None
        self._frames = 0
        self._stamps: deque = deque()
        self._state = LiveState.STOPPED
        self._label = ""
        self._message = "Chưa phát"

    # ------------------------------------------------------------------ lệnh

    def start(self, source: str) -> LiveStatus:
        """Mở nguồn và bắt đầu phát. Ném SourceUnavailable nếu không mở được."""
        with self._lock:
            self._stop_locked()

        candidate = self._make_source(str(source))
        try:
            candidate.start()
        except Exception as exc:                      # noqa: BLE001 — mọi lỗi mở nguồn là 400
            try:
                candidate.stop()
            finally:
                message = _MAX_OPEN_ERROR.format(label=candidate.label, error=exc)
                with self._lock:
                    self._state = LiveState.ERROR
                    self._label = candidate.label
                    self._message = message
                raise SourceUnavailable(message) from exc

        with self._lock:
            self._source = candidate
            self._latest = None
            self._frames = 0
            self._stamps.clear()
            self._label = candidate.label
            self._state = LiveState.RUNNING
            self._message = f"Đang phát từ {candidate.label}"
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="live-stream", daemon=True)
            self._thread.start()
        logger.info("bắt đầu live: %s", candidate.label)
        return self.status()

    def stop(self) -> LiveStatus:
        """Dừng phát và đóng nguồn."""
        with self._lock:
            self._stop_locked()
            self._message = "Đã dừng"
        return self.status()

    # ------------------------------------------------------------------ truy vấn

    def status(self) -> LiveStatus:
        with self._lock:
            return LiveStatus(
                state=self._state,
                source=self._label,
                frames=self._frames,
                measured_fps=self._measured_fps_locked(),
                message=self._message,
            )

    def latest_jpeg(self) -> bytes | None:
        """Frame mới nhất (None khi chưa có) — dùng cho endpoint chụp 1 ảnh."""
        with self._lock:
            return self._latest

    def frames(self, *, idle_timeout: float = 5.0) -> Iterator[bytes]:
        """Sinh luồng part MJPEG: lặp lại frame mới nhất cho tới khi dừng/không có frame mới.

        Lưu ý: `idle_timeout` để client rời đi không treo thread của server mãi.
        """
        last: bytes | None = None
        idle = 0.0
        while True:
            with self._lock:
                data = self._latest
                running = self._state is LiveState.RUNNING
            if data is not None and data is not last:
                last = data
                idle = 0.0
                yield _JPEG_BOUNDARY + str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n"
                continue
            idle += _TICK_S
            if idle > idle_timeout or not running:
                return
            time.sleep(_TICK_S)

    # ------------------------------------------------------------------ nội bộ

    def _run(self) -> None:
        """Thread đọc frame: luôn giữ frame mới nhất, bỏ frame cũ khi client chậm."""
        while not self._stop.is_set():
            started = time.perf_counter()
            with self._lock:
                source = self._source
            data = source.read_jpeg() if source is not None else None
            if data is not None:
                with self._lock:
                    self._latest = data
                    self._frames += 1
                    self._stamps.append(started)
                    self._trim_stamps_locked(started)
            else:
                time.sleep(_TICK_S)                   # nguồn chưa có frame (camera khởi động)
            remaining = self._interval - (time.perf_counter() - started)
            if remaining > 0:
                self._stop.wait(remaining)

    def _stop_locked(self) -> None:
        """Dừng thread + đóng nguồn. Caller phải giữ `_lock`.

        Lưu ý: KHÔNG được gọi `self.status()` ở đây (nó cũng cần `_lock` → deadlock).
        """
        self._stop.set()
        thread, self._thread = self._thread, None
        source, self._source = self._source, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        if source is not None:
            try:
                source.stop()
            except Exception:                        # noqa: BLE001 — đóng nguồn lỗi không được ném
                logger.warning("đóng nguồn live gặp lỗi", exc_info=True)
        if self._state is LiveState.RUNNING:
            self._state = LiveState.STOPPED
        self._latest = None

    def _trim_stamps_locked(self, now: float) -> None:
        cutoff = now - _FPS_WINDOW_S
        while self._stamps and self._stamps[0] < cutoff:
            self._stamps.popleft()

    def _measured_fps_locked(self) -> float:
        """FPS thực đo trong cửa sổ gần nhất (không phải target_fps đặt ra)."""
        if len(self._stamps) < 2:
            return 0.0
        span = self._stamps[-1] - self._stamps[0]
        if span <= 0:
            return 0.0
        return round((len(self._stamps) - 1) / span, 1)
