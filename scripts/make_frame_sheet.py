"""Sinh contact sheet để KIỂM BẰNG MẮT: vật còn trong khung ở những frame nào, ô chọn phủ cái gì.

Vì sao cần script này (và phải commit ảnh sinh ra):
  Ngày 14-11 phát hiện hai lỗi cùng loại đều chỉ thấy được khi **nhìn ảnh** — (1) ô `104,308,209,287`
  phủ khuôn mặt chứ không phải vật; (2) phần lớn "mask rỗng" là do vật đã rời khung giữa clip. Không
  có ảnh trong repo thì không ai kiểm lại được "khung frame `0:110` được chọn TRƯỚC hay SAU khi thấy
  kết quả" — tức là không loại trừ được p-hacking.

Cách dùng:
    python scripts/make_frame_sheet.py --clip data/binh1.mp4 --bbox 300,275,150,410 \\
        --every 25 --out docs/media/frames/binh1_bbox_300-275-150-410.jpg

Output: 1 ảnh (lưới 6 cột) mỗi ô là một frame có số frame in kèm; ô chọn được vẽ trên MỌI frame để
thấy ngay nó trôi khỏi vật ở đâu. Ảnh ghi vào `docs/media/` (thư mục này KHÔNG bị `.gitignore`).
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
CELL = (180, 320)          # (rộng, cao) mỗi ô — đủ thấy vật, giữ ảnh dưới ~1 MB
COLS = 6


def make_sheet(clip: str, bbox=None, every: int = 25) -> np.ndarray:
    """Đọc `clip`, lấy frame mỗi `every` frame, vẽ số frame + `bbox` (x,y,w,h) nếu có → ảnh lưới."""
    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        raise SystemExit(f"[LOI] không mở được clip: {clip}")
    cells, index = [], 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if index % every == 0:
                if bbox:
                    x, y, w, h = bbox
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 3)
                frame = cv2.resize(frame, CELL)
                # Số frame vẽ SAU resize để chữ không bị thu nhỏ theo ảnh.
                cv2.putText(frame, str(index), (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (0, 255, 255), 2)
                cells.append(frame)
            index += 1
    finally:
        cap.release()
    if not cells:
        raise SystemExit(f"[LOI] không đọc được frame nào từ {clip}")
    blank = np.zeros((CELL[1], CELL[0], 3), np.uint8)
    rows = []
    for start in range(0, len(cells), COLS):
        block = cells[start:start + COLS]
        block += [blank] * (COLS - len(block))
        rows.append(np.hstack(block))
    return np.vstack(rows)


def parse_bbox(text: str):
    """`"x,y,w,h"` → tuple; rỗng → `None`. Sai định dạng ⇒ `ValueError` (không đoán)."""
    if not text:
        return None
    try:
        values = [int(v) for v in text.replace(",", " ").split()]
    except ValueError as exc:
        raise ValueError("--bbox phải là x,y,w,h (số nguyên)") from exc
    if len(values) != 4:
        raise ValueError("--bbox phải có đúng 4 số: x,y,w,h")
    return tuple(values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", required=True)
    parser.add_argument("--bbox", default="", help="x,y,w,h vẽ lên mọi frame (tuỳ chọn)")
    parser.add_argument("--every", type=int, default=25, help="lấy 1 frame mỗi N frame (mặc định 25)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        bbox = parse_bbox(args.bbox)
    except ValueError as exc:
        parser.error(str(exc))
    if args.every < 1:
        parser.error("--every phải >= 1")
    sheet = make_sheet(args.clip, bbox=bbox, every=args.every)
    out = Path(args.out)
    if not out.is_absolute():
        out = _REPO_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 72])
    print(f"Ghi: {out} ({out.stat().st_size // 1024} KB, {sheet.shape[1]}×{sheet.shape[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
