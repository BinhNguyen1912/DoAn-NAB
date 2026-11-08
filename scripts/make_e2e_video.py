"""
make_e2e_video.py — sinh fixture video nhỏ cho E2E web (không commit file nặng).
 *
 * Chức năng: tạo `data/e2e_web.mp4` (160×120, 20 frame, một ô sáng chuyển động) và
 *           `data/e2e_bad.txt` (file sai định dạng để test nhánh lỗi upload).
 * Input  : không (đường dẫn cố định trong data/).
 * Output : 2 file trong data/ — kích thước vài KB, .gitignore đã chặn.
 * Lưu ý  : video phải có kích thước NHỎ và CỐ ĐỊNH để test quy đổi toạ độ canvas → pixel
         tính được kỳ vọng bằng tay (x=16, y=36, w=48, h=48 khi kéo 10–40% / 30–70%).
"""

import sys
from pathlib import Path

import cv2
import numpy as np

WIDTH, HEIGHT, FRAMES, FPS = 160, 120, 20, 10


def main() -> int:
    data = Path(__file__).resolve().parents[1] / "data"
    data.mkdir(exist_ok=True)

    video_path = data / "e2e_web.mp4"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT)
    )
    if not writer.isOpened():
        print("[LOI] không tạo được VideoWriter (thiếu codec mp4v?)")
        return 1
    for index in range(FRAMES):
        frame = np.full((HEIGHT, WIDTH, 3), 60, np.uint8)
        x = 10 + index * 2
        cv2.rectangle(frame, (x, 30), (x + 30, 70), (200, 200, 220), -1)
        writer.write(frame)
    writer.release()

    bad_path = data / "e2e_bad.txt"
    bad_path.write_text("khong phai video", encoding="utf-8")

    print(f"[e2e] video: {video_path} ({video_path.stat().st_size} bytes)")
    print(f"[e2e] file sai định dạng: {bad_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
