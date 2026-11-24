"""Sweep siêu tham số **motion-memory của SAMURAI** — chạy chèn kẽ, chấm mIoU theo CẶP.

Vì sao có (24-11-2026, "Tầng 1 — custom model không cần train"): repo chạy `samurai_mode: true` nhưng
**chưa ai đo** 6 siêu tham số điều khiển việc chọn ký ức + Kalman filter
(`kf_score_weight`, `memory_bank_kf_score_threshold`, `stable_frames_threshold`, …). Đó là bề mặt duy
nhất còn lý lẽ để làm hệ "khôn hơn" khi vật di chuyển nhanh / trôi sang nền, mà **không** phải train
(GT hiện có ~84 frame trên 13 bộ — không đủ để fine-tune SAM 2).

Cách chấm (đúng luật repo):
  - **Chèn kẽ** các cấu hình trong từng vòng (SAM 2 **không tất định**: hai lần chạy cùng cấu hình cho
    ô bao cuối khác nhau) ⇒ chênh lệch giữa cấu hình đo trên cùng vòng.
  - **So cặp theo frame** (`scripts/paired_miou.py` làm cùng nguyên tắc): khử phương sai giữa frame.
  - Mọi cấu hình phải đi qua `build_overrides()` (hydra) — **cấm copy file config**, đã đo được là làm
    đổi hành vi (mIoU 0,6987 → 0,2486 dù nội dung y nguyên).

Chạy:

    python scripts/sweep_motion_memory.py --clip data/binh1.mp4 --gt b1 \
        --bbox 300,275,150,410 --image-size 192 --rounds 3 \
        --out data/sweep_motion_memory_2026-11-24_metrics.json

ĐỌC SỐ CHO ĐÚNG (script tự in lại):
  - `mIoU` tuyệt đối KHÔNG phải "độ chính xác": GT tự khớp chính nó chỉ **0,8772** (clip đặc) /
    **0,7550** (túi mờ) ⇒ chênh lệch nhỏ hơn ngưỡng nhiễu của chính clip thì phải viết
    **"không kết luận được"**. Truyền ngưỡng qua `--nguong-nhieu` (mặc định 0,12 = clip đặc).
  - `rounds < 2` ⇒ chỉ là 1 lần chạy, không được tuyên bố gì.
"""
import argparse
import json
import math
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# Cấu hình mặc định: baseline + 4 giả thuyết, đều qua hydra override.
CAU_HINH = [
    ("A_hien_tai", {}),
    ("B_kf_weight_0.5", {"kf_score_weight": 0.5}),
    ("C_kf_nguong_0.2", {"memory_bank_kf_score_threshold": 0.2}),
    ("D_stable_8", {"stable_frames_threshold": 8}),
    ("E_samurai_off", {"samurai_mode": False}),
]


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def frames_gt(gt_dir: Path) -> list[int]:
    """Danh sách frame của bộ GT, đọc từ TÊN FILE (`gt_000030.png`) — không tin index.json."""
    d = gt_dir
    if not d.is_dir():
        raise SystemExit(f"[LOI] không có {d}")
    ra = sorted(int(m.group(1)) for p in d.glob("gt_*.png")
                if (m := re.fullmatch(r"gt_(\d+)", p.stem)))
    if not ra:
        raise SystemExit(f"[LOI] {d} không có gt_*.png (mask GT thật)")
    return ra


def chay_mot(clip, bbox, image_size, frames, pred_dir: Path, overrides: dict, max_frames: int):
    """Chạy `tools/run_live.py` headless để xuất mask tại các frame GT. Trả (ok, log cuối)."""
    pred_dir.mkdir(parents=True, exist_ok=True)
    for f in pred_dir.glob("mask_*.png"):
        f.unlink()
    lenh = [PYTHON, "tools/run_live.py",
            "--source", str(clip), "--bbox", bbox, "--image-size", str(image_size),
            "--no-reid", "--max-frames", str(max_frames),
            "--dump-mask-frames", ",".join(str(f) for f in frames),
            "--dump-mask-dir", str(pred_dir)]
    for k, v in overrides.items():
        lenh += ["--model-override", f"{k}={v}"]
    r = subprocess.run(lenh, cwd=REPO_ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip().splitlines()[-3:]
    return True, []


def cham(gt: str, pred_dir: Path, out: Path):
    """Chấm mIoU bằng `scripts/score_miou.py`; trả `(mIoU, {frame_idx: iou})`."""
    lenh = [PYTHON, "scripts/score_miou.py", "score", "--gt", gt,
            "--pred-dir", str(pred_dir), "--out", str(out)]
    r = subprocess.run(lenh, cwd=REPO_ROOT, capture_output=True, text=True)
    # `score_miou` THOÁT MÃ 1 khi có CẢNH BÁO (GT rỗng, coverage < 100 %) dù số vẫn dùng được —
    # chính nó in "exit 1: số vẫn dùng được nhưng phải đọc kèm canh_bao_gt". Vì vậy điều kiện đúng là
    # "artifact có mặt và parse được", KHÔNG phải returncode == 0 (bản đầu của tệp này hiểu sai nên
    # mọi cấu hình ra mIoU=None với n=0).
    if not out.is_file():
        return None, {}, (r.stdout + r.stderr).strip().splitlines()[-3:]
    d = json.loads(out.read_text(encoding="utf-8"))
    kq = d.get("ket_qua") or {}
    per = {int(x["frame_idx"]): x.get("iou") for x in (kq.get("frames") or [])
           if x.get("iou") is not None}
    return kq.get("mIoU"), per, []


def ci95_bootstrap(chenh: list[float], n_lan: int = 4000, seed: int = 0) -> tuple[float, float]:
    """CI95 của trung bình chênh lệch (bootstrap, không cần scipy)."""
    import random

    rnd = random.Random(seed)
    if len(chenh) < 2:
        return (float("nan"), float("nan"))
    tb = []
    for _ in range(n_lan):
        mau = [chenh[rnd.randrange(len(chenh))] for _ in chenh]
        tb.append(sum(mau) / len(mau))
    tb.sort()
    return tb[int(0.025 * n_lan)], tb[int(0.975 * n_lan) - 1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sweep motion-memory SAMURAI, chấm mIoU theo cặp.")
    ap.add_argument("--clip", required=True)
    ap.add_argument("--gt", required=True, help="ĐƯỜNG DẪN bộ GT, vd docs/gt/b1")
    ap.add_argument("--bbox", required=True, help="x,y,w,h (quy ước UI/API; sẽ đổi sang xyxy)")
    ap.add_argument("--image-size", type=int, default=192)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--max-frames", type=int, default=None)
    ap.add_argument("--nguong-nhieu", type=float, default=0.12,
                    help="ngưỡng nhiễu mIoU của CHÍNH clip (đo bằng scripts/gt_noise.py)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--dung-lai-mask", action="store_true",
                    help="chỉ CHẤM LẠI từ mask đã có trong thư mục tạm (không nạp model)")
    args = ap.parse_args(argv)

    if args.rounds < 2:
        print("[LOI] --rounds phải >= 2: SAM 2 KHÔNG tất định, một lần chạy không kết luận được")
        return 2
    gt_dir = Path(args.gt)
    if not gt_dir.is_absolute():
        gt_dir = REPO_ROOT / gt_dir
    ten_gt = gt_dir.name
    frames = frames_gt(gt_dir)
    max_frames = args.max_frames or (max(frames) + 1)
    tmp = REPO_ROOT / "data" / f"tmp_sweep_{ten_gt}"
    print(f"[sweep] clip={args.clip} gt={args.gt} frames={frames} "
          f"rounds={args.rounds} image_size={args.image_size} max_frames={max_frames}")

    ket_qua = {ten: {"overrides": ov, "mIoU": [], "per_frame": []} for ten, ov in CAU_HINH}
    for lan in range(1, args.rounds + 1):
        for ten, ov in CAU_HINH:
            pd = tmp / f"{ten}_lan{lan}"
            t0 = time.time()
            co_mask = len(list(pd.glob("mask_*.png"))) >= len(frames)
            if args.dung_lai_mask and co_mask:
                ok, loi = True, []
            else:
                ok, loi = chay_mot(args.clip, args.bbox, args.image_size, frames, pd, ov, max_frames)
            if not ok:
                print(f"[sweep] lan{lan} {ten}: LỖI chạy — {loi}")
                ket_qua[ten]["mIoU"].append(None)
                ket_qua[ten]["per_frame"].append({})
                continue
            m, per, loi_cham = cham(str(gt_dir), pd, tmp / f"{ten}_lan{lan}_score.json")
            ket_qua[ten]["mIoU"].append(m)
            ket_qua[ten]["per_frame"].append(per)
            print(f"[sweep] lan{lan} {ten:20s} mIoU={m if m is None else round(m, 4)} "
                  f"n={len(per)} ({time.time() - t0:.0f} s){' | ' + ' '.join(loi_cham) if loi_cham else ''}")

    base = "A_hien_tai"
    for ten, _ in CAU_HINH:
        hop_le = [m for m in ket_qua[ten]["mIoU"] if m is not None]
        ket_qua[ten]["mIoU_tb"] = round(statistics.mean(hop_le), 4) if hop_le else None
        ket_qua[ten]["mIoU_std"] = round(statistics.stdev(hop_le), 4) if len(hop_le) > 1 else None
        # chênh lệch CẶP theo frame, gộp mọi vòng
        chenh, cung_dau = [], 0
        for lan, per in enumerate(ket_qua[ten]["per_frame"]):
            b = ket_qua[base]["per_frame"][lan] if lan < len(ket_qua[base]["per_frame"]) else {}
            for f, v in per.items():
                if b.get(f) is not None and v is not None:
                    d = v - b[f]
                    chenh.append(d)
                    cung_dau += 1 if d > 0 else 0
        if ten == base:
            ket_qua[ten]["chenh_tb"] = 0.0
            ket_qua[ten]["chenh_ci95"] = [0.0, 0.0]
            ket_qua[ten]["n_cap"] = len(chenh)
            ket_qua[ten]["so_frame_tot_hon"] = 0
        else:
            lo, hi = ci95_bootstrap(chenh) if chenh else (float("nan"), float("nan"))
            ket_qua[ten]["chenh_tb"] = round(statistics.mean(chenh), 4) if chenh else None
            ket_qua[ten]["chenh_ci95"] = [None if math.isnan(lo) else round(lo, 4),
                                          None if math.isnan(hi) else round(hi, 4)]
            ket_qua[ten]["n_cap"] = len(chenh)
            ket_qua[ten]["so_frame_tot_hon"] = cung_dau

    payload = {
        "git_rev": _git("rev-parse", "--short", "HEAD"),
        "git_dirty_code": bool(_git("status", "--porcelain", "--", ".", ":!data")),
        "lenh": " ".join(sys.argv), "do_luc": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "clip": args.clip, "gt": str(gt_dir.relative_to(REPO_ROOT)), "bbox_xywh": args.bbox,
        "image_size": args.image_size, "rounds": args.rounds,
        "frames_gt": frames, "nguong_nhieu_miou": args.nguong_nhieu,
        "cau_hinh": {k: v for k, v in ket_qua.items()},
    }

    print(f"\n[sweep] {'cấu hình':22s} {'mIoU tb':>8} {'±std':>7} {'Δ cặp':>8} {'CI95':>22} n_cặp")
    for ten, _ in CAU_HINH:
        d = ket_qua[ten]
        tb = "—" if d["mIoU_tb"] is None else f"{d['mIoU_tb']:.4f}"
        sd = "—" if d["mIoU_std"] is None else f"±{d['mIoU_std']:.4f}"
        ch = "—" if d["chenh_tb"] is None else f"{d['chenh_tb']:+.4f}"
        lo, hi = d["chenh_ci95"]
        ci = "—" if lo is None else f"[{lo:+.4f}, {hi:+.4f}]"
        print(f"  {ten:22s} {tb:>8} {sd:>7} {ch:>8} {ci:>22} {d['n_cap']}")

    print(f"[sweep] NGƯỠNG NHIỄU mIoU của clip = {args.nguong_nhieu}: chênh lệch nhỏ hơn ngưỡng ⇒ "
          "phải viết **\"không kết luận được\"**, không được nói \"tốt hơn\".")
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[sweep] {args.out} (git_rev={payload['git_rev']}, "
              f"git_dirty_code={payload['git_dirty_code']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
