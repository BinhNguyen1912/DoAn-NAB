"""
Chế độ hiển thị MƯỢT (tách luồng) — để demo webcam realtime trên CPU (ADR-0002).

Vấn đề: SAM 2 trên CPU mất 0.4–3 s/frame. Nếu đọc → suy luận → hiển thị tuần tự thì cửa sổ
giật đúng bằng tốc độ model (0.3–2 FPS) — người xem thấy "di chuyển mãi mới nhích".

Giải pháp (3 luồng):
  1. `LatestFrameSource` — luồng capture: liên tục đọc frame MỚI NHẤT từ nguồn (webcam),
     giữ 1 frame + mốc thời gian. Luôn có frame tươi để hiển thị ở 30 FPS.
  2. `InferenceWorker` — luồng suy luận: lấy frame mới nhất đem `engine.start/process`; xong
     thì ghi kết quả kèm mốc thời gian (bỏ qua frame nếu model còn bận — không xếp hàng).
  3. Luồng chính (display loop) — OpenCV chỉ cho 1 luồng dùng GUI: vẽ frame mới nhất + overlay
     của lần suy luận gần nhất, HUD ghi rõ "Overlay: N ms trước".

Trung thực (ADR-0002): video mượt 30 FPS nhưng mask/ô bao là của lần suy luận gần nhất
— tuổi overlay luôn hiển thị trên HUD, và metrics vẫn ghi đúng độ trễ thật từng lần suy luận.

Input  : VideoSource (webcam/RTSP/file), TrackerEngine, PromptSelector, callback display(img, mode),
         Visualizer, MetricsLogger.
Output : InteractiveSummary(processed = số lần suy luận đã chạy).
"""
import threading
import time
from dataclasses import dataclass

import cv2

from src.live_pipeline import (
    InteractiveSummary, QUIT_KEYS, RESET_KEY, _record_from, _HINT_SELECT, _HINT_TRACK,
    _switch_warning, warn_if_bad_selection,
)
from src.video_source import open_video_source

_DISPLAY_SLEEP = 1.0 / 30  # nhịp vẽ ~30 FPS


class LatestFrameSource:
    """Luồng capture: luôn giữ frame MỚI NHẤT + mốc thời gian (không xếp hàng frame cũ)."""

    def __init__(self, source):
        """source: đối tượng có read()/close() (VideoSource đã open)."""
        self._source = source
        self._frame = None
        self._ts = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.frames_captured = 0
        self.started_at = 0.0

    def start(self):
        self.started_at = time.monotonic()
        self._thread = threading.Thread(target=self._loop, name="capture", daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while not self._stop.is_set():
            frame = self._source.read()
            if frame is None:                    # nguồn cạn (file) → nghỉ ngắn rồi thử lại
                time.sleep(0.02)
                continue
            with self._lock:
                self._frame = frame
                self._ts = time.monotonic()
                self.frames_captured += 1

    def latest(self):
        """(frame, ts) mới nhất hoặc (None, 0.0)."""
        with self._lock:
            return self._frame, self._ts

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._source.close()


@dataclass
class StampedResult:
    """Kết quả suy luận + mốc thời gian + số thứ tự (để không consume trùng)."""

    seq: int
    result: object
    computed_at: float

    @property
    def age_ms(self) -> float:
        return (time.monotonic() - self.computed_at) * 1000.0


class InferenceWorker:
    """Luồng suy luận: luôn lấy frame mới nhất, không xếp hàng; đổi đối tượng = set_bbox()."""

    def __init__(self, engine, frame_source):
        self._engine = engine
        self._frames = frame_source
        self._lock = threading.Lock()
        self._stamped = None
        self._bbox = None            # bbox đang track (None = chưa chọn → không suy luận)
        self._pending = None         # yêu cầu từ main thread: ("start", bbox) | ("clear", None)
        self._stop = threading.Event()
        self._thread = None
        self._seq = 0
        self.inference_count = 0
        self._started = False   # engine đã start với bbox hiện tại chưa

    def start(self):
        self._thread = threading.Thread(target=self._loop, name="inference", daemon=True)
        self._thread.start()
        return self

    def set_bbox(self, bbox):
        """Yêu cầu bắt đầu/chọn lại đối tượng.

        CHỈ ghi yêu cầu — mọi thao tác trên engine do luồng suy luận thực hiện, vì gọi
        `engine.reset()` từ main thread trong lúc model đang chạy sẽ phá state
        (`TypeError: 'NoneType' object is not subscriptable`) — bug thật gặp 18-10.
        """
        with self._lock:
            self._pending = ("start", tuple(bbox))
            self._stamped = None

    def clear(self):
        """Dừng suy luận, quay về chế độ chờ chọn đối tượng (phím r).

        Xoá luôn kết quả cũ để vòng hiển thị trở về chế độ chọn (bug thật 18-10:
        không xoá → màn hình vẫn ở chế độ track nên không kéo chọn lại được).
        """
        with self._lock:
            self._pending = ("clear", None)
            self._stamped = None
            self._bbox = None
            self._started = False

    def is_tracking(self):
        """Đang có đối tượng để bám hay không (main thread dùng để quyết định chế độ hiển thị)."""
        with self._lock:
            return self._bbox is not None

    def latest_result(self):
        with self._lock:
            return self._stamped

    def _loop(self):
        while not self._stop.is_set():
            # 1) Xử lý yêu cầu từ main thread (chỉ nơi này được chạm vào engine)
            with self._lock:
                pending, self._pending = self._pending, None
            if pending is not None:
                action, bbox_req = pending
                try:
                    self._engine.reset()
                except Exception as exc:
                    print(f"[LOI] reset engine thất bại: {type(exc).__name__}: {exc}")
                with self._lock:
                    self._started = False
                    self._bbox = bbox_req if action == "start" else None
                    if action != "start":
                        self._stamped = None

            # 2) Suy luận trên frame MỚI NHẤT
            with self._lock:
                bbox = self._bbox
                need_start = not self._started
            frame, _ = self._frames.latest()
            if bbox is None or frame is None:
                time.sleep(0.01)
                continue
            try:
                if need_start:
                    result = self._engine.start(frame, bbox)
                    warn_if_bad_selection(result)
                    with self._lock:
                        self._started = True
                else:
                    result = self._engine.process(frame)
            except Exception as exc:
                # State có thể đã hỏng → về chế độ chờ chọn, KHÔNG lặp lỗi vô hạn
                print(f"[LOI] suy luận thất bại: {type(exc).__name__}: {exc} — "
                      f"bấm r để chọn lại đối tượng")
                try:
                    self._engine.reset()
                except Exception:
                    pass
                with self._lock:
                    self._bbox = None
                    self._started = False
                    self._stamped = None
                time.sleep(0.1)
                continue
            with self._lock:
                self._seq += 1
                self.inference_count += 1
                self._stamped = StampedResult(self._seq, result, time.monotonic())

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)


def run_smooth_display(source, engine, selector, display, max_frames=None, metrics=None,
                       visualizer=None, preselect_bbox=None,
                       on_result=None) -> InteractiveSummary:
    """Vòng lặp hiển thị mượt: video ~30 FPS, overlay cập nhật mỗi lần suy luận xong.

    display: callable(img, mode) -> key (int) — với chạy thật là cv2.imshow + waitKey.
    Trả InteractiveSummary(processed = số lần suy luận).
    """
    summary = InteractiveSummary()
    frames = LatestFrameSource(open_video_source(source).open()).start()
    worker = InferenceWorker(engine, frames).start()
    consumed_seq = 0
    last_bbox = None
    switch = False
    mode = "select"
    selector_bound = False
    disp_count, disp_t0 = 0, time.monotonic()

    try:
        if preselect_bbox is not None:
            worker.set_bbox(preselect_bbox)
            mode = "track"
        while True:
            frame, _ = frames.latest()
            if frame is None:
                time.sleep(0.01)
                continue
            if not selector_bound:
                selector.bind(frame)          # lần đầu: biết kích thước frame
                selector_bound = True

            stamped = worker.latest_result() if worker.is_tracking() else None
            img = None
            if stamped is not None and stamped.seq != consumed_seq:  # mỗi kết quả 1 lần
                consumed_seq = stamped.seq
                summary.processed += 1
                switch = _switch_warning(last_bbox, stamped.result, frame.shape[:2])
                if stamped.result.mask.any():
                    last_bbox = stamped.result.bbox
                if visualizer is not None:
                    visualizer.consume(stamped.result)
                if metrics is not None:
                    metrics.log(_record_from(stamped.result))
                if on_result is not None:
                    on_result(stamped.result)
            if stamped is not None:
                mode = "track"
                if visualizer is not None:
                    elapsed = max(time.monotonic() - disp_t0, 1e-6)
                    display_fps = disp_count / elapsed if disp_count else 0.0
                    img = visualizer.render(frame, stamped.result,
                                            overlay_age_ms=stamped.age_ms,
                                            display_fps=display_fps,
                                            switch_warning=switch)
                else:                       # không có HUD: vẫn phải giữ chế độ track
                    img = frame.copy()
                cv2.putText(img, _HINT_TRACK, (8, 50), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (255, 255, 255), 1, cv2.LINE_AA)
            else:
                mode = "select"
                img = selector.draw(frame)
                cv2.putText(img, _HINT_SELECT, (8, 24), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (255, 255, 255), 1, cv2.LINE_AA)

            key = display(img, mode)
            disp_count += 1
            if time.monotonic() - disp_t0 > 2.0:      # cửa sổ trượt 2 giây
                disp_count, disp_t0 = 0, time.monotonic()
            if key in QUIT_KEYS:
                break
            if key == RESET_KEY:
                selector.bind(frame)
                worker.clear()
                consumed_seq = 0
                if visualizer is not None:
                    visualizer.reset()
                mode = "select"
                continue
            if mode == "select" and selector.has_bbox():
                worker.set_bbox(selector.take_bbox())
                if visualizer is not None:
                    visualizer.reset()
            if max_frames is not None and summary.processed >= max_frames:
                break
            time.sleep(_DISPLAY_SLEEP)
    finally:
        worker.stop()
        frames.stop()
    return summary
