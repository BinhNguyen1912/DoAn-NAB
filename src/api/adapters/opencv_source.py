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

import logging
import time

import cv2

from src.api.domain import LiveState, SourceHealth
from src.video_source import looks_like_file, open_video_source

logger = logging.getLogger("doan.api.opencv_source")

# Đuôi file được coi là video (để quyết định có lặp lại hay không)
_FILE_SUFFIXES = (".mp4", ".avi", ".mov", ".mkv")

# Nguồn sống chết ra sao: `read()` trả None liên tục quá lâu. Kết luận cần ĐỒNG THỜI quá `STALE_S`
# **và** ≥ `MISS_MIN` lần trượt liên tiếp (xem hằng số dưới) — **một** lần im lặng > 3 s KHÔNG đủ
# (read-timeout của nguồn là 5 s, lớn hơn 3 s: kết luận ngay sẽ giết phiên khoẻ).
# So sánh: chế độ `track` đo được 110–111 ms cho ca worker chết (`proc.poll()`, đo 09-11), còn đây
# là "không có tín hiệu" — phải chờ mới biết chắc.
# ⚠️ Đo 09-11 mới làm trên relay ảnh JPEG localhost (~3,75 s); **chưa đo trên webcam/RTSP thật**, và
# với `HttpSnapshotSource` đồng hồ 3 s chỉ bắt đầu SAU `max_misses` lần hỏng liên tiếp (nguồn giữ
# frame cuối) — mạng "black-hole" × timeout 5 s có thể làm ảnh đứng hàng phút trước khi báo lỗi.
STALE_S = 3.0

# PHẢI có thêm dung sai "một lần trượt": `HttpVideoSource`/`RtspVideoSource` đặt read-timeout 5 s
# (`src/video_source.py`), LỚN HƠN `STALE_S` ⇒ chỉ cần MỘT lần `read()` chạm timeout là `age` đã vượt
# 3 s và kết luận ngay sẽ giết một phiên hoàn toàn khoẻ (review độc lập 09-11 vòng 2, P1). Vì vậy
# chỉ kết luận khi `age > ngưỡng` **VÀ** đã trượt `MISS_MIN` lần liên tiếp — nguồn 30 Hz trượt 3 lần
# là ~0,1 s, còn nguồn có read-timeout 5 s thì 3 lần ≈ 15 s (chấp nhận được cho một lần mạng chập).
MISS_MIN = 3

# Ân hạn cho frame ĐẦU: V4L2/RTSP có thể trả False vài giây trong lúc thiết bị chưa sẵn sàng; kết
# luận theo `STALE_S` ngay từ giây thứ 3 sẽ báo lỗi trước khi phiên kịp hiện frame nào.
WARMUP_S = 10.0


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
        # Dung sai "một lần trượt": số lần liên tiếp KHÔNG ra frame + đã từng có frame chưa
        self._misses = 0
        self._got_frame = False

    def start(self) -> None:
        """Mở nguồn. Ném lỗi của video_source nếu không kết nối được."""
        self._capture = open_video_source(self._source, ).open()
        self._last_frame_at = time.monotonic()
        self._closed = False
        self._exhausted = False
        self._misses = 0
        self._got_frame = False

    def read_jpeg(self) -> bytes | None:
        """Đọc 1 frame và nén JPEG; None nếu nguồn đã cạn (file không lặp) hoặc lỗi tạm thời."""
        if self._capture is None:
            return None
        try:
            frame = self._capture.read()
        except Exception as exc:                  # noqa: BLE001 — capture hỏng (cv2.error) là "trượt"
            # `health()` kết luận bằng `_misses`, nên `read()` NÉM cũng phải được đếm như một lần
            # trượt — nếu không, ngưỡng `_misses >= MISS_MIN` làm ca này không bao giờ báo lỗi
            # (review độc lập vòng 3, P3).
            self._misses += 1
            logger.debug("đọc frame lỗi: %s", exc)
            return None
        if frame is None and self._is_file and self._loop:
            frame = self._rewind()
        if frame is None:
            if self._is_file and not self._loop:
                self._exhausted = True          # hết video, không lặp ⇒ phiên KẾT THÚC, không phải lỗi
            self._misses += 1                   # để `health()` có dung sai "một lần trượt"
            return None
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self._quality])
        if not ok:
            # Chỉ tính là "có frame" khi THẬT SỰ ra được JPEG: `imencode` hỏng mãi mà vẫn cập nhật
            # `_last_frame_at` sẽ làm `health()` báo khoẻ trong khi UI không thấy frame nào.
            self._misses += 1
            return None
        self._misses = 0
        self._got_frame = True
        self._last_frame_at = time.monotonic()
        return bytes(buffer)

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
        3. **camera/RTSP/file không trả frame quá lâu** (quá `WARMUP_S` nếu chưa có frame nào, quá
           `STALE_S` nếu đã có) **và đã trượt ≥ `MISS_MIN` lần liên tiếp** hoặc mất `capture` ⇒
           `ERROR`.

        Vì sao cần: chế độ `raw` trước đây không có watchdog — rút webcam (hoặc relay chết) thì
        `read_jpeg()` trả None mãi, API vẫn `running`, ảnh đứng trên UI (review 09-11, P3).

        Vì sao có dung sai: read-timeout của `HttpVideoSource`/`RtspVideoSource` là **5 s**, lớn hơn
        `STALE_S` ⇒ nếu kết luận ngay ở lần trượt đầu thì một cú chập mạng duy nhất giết phiên khoẻ
        (review vòng 2, P1). Đổi lại, ca "mất mạng hoàn toàn" bị chậm thêm `MISS_MIN` lần đọc.
        """
        if self._closed:
            return None                     # chủ động đóng (stop/đổi phiên) — không phải lỗi
        if self._last_frame_at is None:
            return None                     # chưa start
        if self._exhausted:
            return SourceHealth(LiveState.STOPPED, "nguồn đã hết (không lặp lại)")
        if self._capture is None:
            return SourceHealth(LiveState.ERROR, f"mất kết nối nguồn {self._source} — xem log API")
        limit = STALE_S if self._got_frame else WARMUP_S
        age = time.monotonic() - self._last_frame_at
        if age > limit and self._misses >= MISS_MIN:
            kind = "file video" if self._is_file else "camera/luồng"
            return SourceHealth(
                LiveState.ERROR,
                f"{kind} không trả frame trong {age:.0f} s ({self._misses} lần liên tiếp)"
                " — kiểm tra nguồn/kết nối",
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
        """Nguồn có "hết" được rồi lặp lại được không: file video HOẶC thư mục ảnh (`FramesVideoSource`).

        Thiếu `is_dir()` thì chuỗi ảnh (`data/demo_input_frames`) bị coi là camera: không lặp lại khi
        hết, và `health()` báo `ERROR "không trả frame"` cho một phiên kết thúc bình thường — đáng lẽ
        `STOPPED "nguồn đã hết"` (review độc lập 09-11, P2).
        """
        return looks_like_file(source)         # một định nghĩa duy nhất (src/video_source.py)
