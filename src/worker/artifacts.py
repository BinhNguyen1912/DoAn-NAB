"""
Đọc/kiểm tra artifact của một job — toàn bộ hiểu biết về ĐỊNH DẠNG FILE nằm ở đây.

Chức năng: đọc progress.json (tiến trình), summary.json (số liệu tổng hợp), metrics.csv
           (số liệu từng frame), và kiểm tra tên artifact hợp lệ (whitelist).
Input  : job_dir (thư mục job) hoặc đường dẫn file.
Output : dict/list đã đổi kiểu; None/[] khi chưa có hoặc file hỏng.
Lưu ý  : module thuần đọc file — không chạy tiến trình, không biết HTTP, không import cv2/torch.
"""

import csv
import json
import os
from pathlib import Path

from src.worker.command import (
    LOG_NAME,
    METRICS_NAME,
    OUT_NAME,
    PROGRESS_NAME,
    RUN_INFO_NAME,
    SUMMARY_NAME,
    WEB_NAME,
)

# Artifact được phép tải ra ngoài (whitelist cứng — cũng là hàng rào chống path traversal)
ARTIFACT_NAMES = (OUT_NAME, WEB_NAME, METRICS_NAME, SUMMARY_NAME, RUN_INFO_NAME, LOG_NAME)


def _job_path(job_dir) -> Path:
    return Path(job_dir).resolve()


def _read_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def read_progress(job_dir) -> dict | None:
    """Đọc {"frames","total","updated_at"} do pipeline ghi; None nếu chưa có/hỏng."""
    data = _read_json(_job_path(job_dir) / PROGRESS_NAME)
    if not isinstance(data, dict) or "frames" not in data:
        return None
    return data


def load_summary(job_dir) -> dict | None:
    """Đọc summary.json (mean/p95/FPS/tỷ lệ mất dấu); None nếu chưa có/hỏng."""
    data = _read_json(_job_path(job_dir) / SUMMARY_NAME)
    return data if isinstance(data, dict) else None


def _parse_cell(text):
    """Chuyển 1 ô CSV thành int/float/bool/str — không làm hỏng dữ liệu gốc."""
    if text is None or text == "":
        return None
    low = text.strip().lower()
    if low == "true":
        return True
    if low == "false":
        return False
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            continue
    return text


def load_metrics(job_dir) -> list[dict]:
    """Đọc metrics.csv thành list dict đã đổi kiểu số; [] nếu chưa có file."""
    path = _job_path(job_dir) / METRICS_NAME
    if not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return [{k: _parse_cell(v) for k, v in row.items()} for row in csv.DictReader(f)]
    except OSError:
        return []


def artifact_path(job_dir, name: str) -> str | None:
    """Đường dẫn tuyệt đối của artifact, None nếu tên không hợp lệ hoặc file chưa có.

    Lưu ý: whitelist cứng + chặn dấu phân cách đường dẫn = chống path traversal.
    """
    if name not in ARTIFACT_NAMES or "/" in name or "\\" in name or ".." in name:
        return None
    path = _job_path(job_dir) / name
    return str(path) if os.path.isfile(path) else None
