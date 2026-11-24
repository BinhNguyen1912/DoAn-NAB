"""Đo **nhiễu của chính GT** (người tô 2 lần, cùng frame) — để biết chênh mIoU nào là thật.

Vì sao có script này (plan `docs/plan/24-11-2026-bam-bat-vat-bat-ky-duong-b.md`, việc P1-b):

Mọi con số "chất lượng" của đồ án là **mIoU mask vs GT người tô**. Nhưng GT do con người vẽ nên nó có
sai số của riêng nó. Nếu người tô lại **cùng một frame** mà hai lần chỉ khớp nhau ở `IoU = 0,85` thì mọi
chênh lệch mIoU **nhỏ hơn 1 − 0,85 = 0,15** giữa hai cấu hình đều **không kết luận được** — chúng nằm
trong sai số của thước đo, không phải trong hành vi của model.

Repo **chưa từng đo** đại lượng này (AGENTS §6 chỉ có ngưỡng nhiễu cho `drift_iou`/`vos_fps`/`mask_age`).
Hệ quả đã gặp: 0,6987 (@192) vs 0,7268 (@320) được tranh luận như "320 tốt hơn/không", trong khi cả hai
chênh lệch 0,028 < ngưỡng nhiễu của chính GT.

Cách dùng:
    python scripts/gt_noise.py --a docs/gt/tran_nen --b docs/gt/tran_nen_lan2 \
        --out data/gt_noise_2026-11-24_metrics.json

Quy tắc đọc (đăng ký TRƯỚC khi đo, ghi vào artifact):
  - `IoU_GT_mean` = độ khớp trung bình giữa 2 lần tô CÙNG frame.
  - `nguong_khong_ket_luan` = 1 − `IoU_GT_mean`. Chênh mIoU < ngưỡng này ⇒ viết **"không kết luận"**.
  - Đây là nhiễu **intra-labeler** (một người tô 2 lần). Nhiễu **inter-labeler** (2 người khác nhau)
    thường LỚN HƠN ⇒ con số này là **cận dưới** của sai số GT, phải nói rõ khi trích.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.score_miou import doc_mask  # noqa: E402


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=10,
                              cwd=Path(__file__).resolve().parent.parent).stdout.strip()
    except Exception:
        return ""


def _dirty_code() -> tuple[bool, bool]:
    """`(dirty, dirty_code)` — `dirty_code` bỏ qua `data/` (luật AGENTS §6)."""
    out = _git("status", "--porcelain")
    dirty = bool(out)
    code = [ln for ln in out.splitlines() if not ln[3:].startswith("data/")]
    return dirty, bool(code)


def _frames_cua(gt_dir: Path) -> dict[int, Path]:
    ra: dict[int, Path] = {}
    for p in sorted(gt_dir.glob("gt_*.png")):
        try:
            ra[int(p.stem.split("_")[-1])] = p
        except ValueError:
            continue
    return ra


def do(a_dir: Path, b_dir: Path) -> dict:
    a, b = _frames_cua(a_dir), _frames_cua(b_dir)
    chung = sorted(set(a) & set(b))
    dong = []
    for f in chung:
        ma, mb = doc_mask(a[f]), doc_mask(b[f])
        if ma.shape != mb.shape:
            dong.append({"frame_idx": f, "loi": f"kích thước lệch: {ma.shape} vs {mb.shape}"})
            continue
        uni = int((ma | mb).sum())
        inter = int((ma & mb).sum())
        # GT rỗng ở CẢ HAI lần: không có gì để đo (KHÔNG được ghi IoU = 1,0 — bẫy `IoU(rỗng,rỗng)=1`)
        dong.append({
            "frame_idx": f,
            "iou": None if uni == 0 else round(inter / uni, 4),
            "px_a": int(ma.sum()), "px_b": int(mb.sum()),
            "px_chi_a": int((ma & ~mb).sum()), "px_chi_b": int((mb & ~ma).sum()),
            "gt_rong_ca_hai": uni == 0,
        })
    co_iou = [d["iou"] for d in dong if d.get("iou") is not None]
    mean = None if not co_iou else float(np.mean(co_iou))
    return {
        "schema": 1,
        "do_luc": _dt.datetime.now().isoformat(timespec="seconds"),
        "git_rev": _git("rev-parse", "HEAD"),
        "git_dirty": _dirty_code()[0],
        "git_dirty_code": _dirty_code()[1],
        "lenh": f"--a {a_dir} --b {b_dir}",
        "gt_a": str(a_dir), "gt_b": str(b_dir),
        "n_frame_chung": len(co_iou),
        "frame_chi_co_a": sorted(set(a) - set(b)),
        "frame_chi_co_b": sorted(set(b) - set(a)),
        "dao_gt": "intra_labeler",        # một người tô 2 lần ⇒ CẬN DƯỚI của sai số GT
        "ket_qua": {
            "ioU_GT_mean": None if mean is None else round(mean, 4),
            "ioU_GT_min": None if not co_iou else round(float(min(co_iou)), 4),
            "ioU_GT_max": None if not co_iou else round(float(max(co_iou)), 4),
            # Đăng ký TRƯỚC: đây là ngưỡng để MỌI so sánh mIoU phải vượt qua mới được gọi là khác biệt.
            "nguong_khong_ket_luan": None if mean is None else round(1.0 - mean, 4),
            "n": len(co_iou),
            "frames": dong,
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Đo nhiễu GT (IoU giữa 2 lần tô cùng frame).")
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    payload = do(Path(args.a), Path(args.b))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    kq = payload["ket_qua"]
    if kq["ioU_GT_mean"] is None:
        print("[gt_noise] KHÔNG có frame chung nào có vật ⇒ chưa đo được (KHÔNG phải 0)")
        return 2
    print(f"[gt_noise] IoU(GT,GT) = {kq['ioU_GT_mean']:.4f} (min {kq['ioU_GT_min']:.4f}, "
          f"max {kq['ioU_GT_max']:.4f}, n={kq['n']})")
    print(f"[gt_noise] ngưỡng 'không kết luận' cho mọi chênh mIoU = {kq['nguong_khong_ket_luan']:.4f}")
    for d in kq["frames"]:
        if d.get("iou") is not None:
            print(f"  f{d['frame_idx']:3d}: IoU {d['iou']:.4f} | px A {d['px_a']} · B {d['px_b']} "
                  f"| chỉ A {d['px_chi_a']} · chỉ B {d['px_chi_b']}")
    print(f"[gt_noise] ghi: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
