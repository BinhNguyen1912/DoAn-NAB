"""
Nguồn frame cho chế độ LIVE (webcam / RTSP / ảnh snapshot relay / file lặp lại).

Chức năng: hiện thực `FrameSource` bằng `src.video_source.open_video_source` — tái sử dụng
           đúng lớp nguồn đã có 30+ test, chỉ thêm bước nén JPEG và tùy chọn lặp file.
Input  : chuỗi nguồn (0 = webcam, rtsp://…, http://…/snapshot.jpg, đường dẫn video).
Output : bytes JPEG của frame mới nhất, hoặc None khi chưa có frame/nguồn chết.
Lưu ý  : đây là NƠI DUY NHẤT của nhánh live import cv2 (qua video_source). Nguồn là FILE được
         LẶP LẠI (mở lại từ đầu khi hết) để demo live không cần webcam thật — quan trọng vì
         máy này webcam WSL hay kẹt usbipd "Device busy (exported)".
         Từ 09-11 adapter này cũng tự khai sức sống (`health()`) — trước đó chế độ `raw` không có
         watchdog: rút webcam giữa phiên thì API vẫn báo `running` với ảnh đứng (cùng lớp lỗi đã
         sửa cho chế độ `track`).
"""

import time
from pathlib import Path

import cv2

from src.api.domain import LiveState, SourceHealth
from src.video_source import open_video_source

# Đuôi file được coi là video (để quyết định có lặp lại hay không)
_FILE_SUFFIXES = (".mp4", ".avi", ".mov", ".mkv")

# Nguồn sống chết ra sao: `read()` trả None liên tục quá lâu. 3 s là rộng cho camera chậm
# (0,3 frame/giây vẫn kịp) và đủ nhanh để người vận hành thấy lỗi khi rút webcam.
# So sánh: chế độ `track` đo được 91–111 ms cho ca worker chết (`proc.poll()`), còn đây là
# "không có tín hiệu" — phải chờ mới biết chắc.
STALE_S = 3.0


class OpenCvFrameSource:
    """Hiện thực `FrameSource`: đọc frame từ VideoSource và nén thành JPEG."""

    def __init__(self, source: str, *, loop_files: bool = True, jpeg_quality: int = 80) -> None:
        self._source = source
        self._loop = bool(loop_files)
        self._quality = int(jpeg_quality)
        self._capture = None
        self._is_file = self._looks_like_file(source)
        # Trạng thái cho `health()`: mốc frame cuối đọc được + đã bị chủ động đóng chưa
        self._last_frame_at = None
        self._closed = False
        self._exhausted = False

    def start(self) -> None:
        """Mở nguồn. Ném lỗi của video_source nếu không kết nối được."""
        self._capture = open_video_source(self._source, ).open()
        self._last_frame_at = time.monotonic()
        self._closed = False
        self._exhausted = False

    def read_jpeg(self) -> bytes | None:
        """Đọc 1 frame và nén JPEG; None nếu nguồn đã cạn (file không lặp) hoặc lỗi tạm thời."""
        if self._capture is None:
            return None
        frame = self._capture.read()
        if frame is None and self._is_file and self._loop:
            frame = self._rewind()
        if frame is None:
            if self._is_file and not self._loop:
                self._exhausted = True          # hết video, không lặp ⇒ phiên KẾT THÚC, không phải lỗi
            return None
        self._last_frame_at = time.monotonic()
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self._quality])
        return bytes(buffer) if ok else None

    def stop(self) -> None:
        self._closed = True
        if self._capture is not None:
            try:
                self._capture.close()
            finally:
                self._capture = None

    @property
    def label(self) -> str:
        """Mô tả ngắn để hiện trên UI/log."""
        return f"nguồn {self._source}"

    # ------------------------------------------------------------------ HealthReportingSource

    def health(self) -> SourceHealth | None:
        """Nguồn còn ra frame không? None = khoẻ.

        Ba ca, phân biệt rõ vì ba cách xử lý khác nhau ở service:
        1. chưa `start()` hoặc đã `stop()` theo lệnh ⇒ None (không phải lỗi của phiên);
        2. **file hết mà không lặp** ⇒ `STOPPED` ("nguồn đã hết") — phiên kết thúc bình thường;
        3. **camera/RTSP/file không trả frame > `STALE_S`** hoặc mất `capture` ⇒ `ERROR`.

        Vì sao cần: chế độ `raw` trước đây không có watchdog — rút webcam (hoặc relay chết) thì
        `read_jpeg()` trả None mãi, API vẫn `running`, ảnh đứng trên UI (review 09-11, P3).
        """
        if self._closed:
            return None                     # chủ động đóng (stop/đổi phiên) — không phải lỗi
        if self._last_frame_at is None:
            return None                     # chưa start
        if self._exhausted:
            return SourceHealth(LiveState.STOPPED, "nguồn đã hết (không lặp lại)")
        if self._capture is None:
            return SourceHealth(LiveState.ERROR, f"mất kết nối nguồn {self._source} — xem log worker")
        age = time.monotonic() - self._last_frame_at
        if age > STALE_S:
            kind = "file video" if self._is_file else "camera/luồng"
            return SourceHealth(
                LiveState.ERROR,
                f"{kind} không trả frame trong {age:.0f} s — kiểm tra nguồn/kết nối",
            )
        return None

    def _rewind(self):
        """Mở lại file từ đầu (giả lập camera chạy liên tục khi demo bằng video).

        KHÔNG gọi `self.stop()` ở đây: `stop()` đánh dấu `_closed` ("chủ động đóng") và health()
        sẽ im lặng coi nguồn là khoẻ. Đóng capture trực tiếp, và `_last_frame_at` chỉ được cập nhật
        khi THẬT SỰ đọc được frame ⇒ mở lại file lỗi vẫn bị watchdog bắt.
        """
        try:
            capture, self._capture = self._capture, None
            if capture is not None:
                capture.close()
            self._capture = open_video_source(self._source).open()
            return self._capture.read() if self._capture is not None else None
        except (OSError, RuntimeError):
            self._capture = None
            return None

    @staticmethod
    def _looks_like_file(source: str) -> bool:
        if not isinstance(source, str):
            return False
        return Path(source).suffix.lower() in _FILE_SUFFIXES or Path(source).is_file()
