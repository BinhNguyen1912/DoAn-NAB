"""Vẽ ảnh bằng chứng "ô đang hiển thị vs ô VOS" của clip `binh1` (drift = 0).

Sinh `docs/media/drift/binh1_f48-108_mask_vos_bam_dung.jpg`: mỗi panel là MỘT frame video, chồng 4 thứ:

- **xanh lá** = ô chọn ban đầu `300,275,150,410` (`bbox.json`) — **cố định**, KHÔNG phải ô hiển thị;
- **vàng**     = ô VOS của **base** `--base` (mặc định 48) — **mốc so sánh cố định**;
- **hồng**     = ô VOS của **chính frame đó** (lấy từ CSV drift của lần đo `vos_every=3`);
- **cyan**     = viền mask THÔ của model, lấy từ PNG do `live_worker --dump-mask-frames` ghi
                 (`vos_every=1`, vì `--dump-mask-frames` bị chặn khi `every > 1`).

Bốn con số IoU in trên panel tính bằng `src.live_tracking._bbox_iou` (toạ độ bao gồm, +1) trên **cặp ô
đã vẽ** — nên nhãn trên ảnh luôn khớp hình. Chạy lại lệnh dưới là ra đúng file đó.

    python scripts/ve_anh_drift_binh1.py --csv data/drift_samples_binh1_2026-11-14_141609.csv \
        --source data/binh1.mp4 --mask-dir docs/media/drift/masks --base 48 --frames 57 69 90 108

GIỚI HẠN phải nói khi trích ảnh: mask PNG ở phiên `vos_every=1`, CSV ở phiên `vos_every=3` ⇒ **hai
phiên khác nhau** (SAM 2 không tất định, AGENTS §6); bbox hồng vẽ từ CSV chứ không phải từ PNG.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.live_tracking import _bbox_iou                          # noqa: E402

MAU_MASK = (255, 255, 0)      # cyan: viền mask
MAU_O_CHON = (0, 255, 0)      # xanh lá: ô chọn ban đầu (cố định)
MAU_BASE = (0, 255, 255)      # vàng: ô VOS của base (mốc so sánh)
MAU_VOS = (255, 0, 255)       # hồng: ô VOS của frame này


def read_boxes(path: Path) -> dict[int, tuple[int, int, int, int]]:
    with path.open(encoding="utf-8") as fh:
        return {
            int(r["frame_idx"]): (int(r["bbox_x1"]), int(r["bbox_y1"]),
                                  int(r["bbox_x2"]), int(r["bbox_y2"]))
            for r in csv.DictReader(fh)
        }


def ve_panel(img, mask, frame: int, base_box, vos_box, o_chon, iou: float | None):
    import cv2
    import numpy as np

    vis = img.copy()
    if mask is not None:
        if mask.shape[:2] != img.shape[:2]:
            mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        contours, _ = cv2.findContours((mask > 127).astype(np.uint8),
                                       cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, contours, -1, MAU_MASK, 2)
    cv2.rectangle(vis, (o_chon[0], o_chon[1]), (o_chon[0] + o_chon[2], o_chon[1] + o_chon[3]),
                  MAU_O_CHON, 2)
    cv2.rectangle(vis, (base_box[0], base_box[1]), (base_box[2], base_box[3]), MAU_BASE, 3)
    cv2.rectangle(vis, (vos_box[0], vos_box[1]), (vos_box[2], vos_box[3]), MAU_VOS, 3)
    nhan = f"f{frame}  IoU(vang,hong)={iou:.3f}" if iou is not None else f"f{frame}  IoU=None"
    cv2.putText(vis, nhan, (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
    return vis


def main() -> int:
    import cv2

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", required=True, help="CSV drift (vos_every=3) của lần đo")
    parser.add_argument("--source", required=True, help="clip video đã dùng")
    parser.add_argument("--mask-dir", required=True, help="thư mục có mask_%06d.png + manifest.json")
    parser.add_argument("--base", type=int, default=48, help="frame VOS làm mốc (ô vàng)")
    parser.add_argument("--frames", type=int, nargs="+", required=True, help="các frame vẽ panel")
    parser.add_argument("--o-chon", default="300,275,150,410", help="ô chọn ban đầu x,y,w,h")
    parser.add_argument("--out", default="docs/media/drift/binh1_f48-108_mask_vos_bam_dung.jpg")
    parser.add_argument("--rong", type=int, default=340, help="bề rộng mỗi panel (px)")
    args = parser.parse_args()

    boxes = read_boxes(Path(args.csv))
    if args.base not in boxes:
        raise SystemExit(f"CSV không có dòng cho base {args.base}")
    o_chon = tuple(int(v) for v in args.o_chon.split(","))
    if len(o_chon) != 4:
        raise SystemExit("--o-chon phải là x,y,w,h")
    cap = cv2.VideoCapture(args.source)
    panels = []
    for frame in args.frames:
        if frame not in boxes:
            print(f"[bỏ] frame {frame}: CSV không có dòng (chỉ dòng ở lần VOS mới có bbox)")
            continue
        mask_path = Path(args.mask_dir) / f"mask_{frame:06d}.png"
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            print(f"[bỏ] frame {frame}: thiếu {mask_path}")
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, img = cap.read()
        if not ok:
            print(f"[bỏ] frame {frame}: không đọc được từ {args.source}")
            continue
        base_box, vos_box = boxes[args.base], boxes[frame]
        iou = _bbox_iou(base_box, vos_box)
        panels.append(ve_panel(img, mask, frame, base_box, vos_box, o_chon, iou))
        print(f"f{frame}: IoU(ô base {args.base}, ô VOS {frame}) = {iou}")
    cap.release()
    if not panels:
        raise SystemExit("không có panel nào — kiểm --frames/--mask-dir")
    import numpy as np
    chieu_cao = int(args.rong * 1280 / 720)
    panels = [cv2.resize(p, (args.rong, chieu_cao)) for p in panels]
    sheet = np.hstack(panels)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(args.out, sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(f"Ghi: {args.out} ({len(panels)} panel)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
