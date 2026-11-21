"""Thử MỞ camera trên Windows bằng đúng backend mà relay dùng (DirectShow) — chạy trên WINDOWS.

Vì sao có file này (đo 21-11-2026): `./run relay start` báo "camera đang bị app Windows giữ" khi
`/info` trả `w: 0`, nhưng KHÔNG có cách nào kiểm chứng câu đó. Bản vá đầu tiên hỏi
`Get-PnpDevice -PresentOnly -Class Camera` — **SAI**: trên máy này truy vấn đó trả RỖNG (thiết bị
`HD Webcam` của laptop không nằm trong class `Camera` mà Windows báo theo cách khác) trong khi
`cv2.VideoCapture(0, CAP_DSHOW)` mở và đọc được khung 640×480. Kết luận sai đó đã dẫn người dùng đi
cắm lại dây vô ích.

Thứ DUY NHẤT đúng là thử đúng việc relay sẽ làm: mở camera. File này làm việc đó và in kết quả
theo máy đọc được (`OK idx=0 640x480` | `FAIL`), để `scripts/cam_relay.sh` khỏi phải đoán.

    (Windows) %LOCALAPPDATA%\\wincam-venv\\Scripts\\python.exe scripts\\win_cam_probe.py [--max-index 2]
"""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Thử mở camera Windows (DirectShow) và in kết quả")
    ap.add_argument("--max-index", type=int, default=2, help="thử index 0..N (mặc định 2)")
    ap.add_argument("--backend", default="dshow", choices=["dshow", "msmf", "any"],
                    help="backend OpenCV; relay dùng dshow nên mặc định là dshow")
    args = ap.parse_args(argv)

    import cv2

    be = {"dshow": getattr(cv2, "CAP_DSHOW", 0), "msmf": getattr(cv2, "CAP_MSMF", 0),
          "any": cv2.CAP_ANY}[args.backend]
    for idx in range(args.max_index + 1):
        cap = cv2.VideoCapture(idx, be)
        try:
            if not cap.isOpened():
                continue
            ok, frame = cap.read()
            if ok and frame is not None:
                print(f"OK idx={idx} {frame.shape[1]}x{frame.shape[0]}")
                return 0
        finally:
            cap.release()
    print("FAIL khong mo duoc camera nao (index 0..%d, backend=%s)" % (args.max_index, args.backend))
    return 1


if __name__ == "__main__":
    sys.exit(main())
