"""
A/B: **điểm prompt ÂM** có thật sự chữa "bám tràn ra nền cùng tông" không?

Vì sao phải đo: ngày 21-11 ca thật — vật be trơn bị bám sang **cửa/tường be cùng tông**; đo mask-cos
vùng sai 0,752–0,989 vs ca đúng 0,905 ⇒ KHÔNG có ngưỡng cos nào tách được (AGENTS §6) ⇒ hướng chữa
được chọn là cho người dùng đặt **điểm âm**. Nhưng "chọn hướng" không phải "đã chứng minh": phải có
số mIoU TRƯỚC/SAU trên cùng clip, cùng ô chọn, cùng bộ frame.

Thiết kế (không dùng GT để chọn điểm — nếu lấy GT để quyết định đặt điểm ở đâu thì con số là tự khen):
- **A (nền)**: chỉ `bbox`, không điểm nào.
- **B (có điểm âm)**: `bbox` + 4 điểm ÂM ở **ngay ngoài 4 cạnh** của ô (cùng ý tưởng
  `src.geometry_guard.generate_contrast_points`, nhưng BỎ điểm dương ở tâm để cô lập tác dụng của
  điểm âm). Đây đúng là thao tác người dùng làm được khi nhìn thấy nền lọt vào ô.

Cách chạy (CPU):
    python scripts/ab_diem_am.py --sizes 192,512 --device cpu

Đọc kết quả: `scripts/paired_miou.py` in chênh lệch THEO CẶP từng frame (cùng frame, hai biến thể)
kèm CI95 + sign test — cách duy nhất được phép tuyên bố khi chưa có ngưỡng nhiễu mIoU.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.bench_gpu_binh2 import (  # noqa: E402
    GT_DIRS,
    _frames_cua_gt,
    _o_chon_tu_gt,
    _provenance,
    _so_frame_cua_clip,
)
from scripts.paired_miou import so_sanh  # noqa: E402
from scripts.score_miou import cham  # noqa: E402


def mo_rong(bbox_xywh, frame_wh, he_so: float = 1.3):
    """Nới ô ra `he_so` lần mỗi chiều ⇒ mô phỏng ĐÚNG lỗi người dùng: kéo ô rộng tay, bao cả nền."""
    x, y, w, h = bbox_xywh
    W, H = frame_wh
    mx, my = (w * (he_so - 1)) / 2, (h * (he_so - 1)) / 2
    x1, y1 = max(0, int(round(x - mx))), max(0, int(round(y - my)))
    x2, y2 = min(W - 1, int(round(x + w + mx))), min(H - 1, int(round(y + h + my)))
    return (x1, y1, x2 - x1, y2 - y1)


def diem_am(bbox_xywh, frame_wh, *, margin_frac: float = 0.15):
    """4 điểm ÂM ngay NGOÀI 4 cạnh của ô (bỏ điểm nào rơi ra ngoài khung)."""
    x, y, w, h = bbox_xywh
    W, H = frame_wh
    x1, y1, x2, y2 = x, y, x + w, y + h
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    m = max(4.0, min(w, h) * margin_frac)
    ung_vien = [
        (cx, y1 - m),        # trên
        (cx, y2 + m),        # dưới
        (x1 - m, cy),        # trái
        (x2 + m, cy),        # phải
    ]
    ra = []
    for px, py in ung_vien:
        if 0 <= px <= W - 1 and 0 <= py <= H - 1 and (px < x1 or px > x2 or py < y1 or py > y2):
            ra.append((float(px), float(py)))
    return ra


def chay_mot_bien_the(*, clip: Path, out: Path, masks: Path, bbox, frames, size: int,
                      device: str, points, stop_after: int) -> dict:
    masks.mkdir(parents=True, exist_ok=True)
    for f in masks.glob("mask_*.png"):
        f.unlink()
    # Worker CLI chỉ đọc `bbox.json`; điểm prompt đi qua CHÍNH file đó (đúng đường API dùng) —
    # nhờ vậy A/B đo đúng cơ chế thật, không phải một nhánh code riêng của script này.
    du_lieu = {"x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3]}
    if points:
        du_lieu["points"] = [[float(p[0]), float(p[1])] for p in points]
        du_lieu["labels"] = [0] * len(points)
    out.mkdir(parents=True, exist_ok=True)
    (out / "bbox.json").write_text(json.dumps(du_lieu), encoding="utf-8")

    argv = [sys.executable, "-u", str(_REPO / "tools" / "live_worker.py"),
            "--source", str(clip), "--out-dir", str(out),
            "--image-size", str(size), "--vos-every", "1", "--device", device,
            "--dump-mask-frames", ",".join(str(i) for i in frames),
            "--dump-mask-dir", str(masks),
            "--stop-after-frames", str(stop_after), "--max-fps", "1000"]
    proc = subprocess.run(argv, cwd=_REPO, capture_output=True, text=True, timeout=1800)
    log = ((proc.stdout or "") + (proc.stderr or ""))[-4000:]
    (out / "worker.log").write_text(log, encoding="utf-8")
    status_p = out / "status.json"
    status = json.loads(status_p.read_text(encoding="utf-8")) if status_p.is_file() else {}
    if proc.returncode != 0 or status.get("state") == "error":
        return {"loi": status.get("message") or log[-500:], "ma_thoat": proc.returncode}

    chi_tiet = {}
    for d in GT_DIRS:
        gt = _REPO / d
        if not (gt / "index.json").is_file():
            continue
        idx = {int(it["frame_idx"])
               for it in json.loads((gt / "index.json").read_text(encoding="utf-8"))["frames"]}
        item = [{"frame_idx": i, "pred_path": str(masks / f"mask_{i:06d}.png")}
                for i in frames if i in idx]
        kq = cham(item, gt)
        chi_tiet[Path(d).name] = {"mIoU": kq["mIoU"], "n_cham": kq["n_cham"],
                                  "mask_ngoai_gt_mean": kq["mask_ngoai_gt_mean"],
                                  "frames": kq["frames"]}
    cau_hinh = status.get("cau_hinh") or {}
    return {
        "image_size": size, "device": device,
        "image_size_hieu_luc": cau_hinh.get("image_size_hieu_luc"),
        "frames_phat": status.get("frames"), "vos_fps": status.get("vos_fps"),
        "mIoU": {k: v["mIoU"] for k, v in chi_tiet.items()},
        "n_cham": {k: v["n_cham"] for k, v in chi_tiet.items()},
        "chi_tiet": chi_tiet,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A/B điểm prompt ÂM: mIoU trước/sau trên cùng clip")
    ap.add_argument("--clip", default="data/binh2.mp4")
    ap.add_argument("--sizes", default="192,512")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default="")
    ap.add_argument("--mo-rong", type=float, default=1.3,
                    help="hệ số nới ô để mô phỏng 'chọn ô rộng tay bao cả nền' (1.0 = tắt)")
    args = ap.parse_args(argv)

    clip = Path(args.clip)
    clip = clip if clip.is_absolute() else _REPO / clip
    if not clip.is_file():
        print(f"[loi] không có clip {clip}")
        return 2
    gt_dirs = [(_REPO / d) for d in GT_DIRS if (_REPO / d / "index.json").is_file()]
    co_vat, gt_rong = _frames_cua_gt(gt_dirs)
    frames = sorted(set(co_vat) | set(gt_rong))
    bbox = _o_chon_tu_gt(gt_dirs[0])

    import cv2
    cap = cv2.VideoCapture(str(clip))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    pts = diem_am(bbox, (W, H))
    # Ba biến thể: (1) ô ĐÚNG, (2) ô RỘNG (bao cả nền) không điểm, (3) ô RỘNG + điểm âm đặt ở VÀNH
    # giữa ô rộng và vật — đúng thao tác người dùng làm khi thấy nền lọt vào ô.
    bbox_rong = mo_rong(bbox, (W, H), args.mo_rong) if args.mo_rong > 1.0 else bbox
    pts_rong = diem_am(bbox_rong, (W, H), margin_frac=0.04) if bbox_rong != bbox else pts
    pts_rong = [p for p in pts_rong
                if not (bbox[0] <= p[0] <= bbox[0] + bbox[2]
                        and bbox[1] <= p[1] <= bbox[1] + bbox[3])]
    stop_after = _so_frame_cua_clip(clip)
    print(f"[ab] ô đúng {bbox} · ô rộng {bbox_rong} · {len(frames)} frame GT")
    print(f"[ab] điểm âm quanh ô đúng: {pts}")
    print(f"[ab] điểm âm trong ô RỘNG (ngoài vật): {pts_rong}")

    ket_qua = []
    for size in [int(s) for s in args.sizes.split(",") if s.strip()]:
        dong = {}
        bien_the = [("o_dung", bbox, None), ("o_rong", bbox_rong, None),
                    ("o_rong_co_am", bbox_rong, pts_rong)]
        for ten, o, diem in bien_the:
            print(f"[ab] image_size={size} · {ten} …", flush=True)
            out = _REPO / "data" / f"_ab_{args.device}_{size}_{ten}"
            dong[ten] = chay_mot_bien_the(
                clip=clip, out=out, masks=out / "masks", bbox=o, frames=frames,
                size=size, device=args.device, points=diem, stop_after=stop_after)
            if "loi" in dong[ten]:
                print(f"   LỖI: {dong[ten]['loi']}")
            else:
                print(f"   mIoU: {dong[ten]['mIoU']}")
        ket_qua.append({"image_size": size, "o_chon": {"o_dung": list(bbox),
                                                      "o_rong": list(bbox_rong)}, **dong})

    out_json = Path(args.out) if args.out else (
        _REPO / "data" / f"ab_diem_am_{datetime.now():%Y-%m-%d}_metrics.json")
    payload = {**_provenance(), "do_luc": datetime.now().isoformat(timespec="seconds"),
               "lenh": " ".join([Path(sys.executable).name, "scripts/ab_diem_am.py", *sys.argv[1:]]),
               "clip": str(args.clip), "o_chon_xywh": list(bbox),
               "diem_am": [list(p) for p in pts], "frames_gt": frames,
               "ket_qua": ket_qua,
               "dinh_nghia": "mIoU = IoU(mask, GT silhouette) trên frame GT CÓ vật; điểm âm đặt NGOÀI "
                             "4 cạnh ô, sinh từ HÌNH HỌC (không dùng GT)."}
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[ab] {out_json}")

    def _bang(nhan_a, nhan_b, khoa_a, khoa_b):
        print(f"\n== {nhan_a} → {nhan_b} (so cặp theo frame) ==")
        for khoi in ket_qua:
            a, b = khoi.get(khoa_a), khoi.get(khoa_b)
            if not a or not b or "loi" in a or "loi" in b:
                print(f"{khoi['image_size']:>6}  LỖI/thiếu dữ liệu")
                continue
            for gt in (a.get("chi_tiet") or {}):
                if gt not in (b.get("chi_tiet") or {}):
                    continue
                r = so_sanh({"image_size": a["image_size"],
                             "chi_tiet": {gt: a["chi_tiet"][gt]}},
                            {"image_size": b["image_size"],
                             "chi_tiet": {gt: b["chi_tiet"][gt]}}, gt)
                if not r["n"]:
                    continue
                ci = f"[{r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}]"
                print(f"{khoi['image_size']:>6} {gt:<11} A={a['mIoU'].get(gt)} B={b['mIoU'].get(gt)} "
                      f"n={r['n']} B>A {r['so_duong']}/{r['n']} mean {r['mean']:+.4f} "
                      f"CI95 {ci} p={r['p_sign']:.4f}")

    _bang("ô ĐÚNG", "ô RỘNG (không điểm)", "o_dung", "o_rong")
    _bang("ô RỘNG", "ô RỘNG + điểm âm", "o_rong", "o_rong_co_am")
    print("\nĐọc cho đúng: CI95 bắc qua 0 ⇒ KHÔNG kết luận được. n nhỏ (mỗi GT vài frame) ⇒ p chỉ là "
          "chỉ báo. Muốn chắc: lặp 3 lần/cấu hình hoặc tô thêm frame GT.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
