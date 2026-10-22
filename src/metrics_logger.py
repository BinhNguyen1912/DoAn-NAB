"""
MetricsLogger — ghi số liệu từng frame + thống kê tổng hợp cho mục "Đánh giá hiệu năng"
(yêu cầu 6 của đề cương; story 13–16 và 23 của spec, ticket 07).

Chức năng: thuần chức năng — nhận `FrameRecord` mỗi frame (thời gian xử lý ms, điểm tin
cậy mask, toạ độ tâm đối tượng, cờ mất dấu) rồi:
  - `write_csv(path)`  : CSV từng frame — tâm (x, y) ghi đủ để vẽ biểu đồ quỹ đạo;
  - `summary()`        : dict tổng hợp — mean/p95 latency, FPS hiệu dụng, tổng frame,
                         số/tỷ lệ frame mất dấu (mask rỗng hoặc điểm tin cậy dưới ngưỡng);
  - `write_summary_json(path)`: dump summary ra JSON để báo cáo/đọc lại.

Input  : FrameRecord (frame_idx, latency_ms, score, center, lost=None — None thì tự suy
         bằng `is_lost`: tâm None hoặc score <= LOST_SCORE_THRESHOLD).
Output : file CSV + JSON; summary trả dict thuần.
Lưu ý  : cờ mất dấu do caller biết chắc (explicit) được ưu tiên hơn suy đoán từ score;
         không phụ thuộc model — test nhanh trên list bản ghi giả.
"""
import csv
import json
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

# object_score_logits của SAM 2 > 0 nghĩa là tin cậy → dưới bằng 0 coi là mất dấu
LOST_SCORE_THRESHOLD = 0.0

CSV_HEADER = ["frame_idx", "latency_ms", "score", "center_x", "center_y", "lost",
              "state", "reid_score", "reacquired"]


@dataclass
class FrameRecord:
    """Bản ghi 1 frame — đơn vị dữ liệu duy nhất của module (hàm thuần, không model)."""

    frame_idx: int
    latency_ms: float
    score: float                          # điểm tin cậy mask (object_score_logits)
    center: Optional[Tuple[int, int]]     # (cx, cy) tâm đối tượng; None = mất dấu
    lost: Optional[bool] = None           # cờ mất dấu; None → tự suy qua is_lost()
    # Trạng thái tái nhận diện (ADR-0003, ticket 09) — None khi không bật re-ID
    state: Optional[str] = None           # "tracking" | "lost" | "reacquiring"
    reid_score: Optional[float] = None    # cosine tốt nhất frame đó (-1 = không có ứng viên)
    reacquired: Optional[bool] = None     # True ở đúng frame vừa nhận lại đối tượng


def is_lost(record: FrameRecord, threshold: float = LOST_SCORE_THRESHOLD) -> bool:
    """Suy cờ mất dấu: ưu tiên `lost` explicit; ngược lại tâm None hoặc score <= ngưỡng."""
    if record.lost is not None:
        return bool(record.lost)
    return record.center is None or record.score <= threshold


# Trạng thái tái nhận diện mà model KHÔNG chạy (đóng băng) → latency bằng 0, không phải số đo
FROZEN_STATES = ("lost", "reacquiring")


def is_frozen(record: FrameRecord) -> bool:
    """True nếu frame này không chạy model (đang đóng băng chờ nhận lại đối tượng).

    Dùng để loại khỏi thống kê latency/FPS — nếu tính cả, con số FPS bị thổi phồng.
    """
    return record.state in FROZEN_STATES


class MetricsLogger:
    """Thu thập FrameRecord từng frame; xuất CSV + summary — thuần, test không cần model."""

    def __init__(self):
        self.records = []

    def log(self, record: FrameRecord) -> None:
        """Nhận 1 bản ghi thêm vào phiên (thứ tự gọi = thứ tự frame)."""
        self.records.append(record)

    def summary(self) -> dict:
        """Thống kê tổng hợp: mean/p95 latency, FPS hiệu dụng, số/tỷ lệ mất dấu."""
        if not self.records:
            return {
                "total_frames": 0,
                "mean_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "effective_fps": 0.0,
                "mean_score": 0.0,
                "lost_count": 0,
                "lost_ratio": 0.0,
                "frozen_frames": 0,
                "reacquiring_frames": 0,
                "reacquired_count": 0,
            }
        lost_count = sum(1 for r in self.records if is_lost(r))
        # Frame đóng băng (mất dấu → không gọi model) có latency 0. Tính latency trên
        # chúng sẽ kéo mean xuống và làm FPS báo sai (lỗi thật 22-10: 236 thay vì 311 ms).
        frozen = [r for r in self.records if is_frozen(r)]
        measured = [r for r in self.records if not is_frozen(r)]
        latencies = np.array([r.latency_ms for r in measured], dtype=float)
        if latencies.size == 0:
            mean_ms = p95_ms = 0.0
        else:
            mean_ms = float(np.mean(latencies))
            p95_ms = float(np.percentile(latencies, 95))
        return {
            "total_frames": len(self.records),
            "mean_latency_ms": mean_ms,
            "p95_latency_ms": p95_ms,
            "effective_fps": 1000.0 / mean_ms if mean_ms > 0 else 0.0,
            "mean_score": float(np.mean([r.score for r in self.records])),
            "lost_count": lost_count,
            "lost_ratio": lost_count / len(self.records),
            "frozen_frames": len(frozen),
            "reacquiring_frames": sum(1 for r in self.records if r.state == "reacquiring"),
            "reacquired_count": sum(1 for r in self.records if r.reacquired),
        }

    def write_csv(self, path: str) -> str:
        """Ghi CSV từng frame — cột tâm trống khi mất dấu (không vẽ điểm rác)."""
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADER)
            for r in self.records:
                cx, cy = (r.center[0], r.center[1]) if r.center is not None else ("", "")
                writer.writerow([
                    r.frame_idx, f"{float(r.latency_ms):.1f}", f"{float(r.score):.6g}",
                    cx, cy, 1 if is_lost(r) else 0,
                    r.state if r.state is not None else "",
                    f"{float(r.reid_score):.6g}" if r.reid_score is not None else "",
                    (1 if r.reacquired else 0) if r.reacquired is not None else "",
                ])
        return str(path)

    def write_summary_json(self, path: str) -> str:
        """Đổ summary ra JSON (báo cáo đọc lại/pandas)."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.summary(), f, ensure_ascii=False, indent=2)
        return str(path)