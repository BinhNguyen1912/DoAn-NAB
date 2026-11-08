"""
Tầng chạy pipeline cho backend web — mặt tiền (facade) của package `src.worker`.

Chức năng: gom API công khai của 3 module con để tầng trên chỉ cần `from src.worker import ...`.
Input  : xem từng module con (command / artifacts / process).
Output : hàm + hằng số dùng chung.
Lưu ý  : package này KHÔNG import cv2/torch/sam2 — backend phải nhẹ (chạy được trên VPS 4 GB).
         Mọi phụ thuộc nặng nằm trong tiến trình con đã activate conda.

Bố cục:
  command.py   — dựng lệnh (hàm thuần, biết `tools/run_live.py`)
  artifacts.py — đọc progress/summary/metrics + whitelist artifact
  process.py   — subprocess: chạy nền, log, callback khi kết thúc
  web_export.py — chuyển bản ghi mp4v (OpenCV) sang H.264 để trình duyệt phát được
"""

from pathlib import Path

from src.worker.artifacts import (
    ARTIFACT_NAMES,
    artifact_path,
    load_metrics,
    load_summary,
    read_progress,
)
from src.worker.command import (
    LOG_NAME,
    METRICS_NAME,
    OUT_NAME,
    PROGRESS_NAME,
    RUN_INFO_NAME,
    RUN_LIVE_REL,
    SOURCE_NAME,
    SUMMARY_NAME,
    WEB_NAME,
    build_command,
)
from src.worker.process import is_running, notify_on_exit, start
from src.worker.web_export import find_ffmpeg, transcode_for_web

REPO_ROOT = Path(__file__).resolve().parents[2]

__all__ = [
    "ARTIFACT_NAMES",
    "LOG_NAME",
    "METRICS_NAME",
    "OUT_NAME",
    "PROGRESS_NAME",
    "REPO_ROOT",
    "RUN_INFO_NAME",
    "RUN_LIVE_REL",
    "SOURCE_NAME",
    "SUMMARY_NAME",
    "WEB_NAME",
    "artifact_path",
    "build_command",
    "find_ffmpeg",
    "is_running",
    "load_metrics",
    "load_summary",
    "notify_on_exit",
    "read_progress",
    "transcode_for_web",
    "start",
]
