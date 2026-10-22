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


def run_scenario(engine, fraction, frames_n=30, cover=6, start_cover=12):
    """Chạy 1 kịch bản che `fraction` (0..1) và trả (ious, lost, occluded)."""
    fx = generate_tracking_sequence(
        num_frames=frames_n, frame_size=(360, 640), square_size=60,
        start=(80, 80), velocity=(8, 4),
        occlusion_frames=tuple(range(start_cover, start_cover + cover)),
        occlusion_fraction=fraction,
    )
    engine.reset()
    r = engine.start(fx.frames[0], fx.bboxes[0])
    ious, lost = [iou(r.bbox, fx.bboxes[0])], [int(not r.mask.any())]
    for i in range(1, frames_n):
        r = engine.process(fx.frames[i])
        ious.append(iou(r.bbox, fx.bboxes[i]))
        lost.append(int(not r.mask.any()))
    return np.array(ious), np.array(lost), fx.occluded


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
    results = []
    for frac, label in scenarios:
        ious, lost, occl = run_scenario(engine, frac, frames_n=args.frames, cover=args.cover,
                                       start_cover=args.start)
        results.append((label, ious, lost, occl))
        a, b = args.start, args.start + args.cover      # [a,b) = các khung bị che
        print(f"[{label}] truoc che IoU TB={ious[1:a].mean():.3f} | trong che={ious[a:b].mean():.3f} "
              f"(mat dau {lost[a:b].sum()}/{b - a}) | sau che={ious[b:].mean():.3f} "
              f"(mat dau {lost[b:].sum()}/{len(ious) - b}, khung dau={ious[b]:.3f})")

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


if __name__ == "__main__":
    main()
