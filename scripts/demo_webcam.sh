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

# Đọc cue THẬT từ tham số dòng lệnh (--reid-cue X) — KHÔNG dùng biến REID_CUE:
# biến môi trường không được set khi người dùng truyền cờ CLI, in sai sẽ gây hiểu nhầm.
DEMO_CUE="face"
_prev=""
for _a in "$@"; do
  if [ "$_prev" = "--reid-cue" ]; then DEMO_CUE="$_a"; fi
  _prev="$_a"
done
echo "[demo] webcam (source 0) · MƯỢT + TÁI NHẬN DIỆN cue=${DEMO_CUE} · image_size ${IMG_SIZE:-320}"
if [ "$DEMO_CUE" = "face" ]; then
  echo "[demo] đang dùng cue=face (mặc định) — với VẬT (chai, remote) thêm: --reid-cue object"
fi
echo "[demo] xuất: data/webcam_smooth.mp4 + data/smooth_metrics.csv + data/smooth_summary.json"
"$PYTHON" tools/run_live.py \
  --source 0 \
  --display \
  --smooth \
  --reid \
  --image-size "${IMG_SIZE:-320}" \
  --record data/webcam_smooth.mp4 \
  --metrics-csv data/smooth_metrics.csv \
  --metrics-summary data/smooth_summary.json \
  "$@"
