"""
VideoSource — seam thống nhất để lấy frame từ mọi nguồn video.

Chức năng: cung cấp một interface duy nhất cho 3 nguồn — webcam (index), camera rời/
điện thoại qua RTSP URL, video file — để phần còn lại của hệ thống (pipeline, headless)
không cần quan tâm nguồn ở đâu.

Input  : `open_video_source(source)` với source là int (webcam index), đường dẫn file,
         hoặc chuỗi rtsp://...
Output : adapter kế thừa VideoSource, API:
         - open()            : mở nguồn (lazy — factory trả instance chưa mở)
         - frame_size        : (W, H) kích thước frame
         - source_fps        : FPS nguồn (camera/RTSP có thể trả 0.0 — ghi nhận để đo FPS thực)
         - read()            : frame (H, W, 3) uint8, hoặc None khi cạn nguồn
         - close()           : giải phóng tài nguyên (dùng `with` cũng được)
Lưu ý  : RTSP/webcam là adapter mỏng — kiểm chứng thủ công; test tự động focus vào file
         adapter + báo lỗi nguồn. Lớp cơ sở _CaptureSource gom phần bọc cv2.VideoCapture
         dùng chung; mỗi adapter chỉ khai báo cách tạo capture + loại lỗi khi mở thất bại.
"""
from abc import ABC, abstractmethod

import cv2
import numpy as np


class VideoSource(ABC):
    """Interface nguồn frame (đã thống nhất là 1 trong 2 seam chính của hệ thống)."""

    @abstractmethod
    def open(self) -> "VideoSource":
        """Mở nguồn. Ném lỗi rõ ràng nếu nguồn không kết nối được."""

    @property
    @abstractmethod
    def frame_size(self) -> tuple:
        """(W, H)."""

    @property
    @abstractmethod
    def source_fps(self) -> float:
        """FPS nguồn báo cáo (có thể 0.0 với camera — xử lý phía người dùng)."""

    @abstractmethod
    def read(self):
        """Trả frame (H, W, 3) uint8, hoặc None khi hết frame."""

    def close(self) -> None:
        """Giải phóng tài nguyên — default no-op."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class _CaptureSource(VideoSource):
    """Lớp cơ sở bọc cv2.VideoCapture — phần dùng chung của 3 adapter nguồn cv2."""

    def __init__(self):
        self._cap = None

    def _create_capture(self) -> cv2.VideoCapture:
        """Tạo cv2.VideoCapture cho nguồn cụ thể (mỗi adapter tự khai báo)."""
        raise NotImplementedError

    def _raise_open_error(self):
        """Báo lỗi rõ ràng, đúng loại, khi mở nguồn thất bại."""
        raise RuntimeError("Không mở được nguồn video")

    def open(self):
        self._cap = self._create_capture()
        if not self._cap.isOpened():
            self._cap.release()
            self._cap = None
            self._raise_open_error()
        return self

    @property
    def frame_size(self):
        if self._cap is None:
            raise RuntimeError("Gọi open() trước khi đọc thuộc tính nguồn")
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (w, h)

    @property
    def source_fps(self):
        if self._cap is None:
            raise RuntimeError("Gọi open() trước khi đọc thuộc tính nguồn")
        return float(self._cap.get(cv2.CAP_PROP_FPS))

    def read(self):
        if self._cap is None:
            raise RuntimeError("Gọi open() trước khi read()")
        ok, frame = self._cap.read()
        return frame if ok else None

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class FileVideoSource(_CaptureSource):
    """Đọc frame từ video file (mp4/avi...)."""

    def __init__(self, path):
        super().__init__()
        self._path = str(path)

    def _create_capture(self):
        return cv2.VideoCapture(self._path)

    def _raise_open_error(self):
        raise FileNotFoundError(
            f"Không mở được video file: '{self._path}' (file không tồn tại hoặc codec không đọc được)"
        )


class CameraVideoSource(_CaptureSource):
    """Webcam/cam USB cục bộ theo index (adapter mỏng — kiểm chứng thủ công)."""

    def __init__(self, index=0):
        super().__init__()
        self._index = int(index)

    def _create_capture(self):
        return cv2.VideoCapture(self._index)

    def _raise_open_error(self):
        raise RuntimeError(
            f"Không mở được camera index {self._index} "
            f"(bận hoặc không tồn tại — thử index khác, ví dụ 1)"
        )


class HttpVideoSource(_CaptureSource):
    """Camera điện thoại/IP phát MJPEG qua HTTP (IP Webcam, DroidCam, iCam…).

    URL thường gặp: `http://<IP>:8080/video` (MJPEG). Một số app chỉ phát RTSP → dùng
    `rtsp://…` (RtspVideoSource). Lỗi mở nguồn báo rõ: IP thật, cùng Wi-Fi, đường dẫn stream.
    """

    DEFAULT_OPEN_TIMEOUT_MS = 5000

    def __init__(self, url, open_timeout_ms=DEFAULT_OPEN_TIMEOUT_MS):
        super().__init__()
        self._url = str(url)
        self._timeout_ms = int(open_timeout_ms)

    def _create_capture(self):
        # Thử FFMPEG trước (MJPEG/HTTP tốt), không được thì để backend mặc định thử lại
        for backend in (cv2.CAP_FFMPEG, cv2.CAP_ANY):
            cap = cv2.VideoCapture(self._url, backend)
            if cap.isOpened():
                try:
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self._timeout_ms)
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self._timeout_ms)
                except Exception:
                    pass  # backend không hỗ trợ timeout — vẫn dùng được
                return cap
            cap.release()
        return cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)  # cap chưa mở → open() báo lỗi

    def _raise_open_error(self):
        hint = ""
        if "x.x" in self._url or "<" in self._url:
            hint = (" — URL còn là PLACEHOLDER, hãy thay bằng IP thật hiện trên app điện thoại "
                    "(ví dụ http://192.168.1.25:8080/video)")
        raise ConnectionError(
            f"Không mở được nguồn mạng '{self._url}' trong {self._timeout_ms} ms{hint}. "
            f"Kiểm tra: (1) IP thật + điện thoại và máy cùng mạng Wi-Fi; (2) app đã bấm "
            f"Start server; (3) đúng đường dẫn stream (thường là /video); (4) một số app chỉ "
            f"phát RTSP → dùng rtsp://…"
        )


class RtspVideoSource(_CaptureSource):
    """Camera rời/điện thoại qua RTSP — mở có timeout, lỗi nguồn báo rõ thay vì treo."""

    # Timeout để cv2 không treo vô hạn khi camera offline/wifi yếu
    DEFAULT_OPEN_TIMEOUT_MS = 5000

    def __init__(self, url, open_timeout_ms=DEFAULT_OPEN_TIMEOUT_MS):
        super().__init__()
        self._url = str(url)
        self._timeout_ms = int(open_timeout_ms)

    def _create_capture(self):
        cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        try:
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self._timeout_ms)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self._timeout_ms)
        except Exception:
            pass  # một số backend không set được timeout — vẫn dùng được
        return cap

    def _raise_open_error(self):
        raise ConnectionError(
            f"Không kết nối được RTSP nguồn '{self._url}' trong {self._timeout_ms} ms "
            f"(camera offline, sai URL, hoặc mạng yếu — kiểm tra lại)"
        )


def open_video_source(source, open_timeout_ms=RtspVideoSource.DEFAULT_OPEN_TIMEOUT_MS) -> VideoSource:
    """Factory duy nhất: int → webcam; rtsp:// → RTSP; http(s):// → nguồn mạng MJPEG;
    còn lại → video file.

    Trả về instance CHƯA mở (lazy) — gọi .open() hoặc dùng `with`.
    """
    if isinstance(source, (int, np.integer)):
        return CameraVideoSource(int(source))
    text = str(source)
    lower = text.lower()
    if lower.startswith(("rtsp://", "rtspt://")):
        return RtspVideoSource(text, open_timeout_ms=open_timeout_ms)
    if lower.startswith(("http://", "https://")):
        return HttpVideoSource(text, open_timeout_ms=open_timeout_ms)
    return FileVideoSource(text)