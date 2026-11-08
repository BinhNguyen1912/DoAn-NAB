"""
Đo chi phí CPU của các tracker nhẹ (không cần model AI) trên chính máy này.

Chức năng: trả lời "thêm một tracker nhẹ chạy mỗi frame nguồn thì tốn bao nhiêu ms?" — con số
    quyết định kiến trúc hybrid (VOS 10 FPS + tracker 30 FPS) có khả thi hay không.
Input : video 640×480 (`--source`), khung hình đầu để khởi tạo tracker (`--bbox`).
Output: ms/frame mean + p95 cho từng tracker có sẵn trong môi trường.

Vì sao tự đo thay vì trích paper: paper MOSSE/KCF báo "hàng trăm FPS" trên CPU đời cũ, không nói
    độ phân giải, và OpenCV 5.0 đã **bỏ KCF/CSRT khỏi bản pip** (`cv2.TrackerKCF_create` không tồn
    tại) ⇒ số duy nhất dùng được cho báo cáo là số đo tại chỗ.

Tracker được thử (cái nào môi trường có thì chạy):
    - LK  : `cv2.calcOpticalFlowPyrLK` trên lưới điểm trong bbox, lấy dịch chuyển TRUNG VỊ
            (fallback rẻ nhất, không cần model, không cần contrib)
    - MIL : `cv2.TrackerMIL_create` (có trong OpenCV pip)
    - Nano/Vit : `cv2.TrackerNano_create` / `TrackerVit_create` — cần file ONNX (truyền `--onnx`)

Chạy:
    .venv/bin/python -m scripts.benchmark_light_trackers --frames 200
    .venv/bin/python -m scripts.benchmark_light_trackers --onnx models/track/nanotrack.onnx
"""
import argparse
import json
import os
import statistics
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_frames(source: str, bbox, num_frames: int):
    """Đọc tối đa num_frames frame đầu + trả frame gốc và bbox."""
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise FileNotFoundError(f"không mở được nguồn: {source}")
    frames = []
    for _ in range(num_frames):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    if len(frames) < 10:
        raise ValueError(f"nguồn quá ngắn: chỉ đọc được {len(frames)} frame")
    return frames, bbox


def bench_lk(frames, bbox) -> float:
    """LK thưa + dịch chuyển trung vị. Trả ms/frame trung bình."""
    x1, y1, x2, y2 = bbox
    step = max(6, (x2 - x1) // 8)
    pts = np.array([[x, y] for x in range(x1, x2, step) for y in range(y1, y2, step)],
                   dtype=np.float32).reshape(-1, 1, 2)
    prev_gray = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
    times = []
    p0 = pts.copy()
    for frame in frames[1:]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        t0 = time.perf_counter()
        p1, st, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, p0, None,
                                            winSize=(21, 21), maxLevel=2)
        good = None if st is None else (st.reshape(-1) == 1)
        if good is not None and good.any():
            delta = (p1[good] - p0[good]).reshape(-1, 2)
            dx, dy = float(np.median(delta[:, 0])), float(np.median(delta[:, 1]))
            p0 = (p0 + np.array([[[dx, dy]]], dtype=np.float32)).astype(np.float32)
        times.append((time.perf_counter() - t0) * 1000)
        prev_gray = gray
    return statistics.mean(times)


def bench_opencv_tracker(frames, bbox, factory) -> float:
    """Benchmark một tracker của OpenCV (MIL/Nano/Vit). Trả ms/frame trung bình."""
    tracker = factory()
    tracker.init(frames[0], tuple(int(v) for v in bbox))
    times = []
    for frame in frames[1:]:
        t0 = time.perf_counter()
        tracker.update(frame)
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.mean(times)


def main() -> int:
    ap = argparse.ArgumentParser(description="Đo chi phí tracker nhẹ trên CPU")
    ap.add_argument("--source", default="data/binh1.mp4")
    ap.add_argument("--bbox", default="104,308,209,287",
                    help="'x,y,w,h' frame 0 — CÙNG định dạng với tools/run_live.py --bbox")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--onnx", default=None, help="file ONNX cho TrackerNano (tuỳ chọn)")
    args = ap.parse_args()

    x, y, w, h = (int(v) for v in args.bbox.split(","))
    frames, bbox = _read_frames(args.source, (x, y, x + w, y + h), args.frames)
    print(f"nguồn {args.source} | {len(frames)} frame | {frames[0].shape[1]}x{frames[0].shape[0]}")

    results = {}
    results["LK (median Δ)"] = bench_lk(frames, bbox)
    if hasattr(cv2, "TrackerMIL_create"):
        results["MIL"] = bench_opencv_tracker(frames, bbox, cv2.TrackerMIL_create)
    if args.onnx and hasattr(cv2, "TrackerNano_create") and os.path.isfile(args.onnx):
        results["NanoTrack"] = bench_opencv_tracker(frames, bbox,
                                                    lambda: cv2.TrackerNano_create(args.onnx))

    print(f"\n{'tracker':22} {'ms/frame':>9} {'FPS trần':>9}")
    for name, ms in sorted(results.items(), key=lambda kv: kv[1]):
        print(f"{name:22} {ms:>9.2f} {1000 / ms:>9.0f}")

    # Ghi JSON (thư mục data/ đã gitignore trừ *_summary.json — theo quy ước repo)
    out = os.path.join("data", "light_trackers_summary.json")
    os.makedirs("data", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({name: round(ms, 3) for name, ms in results.items()}, f, ensure_ascii=False, indent=2)
    print(f"\n[done] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
