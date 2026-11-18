"""
VideoSource — seam thống nhất để lấy frame từ mọi nguồn video.

Chức năng: cung cấp một interface duy nhất cho 3 nguồn — webcam (index), camera rời/
điện thoại qua RTSP URL, video file — để phần còn lại của hệ thống (pipeline, headless)
không cần quan tâm nguồn ở đâu.

Input  : `open_video_source(source)` với source là int (webcam index) — hoặc chuỗi chỉ gồm
         chữ số ("0", "1" … do lớp HTTP/UI truyền xuống) —, đường dẫn file, hoặc chuỗi rtsp://...
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
import os
from pathlib import Path
import sys
import urllib.request

import cv2
import numpy as np
from src.url_safe import an_userinfo


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
        # Che `user:pass@` (review vòng 2, P2-2): nguồn có scheme LẠ (`rtsps://`, `rtmp://`) hoặc dán
        # kèm dấu cách đầu sẽ RƠI VÀO ĐÂY thay vì adapter mạng ⇒ chuỗi này đi tiếp vào HTTP 400
        # (`detail`), `status.json.message` và `worker.log`.
        raise FileNotFoundError(
            f"Không mở được video file: '{an_userinfo(str(self._path))}' "
            f"(file không tồn tại hoặc codec không đọc được)"
        )


class CameraVideoSource(_CaptureSource):
    """Webcam/cam USB cục bộ theo index (adapter mỏng — kiểm chứng thủ công)."""

    def __init__(self, index=0):
        super().__init__()
        self._index = int(index)

    def _create_capture(self):
        # Linux: OpenCV 5.0 thử backend obsensor/UVC trước → với webcam UVC qua usbipd
        # isOpened()=True nhưng read() luôn False. V4L2 đọc được thật (đo 18-10) → ưu tiên.
        # Ngoài ra webcam này CHỈ trả frame khi ép FOURCC=MJPG + 640x480 (đo 4 tổ hợp:
        # không set → read False kể cả chờ 1s/retry 10 lần; set MJPG → read OK ngay).
        is_linux = sys.platform.startswith("linux")
        backends = (cv2.CAP_V4L2, cv2.CAP_ANY) if is_linux else (cv2.CAP_ANY,)
        for backend in backends:
            cap = cv2.VideoCapture(self._index, backend)
            if cap.isOpened():
                if is_linux:
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                # Đệm 1 frame: driver mặc định giữ 4 frame (đo thật) → sau mỗi lần xử lý
                # 0.5-3s, hàng đợi toàn frame CŨ → cảm giác "di chuyển mãi mới thấy".
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return cap
            cap.release()
        return cv2.VideoCapture(self._index, backends[0])

    def _raise_open_error(self):
        # KHÔNG khuyên "thử index khác" như bản cũ: trên máy demo này webcam kẹt ở DRIVER usbipd-win
        # (`Device busy (exported)`), đã thử index 1, `wsl --shutdown`, reboot, unbind/bind, restart
        # service — không khỏi (AGENTS §6). Hai đường đã chạy được: relay HTTP và file video.
        raise RuntimeError(
            f"Không mở được camera index {self._index} (bận hoặc không tồn tại — kiểm tra thiết bị, "
            "máy nhiều camera thì thử `--source 1`). Nếu máy kẹt driver `usbipd` (WSL) thì index khác "
            "CŨNG không cứu được: dùng relay (`./run relay`, URL lấy từ "
            "`bash scripts/cam_relay.sh snapurl`) hoặc một clip có sẵn (`--source <clip>.mp4`)"
        )


class FramesVideoSource(VideoSource):
    """Đọc frame từ **thư mục ảnh** (JPEG/PNG đã tách sẵn) — định dạng SAM 2 gốc dùng.

    Vì sao cần: bản SAM 2 gốc nhận `video_path` là **thư mục JPEG**, không nhận file video.
    Repo có sẵn `data/demo_input_frames/` (90 ảnh 1280x720 tách từ video demo) nên cần adapter
    này để chạy được:  `python tools/run_live.py --source data/demo_input_frames --display`
    """

    _EXTS = (".jpg", ".jpeg", ".png", ".bmp")

    def __init__(self, path, fps=30.0):
        self._path = str(path)
        self._fps = float(fps)
        self._files = []
        self._idx = 0
        self._size = None

    def open(self):
        names = [n for n in os.listdir(self._path)
                 if n.lower().endswith(self._EXTS)] if os.path.isdir(self._path) else []
        self._files = sorted(names)              # 00000.jpg, 00001.jpg, ...
        if not self._files:
            raise FileNotFoundError(
                f"Thư mục '{self._path}' không có ảnh nào ({', '.join(self._EXTS)}) — "
                f"kiểm tra lại đường dẫn hoặc tách frame từ video trước"
            )
        first = cv2.imread(os.path.join(self._path, self._files[0]))
        if first is None:
            raise FileNotFoundError(f"Không đọc được ảnh đầu tiên trong '{self._path}'")
        self._size = (first.shape[1], first.shape[0])   # (W, H)
        self._idx = 0
        return self

    @property
    def frame_size(self):
        if self._size is None:
            raise RuntimeError("Gọi open() trước khi đọc thuộc tính nguồn")
        return self._size

    @property
    def source_fps(self):
        return self._fps

    def read(self):
        if not self._files:
            raise RuntimeError("Gọi open() trước khi read()")
        if self._idx >= len(self._files):
            return None
        frame = cv2.imread(os.path.join(self._path, self._files[self._idx]))
        self._idx += 1
        return frame

    def close(self):
        self._files = []
        self._idx = 0


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
            f"Không mở được nguồn mạng '{an_userinfo(str(self._url))}' trong "
            f"{self._timeout_ms} ms{hint}. "
            f"Kiểm tra: (1) IP thật + điện thoại và máy cùng mạng Wi-Fi; (2) app đã bấm "
            f"Start server; (3) đúng đường dẫn stream (thường là /video); (4) một số app chỉ "
            f"phát RTSP → dùng rtsp://…"
        )


def is_snapshot_url(url):
    """URL http(s) là **ảnh JPEG rời** (không phải luồng MJPEG)?

    Vì sao cần phân biệt: `cv2.VideoCapture` (đường MJPEG) tốn ~30 ms/frame vì FFMPEG phải
    demux và chờ frame kế tiếp, trong khi lấy 1 ảnh JPEG + `cv2.imdecode` chỉ ~8 ms
    (đo 05-11-2026 trên relay camera Windows 640x480 trong repo).
    """
    path = str(url).split("?", 1)[0].lower()
    return path.endswith((".jpg", ".jpeg")) or "/snapshot" in path


class HttpSnapshotSource(VideoSource):
    """Nguồn camera IP/relay đọc **từng ảnh JPEG rời** (`.../snapshot.jpg`), không dùng MJPEG.

    Dùng khi: relay của repo (`scripts/win_camera_relay.py`) — nó có cả `/video` (MJPEG) và
    `/snapshot.jpg`. Ở nhịp suy luận ~5 FPS của CPU, hỏi từng ảnh rẻ và ít trễ hơn hẳn:
    đo 05-11-2026 → MJPEG `read()` 30,2 ms/frame vs snapshot 8,4 ms/frame.

    Ngữ nghĩa lỗi: nguồn live không được kết thúc pipeline vì một lần mạng chập chờn, nên
    `read()` trả lại FRAME CUỐI khi lấy ảnh thất bại; chỉ trả None (hết nguồn) sau
    `max_misses` lần hỏng liên tiếp.
    """

    def __init__(self, url, timeout_s=5.0, max_misses=20):
        self._url = str(url)
        self._timeout_s = float(timeout_s)
        self._max_misses = int(max_misses)
        self._size = None
        self._last = None
        self._misses = 0

    def open(self):
        frame = self._fetch(attempts=3)
        if frame is None:
            raise ConnectionError(
                f"Không lấy được ảnh JPEG từ '{an_userinfo(str(self._url))}' (thử 3 lần). "
                f"Kiểm tra: relay/camera "
                f"đã chạy chưa, đúng IP:port chưa, và đường dẫn có phải ảnh JPEG "
                f"(ví dụ http://<IP>:8090/snapshot.jpg)"
            )
        self._last = frame
        self._size = (frame.shape[1], frame.shape[0])      # (W, H)
        self._misses = 0
        return self

    @property
    def frame_size(self):
        if self._size is None:
            raise RuntimeError("Gọi open() trước khi đọc thuộc tính nguồn")
        return self._size

    @property
    def source_fps(self):
        # Nguồn "kéo" — không có FPS cố định; pipeline tự đo FPS thực
        return 0.0

    def _fetch(self, attempts=1):
        for _ in range(max(1, attempts)):
            try:
                with urllib.request.urlopen(self._url, timeout=self._timeout_s) as resp:
                    data = resp.read()
                frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    return frame
            except Exception:
                continue
        return None

    def read(self):
        if self._last is None:
            raise RuntimeError("Gọi open() trước khi read()")
        frame = self._fetch(attempts=2)
        if frame is not None:
            self._last = frame
            self._misses = 0
            return frame
        self._misses += 1
        if self._misses >= self._max_misses:
            return None                     # hỏng liên tục → kết thúc như hết nguồn
        return self._last                   # giữ frame cuối, không làm chết demo

    def close(self):
        self._last = None
        self._misses = 0


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
            f"Không kết nối được RTSP nguồn '{an_userinfo(str(self._url))}' trong "
            f"{self._timeout_ms} ms "
            f"(camera offline, sai URL, hoặc mạng yếu — kiểm tra lại)"
        )


FILE_SUFFIXES = (".mp4", ".avi", ".mov", ".mkv")   # một nguồn sự thật cho mọi nơi cần


def looks_like_file(source) -> bool:
    """Nguồn có ĐIỂM KẾT THÚC (file video / thư mục ảnh) ⇒ "hết rồi lặp lại" có nghĩa.

    Webcam (int hoặc chuỗi số), RTSP, HTTP ⇒ `False`: `read()` trả `None` ở đó là mất tín hiệu, mở
    lại thiết bị giữa phiên là bắn vào chân (relay/`usbipd` còn giữ ⇒ "Device busy", AGENTS §6).

    Một chỗ định nghĩa cho cả `LiveTrackingSession._rewind` (đường `track`) và
    `opencv_source._looks_like_file` (đường `raw`) — trước 14-11 hai đường lệch chuẩn nhau.
    """
    if isinstance(source, (int, np.integer)):
        return False
    text = str(source)
    stripped = text.strip()
    if stripped.isdecimal() and not os.path.exists(stripped):
        return False                               # "0" = index webcam (xem factory dưới)
    path = Path(text)
    return path.suffix.lower() in FILE_SUFFIXES or path.is_file() or path.is_dir()


def is_camera_source(source) -> bool:
    """`source` có được hiểu là **CHỈ SỐ CAMERA** (webcam) không? — MỘT bản duy nhất.

    Vì sao phải là hàm dùng chung: `scripts/demo_preflight.py` cần biết "đây là webcam" để in gợi ý
    relay/file. Bản đầu của nó tự viết `str(source).strip().isdigit()` và **lệch** với quy tắc thật ở
    đây ba chỗ: (a) file/thư mục THẬT tên `0` phải là file, không phải webcam (quy ước từ 13-11);
    (b) `isdigit()` nhận `"²"` trong khi `int("²")` ném; (c) `np.integer` cũng là index camera.
    """
    if isinstance(source, (int, np.integer)):
        return True
    stripped = str(source).strip()
    # `isdecimal()`, KHÔNG `isdigit()`: "²".isdigit() là True nhưng `int("²")` ném ValueError
    return stripped.isdecimal() and not os.path.exists(stripped)


def open_video_source(source, open_timeout_ms=RtspVideoSource.DEFAULT_OPEN_TIMEOUT_MS) -> VideoSource:
    """Factory duy nhất: int (hoặc chuỗi chỉ gồm chữ số) → webcam; rtsp:// → RTSP;
    http(s):// → nguồn mạng MJPEG (hoặc ảnh JPEG rời nếu URL là snapshot); thư mục → dãy ảnh
    (frames); còn lại → video file.

    Trả về instance CHƯA mở (lazy) — gọi .open() hoặc dùng `with`.

    Vì sao nhận cả chuỗi số: hợp đồng HTTP của web khai `source: str` với "0 = webcam"
    (`src/api/schemas.py`), và UI mặc định gửi đúng chuỗi `"0"`. Trước 13-11-2026 chuỗi đó rơi
    vào `FileVideoSource` ⇒ live từ web báo "Không mở được video file: '0'" dù người dùng chọn
    webcam (cả mode `raw` lẫn `track`). Ưu tiên vẫn là file/thư mục THẬT trùng tên (một file tên
    "0" là đường dẫn hợp lệ) nên chỉ đổi khi không có gì tồn tại ở tên đó.
    """
    if isinstance(source, (int, np.integer)):
        return CameraVideoSource(int(source))
    text = str(source)
    if is_camera_source(source):
        return CameraVideoSource(int(text.strip()))
    lower = text.lower()
    if lower.startswith(("rtsp://", "rtspt://")):
        return RtspVideoSource(text, open_timeout_ms=open_timeout_ms)
    if lower.startswith(("http://", "https://")):
        if is_snapshot_url(lower):
            return HttpSnapshotSource(text)
        return HttpVideoSource(text, open_timeout_ms=open_timeout_ms)
    if os.path.isdir(text):                      # thư mục ảnh (định dạng SAM 2 gốc)
        return FramesVideoSource(text)
    return FileVideoSource(text)