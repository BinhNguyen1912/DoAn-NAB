"""
Vẽ biểu đồ cho mục "Đánh giá hiệu năng" từ CSV của MetricsLogger.

Chức năng: đọc 1 hoặc nhiều file `*_metrics.csv` (cột: frame_idx, latency_ms, score,
center_x, center_y, lost) → xuất PNG:
  - `<tên>_latency.png`   : độ trễ từng frame + đường trung bình
  - `<tên>_trajectory.png`: quỹ đạo tâm đối tượng (để thấy bám có ổn định)
  - `<tên>_lost.png`      : đánh dấu frame mất dấu
  - `so_sanh_latency.png` : so sánh nhiều file (VD CPU vs GPU) nếu truyền từ 2 file trở lên

Input  : đường dẫn CSV (1..n) + --out DIR (mặc định data/charts).
Output : các file PNG + in bảng tóm tắt (mean/p95/min/max ms, FPS hiệu dụng, tỷ lệ mất dấu).
Lưu ý  : chỉ dùng matplotlib; không cần model, chạy được trên CPU và cả trên Colab.
"""
import argparse
import csv
import os
import sys

import matplotlib

matplotlib.use("Agg")   # không cần màn hình (chạy được trên server/Colab)
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def read_metrics(path):
    """Đọc CSV → dict các mảng numpy."""
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    if not rows:
        raise ValueError(f"{path}: CSV rỗng")
    return {
        "frame": np.array([int(r["frame_idx"]) for r in rows]),
        "latency": np.array([float(r["latency_ms"]) for r in rows]),
        "score": np.array([float(r["score"]) for r in rows]),
        "cx": np.array([float(r["center_x"]) if r["center_x"] else np.nan for r in rows]),
        "cy": np.array([float(r["center_y"]) if r["center_y"] else np.nan for r in rows]),
        "lost": np.array([int(r["lost"]) for r in rows]),
        # Trạng thái tái nhận diện: frame "lost"/"reacquiring" KHÔNG chạy model → latency 0,
        # phải loại khỏi thống kê (nếu không, mean/FPS báo sai — cùng quy tắc với MetricsLogger).
        "frozen": np.array([(r.get("state") in ("lost", "reacquiring")) for r in rows]),
    }


def summarize(name, d):
    measured = ~d["frozen"] if "frozen" in d else np.ones(len(d["latency"]), bool)
    lat = d["latency"][measured] if measured.any() else d["latency"]
    lost = int(d["lost"].sum())
    return {
        "file": name,
        "n": len(d["latency"]),
        "frozen": int((~measured).sum()) if "frozen" in d else 0,
        "mean_ms": float(np.mean(lat)),
        "p95_ms": float(np.percentile(lat, 95)),
        "min_ms": float(np.min(lat)),
        "max_ms": float(np.max(lat)),
        "fps": 1000.0 / float(np.mean(lat)) if np.mean(lat) > 0 else 0.0,
        "lost": lost,
        "lost_ratio": lost / len(d["latency"]),
    }


def plot_one(name, d, out_dir):
    # 1) độ trễ theo frame
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(d["frame"], d["latency"], lw=1, color="#e8701a", label="Độ trễ mỗi frame")
    ax.axhline(float(np.mean(d["latency"])), ls="--", color="#333",
               label=f"Trung bình {np.mean(d['latency']):.0f} ms")
    ax.set_xlabel("Frame")
    ax.set_ylabel("Độ trễ (ms)")
    ax.set_title(f"Độ trễ suy luận — {name}")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p1 = os.path.join(out_dir, f"{name}_latency.png")
    fig.savefig(p1, dpi=130)
    plt.close(fig)

    # 2) quỹ đạo tâm
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot(d["cx"], d["cy"], "-o", ms=2, lw=1, color="#b300b3")
    ax.plot(d["cx"][-1], d["cy"][-1], "o", ms=7, color="#e8701a", label="Tâm hiện tại")
    ax.invert_yaxis()          # toạ độ ảnh: y tăng xuống
    ax.set_xlabel("x (px)")
    ax.set_ylabel("y (px)")
    ax.set_title(f"Quỹ đạo tâm đối tượng — {name}")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p2 = os.path.join(out_dir, f"{name}_trajectory.png")
    fig.savefig(p2, dpi=130)
    plt.close(fig)

    # 3) frame mất dấu
    fig, ax = plt.subplots(figsize=(8, 2.4))
    lost_idx = d["frame"][d["lost"] == 1]
    ax.vlines(lost_idx, 0, 1, color="#c00000", lw=2, label="Mất dấu")
    ax.set_xlim(d["frame"][0], d["frame"][-1] if len(d["frame"]) > 1 else 1)
    ax.set_yticks([])
    ax.set_xlabel("Frame")
    ax.set_title(f"Frame mất dấu — {name} ({len(lost_idx)}/{len(d['frame'])})")
    ax.legend(loc="upper right")
    fig.tight_layout()
    p3 = os.path.join(out_dir, f"{name}_lost.png")
    fig.savefig(p3, dpi=130)
    plt.close(fig)
    return p1, p2, p3


def plot_compare(items, out_dir):
    """So sánh độ trễ trung bình giữa các file (VD CPU vs GPU)."""
    fig, ax = plt.subplots(figsize=(6, 4))
    names = [s["file"] for _, s in items]
    means = [s["mean_ms"] for _, s in items]
    p95 = [s["p95_ms"] for _, s in items]
    x = np.arange(len(names))
    ax.bar(x - 0.18, means, width=0.36, label="Trung bình", color="#4a7ebb")
    ax.bar(x + 0.18, p95, width=0.36, label="p95", color="#e8701a")
    for i, (m, p) in enumerate(zip(means, p95)):
        ax.text(i - 0.18, m, f"{m:.0f}", ha="center", va="bottom", fontsize=8)
        ax.text(i + 0.18, p, f"{p:.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("Độ trễ (ms/frame)")
    ax.set_title("So sánh độ trễ giữa các lần đo")
    ax.set_yscale("log")       # chênh lệch CPU vs GPU rất lớn → thang log
    ax.legend()
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    p = os.path.join(out_dir, "so_sanh_latency.png")
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return p


def main():
    ap = argparse.ArgumentParser(description="Vẽ biểu đồ đánh giá hiệu năng từ CSV metrics")
    ap.add_argument("csv", nargs="+", help="1 hoặc nhiều file *_metrics.csv")
    ap.add_argument("--out", default="data/charts", help="thư mục xuất PNG (mặc định data/charts)")
    ap.add_argument("--skip-warmup", type=int, default=0,
                    help="bỏ N frame đầu khi tính thống kê (frame 0 trên GPU gồm warmup CUDA "
                         "~3 s nên làm sai lệch mean)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    items = []
    print(f"{'file':28} {'n':>5} {'mean':>8} {'p95':>8} {'min':>8} {'max':>8} {'FPS':>6} {'mất dấu':>9}")
    for path in args.csv:
        name = os.path.splitext(os.path.basename(path))[0].replace("_metrics", "")
        d = read_metrics(path)
        label = name
        if args.skip_warmup:
            if len(d["latency"]) <= args.skip_warmup:
                # File ít frame hơn số muốn bỏ ⇒ giữ nguyên + báo rõ (trước đây crash IndexError
                # trong np.percentile vì mảng rỗng — gặp thật khi trộn file CPU 5 frame với file GPU).
                print(f"[bỏ qua --skip-warmup {args.skip_warmup} cho {name}: chỉ có "
                      f"{len(d['latency'])} frame]", file=sys.stderr)
            else:
                d = {k: (v[args.skip_warmup:] if hasattr(v, "__len__") else v) for k, v in d.items()}
                label = f"{name} (bỏ {args.skip_warmup} frame đầu)"
        s = summarize(label, d)
        items.append((d, s))
        print(f"{name:28} {s['n']:5d} {s['mean_ms']:8.0f} {s['p95_ms']:8.0f} "
              f"{s['min_ms']:8.0f} {s['max_ms']:8.0f} {s['fps']:6.2f} "
              f"{s['lost']:4d}/{s['n']:<4d}")
        for p in plot_one(name, d, args.out):
            print(f"  → {p}")

    if len(items) >= 2:
        print(f"  → {plot_compare(items, args.out)}")

    print(f"\n[done] biểu đồ trong {args.out}/")


if __name__ == "__main__":
    sys.exit(main())
