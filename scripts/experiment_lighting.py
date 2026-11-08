"""
Thí nghiệm "đổi điều kiện ánh sáng" — yêu cầu 11 của GVHD
("kiểm thử khả năng bám bắt trong các điều kiện chuyển động, che khuất và **thay đổi ánh sáng**").

Chức năng: sinh chuỗi frame giả lập (ô vuông cam trên nền xám, quỹ đạo biết trước), rồi **làm tối
dần khung hình theo hệ số gain** (1,0 = gốc; 0,5 = tối một nửa; 0,15 = gần như mất chi tiết) trước khi
đưa vào TrackerEngine thật → đo **IoU** với đáp án và **số khung mất dấu** ở từng mức sáng.

Input  : --image-size (mặc định 320), --frames, --gains (danh sách hệ số sáng)
Output : bảng in ra console + data/charts/lighting_iou_<size>.png + data/lighting_iou_<size>.csv
Lưu ý  : chỉ dùng fixture tổng hợp (không cần webcam), chạy trên CPU. Đây là phép đo **độ bền của
         mô hình** với ánh sáng yếu; kết quả trên cảnh thật còn phụ thuộc camera/đèn (ADR-0002 —
         ghi đúng điều kiện đo, không suy rộng).
         Hàm `apply_lighting` là hàm THUẦN (numpy) → phần logic test được không cần model.
"""
import argparse
import csv
import os
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.synthetic_video import generate_tracking_sequence  # noqa: E402
from src.tracker_engine import DEFAULT_CKPT, MODEL_CFG, TrackerEngine  # noqa: E402

# Các mức sáng mặc định: 1,0 (gốc) → 0,6 → 0,35 → 0,2 (đèn yếu) → 0,1 (gần như tối)
DEFAULT_GAINS = (1.0, 0.6, 0.35, 0.2, 0.1)


def apply_lighting(frame, gain: float) -> np.ndarray:
    """Nhân độ sáng khung hình với `gain` rồi cắt về [0, 255] — giữ nguyên dtype uint8.

    Phải ép float32 trước khi nhân: nhân trực tiếp trên uint8 sẽ **tràn số** (250 × 2 = 244)
    → frame bị đảo màu, làm sai toàn bộ thí nghiệm.
    """
    data = frame.astype(np.float32) * float(gain)
    return np.clip(data, 0.0, 255.0).astype(np.uint8)


def iou(a, b) -> float:
    """IoU hai bbox (x1, y1, x2, y2) — để đọc kết quả, không phụ thuộc code sản phẩm."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix = max(0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union else 0.0


def make_sequence(frames_n=15, frame_size=(360, 640), square_size=60,
                  start=(80, 80), velocity=(8, 4)):
    """Chuỗi fixture (ô vuông cam trên nền xám) + đáp án bbox từng khung."""
    return generate_tracking_sequence(
        num_frames=frames_n, frame_size=frame_size, square_size=square_size,
        start=start, velocity=velocity,
    )


def run_gain(engine, fixture, gain: float):
    """Chạy 1 mức sáng; trả (ious, lost) độ dài = số khung.

    `engine.reset()` trước mỗi mức sáng: cùng một engine dùng lại nhiều lần thì bộ nhớ SAM 2
    của mức trước sẽ rò sang mức sau → số đo không còn là "ảnh hưởng của ánh sáng".
    """
    engine.reset()
    frames = [apply_lighting(f, gain) for f in fixture.frames]
    res = engine.start(frames[0], fixture.bboxes[0])
    ious = [iou(res.bbox, fixture.bboxes[0])]
    lost = [int(not res.mask.any())]
    for i in range(1, len(frames)):
        res = engine.process(frames[i])
        ious.append(iou(res.bbox, fixture.bboxes[i]))
        lost.append(int(not res.mask.any()))
    return np.array(ious, dtype=float), np.array(lost, dtype=int)


def run_sweep(engine, gains=DEFAULT_GAINS, frames_n=15, fixture=None):
    """Quét nhiều mức sáng; trả list dict {gain, mean_iou, min_iou, lost_frames, frames}."""
    fixture = fixture if fixture is not None else make_sequence(frames_n=frames_n)
    rows = []
    for gain in gains:
        ious, lost = run_gain(engine, fixture, gain)
        rows.append({
            "gain": float(gain),
            "frames": int(ious.size),
            "mean_iou": float(ious.mean()),
            "min_iou": float(ious.min()),
            "lost_frames": int(lost.sum()),
        })
    return rows


def write_csv(rows, path: str) -> str:
    """Ghi bảng kết quả ra CSV để báo cáo/bảng biểu dùng lại."""
    parent = os.path.dirname(str(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def write_json(rows, path: str) -> str:
    """Ghi bảng kết quả ra JSON (`*_summary.json` — được `.gitignore` giữ lại làm bằng chứng đo)."""
    import json

    parent = os.path.dirname(str(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"experiment": "do-i-anh-sang", "rows": rows}, f, ensure_ascii=False, indent=2)
    return str(path)


def plot(rows, image_size: int, out_dir: str = "data/charts") -> str:
    """Vẽ IoU theo mức sáng (trung bình + thấp nhất) — ảnh cho báo cáo."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gains = [r["gain"] for r in rows]
    fig, ax = plt.subplots(figsize=(7.5, 4.0))
    ax.plot(gains, [r["mean_iou"] for r in rows], "-o", lw=1.6, label="IoU trung bình")
    ax.plot(gains, [r["min_iou"] for r in rows], "--s", ms=4, lw=1.1, label="IoU thấp nhất")
    ax.set_xlabel("Hệ số sáng (1,0 = ảnh gốc, 0,1 = gần như tối)")
    ax.set_ylabel("IoU với đáp án (1,0 = khớp hoàn toàn)")
    ax.set_ylim(-0.02, 1.05)
    ax.set_title(f"Bám bắt khi đổi ánh sáng — image_size {image_size}")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"lighting_iou_{image_size}.png")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def _build_sam2_video_predictor(*args, **kwargs):
    """Lazy import sam2 — chỉ cần khi chạy main() với model thật."""
    from sam2.build_sam import build_sam2_video_predictor

    return build_sam2_video_predictor(*args, **kwargs)


def main():
    ap = argparse.ArgumentParser(description="Thí nghiệm đổi ánh sáng (đo IoU theo mức sáng)")
    ap.add_argument("--image-size", type=int, default=320)
    ap.add_argument("--frames", type=int, default=15)
    ap.add_argument("--gains", type=float, nargs="+", default=list(DEFAULT_GAINS),
                    help="các hệ số sáng cần đo (mặc định 1.0 0.6 0.35 0.2 0.1)")
    ap.add_argument("--out", default="data/charts", help="thư mục xuất ảnh")
    args = ap.parse_args()

    pred = _build_sam2_video_predictor(MODEL_CFG, DEFAULT_CKPT, device="cpu",
                                       hydra_overrides_extra=[f"++model.image_size={args.image_size}"])
    engine = TrackerEngine(pred)
    rows = run_sweep(engine, gains=args.gains, frames_n=args.frames)

    for r in rows:
        print(f"[gain {r['gain']:.2f}] IoU TB={r['mean_iou']:.3f} | thấp nhất={r['min_iou']:.3f} "
              f"| mất dấu {r['lost_frames']}/{r['frames']}")
    print("[done] CSV:", write_csv(rows, os.path.join("data", f"lighting_iou_{args.image_size}.csv")))
    print("[done] JSON:", write_json(rows, os.path.join("data", f"lighting_iou_{args.image_size}_summary.json")))
    print("[done] biểu đồ:", plot(rows, args.image_size, args.out))


if __name__ == "__main__":
    main()
