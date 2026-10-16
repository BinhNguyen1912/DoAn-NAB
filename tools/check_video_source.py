"""
Script kiểm tra nhanh VideoSource — chọn nguồn bằng 1 tham số (ticket 03, tiêu chí 4).

Cách chạy (env conda `samurai`):
  python tools/check_video_source.py --source 0                      # webcam index 0
  python tools/check_video_source.py --source rtsp://IP:554/stream    # camera điện thoại/IP
  python tools/check_video_source.py --source data/video.mp4          # video file
  python tools/check_video_source.py --source video.mp4 --num 60      # đọc 60 frame rồi dừng

Output: in thông tin nguồn (kích thước, FPS nguồn, số frame đọc được / độ trễ đọc).
Dùng để xác nhận thủ công webcam/RTSP (không test tự động — phụ thuộc thiết bị).
"""
import argparse
import os
import sys
import time

import numpy as np

# Cho phép chạy script từ bất kỳ đâu: thêm thư mục gốc repo vào sys.path trước khi import src.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.video_source import open_video_source


def main():
    ap = argparse.ArgumentParser(description="Kiểm tra nhanh nguồn video (webcam/RTSP/file)")
    ap.add_argument("--source", required=True, help="index webcam (số), rtsp://URL, hoặc đường dẫn file")
    ap.add_argument("--num", type=int, default=30, help="số frame tối đa đọc thử (mặc định 30)")
    ap.add_argument("--open_timeout_ms", type=int, default=5000, help="timeout mở RTSP")
    args = ap.parse_args()

    # Chọn nguồn: số chữ → index webcam; chuỗi → path/RTSP (factory tự định tuyến)
    source_arg = args.source
    if source_arg.isdigit():
        source_arg = int(source_arg)

    try:
        src = open_video_source(source_arg, open_timeout_ms=args.open_timeout_ms).open()
    except (FileNotFoundError, ConnectionError, RuntimeError, ValueError) as exc:
        print(f"[LOI] {exc}")
        raise SystemExit(1)

    with src:
        kind = type(src).__name__
        print(f"[nguồn] {source_arg!r} → {kind} | kích thước (W,H)={src.frame_size} | FPS nguồn={src.source_fps}")

        read_times = []
        count = 0
        while count < args.num:
            t0 = time.time()
            frame = src.read()
            read_times.append((time.time() - t0) * 1000)
            if frame is None:
                break
            count += 1
            if count == 1:
                print(f"[frame đầu] shape={frame.shape} dtype={frame.dtype}")

    if count:
        ms = float(np.mean(read_times[1:]) if len(read_times) > 1 else read_times[0])
        print(f"[OK] đọc được {count} frame | thời gian read trung bình {ms:.1f} ms/frame")
    else:
        print("[LOI] không đọc được frame nào từ nguồn")
        raise SystemExit(1)


if __name__ == "__main__":
    main()