"""
Nguồn frame cho chế độ LIVE (webcam / RTSP / ảnh snapshot relay / file lặp lại).

Chức năng: hiện thực `FrameSource` bằng `src.video_source.open_video_source` — tái sử dụng
           đúng lớp nguồn đã có 30+ test, chỉ thêm bước nén JPEG và tùy chọn lặp file.
Input  : chuỗi nguồn (0 = webcam, rtsp://…, http://…/snapshot.jpg, đường dẫn video).
Output : bytes JPEG của frame mới nhất, hoặc None khi chưa có frame/nguồn chết.
Lưu ý  : đây là NƠI DUY NHẤT của nhánh live import cv2 (qua video_source). Nguồn là FILE được
         LẶP LẠI (mở lại từ đầu khi hết) để demo live không cần webcam thật — quan trọng vì
         máy này webcam WSL hay kẹt usbipd "Device busy (exported)".
"""

from pathlib import Path

import cv2

from src.video_source import open_video_source

# Đuôi file được coi là video (để quyết định có lặp lại hay không)
_FILE_SUFFIXES = (".mp4", ".avi", ".mov", ".mkv")


class OpenCvFrameSource:
    """Hiện thực `FrameSource`: đọc frame từ VideoSource và nén thành JPEG."""

    def __init__(self, source: str, *, loop_files: bool = True, jpeg_quality: int = 80) -> None:
        self._source = source
        self._loop = bool(loop_files)
        self._quality = int(jpeg_quality)
        self._capture = None
        self._is_file = self._looks_like_file(source)

    def start(self) -> None:
        """Mở nguồn. Ném lỗi của video_source nếu không kết nối được."""
        self._capture = open_video_source(self._source, ).open()

    def read_jpeg(self) -> bytes | None:
        """Đọc 1 frame và nén JPEG; None nếu nguồn đã cạn (file không lặp) hoặc lỗi tạm thời."""
        if self._capture is None:
            return None
        frame = self._capture.read()
        if frame is None and self._is_file and self._loop:
            frame = self._rewind()
        if frame is None:
            return None
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self._quality])
        return bytes(buffer) if ok else None

    def stop(self) -> None:
        if self._capture is not None:
            try:
                self._capture.close()
            finally:
                self._capture = None

    @property
    def label(self) -> str:
        """Mô tả ngắn để hiện trên UI/log."""
        return f"nguồn {self._source}"

    def _rewind(self):
        """Mở lại file từ đầu (giả lập camera chạy liên tục khi demo bằng video)."""
        try:
            self.stop()
            self.start()
            return self._capture.read() if self._capture is not None else None
        except (OSError, RuntimeError):
            return None

    @staticmethod
    def _looks_like_file(source: str) -> bool:
        if not isinstance(source, str):
            return False
        return Path(source).suffix.lower() in _FILE_SUFFIXES or Path(source).is_file()
