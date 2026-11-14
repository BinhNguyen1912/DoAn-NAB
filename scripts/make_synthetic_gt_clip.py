"""
Sinh clip TỔNG HỢP có GT mask biết trước (việc #6): dùng để **kiểm chính đường chấm mIoU**, không
phải để khoe chất lượng.

Vì sao cần: `scripts/score_miou.py` chỉ có giá trị nếu nó chấm ra số đúng trên một ca mà ta BIẾT
trước đáp án (một ô vuông trắng đi ngang trên nền phẳng). Chạy nó trên fixture tổng hợp rồi ghi
"mIoU 0,9x" là **cận trên** — GT ≡ đúng vùng pixel của ô vuông và prompt là đúng bbox của nó
(AGENTS §6). Muốn nói chất lượng trên video THẬT thì phải gán tay (`scripts/score_miou.py label`).

Cách dùng:
    python scripts/make_synthetic_gt_clip.py --out-clip data/synthetic_gt.mp4 \\
        --out-gt docs/gt/synthetic_tong_hop --frames 24
Output: clip mp4 + `gt_<idx>.png` cho MỌI frame + `index.json` (nguoi_gan = "sinh tổng hợp",
gt_do_model_goi_y = false ⇒ hợp lệ để chấm).
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[1]
SIZE = (320, 240)          # (rộng, cao)
BOX = 60                   # cạnh ô vuông (px)


def frame_and_gt(index: int) -> tuple:
    """Frame `index` + mask GT của nó: nền xám nhiễu nhẹ, ô vuông trắng đi ngang rồi quay lại."""
    w, h = SIZE
    rng = np.random.default_rng(index)                       # nhiễu TẤT ĐỊNH theo frame
    frame = np.full((h, w, 3), 60, np.uint8)
    frame += rng.integers(0, 12, size=(h, w, 3), dtype=np.uint8)
    # đi ngang rồi quay lại (tam giác) để clip có chuyển động hai chiều
    total = 48
    phase = index % total
    vi_tri = phase if phase <= total // 2 else total - phase
    x0 = int(20 + vi_tri * (w - BOX - 40) / (total // 2))
    y0 = h // 2 - BOX // 2
    cv2.rectangle(frame, (x0, y0), (x0 + BOX, y0 + BOX), (245, 245, 245), -1)
    gt = np.zeros((h, w), np.uint8)
    gt[y0:y0 + BOX, x0:x0 + BOX] = 255
    return frame, gt, (x0, y0, BOX, BOX)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Clip tổng hợp + GT mask biết trước (kiểm mIoU).")
    parser.add_argument("--out-clip", default="data/synthetic_gt.mp4")
    parser.add_argument("--out-gt", default="docs/gt/synthetic_tong_hop")
    parser.add_argument("--frames", type=int, default=24)
    parser.add_argument("--fps", type=float, default=10.0)
    args = parser.parse_args(argv)

    clip_path = Path(args.out_clip)
    if not clip_path.is_absolute():
        clip_path = _REPO_ROOT / clip_path
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    gt_dir = Path(args.out_gt)
    if not gt_dir.is_absolute():
        gt_dir = _REPO_ROOT / gt_dir
    gt_dir.mkdir(parents=True, exist_ok=True)

    writer = cv2.VideoWriter(str(clip_path), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, SIZE)
    if not writer.isOpened():
        print(f"[LOI] không tạo được video {clip_path}")
        return 1
    frames = []
    try:
        for index in range(args.frames):
            frame, gt, bbox = frame_and_gt(index)
            writer.write(frame)
            cv2.imwrite(str(gt_dir / f"gt_{index:06d}.png"), gt)
            frames.append({"frame_idx": index, "bbox_xywh": list(bbox)})
    finally:
        writer.release()

    index_data = {
        "clip": str(clip_path.relative_to(_REPO_ROOT)) if clip_path.is_relative_to(_REPO_ROOT)
        else str(clip_path),
        "ten": gt_dir.name,
        "frames": frames,
        "nguoi_gan": "sinh tổng hợp (make_synthetic_gt_clip.py) — GT ≡ pixel ô vuông, KHÔNG gán tay",
        "gt_do_model_goi_y": False,
        "tao_luc": datetime.now().isoformat(timespec="seconds"),
        "canh_bao": "Fixture TỔNG HỢP: mIoU chấm trên đây là CẬN TRÊN, cấm trích như mIoU trên "
                    "video thật. Muốn số thật thì gán tay bằng `scripts/score_miou.py label`.",
    }
    (gt_dir / "index.json").write_text(json.dumps(index_data, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    print(f"[gt] clip: {clip_path} ({args.frames} frame {SIZE[0]}×{SIZE[1]})")
    print(f"[gt] GT:   {gt_dir} ({args.frames} file gt_*.png + index.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
