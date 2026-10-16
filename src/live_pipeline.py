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
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from src.video_source import open_video_source

_OVERLAY_COLOR_MASK = (0, 140, 255)   # BGR cam — cùng màu fixture
_OVERLAY_COLOR_BOX = (0, 0, 255)      # BGR đỏ
_OVERLAY_ALPHA = 0.35


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


def run_tracking(source, engine, bbox, on_frame=None, max_frames=None) -> SessionSummary:
    """Chạy vòng lặp: đọc frame → track → overlay → gọi on_frame (trả False = dừng)."""
    summary = SessionSummary(total_frames=0)
    src = open_video_source(source).open()
    try:
        frame = src.read()
        if frame is None:
            raise RuntimeError("Nguồn không đưa được frame nào")
        result = engine.start(frame, bbox)
        img = draw_overlay_minimal(frame, result)
        summary.latencies_ms.append(result.elapsed_ms)
        summary.total_frames += 1
        if on_frame is not None and on_frame(img, result) is False:
            return summary

        while max_frames is None or summary.total_frames < max_frames:
            frame = src.read()
            if frame is None:
                break
            result = engine.process(frame)
            img = draw_overlay_minimal(frame, result)
            summary.latencies_ms.append(result.elapsed_ms)
            summary.total_frames += 1
            if on_frame is not None and on_frame(img, result) is False:
                break
    finally:
        src.close()
    return summary