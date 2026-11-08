"""
Thí nghiệm "bị che khuất MỘT PHẦN" — bằng chứng cho tên đề tài.

Chức năng: sinh chuỗi frame có đối tượng bị **vật cản che dần từ 0% → 100%**, chạy TrackerEngine
thật, đo **IoU** giữa bbox dự đoán và bbox đúng ở từng khung, đánh dấu khung bị che và khung
mất dấu, rồi vẽ biểu đồ + in bảng tổng hợp.

Input  : --image-size (mặc định 320), --frames, --fraction (0.5 = che nửa), --cover (số khung bị che)
Output : data/charts/occlusion_iou.png + bảng in ra console + data/occlusion_iou.csv
Lưu ý  : chỉ dùng fixture tổng hợp (không cần webcam), chạy được trên CPU.
         "Mất dấu" = mask rỗng (hệ thống không tìm ra đối tượng) — khác với "che" (không có gì để thấy).
"""
import argparse
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.mask_filter import mask_iou  # noqa: E402
from src.synthetic_video import generate_tracking_sequence  # noqa: E402
from src.tracker_engine import DEFAULT_CKPT, MODEL_CFG, TrackerEngine  # noqa: E402


def iou(a, b):
    """IoU hai bbox (x1, y1, x2, y2)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix = max(0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union else 0.0


def _mask_iou_or_nan(pred, gt):
    """mIoU 1 frame; NaN khi không đo được (một trong hai mask rỗng)."""
    if gt is None or pred is None or not gt.any() or not pred.any():
        return float("nan")
    return mask_iou(pred, gt)


def summarize(ious, lost, mask_ious, occl, start, cover):
    """Gom số của 1 kịch bản — cùng một chỗ cho cả bbox IoU và **mIoU mask vs GT**.

    Vì sao cần mIoU: đề tài tên là *segmentation*; IoU hộp bao không trả lời được "mask có đúng
    không". GT mask ở đây là giải tích (ô vuông trừ dải bị che) nên đo được **mọi frame**, không
    phải gán tay vài chục frame.
    """
    a, b = start, start + cover

    def _mean(values):
        """Trung bình trên các frame ĐO ĐƯỢC; None nếu không có frame nào đo được."""
        clean = np.asarray(values, dtype=float)
        clean = clean[~np.isnan(clean)]
        return round(float(clean.mean()), 4) if clean.size else None

    return {
        "bbox_iou_truoc": round(float(ious[1:a].mean()), 4) if a > 1 else None,
        "bbox_iou_trong": round(float(ious[a:b].mean()), 4),
        "bbox_iou_sau": round(float(ious[b:].mean()), 4),
        # NaN = frame không đo được (GT rỗng do bị che kín, hoặc model trả mask rỗng):
        # `mask_iou(rỗng, rỗng) = 1,0` nếu tính bừa sẽ biến "che kín" thành "phân đoạn hoàn hảo".
        "mask_miou_truoc": _mean(mask_ious[1:a]) if a > 1 else None,
        "mask_miou_trong": _mean(mask_ious[a:b]),
        "mask_miou_sau": _mean(mask_ious[b:]),
        "so_frame_do_miou": int(np.count_nonzero(~np.isnan(np.asarray(mask_ious, float)))),
        "mat_dau_trong_che": int(lost[a:b].sum()),
        "mat_dau_sau_che": int(lost[b:].sum()),
        "so_frame": int(len(ious)),
        "so_lan_cap_nhat_mask_trong_che": int(min(cover, sum(int(x) for x in occl[a:b]))),
    }


def run_scenario(engine, fraction, frames_n=30, cover=6, start_cover=12):
    """Chạy 1 kịch bản che `fraction` (0..1) và trả (bbox_ious, lost, occluded, mask_ious)."""
    fx = generate_tracking_sequence(
        num_frames=frames_n, frame_size=(360, 640), square_size=60,
        start=(80, 80), velocity=(8, 4),
        occlusion_frames=tuple(range(start_cover, start_cover + cover)),
        occlusion_fraction=fraction,
    )
    engine.reset()
    r = engine.start(fx.frames[0], fx.bboxes[0])
    ious, lost = [iou(r.bbox, fx.bboxes[0])], [int(not r.mask.any())]
    mask_ious = [_mask_iou_or_nan(r.mask, fx.masks[0])]
    for i in range(1, frames_n):
        r = engine.process(fx.frames[i])
        ious.append(iou(r.bbox, fx.bboxes[i]))
        lost.append(int(not r.mask.any()))
        mask_ious.append(_mask_iou_or_nan(r.mask, fx.masks[i]))
    return np.array(ious), np.array(lost), fx.occluded, np.array(mask_ious)


def _build_sam2_video_predictor(*args, **kwargs):
    """Lazy import sam2 — chỉ cần khi chạy main() với model thật."""
    from sam2.build_sam import build_sam2_video_predictor

    return build_sam2_video_predictor(*args, **kwargs)


def main():
    ap = argparse.ArgumentParser(description="Thí nghiệm che khuất một phần (đo IoU theo khung)")
    ap.add_argument("--image-size", type=int, default=320)
    ap.add_argument("--frames", type=int, default=30)
    ap.add_argument("--cover", type=int, default=6, help="số khung bị che")
    ap.add_argument("--start", type=int, default=12, help="khung bắt đầu bị che")
    ap.add_argument("--fraction", type=float, default=0.5, help="phần bị che (0.5 = một nửa)")
    ap.add_argument("--out", default="data/charts", help="thư mục xuất ảnh")
    args = ap.parse_args()

    pred = _build_sam2_video_predictor(MODEL_CFG, DEFAULT_CKPT, device="cpu",
                                     hydra_overrides_extra=[f"++model.image_size={args.image_size}"])
    engine = TrackerEngine(pred)

    scenarios = [(args.fraction, f"che {args.fraction * 100:.0f}%"), (1.0, "che 100%")]
    results, summary = [], {}
    for frac, label in scenarios:
        ious, lost, occl, mask_ious = run_scenario(engine, frac, frames_n=args.frames,
                                                   cover=args.cover, start_cover=args.start)
        results.append((label, ious, lost, occl))
        row = summarize(ious, lost, mask_ious, occl, args.start, args.cover)
        summary[label] = row
        print(f"[{label}] bbox IoU: truoc={row['bbox_iou_truoc']} trong={row['bbox_iou_trong']} "
              f"sau={row['bbox_iou_sau']} | MASK mIoU: truoc={row['mask_miou_truoc']} "
              f"trong={row['mask_miou_trong']} sau={row['mask_miou_sau']} | "
              f"mat dau: trong che {row['mat_dau_trong_che']}/{args.cover}, "
              f"sau che {row['mat_dau_sau_che']}")

    fig, ax = plt.subplots(figsize=(9, 4.2))
    for label, ious, _lost, _occl in results:
        ax.plot(range(len(ious)), ious, "-o", ms=3, lw=1.4, label=label)
    ax.axvspan(args.start, args.start + args.cover, color="#f0c0c0", alpha=0.6, label="vùng bị che")
    ax.set_xlabel("Khung hình")
    ax.set_ylabel("IoU (1.0 = khớp hoàn toàn với đáp án)")
    ax.set_ylim(-0.02, 1.05)
    ax.set_title(f"Bám bắt khi bị che khuất — image_size {args.image_size}")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    os.makedirs(args.out, exist_ok=True)
    png = os.path.join(args.out, f"occlusion_iou_{args.image_size}.png")
    fig.savefig(png, dpi=130)
    plt.close(fig)
    print(f"[done] biểu đồ: {png}")

    import json
    import subprocess

    artifact = {
        "git_rev": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                  cwd=_ROOT).stdout.strip(),
        "moi_truong": "CPU (không GPU rời), torch bản CPU",
        "image_size": args.image_size,
        "so_frame": args.frames,
        "khung_bi_che": [args.start, args.start + args.cover],
        "ket_qua": summary,
        "ghi_chu": "GT mask là GIẢI TÍCH (ô vuông trừ dải bị che) trên fixture tổng hợp — "
                   "KHÔNG phải mIoU trên dataset thật; không được trích dẫn như số liệu DAVIS.",
    }
    path = os.path.join(_ROOT, "data",
                        f"occlusion_metrics_{args.image_size}_metrics.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2)
    print(f"[done] số liệu: {path}")


if __name__ == "__main__":
    main()
