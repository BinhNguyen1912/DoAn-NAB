"""
LiveStreamService — phiên phát trực tiếp: giữ nguồn frame, phát frame mới nhất cho client.

Chức năng: mở nguồn (webcam/RTSP/ảnh relay/file lặp), chạy một thread đọc frame theo nhịp
           `target_fps`, giữ **frame mới nhất** trong bộ đệm 1 phần tử (client chậm thì bỏ
           frame cũ, không bao giờ chậm dần), và cung cấp luồng JPEG cho endpoint MJPEG.
Input  : `make_source(source, mode, bbox) -> FrameSource` (nhà máy được tiêm vào), target_fps.
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

from src.api.domain import LiveBusy, LiveState, LiveStatus, SourceUnavailable
from src.api.ports import FrameSource, HealthReportingSource, LiveTelemetrySource

logger = logging.getLogger("doan.api.live")

_TICK_S = 0.01          # nhịp chờ nhỏ khi nguồn chưa có frame / khi client chậm
# Nhịp ĐỌC frame của API. Phải >= nhịp PHÁT của worker (`--max-fps` mặc định 30): đọc 15 Hz trong
# khi worker ghi 30 Hz sẽ báo FPS trần 15 — lệch hẳn 29,9 của status.json (lỗi P2, review 08-11).
LIVE_READ_FPS = 30

_FPS_WINDOW_S = 2.0     # cửa sổ đo FPS thực
# Nhịp KIỂM TRA SỨC SỐNG của nguồn. Không kiểm mỗi frame (30 lần/giây): mỗi lần kiểm là một lần
# `proc.poll()` + đọc `status.json` + `stat(frame.jpg)`. 0,2 s đủ nhanh để UI báo lỗi trong ≤ 1 s
# (mục tiêu của plan là ≤ 2 s) mà không đụng tới đường đọc frame nóng.
_HEALTH_EVERY_S = 0.2
# Tấm chắn cuối cho nguồn KHÔNG tự khai sức sống (`FrameSource` không phải `HealthReportingSource`):
# `read_jpeg()` ném lỗi liên tục quá lâu thì phiên coi như chết, thay vì `running` mãi mà 0 frame.
_READ_ERROR_GIVE_UP_S = 5.0
# Log lần đầu + mỗi 100 lần: nhịp đọc 30 Hz ⇒ log từng lần là ~1.800 dòng/phút, che mất log thật.
_READ_ERROR_LOG_EVERY = 100
_JPEG_BOUNDARY = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
_MAX_OPEN_ERROR = "Không mở được {label}: {error}"


class LiveStreamService:
    """Một phiên live tại một thời điểm (đủ cho đồ án; đa phiên sẽ cần kho theo id)."""

    def __init__(self, make_source: Callable[..., FrameSource], *, target_fps: int = LIVE_READ_FPS) -> None:
        self._make_source = make_source
        self._interval = 1.0 / max(1, int(target_fps))
        self._lock = threading.Lock()
        # Một lần `start()` tại một thời điểm: mở nguồn worker có thể mất 20–240 s (nạp model).
        # Hai request đồng thời (double-click, 2 tab, curl) sẽ tạo 2 worker cùng ghi
        # /dev/shm/doan-live ⇒ frame trộn của hai phiên, và worker thua bị mất tham chiếu (rò).
        self._start_lock = threading.Lock()
        self._pending: FrameSource | None = None    # nguồn đang mở (để stop() huỷ được)
        # "Thế hệ" phiên: thread đọc của phiên CŨ không được ghi `_latest` sau khi phiên mới/stop
        # đã dọn. Không có nó, `stop()` xoá `_latest` rồi thread (vừa quá join(2s)) ghi lại ⇒ test
        # `latest_jpeg() is None` chập chờn (gặp thật 08-11).
        self._generation = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._source: FrameSource | None = None
        self._latest: bytes | None = None
        self._frames = 0
        self._stamps: deque = deque()
        self._state = LiveState.STOPPED
        self._label = ""
        self._message = "Chưa phát"
        # Đếm lỗi đọc liên tiếp (xem `_note_read_error`); mốc thời gian đầu chuỗi lỗi
        self._read_errors = 0
        self._read_error_since: float | None = None

    # ------------------------------------------------------------------ lệnh

    def start(self, source: str, *, mode: str = "raw", bbox=None,
              image_size: int | None = None, vos_every: int | None = None,
              mask_smoothing: float | None = None) -> LiveStatus:
        """Mở nguồn và bắt đầu phát.

        mode="raw"   : phát khung hình gốc (nhanh, không cần model).
        mode="track" : chạy worker bám đối tượng ở tiến trình riêng (cần bbox), phát frame đã overlay.
        Ném SourceUnavailable nếu không mở được nguồn/worker, LiveBusy nếu đang mở phiên khác.
        """
        if not self._start_lock.acquire(blocking=False):
            # KHÔNG chờ: nạp model có thể 20–240 s; chờ sẽ treo HTTP request và vẫn có thể
            # tạo worker thứ hai nếu client kịp retry.
            raise LiveBusy("đang mở một phiên live khác (nạp model) — chờ vài giây rồi thử lại")
        try:
            with self._lock:
                self._stop_locked()
                self._stop.clear()          # xoá dấu stop cũ để phiên mới không tự huỷ

            candidate = self._make_source(str(source), mode, bbox, image_size, vos_every,
                                          mask_smoothing)
            with self._lock:                # công bố TRƯỚC khi mở → stop() huỷ được giữa chừng
                self._pending = candidate
                self._label = candidate.label
                # `LOADING`, không giữ `error` của phiên trước: nạp worker `track` mất 20–240 s, mà
                # để `error` thì UI hiện `role="alert"` + `/api/live/stream` trả 409 "đã dừng vì lỗi"
                # trong suốt lúc nạp bình thường (ticket 16, P3 review vòng 4).
                self._state = LiveState.LOADING
                self._message = f"Đang mở {candidate.label}…"
            try:
                candidate.start()
            except Exception as exc:                      # noqa: BLE001 — mọi lỗi mở nguồn là 400
                with self._lock:
                    self._pending = None
                    cancelled = self._stop.is_set()
                    self._state = LiveState.STOPPED if cancelled else LiveState.ERROR
                    self._message = ("Đã dừng khi đang mở nguồn" if cancelled
                                     else _MAX_OPEN_ERROR.format(label=candidate.label, error=exc))
                    message = self._message
                candidate.stop()
                if cancelled:
                    logger.info("huỷ mở nguồn theo lệnh dừng: %s", candidate.label)
                    return self.status()
                raise SourceUnavailable(message) from exc

            with self._lock:
                self._pending = None
                cancelled = self._stop.is_set()      # stop() được gọi trong lúc nạp model
                if not cancelled:
                    self._source = candidate
                    self._latest = None
                    self._frames = 0
                    self._stamps.clear()
                    # PHẢI reset bộ đếm lỗi đọc theo TỪNG phiên: để rò từ phiên trước thì lần đọc
                    # lỗi ĐẦU TIÊN của phiên mới thấy `stuck_s` = hàng chục giây ⇒ give-up ngay và
                    # giết phiên khoẻ sau một lỗi tạm thời (review độc lập vòng 3, P1).
                    self._read_errors = 0
                    self._read_error_since = None
                    self._label = candidate.label
                    self._state = LiveState.RUNNING
                    self._message = f"Đang phát từ {candidate.label}"
                    self._generation += 1
                    self._thread = threading.Thread(target=self._run, args=(self._generation,),
                                                    name="live-stream", daemon=True)
                    self._thread.start()
            if cancelled:
                candidate.stop()                     # không để worker mồ côi
                logger.info("huỷ phiên live vừa mở vì đã có lệnh dừng: %s", candidate.label)
                return self.status()
            logger.info("bắt đầu live: %s", candidate.label)
            return self.status()
        finally:
            self._start_lock.release()

    def stop(self) -> LiveStatus:
        """Dừng phát và đóng nguồn.

        Gọi trong lúc `start()` đang nạp model: `self._stop` được set ⇒ sau khi `start()` xong,
        nó tự đóng nguồn vừa mở thay vì để worker mồ côi chạy tiếp.
        """
        with self._lock:
            self._stop_locked()
            self._state = LiveState.STOPPED     # kể cả phiên trước đang ERROR
            self._message = "Đã dừng"
        return self.status()

    # ------------------------------------------------------------------ truy vấn

    def status(self) -> LiveStatus:
        with self._lock:
            # `_pending` = nguồnđang mở (worker `track` nạp model 20–240 s, `self._source` còn None).
            # Phải đọc luôn nó: không thì suốt giai đoạn `loading` API trả `device=""` và HUD ẩn
            # dòng thiết bị đúng lúc người xem cần biết nhất (P2, review độc lập 12-11 — ticket 21).
            source = self._pending or self._source
            base = dict(
                state=self._state,
                source=self._label,
                frames=self._frames,
                measured_fps=self._measured_fps_locked(),
                message=self._message,
            )
        # Đọc số liệu chi tiết NGOÀI lock (đọc file, có thể chậm) — nguồn không hỗ trợ thì bỏ qua
        if isinstance(source, LiveTelemetrySource):
            try:
                detail = source.telemetry()
            except Exception as exc:               # noqa: BLE001 — số liệu hỏng không được làm sập API
                # NHƯNG không được im lặng: nuốt lỗi ở đây từng làm cả một trường số liệu mới
                # "chết trong adapter" mà test vẫn xanh (bài học 08-11)
                logger.warning("đọc số liệu từ nguồn live thất bại: %s", exc)
                detail = None
            if detail is not None:
                base.update(display_fps=detail.display_fps, mask_fps=detail.mask_fps,
                            device=detail.device,
                            stability=detail.stability, stability_n=detail.stability_n,
                            latency_ms=detail.latency_ms,
                            empty_runs=detail.empty_runs,
                            empty_frac_window=detail.empty_frac_window,
                            empty_window_n=detail.empty_window_n,
                            drift_p05=detail.drift_p05, drift_n=detail.drift_n,
                            mask_age_total_ms=detail.mask_age_total_ms,
                            mask_age_p95=detail.mask_age_p95, age_n=detail.age_n)
        return LiveStatus(**base)

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

    def _run(self, generation: int) -> None:
        """Thread đọc frame: luôn giữ frame mới nhất, bỏ frame cũ khi client chậm.

        `generation` là thế hệ phiên: thread của phiên cũ tự thoát và **không ghi** `_latest`,
        kể cả khi `stop()` đã join timeout và nó còn sống thêm một nhịp.

        Watchdog: mỗi `_HEALTH_EVERY_S`, hỏi nguồn (nếu nó tự khai được sức sống) một câu. Nguồn
        chết/treo ⇒ `Error`/`Stopped` + message, thread thoát ⇒ `frames()` đóng luồng MJPEG thay vì
        treo client. KHÔNG xoá `_latest`: ảnh cuối vẫn còn cho `/api/live/frame` vài giây cuối.
        """
        next_health = 0.0
        while not self._stop.is_set():
            started = time.perf_counter()
            with self._lock:
                if generation != self._generation:
                    return
                source = self._source
            if source is not None and started >= next_health:
                next_health = started + _HEALTH_EVERY_S
                if self._check_health(source, generation):
                    return
            data = self._read_safely(source, generation)
            if data is not None:
                with self._lock:
                    if generation != self._generation:
                        return
                    # CHỈ đếm khi nội dung ĐỔI: với chế độ track, worker ghi frame chậm hơn nhịp
                    # đọc rất nhiều (model 2,5 s/frame) — đếm theo lần đọc sẽ báo sai 15 FPS
                    # trong khi thực tế 0,4 FPS (bug thật đo được 08-11).
                    changed = data != self._latest
                    if changed:
                        self._latest = data
                        self._frames += 1
                        self._stamps.append(started)
                        self._trim_stamps_locked(started)
            else:
                time.sleep(_TICK_S)                   # nguồn chưa có frame (camera khởi động)
            remaining = self._interval - (time.perf_counter() - started)
            if remaining > 0:
                self._stop.wait(remaining)

    def _read_safely(self, source: FrameSource | None, generation: int) -> bytes | None:
        """`read_jpeg()` không được phép làm CHẾT thread đọc.

        Nếu adapter ném (capture hỏng, codec lạ), thread sẽ chết mà `_state` vẫn `running` — đúng
        lớp lỗi "hỏng mà trông như đang chạy" mà watchdog này sinh ra để xoá (review 09-11, P3).
        Coi như "frame này không có": watchdog/sức sống của nguồn sẽ quyết định sau.
        """
        if source is None:
            return None
        try:
            data = source.read_jpeg()
        except Exception as exc:                       # noqa: BLE001 — không được làm sập thread
            self._note_read_error(source, generation, exc)
            return None
        if self._read_errors:
            with self._lock:
                if generation == self._generation:
                    self._read_errors = 0
                    self._read_error_since = None
        return data

    def _note_read_error(self, source: FrameSource, generation: int, exc: BaseException) -> None:
        """Ghi nhận một lần `read_jpeg()` ném lỗi — có đếm, có ngưỡng, không xả log 30 Hz.

        Vì sao cần ngưỡng: `_read_safely` nuốt lỗi để thread không chết, nhưng nếu nguồn *không*
        tự khai được sức sống (`FrameSource` trơn) thì nuốt lỗi = `running` vĩnh viễn mà 0 frame.
        Lỗi liên tiếp quá `_READ_ERROR_GIVE_UP_S` ⇒ `error` + message (review 09-11 vòng 2, P3).
        """
        should_fail = False
        with self._lock:
            if generation != self._generation:
                return
            self._read_errors += 1
            if self._read_error_since is None:
                self._read_error_since = time.monotonic()
            count = self._read_errors
            stuck_s = time.monotonic() - self._read_error_since
            label = self._label
            if stuck_s > _READ_ERROR_GIVE_UP_S and self._state is LiveState.RUNNING:
                self._state = LiveState.ERROR
                self._message = f"đọc frame từ {label} lỗi liên tiếp {stuck_s:.0f} s: {exc}"
                # Đánh dấu dừng để thread đọc thoát (nguồn sẽ được đóng ở `stop()`/`start()` sau)
                self._stop.set()
                should_fail = True
        if count == 1 or count % _READ_ERROR_LOG_EVERY == 0:
            logger.warning("đọc frame từ %s thất bại %d lần liên tiếp: %s", label, count, exc)
        if should_fail:
            logger.error("nguồn live lỗi (%s): %s", label, self._message)
            # Đóng nguồn ngay (NGOÀI `_lock`): nguồn còn giữ webcam/thiết bị thì lần "Bật phát"
            # sau sẽ không mở được. Cùng lý do như `_check_health` (review vòng 3, P3).
            try:
                source.stop()
            except Exception:                          # noqa: BLE001 — dọn dẹp lỗi không được ném
                logger.warning("đóng nguồn live sau khi give-up gặp lỗi", exc_info=True)

    def _check_health(self, source: FrameSource, generation: int) -> bool:
        """Nguồn đã chết/treo/kết thúc? True = thread đọc phải dừng.

        Lỗi trong lúc kiểm tra KHÔNG phải bằng chứng nguồn chết (đọc file có thể hỏng tạm thời):
        ghi cảnh báo rồi đi tiếp. Nuốt im lặng thì không được — chính lỗi "chết trong adapter" đã
        làm một trường số liệu ngừng chạy mà test vẫn xanh (review 08-11).
        """
        if not isinstance(source, HealthReportingSource):
            return False
        try:
            health = source.health()
        except Exception as exc:                       # noqa: BLE001 — không được làm sập thread
            logger.warning("kiểm tra sức sống nguồn live thất bại: %s", exc)
            return False
        if health is None:
            return False
        with self._lock:
            if generation != self._generation:
                return True                            # phiên đã bị thay thế: chỉ cần thoát
            if self._state is not LiveState.RUNNING:
                return True
            self._state = health.state
            self._message = health.message or "nguồn đã dừng"
            label = self._label
        if health.state is LiveState.ERROR:
            logger.error("nguồn live lỗi (%s): %s", label, health.message)
        else:
            logger.info("nguồn live kết thúc (%s): %s", label, health.message)
        # Dọn nguồn ngay: worker TREO mà còn sống thì vẫn giữ webcam/GPU, và lần "Bật phát" sau sẽ
        # không mở được nguồn. Gọi NGOÀI `_lock` (stop() có thể chờ SIGTERM tới 2 s); stop() lần
        # hai từ request `stop()` là vô hại (adapter đã đặt `_proc = None`).
        try:
            source.stop()
        except Exception:                          # noqa: BLE001 — dọn dẹp lỗi không được ném
            logger.warning("đóng nguồn live sau khi phát hiện lỗi gặp lỗi", exc_info=True)
        return True

    def _stop_locked(self) -> None:
        """Dừng thread + đóng nguồn. Caller phải giữ `_lock`.

        Lưu ý: KHÔNG được gọi `self.status()` ở đây (nó cũng cần `_lock` → deadlock).
        """
        self._stop.set()
        self._generation += 1        # vô hiệu hoá thread cũ: nó không được ghi `_latest` nữa
        thread, self._thread = self._thread, None
        source, self._source = self._source, None
        pending, self._pending = self._pending, None
        if pending is not None and pending is not source:
            # Nguồn đang NẠP (worker mở model 20–60 s): đóng luôn để `start()` không phải chờ
            # hết `startup_timeout`, và để không có worker mồ côi.
            try:
                pending.stop()
            except Exception:                   # noqa: BLE001 — đóng nguồn lỗi không được ném
                logger.warning("đóng nguồn đang mở gặp lỗi", exc_info=True)
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
