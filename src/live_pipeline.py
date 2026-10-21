"""
Live pipeline — lát dọc "hệ thống sống": nối VideoSource → TrackerEngine → overlay + metrics.

Chức năng: vòng lặp tracking — đọc frame từ nguồn, track bằng engine (SAMURAI streaming),
vẽ overlay tối thiểu (mask mờ + ô bao + nhãn frame), giao từng frame cho phần hiển thị
(tiêm qua callback `on_frame` — giúp test headless), thu số liệu độ trễ trung thực.

Input  : source (index webcam / rtsp:// / video file), engine SAMURAI, bbox chọn đối tượng,
         callback on_frame(img, result) — trả False để dừng đúng cách.
Output : SessionSummary (tổng frame, latencies, mean/p95 ms, FPS hiệu dụng).
Lưu ý  : số FPS/latency là THỰC ĐO trên phần cứng chạy (ADR-0002: báo cáo trung thực,
         không claim real-time). Chức năng vẽ HUD đầy đủ/quỹ đạo là ticket 06.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

from src.video_source import open_video_source
from src.metrics_logger import FrameRecord
from src.identity_guard import is_suspect_switch

_OVERLAY_COLOR_MASK = (0, 140, 255)   # BGR cam — cùng màu fixture
_OVERLAY_COLOR_BOX = (0, 0, 255)      # BGR đỏ
_OVERLAY_ALPHA = 0.35

# Phím thoát dùng chung (q / ESC) — run_interactive + tools/run_live cùng quy ước
QUIT_KEYS = (ord("q"), 27)
RESET_KEY = ord("r")

# Ngưỡng cảnh báo chọn sai: SAM 2 luôn trả mask cho BẤT KỲ ô nào (kể cả nền trống) —
# đo thật 18-10: chọn nền nhỏ vẫn được mask 1.2% khung (không phân biệt được với đối tượng),
# nhưng chọn ô phủ cả khung → mask 97.6% khung → phát hiện được.
MASK_FRAME_WARN_RATIO = 0.6

# Hint hiển thị trên khung: viết KHÔNG dấu vì font Hershey của cv2.putText
# không render được chữ có dấu tiếng Việt
_HINT_SELECT = "[SELECT] keo chuot ve o chon doi tuong | r: chon lai | q/ESC: thoat"
_HINT_TRACK = "[TRACK] r: chon lai doi tuong | q/ESC: thoat"


@dataclass
class SessionSummary:
    """Số liệu tổng hợp 1 phiên tracking (dùng in console / sau này cho MetricsLogger)."""

    total_frames: int
    latencies_ms: list = field(default_factory=list)

    @property
    def mean_ms(self) -> float:
        return float(np.mean(self.latencies_ms)) if self.latencies_ms else 0.0

    @property
    def p95_ms(self) -> float:
        return float(np.percentile(self.latencies_ms, 95)) if self.latencies_ms else 0.0

    @property
    def effective_fps(self) -> float:
        """FPS hiệu dụng theo độ trễ trung bình (thước đo trung thực, không phải FPS nguồn)."""
        return 1000.0 / self.mean_ms if self.mean_ms > 0 else 0.0


def draw_overlay_minimal(frame, result):
    """Overlay tối thiểu: tô mask mờ + ô bao + nhãn `f<i> ms`."""
    img = frame.copy()
    if result.mask is not None and result.mask.any():
        tint = img.copy()
        tint[result.mask] = _OVERLAY_COLOR_MASK
        img = cv2.addWeighted(img, 1.0 - _OVERLAY_ALPHA, tint, _OVERLAY_ALPHA, 0)
    x1, y1, x2, y2 = [int(v) for v in result.bbox]
    if x2 > x1 and y2 > y1:
        cv2.rectangle(img, (x1, y1), (x2, y2), _OVERLAY_COLOR_BOX, 2)
    cv2.putText(img, f"f{result.frame_idx} {result.elapsed_ms:.0f}ms", (8, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    return img


def warn_if_bad_selection(result):
    """Cảnh báo khi ô chọn không có đối tượng rõ ràng (mask rỗng hoặc phủ gần cả khung).

    Vì SAM 2 là promptable segmentation: vẽ ô vào nền trống nó vẫn trả mask, nên không thể
    biết chắc “đây không phải đối tượng”. Phát hiện được: mask rỗng (không phân đoạn được)
    hoặc mask > MASK_FRAME_WARN_RATIO khung (ô quá lớn/nền đồng nhất).
    """
    mask = result.mask
    if mask is None or not mask.any():
        print("[WARN] ô chọn không phân đoạn được đối tượng (mask rỗng) — bấm r để chọn lại")
        return
    ratio = float(mask.sum()) / mask.size
    if ratio > MASK_FRAME_WARN_RATIO:
        print(f"[WARN] mask phủ {ratio * 100:.0f}% khung — ô chọn có thể quá lớn hoặc không "
              f"chứa đối tượng; bấm r để chọn lại")


def _switch_warning(prev_bbox, result, frame_shape):
    """Cảnh báo khi ô bao nhảy quá xa trong 1 bước (nghi bám sang đối tượng khác)."""
    if is_suspect_switch(prev_bbox, result.bbox, frame_shape):
        print(f"[WARN] nghi ngờ ĐỔI ĐỐI TƯỢNG (ô bao nhảy từ {tuple(prev_bbox)} "
              f"sang {result.bbox}) — bấm r chọn lại")
        return True
    return False


def _record_from(result) -> FrameRecord:
    """TrackingResult → FrameRecord cho MetricsLogger: tâm từ bbox, mất dấu khi mask rỗng."""
    x1, y1, x2, y2 = [int(v) for v in result.bbox]
    center = ((x1 + x2) // 2, (y1 + y2) // 2) if (x2 > x1 and y2 > y1) else None
    return FrameRecord(
        frame_idx=result.frame_idx,
        latency_ms=result.elapsed_ms,
        score=result.score,
        center=center,
        lost=not (result.mask is not None and result.mask.any()),
    )


def _annotate(frame, result, visualizer):
    """Frame + result → HUD: Visualizer đầy đủ nếu có, không thì overlay tối thiểu."""
    if visualizer is not None:
        return visualizer.update(frame, result)
    return draw_overlay_minimal(frame, result)


def _maybe_reanchor(engine, frame, last_bbox, frame_idx, every):
    """Tối ưu TỐC ĐỘ (tuỳ chọn): reset state + chọn lại bbox hiện tại mỗi `every` frame.

    Vì sao nhanh hơn: chi phí propagate của SAMURAI tăng theo số frame nằm trong
    `output_dict["non_cond_frame_outputs"]` — đo thật 18-10: 3.4s khi lưu 1 frame → 8.3s khi
    lưu 8 frame. Reset đưa chi phí về mức nền. Cắt bớt entry cũ trực tiếp KHÔNG được
    (SAM 2 tham chiếu frame cũ → `KeyError`), nên reset là cách an toàn.
    Đánh đổi: mất bộ nhớ dài hạn. Đo trên fixture (ô vuông + bị che 5 frame):
    baseline IoU sau che 0.981 / mất dấu 5/19; re-anchor 3: IoU 0.969 / mất dấu 0/19.
    """
    if not every or frame_idx == 0 or frame_idx % every != 0 or last_bbox is None:
        return None
    engine.reset()
    return engine.start(frame, last_bbox)


def run_tracking(source, engine, bbox, on_frame=None, max_frames=None,
                 visualizer=None, metrics=None, reanchor_every=None) -> SessionSummary:
    """Chạy vòng lặp: đọc frame → track → overlay → gọi on_frame (trả False = dừng).

    visualizer    : Visualizer (ticket 06) — HUD đầy đủ + ghi video nếu đã open_recorder.
                    None → overlay tối thiểu draw_overlay_minimal (ticket 04).
    metrics       : MetricsLogger (ticket 07) — log FrameRecord mỗi frame.
    reanchor_every: N > 0 → reset + chọn lại bbox mỗi N frame (nhanh hơn, đổi chất lượng
                    memory dài hạn — xem `_maybe_reanchor`). None = tắt (mặc định).
    """
    summary = SessionSummary(total_frames=0)
    src = open_video_source(source).open()
    try:
        frame = src.read()
        if frame is None:
            raise RuntimeError("Nguồn không đưa được frame nào")
        result = engine.start(frame, bbox)
        last_bbox = result.bbox if result.mask.any() else tuple(bbox)
        warn_if_bad_selection(result)
        if metrics is not None:
            metrics.log(_record_from(result))
        img = _annotate(frame, result, visualizer)
        summary.latencies_ms.append(result.elapsed_ms)
        summary.total_frames += 1
        if on_frame is not None and on_frame(img, result) is False:
            return summary

        while max_frames is None or summary.total_frames < max_frames:
            frame = src.read()
            if frame is None:
                break
            reanchored = _maybe_reanchor(engine, frame, last_bbox,
                                         summary.total_frames, reanchor_every)
            result = reanchored if reanchored is not None else engine.process(frame)
            if result.mask.any():
                last_bbox = result.bbox
            if metrics is not None:
                metrics.log(_record_from(result))
            img = _annotate(frame, result, visualizer)
            summary.latencies_ms.append(result.elapsed_ms)
            summary.total_frames += 1
            if on_frame is not None and on_frame(img, result) is False:
                break
    finally:
        src.close()
    return summary


@dataclass
class InteractiveSummary:
    """Số liệu 1 phiên tương tác (frame chọn không đếm, chỉ đếm frame đã track)."""

    processed: int = 0


def run_interactive(source, engine, selector, display, max_frames=None,
                    preselect_bbox=None, on_result=None,
                    visualizer=None, metrics=None, reanchor_every=None) -> InteractiveSummary:
    """Vòng lặp tương tác: chọn ô bằng chuột → track → r chọn lại → q/ESC thoát.

    source   : nguồn video (truyền vào open_video_source).
    engine   : TrackerEngine (có start/process/reset) — hoặc duck-type tương tự.
    selector : PromptSelector; caller gắn vào window bằng
               cv2.setMouseCallback(window, selector.on_mouse). Test có thể pre-arm bbox.
    display  : callable(img, mode) -> key (int); mode là 'select' hoặc 'track'.
               Trả QUIT_KEYS để thoát; với chạy thực đây là cv2.imshow + waitKey.
    max_frames: gioi han so frame da track (chon lai van duoc qua gioi han).
    preselect_bbox: (x1,y1,x2,y2) arm sẵn vào selector sau khi bind frame (từ --bbox) —
               track ngay không cần kéo chuột. None = để người dùng kéo chuột.
    on_result: callable(TrackingResult) gọi sau mỗi start/process — để caller log số liệu
               (ms, bbox...) mà display callback không cần biết result.
    visualizer: Visualizer (ticket 06) cho HUD đầy đủ + ghi video; r chọn lại sẽ reset()
               quỹ đạo. None → overlay tối thiểu như ticket 04.
    metrics   : MetricsLogger (ticket 07) — log FrameRecord mỗi frame track (kể cả mất dấu).
    reanchor_every: N > 0 → reset + chọn lại bbox mỗi N frame (nhanh hơn, đánh đổi memory).
    Output   : InteractiveSummary(processed = số frame đã track).
    """
    summary = InteractiveSummary()
    src = open_video_source(source).open()
    try:
        frame = src.read()
        if frame is None:
            raise RuntimeError("Nguồn không đưa được frame nào")
        selector.bind(frame)
        if preselect_bbox is not None:
            # arm bbox chỉ định sẵn qua đúng đường sự kiện chuột (chuẩn hoá + min-size)
            selector.on_mouse(cv2.EVENT_LBUTTONDOWN, preselect_bbox[0], preselect_bbox[1], 0, None)
            selector.on_mouse(cv2.EVENT_LBUTTONUP, preselect_bbox[2], preselect_bbox[3], 0, None)
        mode = "select"
        last_result = None

        while max_frames is None or summary.processed < max_frames or mode == "select":
            if mode == "select":
                img = selector.draw(frame)
                cv2.putText(img, _HINT_SELECT, (8, 24), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (255, 255, 255), 1, cv2.LINE_AA)
                key = display(img, "select")
                if key in QUIT_KEYS:
                    break
                if selector.has_bbox():
                    bbox = selector.take_bbox()
                    last_result = engine.start(frame, bbox)
                    last_bbox = last_result.bbox if last_result.mask.any() else tuple(bbox)
                    warn_if_bad_selection(last_result)
                    summary.processed += 1
                    if on_result is not None:
                        on_result(last_result)
                    if metrics is not None:
                        metrics.log(_record_from(last_result))
                    mode = "track"
            else:  # track
                img = _annotate(frame, last_result, visualizer)
                cv2.putText(img, _HINT_TRACK, (8, 50), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (255, 255, 255), 1, cv2.LINE_AA)
                key = display(img, "track")
                if key in QUIT_KEYS:
                    break
                if key == RESET_KEY:
                    engine.reset()
                    selector.bind(frame)  # chọn lại trên frame hiện tại
                    if visualizer is not None:
                        visualizer.reset()  # quỹ đạo đối tượng cũ bỏ đi
                    mode = "select"
                    continue
                frame = src.read()
                if frame is None:
                    break
                reanchored = _maybe_reanchor(engine, frame, last_bbox,
                                             summary.processed, reanchor_every)
                last_result = reanchored if reanchored is not None else engine.process(frame)
                switch = _switch_warning(last_bbox, last_result, frame.shape[:2])
                if last_result.mask.any():
                    last_bbox = last_result.bbox
                summary.processed += 1
                if on_result is not None:
                    on_result(last_result)
                if metrics is not None:
                    metrics.log(_record_from(last_result))
    finally:
        src.close()
    return summary
