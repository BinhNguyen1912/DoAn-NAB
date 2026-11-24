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
    CONTINUE_KEY, IdentityWatch, _switch_warning, warn_if_bad_selection, chuan_hoa_phim,
)
from src.video_source import open_video_source

_DISPLAY_SLEEP = 1.0 / 30  # nhịp vẽ ~30 FPS
# Số lần thử lại một ngoại lệ suy luận TRƯỚC khi bỏ ô và về chế độ chờ chọn (review vòng 2, 23-11).
_LOI_THU_LAI = 3


class LatestFrameSource:
    """Luồng capture: luôn giữ frame MỚI NHẤT + mốc thời gian (không xếp hàng frame cũ)."""

    def __init__(self, source, max_fps=None):
        """source: đối tượng có read()/close() (VideoSource đã open).

        `max_fps`: TRẦN số lần đọc nguồn mỗi giây (`None` = không chặn).
        Vì sao có (plan 24-11, việc 3): vòng này đọc **hết tốc lực**, đo trên relay ảnh JPEG
        localhost = **293 lần/s** cho một nguồn chỉ phát **~16 fps** ⇒ 18 lần giải mã JPEG vô ích
        mỗi khung, 1,6 MB/s loopback, và **0,36 lõi (8 % của 4,3 lõi)** trong khi model đã ăn 85 %.
        Ngủ theo **mốc ĐẦU vòng** (bài học relay AGENTS §6: đừng `sleep(interval)` sau khi đã làm
        việc, vì chu kỳ = công việc + interval ⇒ chậm hơn `max_fps` một cách âm thầm).
        """
        self._source = source
        self._max_fps = float(max_fps) if max_fps else None
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
            moc = time.monotonic()               # mốc ĐẦU vòng, trước khi đọc
            frame = self._source.read()
            if frame is None:                    # nguồn cạn (file) → nghỉ ngắn rồi thử lại
                time.sleep(0.02)
                continue
            with self._lock:
                self._frame = frame
                self._ts = time.monotonic()
                self.frames_captured += 1
            if self._max_fps:
                con_lai = moc + 1.0 / self._max_fps - time.monotonic()
                # `self._stop.wait(...)`: `time.sleep` không ngắt được ⇒ `stop()` có thể join hết hạn
                # 2 s (khi `max_fps` nhỏ) rồi `close()` chạy trong lúc thread còn `read()` ⇒ nguồn ném
                # RuntimeError sau Ctrl+C (P3 review 24-11). `wait` trả True ngay khi có tín hiệu dừng.
                if con_lai > 0 and self._stop.wait(con_lai):
                    return

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

    def __init__(self, engine, frame_source, reid_session=None, frozen_poll_interval=0.04):
        self._engine = engine
        self._frames = frame_source
        self._reid = reid_session       # ReIdSession (ADR-0003) — None = không tái nhận diện
        self._frozen_poll = float(frozen_poll_interval)  # nhịp vòng khi đóng băng (xem _loop)
        self._lock = threading.Lock()
        self._stamped = None
        self._bbox = None            # bbox đang track (None = chưa chọn → không suy luận)
        self._pending = None         # yêu cầu từ main thread: ("start", bbox) | ("clear", None)
        self._stop = threading.Event()
        self._thread = None
        self._seq = 0
        self.inference_count = 0
        self._started = False   # engine đã start với bbox hiện tại chưa
        self._reid_state = None
        self._reid_score = None
        self._reid_ncc = None
        self._reid_vetoed = False
        self._track_cos = None
        self._verify_cos = None
        self._cos_truoc_cong = None
        self._cand_n = None
        self._loi_lien_tiep = 0      # số lần `step()`/`process()` ném LIÊN TIẾP (0 = đang khoẻ)
        self._reacquired = False
        self._pending_suspicious = None   # yêu cầu đổi cờ "nghi" từ main thread (None = không có)

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

    def reanchor(self, bbox):
        """Neo lại engine ở `bbox` nhưng **GIỮ** mẫu tham chiếu của Re-ID.

        Dùng cho phím `c` ("vẫn đúng, tiếp tục"): người dùng xác nhận vùng đang bị nghi LÀ vật, nên
        chỉ cần bám lại từ đó — xoá ký ức đặc trưng (`reset()` như `set_bbox`) là mất luôn khả năng
        nhận lại về sau mà không có lý do.
        """
        with self._lock:
            self._pending = ("reanchor", tuple(bbox))
            self._stamped = None

    def request_suspicious(self, suspicious: bool):
        """Báo tầng suy luận rằng cổng hiển thị đang/không còn NGHI đổi đối tượng.

        Gọi từ main thread (an toàn); việc đặt cờ lên `ReIdSession` diễn ra trong luồng suy luận —
        cùng lý do `set_bbox()` không được chạm engine từ main thread (bug thật 18-10).

        Chỉ chuyển TIẾP mỗi lần giá trị ĐỔI (`cờ nghi` giữ nguyên nhiều frame).
        """
        with self._lock:
            self._pending_suspicious = bool(suspicious)

    def reid_status(self):
        """(state, reid_score, reacquired, ncc) gần nhất — None khi không bật re-ID."""
        with self._lock:
            return self._reid_state, self._reid_score, self._reacquired, self._reid_ncc

    def track_cos(self):
        """`cos` với NEO danh tính của lần suy luận gần nhất (`None` = chưa đo)."""
        with self._lock:
            return self._track_cos

    def verify_cos(self):
        """`cos` của cổng XÁC MINH mask-vs-mask ở frame gần nhất (`None` = chưa chấm)."""
        with self._lock:
            return self._verify_cos

    def cos_truoc_cong(self):
        """Cosine cao nhất của frame chấm TRƯỚC mọi cổng (`None` = chưa chấm)."""
        with self._lock:
            return self._cos_truoc_cong

    def cand_n(self):
        """Số ứng viên đã được chấm điểm ở frame gần nhất (`None` = không ở chế độ tìm lại)."""
        with self._lock:
            return self._cand_n

    def reid_vetoed(self) -> bool:
        """Frame gần nhất có ứng viên bị BỎ vì trùng khuôn mặt/đầu (HUD phải nói rõ lý do)."""
        with self._lock:
            return self._reid_vetoed

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
                if self._reid is not None and action != "reanchor":
                    self._reid.reset()
                with self._lock:
                    self._started = False
                    self._bbox = bbox_req if action in ("start", "reanchor") else None
                    # P2 review độc lập 23-11: KHÔNG reset bộ đếm lỗi ở đây thì 2 cú chập của phiên
                    # TRƯỚC + 1 lỗi đầu tiên của phiên MỚI ⇒ `so_lan = 3` ⇒ bỏ ô ngay và in
                    # "3 lần liên tiếp" (sai sự thật). Cùng bài học AGENTS §6: bộ đếm phải reset
                    # trong `start()`.
                    self._loi_lien_tiep = 0
                    # P3 review: `_reid_ncc` cũng phải reset — nếu không, frame `start()` đầu tiên
                    # của vật MỚI mang `ncc` của phiên TRƯỚC (cùng lớp lỗi vừa sửa cho verify_cos).
                    self._reid_ncc = None
                    if action not in ("start", "reanchor"):
                        self._stamped = None
            # 1b) Cờ "nghi đổi đối tượng" từ main thread — đặt SAU reset (reset() xoá cờ)
            with self._lock:
                suspicious_req, self._pending_suspicious = self._pending_suspicious, None
            if suspicious_req is not None and self._reid is not None:
                self._reid.set_suspicious(suspicious_req)

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
                    if self._reid is not None:
                        result = self._reid.start(frame, bbox)
                        with self._lock:
                            self._reid_state = self._reid.state
                            self._reid_score, self._reacquired = None, False
                            self._reid_vetoed = False
                            self._track_cos = None
                            # RÒ SỐ (review vòng 2, 23-11): không reset 2 ô này thì sau khi bấm
                            # `r` chọn lại, frame đầu của lần chọn MỚI vẫn mang `verify_cos` của
                            # lần chọn CŨ ⇒ CSV gán số của vật trước cho vật sau.
                            self._verify_cos = None
                            self._cos_truoc_cong = None
                            self._cand_n = None
                    else:
                        result = self._engine.start(frame, bbox)
                    warn_if_bad_selection(result)
                    with self._lock:
                        self._started = True
                elif self._reid is not None:
                    step = self._reid.step(frame)
                    result = step.result
                    with self._lock:
                        self._reid_state = step.state
                        self._reid_score = step.reid_score
                        self._reid_vetoed = bool(getattr(step, "vetoed", False))
                        self._reacquired = step.reacquired
                        self._reid_ncc = step.ncc
                        self._track_cos = getattr(step, "track_cos", None)
                        self._verify_cos = getattr(step, "verify_cos", None)
                        self._cos_truoc_cong = getattr(step, "cos_truoc_cong", None)
                        self._cand_n = getattr(step, "cand_n", None)
                else:
                    result = self._engine.process(frame)
            except Exception as exc:
                with self._lock:
                    self._loi_lien_tiep += 1
                    so_lan = self._loi_lien_tiep
                if so_lan < _LOI_THU_LAI:
                    # MỘT ngoại lệ không được giết cả phiên (review vòng 2, 23-11): nhánh cũ đặt
                    # `_bbox = None` ngay từ lần đầu, mà vòng hiển thị vẫn dán `stamped.result` cũ
                    # lên frame live ⇒ demo "trông như đang chạy" với mask ĐÓNG BĂNG. Nay giữ ô và
                    # thử lại; chỉ lỗi LIÊN TIẾP mới về chế độ chờ chọn.
                    print(f"[LOI] suy luận thất bại ({so_lan}/{_LOI_THU_LAI}) "
                          f"{type(exc).__name__}: {exc} — thử lại")
                    time.sleep(0.1)
                    continue
                # Lỗi liên tiếp ⇒ state có thể đã hỏng: về chế độ chờ chọn, KHÔNG lặp vô hạn
                print(f"[LOI] suy luận thất bại {so_lan} lần liên tiếp: {type(exc).__name__}: "
                      f"{exc} — bấm r để chọn lại đối tượng")
                try:
                    self._engine.reset()
                except Exception:
                    pass
                with self._lock:
                    self._bbox = None
                    self._started = False
                    self._stamped = None
                    self._reid_state = None
                    self._loi_lien_tiep = 0
                time.sleep(0.1)
                continue
            with self._lock:
                self._loi_lien_tiep = 0      # có kết quả ⇒ chuỗi lỗi đã đứt
                self._seq += 1
                self.inference_count += 1
                self._stamped = StampedResult(self._seq, result, time.monotonic())
                frozen = self._reid is not None and self._reid.state != "tracking"

            # 3) Đang đóng băng (chỉ detect mặt, KHÔNG chạy model) → không quay vòng hết tốc CPU.
            # Lỗi thật 22-10: vòng lặp quay ~50–100 lần/s, frame_idx phình lên 213 trong khi
            # chỉ 145 kết quả thật được hiển thị → tốn CPU và số frame mất nghĩa.
            if frozen:
                time.sleep(self._frozen_poll)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)


def run_smooth_display(source, engine, selector, display, max_frames=None, metrics=None,
                       visualizer=None, preselect_bbox=None,
                       on_result=None, reid_session=None, source_max_fps=None, *,
                       settle_steps=None, max_jump_ratio=None,
                       lost_reset_streak=None) -> InteractiveSummary:
    """Vòng lặp hiển thị mượt: video ~30 FPS, overlay cập nhật mỗi lần suy luận xong.

    display: callable(img, mode) -> key (int) — với chạy thật là cv2.imshow + waitKey.
    Trả InteractiveSummary(processed = số lần suy luận).
    """
    summary = InteractiveSummary()
    if visualizer is not None:
        # Banner mất dấu phải nói ĐÚNG khả năng (ticket #43): không re-ID thì in "bấm r chọn lại".
        visualizer.reid_enabled = reid_session is not None
    # `source_max_fps` chỉ nên đặt cho nguồn LIVE (relay/webcam/RTSP): nguồn FILE phải đọc nhanh
    # nhất có thể để replay đúng thứ tự frame.
    frames = LatestFrameSource(open_video_source(source).open(),
                               max_fps=source_max_fps).start()
    worker = InferenceWorker(engine, frames, reid_session=reid_session).start()
    consumed_seq = 0
    last_bbox = None
    # Cổng "nghi đổi đối tượng" CÓ NHỚ (21-11) — xem `src/identity_guard.IdentityWatch`.
    # `settle_steps=None` ⇒ giữ mặc định của `IdentityWatch`. Có mặt để `--settle-steps` THẬT SỰ
    # đổi được hành vi: trước 24-11 `run_info` ghi `settle_steps=8` như một biến điều khiển trong khi
    # không tồn tại cờ nào (provenance giả — review độc lập 24-11, P1).
    from src.identity_guard import DEFAULT_SETTLE_STEPS

    watch = IdentityWatch(
        settle_steps=DEFAULT_SETTLE_STEPS if settle_steps is None else settle_steps,
        **({} if max_jump_ratio is None else {"max_jump_ratio": max_jump_ratio}),
        **({} if lost_reset_streak is None else {"lost_reset_streak": lost_reset_streak}),
    )
    switch = False
    last_nghi = False      # trạng thái nghi đã báo xuống worker (chống gửi lặp mỗi frame)
    # Ô của CHÍNH frame bật cờ nghi (tức ô model vừa đưa ra ở cú nhảy), dùng cho phím `c`.
    # KHÔNG phải "ô trước cú nhảy": `c` nghĩa là "vùng đang hiện là đúng", nên neo vào ô đó mới khớp
    # ý người dùng; neo về ô trước cú nhảy là neo về chỗ đã trôi đi (P1 review 23-11).
    bbox_luc_nghi = None

    def _bao_nghi(co):
        """Đồng bộ cờ nghi xuống luồng suy luận — CHỈ khi giá trị đổi.

        Quan trọng ở chiều `False`: `c` ("vẫn đúng, tiếp tục") và `r` (chọn lại) đều phải XOÁ cờ
        nghi trong `ReIdSession`, nếu không bước tracking kế tiếp lại bị bỏ track ngay và hệ quay
        vòng: bỏ → tìm lại → người dùng xác nhận → bỏ tiếp.
        """
        nonlocal last_nghi, bbox_luc_nghi
        if co and not last_nghi and reid_session is None:
            print("[WARN] cổng NGHI ĐỔI ĐỐI TƯỢNG bật nhưng KHÔNG có Re-ID (thiếu --reid) ⇒ hệ "
                  "không tự tìm lại được; bấm r rồi kéo chọn lại ô quanh vật.")
        if co and not last_nghi:
            # Nhớ ô LÚC NGHI (ô của chính frame này): nếu người dùng bấm `c` ("vẫn đúng") thì cần ô
            # đó để neo lại — sau bước bỏ track, kết quả mới là mask rỗng nên `last_bbox` không dùng được.
            bbox_luc_nghi = tuple(last_bbox) if last_bbox and tuple(last_bbox) != (0, 0, 0, 0) else None
        if co != last_nghi:
            worker.request_suspicious(co)
            last_nghi = co
    reid_state = reid_score = reacquired = reid_ncc = None
    reid_vetoed = False
    mode = "select"
    selector_bound = False
    disp_count, disp_t0 = 0, time.monotonic()

    try:
        if preselect_bbox is not None:
            worker.set_bbox(preselect_bbox)
            # 23-11: đường `--bbox` (không kéo chuột) cũng phải để lại ô chọn trong summary.
            summary.prompt_bbox = tuple(int(v) for v in preselect_bbox)
            mode = "track"
        while True:
            frame, _ = frames.latest()
            if frame is None:
                time.sleep(0.01)
                continue
            if metrics is not None:
                # MỖI frame (so tuple): `frame_shape_doi` phải ĐO được, không chỉ công bố 0.
                metrics.note_frame_shape(frame.shape)
            if not selector_bound:
                selector.bind(frame)          # lần đầu: biết kích thước frame
                selector_bound = True

            stamped = worker.latest_result() if worker.is_tracking() else None
            img = None
            if stamped is not None and stamped.seq != consumed_seq:  # mỗi kết quả 1 lần
                consumed_seq = stamped.seq
                summary.processed += 1
                reid_state, reid_score, reacquired, reid_ncc = worker.reid_status()
                reid_vetoed = worker.reid_vetoed()
                if reacquired:
                    # Re-ID đã tìm lại được đối tượng và xác nhận danh tính ⇒ xoá nghi, đặt lại mốc
                    watch.reset()
                    switch = False
                    last_bbox = tuple(stamped.result.bbox) if stamped.result.mask.any() else None
                else:
                    # Cổng CÓ NHỚ (21-11): báo 1 lần ⇒ ẩn overlay tới khi bấm `r`/`c`. Không nhớ thì
                    # đúng ca `demoip_1121-121732` (báo ở f178 rồi vẽ mask SAI 65 frame) không được xử lý.
                    switch = watch.nghi
                    # ⚠ PHẢI cập nhật cổng TRƯỚC khi gán `last_bbox = ô hiện tại`: bản đầu đặt SAU nên
                    # `watch.update(last_bbox, bbox)` so **ô với chính nó** ⇒ nhảy = 0 ⇒ cổng CÓ NHỚ
                    # KHÔNG BAO GIỜ bật trên đúng đường `./run demoip` (chế độ MƯỢT). Bắt được nhờ phiên
                    # thật `demoip_1121-131421`: console in 2 lần WARN mà CSV ghi `nghi_doi_tuong` TRỐNG
                    # cả 334 dòng ⇒ hệ vẫn vẽ mask của vùng sai (người dùng: "vẫn focus nhầm").
                    # `co_mask`: chỉ đếm bước ổn định khi model THẬT SỰ trả mask (24-11).
                    co_mask = bool(stamped.result.mask is not None
                                   and stamped.result.mask.any())
                    watch.update(last_bbox, stamped.result.bbox, frame.shape[:2],
                                 co_mask=co_mask)
                    # WARN + banner CHỈ khi cổng thật sự chấm cú nhảy: bước đầu của phiên bám mới
                    # sau khi vật rời khung được MIỄN chấm (`watch.vua_bao`), nên không in.
                    if watch.vua_bao:
                        _switch_warning(last_bbox, stamped.result, frame.shape[:2])
                    # Banner = ĐÚNG trạng thái latch (`watch.nghi`), KHÔNG dính kiểu sticky: latch có
                    # thể được xoá từ bên trong `watch.update` (tái bám sau khi vật rời khung, 24-11)
                    # mà không ai gán `switch = False` ⇒ banner "đổi đối tượng" treo trên màn hình
                    # trong khi mask đã vẽ lại bình thường.
                    switch = watch.nghi
                    if co_mask:
                        last_bbox = stamped.result.bbox
                    else:
                        # Mất dấu ⇒ đặt mốc rỗng để khi vật xuất hiện lại không bị so với ô cũ
                        # từ nhiều giây trước (luật của is_suspect_switch).
                        last_bbox = (0, 0, 0, 0)
                # Cổng hiển thị vừa đổi trạng thái ⇒ báo xuống luồng suy luận (chỉ khi ĐỔI).
                # `True` = ngừng tin track hiện tại ⇒ session bỏ track + vào nhánh TÌM LẠI; `False`
                # = đã hết nghi (nhận lại được / người dùng bấm `r`/`c`) ⇒ được học mẫu lại.
                if watch.nghi != last_nghi:
                    _bao_nghi(watch.nghi)
                if visualizer is not None:
                    visualizer.consume(stamped.result)
                    # 24-11: quỹ đạo KHÔNG được nối qua cú nhảy. `consume()` gắn điểm vô điều kiện,
                    # nên trong lúc `nghi` phải xóa mỗi bước (khi chuyển sang `chua_xac_minh` thì
                    # đường mới bắt đầu từ vùng mới — không có đoạn thẳng xuyên khung).
                    if watch.nghi:
                        visualizer.clear_trajectory()
                    if watch.chua_xac_minh:
                        summary.chua_xac_minh_n += 1
                if metrics is not None:
                    metrics.log(_record_from(stamped.result, reid_state, reid_score,
                                             reacquired, reid_ncc,
                                             vetoed=worker.reid_vetoed(),
                                             track_cos=worker.track_cos(),
                                             nghi_doi_tuong=True if watch.nghi else None,
                                             verify_cos=worker.verify_cos(),
                                             cos_truoc_cong=worker.cos_truoc_cong(),
                                             cand_n=worker.cand_n()))
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
                                            switch_warning=switch,
                                            chua_xac_minh=watch.chua_xac_minh,
                                            reid_state=reid_state, reid_score=reid_score,
                                            reid_vetoed=reid_vetoed)
                else:                       # không có HUD: vẫn phải giữ chế độ track
                    img = frame.copy()
                cv2.putText(img, _HINT_TRACK, (8, 50), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (255, 255, 255), 1, cv2.LINE_AA)
            else:
                mode = "select"
                img = selector.draw(frame)
                cv2.putText(img, _HINT_SELECT, (8, 24), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (255, 255, 255), 1, cv2.LINE_AA)

            key = chuan_hoa_phim(display(img, mode))
            disp_count += 1
            if time.monotonic() - disp_t0 > 2.0:      # cửa sổ trượt 2 giây
                disp_count, disp_t0 = 0, time.monotonic()
            if key in QUIT_KEYS:
                break
            if key == CONTINUE_KEY and (watch.nghi or watch.chua_xac_minh):
                # "vẫn đúng đối tượng": xoá nghi, KHÔNG chọn lại ô.
                # 24-11 (review P1-a): điều kiện cũ chỉ `watch.nghi` ⇒ ở trạng thái `chua_xac_minh`
                # HUD MỜI bấm `c` mà `c` KHÔNG CÓ TÁC DỤNG ⇒ kẹt "chưa xác minh" tới hết phiên
                # (đúng cái người dùng phàn nàn, chỉ khác là còn thấy viền).
                da_chua_xac_minh = watch.chua_xac_minh
                watch.reset()
                _bao_nghi(False)
                switch = False
                # Từ 23-11: cờ nghi khiến session BỎ track (để đi tìm lại) ⇒ "tiếp tục" phải NEO
                # LẠI engine ở ô vừa bị nghi, không chỉ xoá cờ (nếu không, hệ vẫn đang ở trạng thái
                # tìm lại và người dùng tưởng đã xác nhận xong).
                # Chỉ neo lại khi CÓ Re-ID: không có Re-ID thì `c` giữ nguyên hành vi cũ (chỉ xoá cờ),
                # tránh reset ký ức SAM 2 + nháy HUD "kéo chuột chọn" vô ích (P2 review 23-11).
                if bbox_luc_nghi is not None and reid_session is not None:
                    worker.reanchor(bbox_luc_nghi)
                    consumed_seq = 0
                    last_bbox = bbox_luc_nghi
                # 24-11: quỹ đạo là dấu vết của vật ĐANG được quan sát; sau khi xác nhận, nối điểm
                # trước cú nhảy với vùng mới sẽ vẽ một đường xuyên khung (P2 review 24-11) ⇒ xoá.
                if visualizer is not None and da_chua_xac_minh:
                    visualizer.clear_trajectory()
                print("[track] da xac nhan: tiep tuc bam doi tuong hien tai")
                continue
            if key == RESET_KEY:
                watch.reset()          # chọn lại ⇒ xoá nghi của phiên trước
                _bao_nghi(False)
                switch = False
                last_bbox = None
                selector.bind(frame)
                worker.clear()
                consumed_seq = 0
                if visualizer is not None:
                    visualizer.reset()
                mode = "select"
                continue
            if mode == "select" and selector.has_bbox():
                watch.reset()          # phiên bám MỚI ⇒ xoá nghi (nếu không, ô vừa chọn vẫn bị ẩn)
                switch = False
                _bbox_moi = selector.take_bbox()
                # 23-11: ô chọn ĐẦU TIÊN + đếm lần chọn lại (replay + giải thích phiên)
                if summary.prompt_bbox is None:
                    summary.prompt_bbox = tuple(int(v) for v in _bbox_moi)
                else:
                    summary.reselect_n += 1
                # Cảnh báo nếu ô chọn phủ KHUÔN MẶT (đo 21-11: ô chọn trùng mặt IoU 0,768, và đặc trưng
                # tông da làm re-ID "nhận lại" vào mặt). Chỉ cảnh báo, KHÔNG sửa ô.
                try:
                    from src.face_guard import kiem_o_chon

                    _x1, _y1, _x2, _y2 = (int(v) for v in _bbox_moi)
                    _cau, _mat = kiem_o_chon(frame, (_x1, _y1, max(1, _x2 - _x1), max(1, _y2 - _y1)))
                    if _cau:
                        print(_cau, flush=True)
                    if _mat is not None and visualizer is not None:
                        # Vẽ ô mặt lên ảnh (không thể bỏ qua như một dòng console).
                        visualizer.canh_bao_o_chon_phu_mat(_mat)
                except Exception:              # fail-open
                    pass
                worker.set_bbox(_bbox_moi)
                if visualizer is not None:
                    visualizer.reset()
            if max_frames is not None and summary.processed >= max_frames:
                break
            time.sleep(_DISPLAY_SLEEP)
    finally:
        worker.stop()
        frames.stop()
    return summary
