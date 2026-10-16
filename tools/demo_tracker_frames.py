"""
Script demo TrackerEngine streaming — đọc frames từ thư mục JPG, track theo bbox, in kết quả.

Cách chạy (env conda `samurai`):
  python tools/demo_tracker_frames.py --frames_dir data/demo_input_frames \
      --bbox data/dog_bbox_frame0.txt --num 10

In mỗi frame: số thứ tự, bbox, điểm tin cậy, thời gian xử lý (ms) — minh chứng
TrackerEngine feed từng frame và nhận kết quả từng frame (không load cả video).
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.tracker_engine import DEFAULT_CKPT, TrackerEngine   # noqa: E402

# Giảm nhiễu progress bar tqdm của SAM 2 khi chạy demo
import sam2.sam2_video_predictor as _vp   # noqa: E402
_vp.tqdm = lambda it, *a, **k: it

def main():
    ap = argparse.ArgumentParser(description="Demo TrackerEngine streaming trên thư mục frames")
    ap.add_argument("--frames_dir", required=True, help="thư mục chứa frame 00000.jpg...")
    ap.add_argument("--bbox", required=True, help="file txt 'x,y,w,h' frame 0, hoặc dạng 'x,y,w,h' trực tiếp")
    ap.add_argument("--num", type=int, default=10, help="số frame xử lý tối đa (0 = tất cả)")
    ap.add_argument("--ckpt", default=None, help="đường dẫn checkpoint (mặc định tiny trong samurai/)")
    args = ap.parse_args()

    # bbox: file txt hoặc chuỗi trực tiếp
    text = args.bbox
    if os.path.isfile(text):
        with open(text) as f:
            text = f.readline().strip()
    x, y, w, h = map(int, text.split(","))
    bbox = (x, y, x + w, y + h)

    # Đọc frames từ thư mục JPG (sắp xếp theo tên)
    jpgs = sorted(
        f for f in os.listdir(args.frames_dir) if f.lower().endswith((".jpg", ".jpeg"))
    )
    if not jpgs:
        print(f"[LOI] không có JPG nào trong {args.frames_dir}")
        raise SystemExit(1)

    print("build TrackerEngine (SAM 2.1 tiny, CPU)...")
    engine = TrackerEngine.build_default(checkpoint=args.ckpt or DEFAULT_CKPT)

    frame = cv2.imread(os.path.join(args.frames_dir, jpgs[0]))
    if frame is None:
        print("[LOI] không đọc được frame nào")
        raise SystemExit(1)

    t0 = time.time()
    res = engine.start(frame, bbox)
    print(f"[f{res.frame_idx}] bbox={res.bbox} score={res.score:.2f} ms={res.elapsed_ms:.0f}")

    limit = args.num if args.num > 0 else float("inf")
    processed = 1
    while processed < limit:
        if processed >= len(jpgs):
            break
        frame = cv2.imread(os.path.join(args.frames_dir, jpgs[processed]))
        if frame is None:
            break
        res = engine.process(frame)
        processed += 1
        empty = " MASK RỖNG (mất dấu?)" if res.mask.sum() == 0 else ""
        print(f"[f{res.frame_idx}] bbox={res.bbox} score={res.score:.2f} ms={res.elapsed_ms:.0f}{empty}")

    total = time.time() - t0
    print(f"=== tổng {processed} frame trong {total:.1f}s | {total/processed*1000:.0f} ms/frame ===")


if __name__ == "__main__":
    main()