"""
LiveTrackingSession — vòng lặp bám đối tượng cho LUỒNG TRỰC TIẾP (chạy trong tiến trình worker).

Chức năng: mở nguồn frame, chờ ô chọn đối tượng (hoặc nhận sẵn), bám bằng engine VOS, vẽ overlay
           rồi ghi **frame mới nhất** + **trạng thái** ra thư mục chia sẻ để API đọc và phát.
Input  : engine (TrackerEngine hoặc engine giả trong test), LiveTrackConfig (nguồn, thư mục ra, fps).
Output : `<out_dir>/frame.jpg` (JPEG mới nhất), `<out_dir>/status.json`, `<out_dir>/worker.log`.
Lưu ý  : đây là phần CHẠY TRONG TIẾN TRÌNH RIÊNG (tools/live_worker.py) — nhờ vậy API vẫn không
         import torch/SAM 2 (ADR-0005) và có thể nằm trên máy yếu, thậm chí VPS 4 GB.
         Giao tiếp qua FILE trong /dev/shm (tmpfs): ghi atomic bằng os.replace, không dùng socket
         để giữ đơn giản và để lần chạy lỗi vẫn còn dấu vết đọc được.
         Chỉ giữ frame MỚI NHẤT (không hàng đợi) — độ trễ thấp quan trọng hơn phát đủ frame.
"""

import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from src.live_pipeline import _OVERLAY_ALPHA, _OVERLAY_COLOR_BOX, _OVERLAY_COLOR_MASK
from src.video_source import open_video_source

FRAME_NAME = "frame.jpg"
STATUS_NAME = "status.json"
BBOX_NAME = "bbox.json"

STATE_LOADING = "loading"          # đang nạp model (20–60 s trên CPU)
STATE_WAITING = "waiting_selection"  # đã có khung hình, chờ người dùng chọn đối tượng
STATE_TRACKING = "tracking"
STATE_ERROR = "error"
STATE_STOPPED = "stopped"


@dataclass
class LiveTrackConfig:
    """Tham số một phiên bám trực tiếp."""

    source: str
    out_dir: Path
    max_fps: float = 15.0
    trajectory_len: int = 100
    jpeg_quality: int = 80
    loop_files: bool = True
    stop_after_frames: int | None = None      # cho test/thử nhanh


@dataclass
class LiveTrackStats:
    """Số liệu đo được của phiên (ghi ra status.json mỗi frame)."""

    state: str = STATE_LOADING
    frames: int = 0
    measured_fps: float = 0.0
    inference_ms: float = 0.0
    lost_streak: int = 0
    bbox: list = field(default_factory=list)
    message: str = ""


def write_json_atomic(path: Path, data: dict) -> None:
    """Ghi JSON atomic — API đọc không bao giờ thấy file dở."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    os.replace(tmp, path)


def write_bytes_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as handle:
        handle.write(data)
    os.replace(tmp, path)


def read_bbox(path: Path):
    """Đọc ô chọn do API ghi; None nếu chưa có hoặc hỏng."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    try:
        bbox = (int(data["x"]), int(data["y"]), int(data["w"]), int(data["h"]))
    except (KeyError, TypeError, ValueError):
        return None
    return bbox if bbox[2] > 0 and bbox[3] > 0 else None


class LiveTrackingSession:
    """Một phiên bám trực tiếp: đọc frame → (chờ bbox) → bám → ghi ảnh/trạng thái."""

    def __init__(self, engine, config: LiveTrackConfig) -> None:
        self._engine = engine
        self._cfg = config
        self._stats = LiveTrackStats()
        self._trail: deque = deque(maxlen=config.trajectory_len)
        self._frames_window: deque = deque()
        self._source = None

    # ------------------------------------------------------------------ API công khai

    def run(self, stop_event=None) -> LiveTrackStats:
        """Chạy tới khi hết nguồn (file không lặp), đủ frame, hoặc `stop_event` được set."""
        out_dir = Path(self._cfg.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        self._publish_status(out_dir)

        self._source = open_video_source(self._cfg.source).open()
        interval = 1.0 / max(1.0, float(self._cfg.max_fps))
        engine_started = False
        try:
            while not (stop_event is not None and stop_event.is_set()):
                began = time.perf_counter()
                frame = self._source.read()
                if frame is None:
                    frame = self._rewind()
                    if frame is None:
                        break

                if not engine_started:
                    # Trong lúc chờ, vẫn phát khung hình TRƠN để UI hiện luồng và người dùng chọn ô
                    bbox = read_bbox(out_dir / BBOX_NAME)
                    if bbox is None:
                        self._stats.state = STATE_WAITING
                        self._publish_frame(out_dir, frame)
                        self._sleep(interval, began)
                        continue
                    result = self._engine.start(frame, bbox)
                    self._stats.state = STATE_TRACKING
                    engine_started = True
                else:
                    result = self._engine.process(frame)

                self._update_stats(result)
                self._publish_frame(out_dir, self._annotate(frame, result))
                self._publish_status(out_dir)

                if self._cfg.stop_after_frames and self._stats.frames >= self._cfg.stop_after_frames:
                    break
                self._sleep(interval, began)
        finally:
            if self._source is not None:
                self._source.close()
            self._stats.state = STATE_STOPPED
            self._publish_status(out_dir)
        return self._stats

    # ------------------------------------------------------------------ nội bộ

    def _rewind(self):
        """Mở lại file từ đầu (demo live bằng video); nguồn thật hoặc lỗi → None."""
        if not self._cfg.loop_files:
            return None
        try:
            source, self._source = self._source, None
            if source is not None:
                source.close()
            self._source = open_video_source(self._cfg.source).open()
            return self._source.read()
        except (OSError, RuntimeError):
            return None

    def _update_stats(self, result) -> None:
        now = time.perf_counter()
        self._stats.frames += 1
        self._stats.inference_ms = round(float(getattr(result, "elapsed_ms", 0.0)), 1)
        self._frames_window.append(now)
        cutoff = now - 2.0
        while self._frames_window and self._frames_window[0] < cutoff:
            self._frames_window.popleft()
        if len(self._frames_window) >= 2:
            span = self._frames_window[-1] - self._frames_window[0]
            if span > 0:
                self._stats.measured_fps = round((len(self._frames_window) - 1) / span, 1)

        mask = getattr(result, "mask", None)
        lost = mask is None or not mask.any()
        self._stats.lost_streak = self._stats.lost_streak + 1 if lost else 0
        self._stats.bbox = [int(v) for v in result.bbox]
        if not lost:
            center = ((result.bbox[0] + result.bbox[2]) // 2, (result.bbox[1] + result.bbox[3]) // 2)
            self._trail.append((int(center[0]), int(center[1])))

    def _annotate(self, frame, result):
        """Tô mask + ô bao + quỹ đạo + HUD. Chữ HUD dùng ASCII vì font Hershey không có dấu."""
        img = frame.copy()
        mask = getattr(result, "mask", None)
        if mask is not None and mask.any():
            tint = img.copy()
            tint[mask] = _OVERLAY_COLOR_MASK
            img = cv2.addWeighted(img, 1.0 - _OVERLAY_ALPHA, tint, _OVERLAY_ALPHA, 0)

        x1, y1, x2, y2 = [int(v) for v in result.bbox]
        if x2 > x1 and y2 > y1:
            cv2.rectangle(img, (x1, y1), (x2, y2), _OVERLAY_COLOR_BOX, 2)

        points = list(self._trail)
        for index in range(1, len(points)):
            cv2.line(img, points[index - 1], points[index], (255, 0, 255), 2)  # BGR tím

        hud = f"LIVE {self._stats.measured_fps:.1f} FPS | {self._stats.inference_ms:.0f} ms"
        if self._stats.lost_streak:
            hud += f" | MAT DAU {self._stats.lost_streak}"
        # ASCII (không dấu) là BẮT BUỘC: cv2.putText/Hershey không render được dấu tiếng Việt
        cv2.putText(img, hud, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        return img

    def _publish_frame(self, out_dir: Path, frame) -> None:
        ok, buffer = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self._cfg.jpeg_quality]
        )
        if ok:
            write_bytes_atomic(out_dir / FRAME_NAME, bytes(buffer))

    def _publish_status(self, out_dir: Path) -> None:
        write_json_atomic(out_dir / STATUS_NAME, {
            "state": self._stats.state,
            "frames": self._stats.frames,
            "measured_fps": self._stats.measured_fps,
            "inference_ms": self._stats.inference_ms,
            "lost_streak": self._stats.lost_streak,
            "bbox": self._stats.bbox,
            "message": self._stats.message,
        })

    @staticmethod
    def _sleep(interval: float, began: float) -> None:
        remaining = interval - (time.perf_counter() - began)
        if remaining > 0:
            time.sleep(remaining)
