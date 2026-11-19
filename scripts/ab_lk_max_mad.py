"""A/B LIVE cửa chống-trôi LK (`--lk-max-mad`) trên ≥2 clip — bước chốt của ticket #38.

Vì sao không sửa `LightTracker`/`DEFAULT_MAX_MAD`: đo offline 19-11 (`scripts/do_thu_lk.py`) cho thấy
1,5 px chặn LK quá mức, nhưng phép đo đó là **một bước nhảy ~3 frame** và mốc so là **ô VOS**. Đường
live đi **chuỗi** update 1 frame/bước, và ô hiển thị còn qua `_interp` — hai thứ offline không tái tạo.
Đổi mặc định mà không có số live + ảnh kiểm là đúng thứ AGENTS §6 cấm.

Cách chạy: KHÔNG dùng API (API chưa có trường cho cờ này ⇒ nó là dụng cụ ĐO, không phải tính năng của
hợp đồng HTTP). Chạy thẳng `tools/live_worker.py`, mỗi lần một phiên ngắn, đọc `drift_samples.csv` +
`status.json` do chính phiên ghi.

Các lần chạy được CHÈN KẼ (`a,b,a,b,a,b`) chứ không chạy liền từng cấu hình: nhiệt máy / cache / tải
nền đổi dần theo phiên, chạy liền 3 lần A rồi 3 lần B thì chênh lệch phiên bị quy oan cho cấu hình
(bài học `./run ab`, AGENTS §6).

Chỉ số so sánh (`--frame-window` để chỉ tính lúc vật còn trong khung):

- `lk_ok_frac` — tỉ lệ mẫu VOS mà LK dám nhận (mẫu số = số dòng CÓ `lk_ok`, không phải tổng số dòng);
- `drift_iou` trung bình + `stability` nếu có;
- `empty_frac` — tỉ lệ mask rỗng (để phát hiện cấu hình làm model "tưởng tượng" ít/nhiều hơn);
- `measured_fps`, `vos_fps`, `mask_age_p95` (cấu hình không được làm chậm phiên).

Kết luận chỉ được viết "tốt hơn" khi chênh > ngưỡng nhiễu: `drift_iou` ±0,010 cho ô chai (55 s),
`lk_ok_frac` phải tăng ≥ 2× mới đáng đổi mặc định (ticket #38).
"""

from __future__ import annotations

import argparse
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

NGUONG_DRIFT = 0.010          # ngưỡng nhiễu `drift_iou` cho ô CHAI (55 s) — AGENTS §6
NGUONG_TOI_THIEU_LK = 2.0     # `lk_ok_frac` phải tăng ≥ 2× mới đáng đổi mặc định (ticket #38)


def _python() -> str:
    return sys.executable or "python3"


def chay_mot_lan(*, source: str, bbox: str, image_size: int | None, vos_every: int,
                 lk_max_mad: float, frames: int, out_dir: Path) -> dict:
    """Chạy MỘT phiên worker rồi trả `status.json` đã parse (kèm đường dẫn CSV)."""
    lenh = [_python(), str(REPO_ROOT / "tools" / "live_worker.py"),
            "--source", source, "--out-dir", str(out_dir),
            "--vos-every", str(vos_every), "--stop-after-frames", str(frames),
            "--lk-max-mad", str(lk_max_mad), "--bbox", bbox]
    if image_size is not None:
        lenh += ["--image-size", str(image_size)]
    subprocess.run(lenh, cwd=str(REPO_ROOT), check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    status_path = out_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    return {"status": status, "csv": str(out_dir / "drift_samples.csv"),
            "lenh": " ".join(lenh)}


def doc_csv(path: str, *, khung: list[tuple[int, int]] | None = None) -> dict:
    """Gộp số từ `drift_samples.csv`. Hàm THUẦN (test được, không cần model).

    `lk_ok_frac` tính trên **mẫu số là số dòng CÓ `lk_ok`** — không phải tổng số dòng. Trộn hai thứ đó
    từng làm báo cáo sai (32/83 dòng trống `lk_ok` vì frame chưa từng phát; review 19-11).
    """
    import csv as _csv

    rows = []
    p = Path(path)
    if p.exists():
        with p.open(encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                try:
                    frame = int(row["frame_idx"])
                except (KeyError, TypeError, ValueError):
                    continue
                if khung and not any(a <= frame <= c for a, c in khung):
                    continue
                rows.append(row)
    lk = [r["lk_ok"] for r in rows if (r.get("lk_ok") or "").strip() != ""]
    lk_ok = [v for v in lk if v.strip() == "1"]
    empty = [r.get("empty") for r in rows if (r.get("empty") or "").strip() != ""]
    drift = []
    for r in rows:
        try:
            drift.append(float(r["drift_iou"]))
        except (KeyError, TypeError, ValueError):
            continue
    return {
        "n_dong": len(rows),
        "n_lk_do_duoc": len(lk),
        "lk_ok_n": len(lk_ok),
        "lk_ok_frac": round(len(lk_ok) / len(lk), 3) if lk else None,
        "n_empty_do_duoc": len(empty),
        "empty_frac": round(sum(1 for v in empty if v.strip() == "1") / len(empty), 3) if empty else None,
        "drift_n": len(drift),
        "drift_iou": round(statistics.fmean(drift), 4) if drift else None,
    }


def tong_hop(lan: list[dict]) -> dict:
    """Trung bình ± độ lệch chuẩn qua các lần chạy (mẫu) của CÙNG một cấu hình."""
    def _stats(values):
        v = [x for x in values if x is not None]
        if not v:
            return {"mean": None, "std": None, "n": 0}
        return {"mean": round(statistics.fmean(v), 4),
                "std": round(statistics.stdev(v), 4) if len(v) > 1 else None, "n": len(v)}

    return {
        "lk_ok_frac": _stats([x["csv"]["lk_ok_frac"] for x in lan]),
        "drift_iou": _stats([x["csv"]["drift_iou"] for x in lan]),
        "empty_frac": _stats([x["csv"]["empty_frac"] for x in lan]),
        "measured_fps": _stats([(x["status"].get("stats") or {}).get("measured_fps") for x in lan]),
        "vos_fps": _stats([(x["status"].get("stats") or {}).get("vos_fps") for x in lan]),
        "mask_age_p95": _stats([(x["status"].get("stats") or {}).get("mask_age_p95") for x in lan]),
    }


def ket_luan(a: dict, b: dict, *, nguong_drift: float = NGUONG_DRIFT) -> dict:
    """So hai cấu hình bằng số, KHÔNG bằng cảm giác. Hàm THUẦN.

    Quy ước của repo: chênh lệch < ngưỡng nhiễu ⇒ viết **"không phân biệt được"**, không viết "tốt hơn".
    """
    def _mean(x, key):
        return ((x.get(key) or {}).get("mean"))

    a_lk, b_lk = _mean(a, "lk_ok_frac"), _mean(b, "lk_ok_frac")
    a_dr, b_dr = _mean(a, "drift_iou"), _mean(b, "drift_iou")
    # `a = 0` là trường hợp MẠNH NHẤT (LK chưa từng nhận), không phải "không so được": ghi "inf" thay
    # vì `None` để không bị đọc thành "thiếu dữ liệu". `float("inf")` không JSON-hoá được nên dùng chuỗi.
    if a_lk is None or b_lk is None:
        tang_lk = None
    elif a_lk == 0:
        tang_lk = "inf" if b_lk > 0 else 1.0
    else:
        tang_lk = round(b_lk / a_lk, 2)
    du_lk = tang_lk == "inf" or (isinstance(tang_lk, float) and tang_lk >= NGUONG_TOI_THIEU_LK)
    chenh_dr = None if (a_dr is None or b_dr is None) else round(b_dr - a_dr, 4)
    # `drift_iou` TĂNG = ô hiển thị gần ô VOS kế tiếp hơn = TỐT. Cổng nhiễu chỉ được chặn chiều
    # GIẢM: bản đầu mình dùng `abs(chenh) <= nguong` nên coi cả cải thiện là "không đủ điều kiện" —
    # luật ill-posed, đúng loại lỗi "cổng danh nghĩa" (review nội bộ 19-11).
    du = bool(du_lk and chenh_dr is not None and chenh_dr >= -nguong_drift)
    return {
        "lk_ok_frac_tang_lan": tang_lk,
        "drift_iou_chenh": chenh_dr,
        "nguong_drift": nguong_drift,
        "nguong_lk_toi_thieu": NGUONG_TOI_THIEU_LK,
        "drift_khong_phan_biet_duoc": None if chenh_dr is None else abs(chenh_dr) <= nguong_drift,
        "drift_khong_te_di": None if chenh_dr is None else chenh_dr >= -nguong_drift,
        "du_dieu_kien_doi_mac_dinh": du,
        "ket_luan": (
            "ĐỦ điều kiện đổi mặc định (vẫn cần kiểm ảnh ô bao không trôi vào nền)" if du
            else "KHÔNG đủ điều kiện đổi mặc định ⇒ hoặc ẩn ô cũ giữa hai lần VOS, hoặc đo lại"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", action="append", required=True,
                        help="clip nguồn (lặp được — ticket #38 cần ≥ 2 clip)")
    parser.add_argument("--bbox", action="append", required=True,
                        help='ô chọn "x,y,w,h" (lặp được, ghép theo thứ tự với --source)')
    parser.add_argument("--image-size", type=int, default=192)
    parser.add_argument("--vos-every", type=int, default=3)
    parser.add_argument("--frames", type=int, default=180, help="số frame mỗi lần chạy")
    parser.add_argument("--lan", type=int, default=3, help="số lần/cấu hình (chèn kẽ; <2 không kết luận)")
    parser.add_argument("--max-mad", type=float, nargs="+", default=[1.5, 6.0])
    parser.add_argument("--frame-window", default="", metavar="dau:cuoi[,dau:cuoi]",
                        help="chỉ tính mẫu trong khung vật còn trong hình")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    if len(args.source) != len(args.bbox):
        raise SystemExit("--source và --bbox phải cùng số lượng (ghép theo thứ tự)")
    if args.lan < 2:
        print("[CANH BAO] --lan < 2: chưa có ngưỡng nhiễu, KHÔNG được kết luận cấu hình nào tốt hơn")

    khung = []
    for part in filter(None, args.frame_window.split(",")):
        dau, _, cuoi = part.partition(":")
        if not (dau.strip().isdigit() and cuoi.strip().isdigit()):
            raise SystemExit(f"--frame-window {part!r} phải là dau:cuoi")
        khung.append((int(dau), int(cuoi)))
    khung_or_none = khung or None

    theo_cau_hinh: dict[float, list] = {m: [] for m in args.max_mad}
    for clip, bbox in zip(args.source, args.bbox):
        for lan_idx in range(args.lan):
            # CHÈN KẼ: mỗi vòng lặp chạy MỌI cấu hình một lần, thứ tự đảo chiều ở vòng lẻ để
            # "cấu hình chạy sau" không luôn là cấu hình được ưu ái.
            thu_tu = list(args.max_mad)
            if lan_idx % 2 == 1:
                thu_tu.reverse()
            for max_mad in thu_tu:
                with tempfile.TemporaryDirectory(prefix=f"ab_lk_{max_mad}_", dir="/dev/shm") as tmp:
                    out_dir = Path(tmp)
                    res = chay_mot_lan(source=clip, bbox=bbox, image_size=args.image_size,
                                       vos_every=args.vos_every, lk_max_mad=max_mad,
                                       frames=args.frames, out_dir=out_dir)
                    res["csv"] = doc_csv(res["csv"], khung=khung_or_none)
                    res["clip"], res["max_mad_yeu_cau"] = clip, max_mad
                    # Bằng chứng cấu hình HIỆU LỰC (không tin cờ CLI): status.json phải echo dúng.
                    res["max_mad_hieu_luc"] = ((res["status"].get("cau_hinh") or {}).get("lk_max_mad"))
                theo_cau_hinh[max_mad].append(res)
                print(f"{Path(clip).name} lần {lan_idx + 1} · max_mad {max_mad} → "
                      f"lk_ok {res['csv']['lk_ok_n']}/{res['csv']['n_lk_do_duoc']} "
                      f"({res['csv']['lk_ok_frac']}) · drift_iou {res['csv']['drift_iou']} · "
                      f"empty {res['csv']['empty_frac']} · hiệu lực {res['max_mad_hieu_luc']}")

    tong = {str(m): tong_hop(v) for m, v in theo_cau_hinh.items()}
    # Tách theo clip: gộp 2 clip rồi lấy trung bình sẽ CHE mất khác biệt (binh1 ×3,8 còn binh2 ×1,7
    # ⇒ gộp ra 2,1 "vừa đủ ngưỡng" trong khi thực chất hai clip cho hai câu trả lời khác nhau).
    tong_theo_clip = {
        Path(clip).name: {str(m): tong_hop([r for r in v if r["clip"] == clip])
                          for m, v in theo_cau_hinh.items()}
        for clip in args.source}
    lech = [r for v in theo_cau_hinh.values() for r in v
            if r["max_mad_hieu_luc"] is None
            or abs(float(r["max_mad_hieu_luc"]) - r["max_mad_yeu_cau"]) > 1e-9]
    cau_hinh = sorted(tong)
    so_sanh = {}
    if len(cau_hinh) >= 2:
        a, b = cau_hinh[0], cau_hinh[-1]
        so_sanh = {"a": a, "b": b, **ket_luan(tong[a], tong[b])}

    from scripts.measure_watchdog import _git_provenance

    rev, dirty, dirty_code, loi = _git_provenance()
    artifact = {
        "git_rev": rev, "git_dirty": dirty, "git_dirty_code": dirty_code, "git_loi": loi,
        "do_luc": datetime.now().isoformat(timespec="seconds"),
        "lenh": " ".join(["python scripts/ab_lk_max_mad.py"] + sys.argv[1:]),
        "nguon_so": {"clips": args.source, "bbox": args.bbox, "image_size": args.image_size,
                     "vos_every": args.vos_every, "frames": args.frames, "lan": args.lan,
                     "cua_so_frame": [[a, b] for a, b in khung] or None},
        "cau_hinh_hieu_luc_lech": lech,
        "tong_hop": tong,
        "tong_hop_theo_clip": tong_theo_clip,
        "so_sanh_theo_clip": {
            ten: ket_luan(tt[cau_hinh[0]], tt[cau_hinh[-1]]) for ten, tt in tong_theo_clip.items()
        } if len(cau_hinh) >= 2 else {},
        "so_sanh": so_sanh,
        "dinh_nghia": ("`lk_ok_frac` = tỉ lệ mẫu VOS mà LK dám nhận, mẫu số là số dòng CÓ `lk_ok`. "
                       "`drift_iou` ở đây là của đường live (ô hiển thị vs lần VOS kế tiếp), KHÔNG "
                       "phải độ chính xác bám vật — muốn thế phải có mIoU vs GT."),
        "lan_chay": {str(m): v for m, v in theo_cau_hinh.items()},
    }
    out = Path(args.out) if args.out else REPO_ROOT / "data" / (
        f"ab_lk_max_mad_{datetime.now():%Y-%m-%d}_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{json.dumps(so_sanh, ensure_ascii=False)}")
    print(f"Ghi: {out}")
    if lech:
        print(f"[LOI] {len(lech)} lần chạy có lk_max_mad hiệu lực KHÁC yêu cầu ⇒ số không dùng được",
              file=sys.stderr)
        return 1
    if loi:
        print(f"[LOI] không lấy được provenance: {loi}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
