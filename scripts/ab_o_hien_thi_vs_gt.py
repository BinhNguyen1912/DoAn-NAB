"""A/B **ô NGƯỜI XEM THẤY vs GT người tô** — phép đo trả lời được `max_mad` (ticket #38).

Vì sao phải có phép đo này (phát hiện 20-11): `mIoU` **không** dùng được để chọn `max_mad` — muốn chấm
mIoU hợp lệ phải chạy `--vos-every 1`, mà cấu hình đó **tắt hẳn LK** ⇒ `max_mad` không tham gia phép đo.
Còn `drift_iou` chỉ nói ô hiển thị có khớp **ô VOS** hay không (độ tự nhất quán), không nói ô đó có đúng
**vật** hay không.

Phép đo ở đây: hộp bao suy từ **mask người tô** (`docs/gt/<tên>`) = vị trí thật của vật; ô mà pipeline
**vẽ lên HUD** ở đúng frame đó (`--dump-shown-csv`) là thứ người xem thấy. `IoU(ô hiển thị, ô GT)` mới là
"ô bám có đúng chỗ không".

Cách chạy được CHÈN KẼ (a,b,a,b,a,b) và đảo thứ tự vòng lẻ — chạy liền 3 lần A rồi 3 lần B thì chênh
lệch nhiệt/cache bị quy oan cho cấu hình (bài học `./run ab`, AGENTS §6).

    python scripts/ab_o_hien_thi_vs_gt.py --gt docs/gt/b1 --clip data/binh1.mp4 \\
        --bbox 300,275,150,410 --lan 3 --max-mad 1.5 6.0

Quy tắc đọc số (giống mọi phép đo khác của repo): chênh lệch **< độ lệch chuẩn giữa các lần chạy** ⇒
viết "không phân biệt được", không viết "tốt hơn". Frame GT **rỗng** (không có vật) ⇒ **không chấm**.
Frame GT có vật mà pipeline không vẽ ô nào ⇒ IoU **0,0** (bám sai thật), KHÔNG phải "không đo được".
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.live_tracking import _bbox_iou                        # noqa: E402

SHOWN_HEADER = ("frame_idx", "x1", "y1", "x2", "y2", "lk_ok")


def hop_tu_gt(gt_dir: Path) -> dict[int, tuple[int, int, int, int]]:
    """`frame → hộp bao (x1,y1,x2,y2)` suy từ mask NGƯỜI tô. Bỏ frame `gt_rong` (không có vật)."""
    import cv2

    index = json.loads((gt_dir / "index.json").read_text(encoding="utf-8"))
    rong = {int(f) for f in (index.get("gt_rong") or [])}
    ra = {}
    for path in sorted(gt_dir.glob("gt_*.png")):
        frame = int(path.stem.split("_")[-1])
        if frame in rong:
            continue
        mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            continue
        ys, xs = (mask > 127).nonzero()
        if len(xs) == 0:      # mask rỗng mà KHÔNG khai `gt_rong`: mâu thuẫn ⇒ bỏ, không chấm bừa
            continue
        ra[frame] = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    return ra


def doc_shown(path: Path) -> dict[int, tuple[tuple[int, int, int, int] | None, bool]]:
    """`frame → (ô hiển thị | None, lk_ok)` từ `--dump-shown-csv`.

    Ô trống (4 cột rỗng) = frame đó **không có ô nào hiển thị** ⇒ `None` (khác `(0,0,0,0)`).
    """
    ra = {}
    if not path.exists():
        return ra
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                frame = int(row["frame_idx"])
            except (KeyError, TypeError, ValueError):
                continue
            try:
                box = tuple(int(row[k]) for k in ("x1", "y1", "x2", "y2"))
            except (KeyError, TypeError, ValueError):
                box = None
            # Cho phép hộp MỎNG 1 px (`x1 == x2`): repo coi đó là vật thật ở xa (xem
            # `_bbox_hop_le`); chỉ hộp ĐẢO toạ độ mới là không dùng được.
            if box is not None and (box[2] < box[0] or box[3] < box[1] or box[0] < 0 or box[1] < 0):
                box = None
            ra[frame] = (box, str(row.get("lk_ok", "")).strip() == "1")
    return ra


def cham(hop_gt: dict, shown: dict) -> dict:
    """Chấm `IoU(ô hiển thị, ô GT)`. Hàm THUẦN (test được, không cần video/model).

    Ba ca phải tách:
      - GT có vật, **không có ô hiển thị** ⇒ `iou = 0.0` (bám sai thật) — KHÔNG bỏ mẫu;
      - GT có vật, có ô nhưng suy biến ⇒ `None` + đếm `khong_do_duoc` (không quy thành 0);
      - frame GT có vật **không xuất hiện** trong CSV ⇒ `thieu_frame` (chưa chạy tới frame đó).
    """
    theo_frame, thieu = [], []
    for frame, gt in sorted(hop_gt.items()):
        if frame not in shown:
            thieu.append(frame)
            continue
        box, lk_ok = shown[frame]
        if box is None:
            theo_frame.append({"frame_idx": frame, "iou": 0.0, "lk_ok": lk_ok,
                               "vi_sao": "không có ô hiển thị ⇒ 0,0 (bám sai thật)"})
            continue
        iou = _bbox_iou(box, gt)
        if iou is None:
            theo_frame.append({"frame_idx": frame, "iou": None, "lk_ok": lk_ok,
                               "vi_sao": "ô suy biến ⇒ không đo được"})
            continue
        theo_frame.append({"frame_idx": frame, "iou": round(float(iou), 4), "lk_ok": lk_ok,
                           "hop": list(box), "hop_gt": list(gt)})
    do_duoc = [r["iou"] for r in theo_frame if r["iou"] is not None]
    return {
        "n_gt_co_vat": len(hop_gt),
        "n_cham": len(do_duoc),
        "thieu_frame": thieu,
        "iou_mean": round(statistics.fmean(do_duoc), 4) if do_duoc else None,
        "iou_min": round(min(do_duoc), 4) if do_duoc else None,
        "lk_ok_frac": (round(sum(1 for r in theo_frame if r["lk_ok"]) / len(theo_frame), 3)
                       if theo_frame else None),
        "theo_frame": theo_frame,
    }


def _python() -> str:
    return sys.executable or "python3"


def chay_mot_lan(*, clip: str, bbox: str, image_size: int | None, vos_every: int,
                 max_mad: float, frames: int, out_dir: Path) -> dict:
    lenh = [_python(), str(REPO_ROOT / "tools" / "live_worker.py"),
            "--source", clip, "--out-dir", str(out_dir),
            "--vos-every", str(vos_every), "--stop-after-frames", str(frames),
            "--lk-max-mad", str(max_mad), "--bbox", bbox,
            "--dump-shown-csv", str(out_dir / "shown.csv")]
    if image_size is not None:
        lenh += ["--image-size", str(image_size)]
    subprocess.run(lenh, cwd=str(REPO_ROOT), check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    status_path = out_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    return {"status": status, "shown": out_dir / "shown.csv", "lenh": " ".join(lenh)}


def tong_hop(lan: list[dict]) -> dict:
    """Trung bình ± độ lệch chuẩn qua các lần chạy của CÙNG cấu hình."""
    def _stats(values):
        v = [x for x in values if x is not None]
        if not v:
            return {"mean": None, "std": None, "n": 0}
        return {"mean": round(statistics.fmean(v), 4),
                "std": round(statistics.stdev(v), 4) if len(v) > 1 else None, "n": len(v)}

    return {
        "iou_mean": _stats([r["cham"]["iou_mean"] for r in lan]),
        "iou_min": _stats([r["cham"]["iou_min"] for r in lan]),
        "lk_ok_frac": _stats([r["cham"]["lk_ok_frac"] for r in lan]),
        "n_cham": _stats([r["cham"]["n_cham"] for r in lan]),
        "measured_fps": _stats([r["status"].get("measured_fps") for r in lan]),
    }


def so_sanh(a: dict, b: dict) -> dict:
    """So hai cấu hình bằng SỐ, dùng ngưỡng nhiễu = độ lệch chuẩn lớn hơn của hai bên.

    Hàm THUẦN. Chênh lệch nhỏ hơn ngưỡng ⇒ "không phân biệt được" (AGENTS §6), không viết "tốt hơn".
    """
    a_mean, b_mean = a["iou_mean"]["mean"], b["iou_mean"]["mean"]
    if a_mean is None or b_mean is None:
        return {"ket_luan": "KHÔNG kết luận: một bên không chấm được frame nào"}
    chenh = round(b_mean - a_mean, 4)
    nhieu = max(float(a["iou_mean"]["std"] or 0.0), float(b["iou_mean"]["std"] or 0.0))
    phan_biet = abs(chenh) > nhieu
    return {
        "chenh_iou": chenh,
        "nguong_nhieu": round(nhieu, 4),
        "phan_biet_duoc": phan_biet,
        "ket_luan": (f"ô hiển thị {'TỐT HƠN' if chenh > 0 else 'TỆ HƠN'} {abs(chenh):.3f} IoU "
                     f"(> ngưỡng nhiễu {nhieu:.3f})" if phan_biet else
                     f"KHÔNG phân biệt được (chênh {chenh:+.3f} ≤ ngưỡng nhiễu {nhieu:.3f})"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gt", required=True, help="thư mục GT (docs/gt/<tên>, có index.json)")
    parser.add_argument("--clip", required=True)
    parser.add_argument("--bbox", required=True, help='"x,y,w,h" (như bbox.json/UI)')
    parser.add_argument("--image-size", type=int, default=192)
    parser.add_argument("--vos-every", type=int, default=3)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--lan", type=int, default=3, help="số lần/cấu hình (chèn kẽ; <2 không kết luận)")
    parser.add_argument("--max-mad", type=float, nargs="+", default=[1.5, 6.0])
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    hop_gt = hop_tu_gt(Path(args.gt))
    if not hop_gt:
        raise SystemExit(f"[LOI] {args.gt} không có frame nào có vật (toàn `gt_rong`?)")
    if args.lan < 2:
        print("[CANH BAO] --lan < 2 ⇒ chưa có ngưỡng nhiễu, KHÔNG được kết luận cấu hình nào tốt hơn")

    theo_cau_hinh: dict[float, list] = {m: [] for m in args.max_mad}
    for vong in range(args.lan):
        thu_tu = list(args.max_mad)
        if vong % 2 == 1:                       # đảo chiều vòng lẻ: "chạy sau" không luôn là cấu hình ưu ái
            thu_tu.reverse()
        for max_mad in thu_tu:
            with tempfile.TemporaryDirectory(prefix=f"ab_o_{max_mad}_", dir="/dev/shm") as tmp:
                res = chay_mot_lan(clip=args.clip, bbox=args.bbox, image_size=args.image_size,
                                   vos_every=args.vos_every, max_mad=max_mad,
                                   frames=args.frames, out_dir=Path(tmp))
                res["cham"] = cham(hop_gt, doc_shown(res["shown"]))
                res["max_mad_yeu_cau"] = max_mad
                res["max_mad_hieu_luc"] = ((res["status"].get("cau_hinh") or {}).get("lk_max_mad"))
                res["shown"] = str(res["shown"])
            theo_cau_hinh[max_mad].append(res)
            c = res["cham"]
            print(f"vòng {vong + 1} · max_mad {max_mad} → IoU(ô hiển thị, ô GT) {c['iou_mean']} "
                  f"(tệ nhất {c['iou_min']}) trên {c['n_cham']}/{c['n_gt_co_vat']} frame · "
                  f"lk_ok {c['lk_ok_frac']} · hiệu lực {res['max_mad_hieu_luc']}")

    tong = {str(m): tong_hop(v) for m, v in theo_cau_hinh.items()}
    lech = [r for v in theo_cau_hinh.values() for r in v
            if r["max_mad_hieu_luc"] is None
            or abs(float(r["max_mad_hieu_luc"]) - float(r["max_mad_yeu_cau"])) > 1e-9]
    khoa = sorted(tong, key=float)
    ss = so_sanh(tong[khoa[0]], tong[khoa[-1]]) if len(khoa) >= 2 else {}

    from scripts.measure_watchdog import _git_provenance

    rev, dirty, dirty_code, loi = _git_provenance()
    artifact = {
        "git_rev": rev, "git_dirty": dirty, "git_dirty_code": dirty_code, "git_loi": loi,
        "do_luc": datetime.now().isoformat(timespec="seconds"),
        "lenh": " ".join(["python scripts/ab_o_hien_thi_vs_gt.py"] + (argv or sys.argv[1:])),
        "nguon_so": {"gt": args.gt, "clip": args.clip, "bbox": args.bbox,
                     "image_size": args.image_size, "vos_every": args.vos_every,
                     "frames": args.frames, "lan": args.lan,
                     "frame_gt_co_vat": sorted(hop_gt)},
        "dinh_nghia": ("IoU(ô bao ĐANG HIỂN THỊ ở frame đó, hộp bao suy từ mask NGƯỜI tô). GT có vật "
                       "mà không vẽ ô nào ⇒ 0,0 (bám sai thật), KHÔNG phải 'không đo được'. Đây là "
                       "phép đo 'ô bám đúng chỗ không' — khác `drift_iou` (khớp ô VOS) và khác mIoU "
                       "(mask vs GT, chỉ chạy được với vos_every=1 nên không thấy LK)."),
        "cau_hinh_hieu_luc_lech": lech,
        "tong_hop": tong,
        "so_sanh": ss,
        "lan_chay": {str(m): [{k: v for k, v in r.items() if k != "status"} for r in rs]
                     for m, rs in theo_cau_hinh.items()},
    }
    out = Path(args.out) if args.out else REPO_ROOT / "data" / (
        f"ab_o_hien_thi_vs_gt_{datetime.now():%Y-%m-%d}_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{json.dumps(ss, ensure_ascii=False)}")
    print(f"Ghi: {out}")
    if lech:
        print(f"[LOI] {len(lech)} lần chạy có lk_max_mad hiệu lực KHÁC yêu cầu", file=sys.stderr)
        return 1
    if loi:
        print(f"[LOI] không lấy được provenance: {loi}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
