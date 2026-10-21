#!/usr/bin/env bash
# Demo webcam realtime (chế độ mượt) — chạy 1 lệnh, không cần gõ tham số dài.
#
#   bash scripts/demo_webcam.sh           # demo mượt, xuất mp4 + CSV + JSON
#   bash scripts/demo_webcam.sh --max-frames 5   # chạy nhanh 5 frame (để thử)
#
# Yêu cầu: đã `conda activate samurai` (hoặc sửa PYTHON bên dưới).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python}"
export PYTHONUNBUFFERED=1     # in log ngay (không bị buffer khi chạy nền/ redirect)
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "[LOI] Không thấy 'python' — chạy: source ~/miniconda3/etc/profile.d/conda.sh && conda activate samurai"
  exit 1
fi

echo "[demo] webcam (source 0) · chế độ MƯỢT · image_size 384"
echo "[demo] xuất: data/webcam_smooth.mp4 + data/smooth_metrics.csv + data/smooth_summary.json"
"$PYTHON" tools/run_live.py \
  --source 0 \
  --display \
  --smooth \
  --image-size 384 \
  --record data/webcam_smooth.mp4 \
  --metrics-csv data/smooth_metrics.csv \
  --metrics-summary data/smooth_summary.json \
  "$@"
