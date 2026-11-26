#!/usr/bin/env python3
"""Sinh MASK GIẢ (pseudo-GT) từ 1 490 ô người dùng đã vẽ, bằng SAM 2 (prompt = hộp).

Vì sao cần
----------
Muốn train lại SAM 2 thì cần **mask pixel**, không phải hộp. Repo có 1 490 ô GT nhưng **0 mask**
(bộ GT mask lớn nhất chỉ 36 frame). Mỗi ô đủ để SAM 2 tự cắt mask ở đúng frame đó ⇒ biến 1 490 hộp
thành ~1 270 mask để (a) chấm mIoU trên nhiều frame hơn, (b) làm dữ liệu sửa tay dần thành GT thật.

Đây là **mask GIẢ**, không phải GT: nó do chính model sinh ra từ hộp của người, nên
  * dùng để **đo/kiểm** thì phải nói rõ "pseudo-GT" và **không** dùng để tuyên bố model tốt;
  * dùng để **train** thì là self-training — phải có bước sửa tay (hoặc ít nhất lọc bằng `--qc`).
Vì vậy script ghi kèm cờ QC cho từng mask và **đếm** các ca nghi ngờ.

QC (để biết mask nào cần xem lại bằng mắt)
------------------------------------------
- `rong`: mask rỗng dù người đã vẽ hộp.
- `nho`: diện tích mask < 20 % diện tích hộp (SAM 2 bắt được mẩu).
- `tran`: diện tích mask > 150 % diện tích hộp (mask "ăn" nền).
- `cham_bien`: mask chạm mép khung trong khi hộp KHÔNG chạm mép.
Mỗi cờ đều ghi vào manifest + đếm trong artifact (AGENTS §6: "0/None ≠ đã đo").

    python scripts/make_pseudo_masks.py --limit 8            # thử 8 ô, đo ms/mask
    python scripts/make_pseudo_masks.py --image-size 512     # chạy đủ (mặc định 512)
    python scripts/make_pseudo_masks.py --qc                 # chỉ in danh sách mask cần xem lại
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import os  # noqa: E402

from build_verifier_dataset import doc_nhan_hieu_luc  # noqa: E402  (một định nghĩa "nhãn hiệu lực")
from tools import label_ui as L  # noqa: E402             (một định nghĩa "bước → frame")

DATA = ROOT / "data"
NHAN = DATA / "nhan"
DEFAULT_OUT = DATA / "gt_pseudo"

NHO, TRAN = 0.20, 1.50          # ngưỡng QC theo tỉ lệ diện tích mask / diện tích hộp


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=False).stdout.strip()
    except OSError:
        return ""


def bam_hop(box: list[int]) -> str:
    """Hash ngắn của HỘP — đưa vào TÊN FILE mask.

    Vì sao: cache khoá `(phiên, bước)` từng phục vụ mask CŨ sau khi người dùng **vẽ lại hộp** cho cùng
    bước, và `qc` lại tính theo hộp MỚI ⇒ cờ vô nghĩa mà `loi_* = 0` (review độc lập 26-11, P1).
    Đổi hộp ⇒ đổi tên file ⇒ tự động cache-miss.
    """
    return hashlib.sha256(json.dumps(list(box), sort_keys=True).encode()).hexdigest()[:8]


def dau_van_tay(image_size: int, checkpoint: str, model_cfg: str) -> str:
    """Vân tay của THAM SỐ + NGUỒN: đổi `image_size`/checkpoint/cfg, hoặc CSV/video/nhãn đổi ⇒ xoá cache.

    Bản đầu chỉ khoá `(phiên, bước)` ⇒ chạy `--image-size 1024` sau lần 512 vẫn phục vụ 1 231 mask 512
    trong khi artifact khai `1024` (review độc lập 26-11, P1).
    """
    h = hashlib.sha256(f"size={image_size}|ckpt={checkpoint}|cfg={model_cfg}|".encode())
    for tep in sorted(NHAN.glob("*.jsonl")):
        for f in (tep, DATA / f"{tep.stem}_metrics.csv", DATA / f"{tep.stem}.mp4"):
            try:
                st = f.stat()
                h.update(f"{f.name}:{st.st_mtime_ns}:{st.st_size};".encode())
            except OSError:
                h.update(f"{f.name}:-;".encode())
    return h.hexdigest()[:16]


def don_cache_neu_can(out_dir: pathlib.Path, van_tay: str) -> bool:
    """Xoá mask của lần chạy trước nếu vân tay khác. Trả True nếu ĐÃ xoá."""
    tep = out_dir / ".dau_van_tay"
    cu = tep.read_text(encoding="utf-8").strip() if tep.is_file() else None
    if cu == van_tay:
        return False
    import shutil
    for con in list(out_dir.iterdir()) if out_dir.is_dir() else []:
        if con.is_dir():                       # giữ file ở gốc (manifest/artifact không nằm ở đây)
            shutil.rmtree(con, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    tep.write_text(van_tay, encoding="utf-8")
    return cu is not None


def o_hop_le(b: object, rong: int, cao: int) -> bool:
    """`bbox_dung` = [x1,y1,x2,y2] theo pixel video (đã kiểm lúc ghi nhãn, kiểm lại cho chắc)."""
    if not (isinstance(b, (list, tuple)) and len(b) == 4):
        return False
    try:
        x1, y1, x2, y2 = (float(v) for v in b)
    except (TypeError, ValueError):
        return False
    if not all(np.isfinite([x1, y1, x2, y2])):
        return False
    return 0 <= x1 < x2 <= rong and 0 <= y1 < y2 <= cao and (x2 - x1) >= 3 and (y2 - y1) >= 3


def qc(mask: np.ndarray, box: list[int], rong: int, cao: int) -> dict:
    """Cờ nghi ngờ cho một mask. Trả dict — `rong` là cờ boolean, số liệu để đọc lại."""
    dien_tich = int(mask.sum())
    x1, y1, x2, y2 = box
    d_h = max(1, (x2 - x1) * (y2 - y1))
    ty = dien_tich / d_h
    co = {"rong": dien_tich == 0, "nho": 0 < ty < NHO, "tran": ty > TRAN,
          "ty_le_dien_tich": round(ty, 3), "dien_tich": dien_tich, "dien_tich_hop": d_h}
    # So theo TỪNG PHÍA: mask chạm mép nào thì chỉ bỏ qua nếu mép HỘP tương ứng cũng sát mép đó.
    # Bản đầu dùng OR 4 phía ⇒ hộp chạm đáy (y2 = cao-1) làm BỎ SÓT mask tràn sang trái/phải/trên
    # (review độc lập 26-11, P2).
    phia = {"tren": mask[0, :].any(), "duoi": mask[-1, :].any(),
            "trai": mask[:, 0].any(), "phai": mask[:, -1].any()}
    hop_sat = {"tren": y1 <= 2, "duoi": y2 >= cao - 2, "trai": x1 <= 2, "phai": x2 >= rong - 2}
    co["cham_bien"] = any(phia[k] and not hop_sat[k] for k in phia)
    co["nghi"] = co["rong"] or co["nho"] or co["tran"] or co["cham_bien"]
    return co


def thu_thap_muc_tieu() -> tuple[list[dict], dict]:
    """Mọi (phiên, bước) có `bbox_dung` ⇒ (việc cần làm, đếm lý do BỊ BỎ).

    Đếm là bắt buộc: `so_o_hop_le` là mẫu số SAU lọc, nên nếu không đếm thì câu "1 490 ô → 1 251" không
    kiểm được và `loi_* = 0` bị đọc thành "không mất gì" (review độc lập 26-11, P2).
    """
    viec, bo_qua = [], {}

    def bo(khoa: str) -> None:
        bo_qua[khoa] = bo_qua.get(khoa, 0) + 1

    for tep in sorted(NHAN.glob("*.jsonl")):
        phien = tep.stem
        csv_p = DATA / f"{phien}_metrics.csv"
        if not csv_p.is_file():
            bo("thieu_csv")
            continue
        try:
            d = L.doc_phien_cached(csv_p)
        except (OSError, ValueError):
            bo("csv_hong")
            continue
        mo = L._mo_video(phien)
        if not mo:
            bo("thieu_video")
            continue
        fps, video_rong, video_cao = mo[1], mo[3], mo[4]
        for buoc, r in sorted(doc_nhan_hieu_luc(tep).items()):
            box = r.get("bbox_dung")
            if not box:
                continue
            if not 0 <= buoc < len(d["frames"]):
                bo("buoc_ngoai_dai")
                continue
            box = [int(round(float(v))) for v in box]
            if not o_hop_le(box, video_rong, video_cao):
                bo("hop_khong_hop_le")
                continue
            idx, _loi = L.chi_so_khung(phien, buoc)
            if idx is None:
                bo("khong_anh_xa_duoc_frame")
                continue
            viec.append({"phien": phien, "buoc": buoc, "frame_idx": idx, "box": box,
                         "nhan": r.get("nhan"), "video_rong": video_rong,
                         "video_cao": video_cao, "fps": fps,
                         "check_do": r.get("che_do")})
    return viec, bo_qua


def sinh_mask(engine, viec: list[dict], out_dir: pathlib.Path, ghi_de: bool) -> tuple[list, dict]:
    """Chạy SAM 2 cho từng mục tiêu. Trả (bản ghi, đếm)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ban_ghi, dem = [], {"co_cache": 0, "moi": 0, "loi_doc_frame": 0, "loi_mask": 0}
    tong_ms = 0.0
    for k, v in enumerate(viec, 1):
        phien, buoc = v["phien"], v["buoc"]
        thu_muc = out_dir / phien
        dich = thu_muc / f"{buoc:05d}_{bam_hop(v['box'])}.png"
        if ghi_de and dich.is_file() and dich.stat().st_size > 0:
            m = cv2.imread(str(dich), cv2.IMREAD_GRAYSCALE)
            if m is not None:
                rec = dict(v)
                rec["mask"] = str(dich.relative_to(out_dir))
                rec["qc"] = qc(m > 127, v["box"], v["video_rong"], v["video_cao"])
                ban_ghi.append(rec)
                dem["co_cache"] += 1
                continue
        mo = L._mo_video(phien)
        if not mo:
            dem["loi_doc_frame"] += 1
            continue
        cap, _, _, _, _ = mo
        with L._CAP_LOCK:
            if not cap.set(cv2.CAP_PROP_POS_FRAMES, v["frame_idx"]):
                dem["loi_doc_frame"] += 1
                continue
            vi_tri = int(round(cap.get(cv2.CAP_PROP_POS_FRAMES) or v["frame_idx"]))
            if abs(vi_tri - v["frame_idx"]) > 1:
                dem["loi_doc_frame"] += 1
                continue
            ok, khung = cap.read()
        if not ok or khung is None:
            dem["loi_doc_frame"] += 1
            continue

        t0 = time.perf_counter()
        try:
            kq = engine.start(khung, tuple(v["box"]))
            mask = np.asarray(kq.mask).astype(bool)
        except Exception as e:      # noqa: BLE001 — model lỗi không được làm chết cả lô
            dem["loi_mask"] += 1
            if dem["loi_mask"] <= 3:
                print(f"  LỖI model {phien}#{buoc}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        tong_ms += (time.perf_counter() - t0) * 1000
        dem["moi"] += 1
        rec = dict(v)
        rec["qc"] = qc(mask, v["box"], v["video_rong"], v["video_cao"])
        if ghi_de:
            thu_muc.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(dich), (mask.astype(np.uint8) * 255))
            rec["mask"] = str(dich.relative_to(out_dir))
        ban_ghi.append(rec)
        if k % 50 == 0:
            print(f"  {k}/{len(viec)} … {tong_ms / max(dem['moi'], 1):.0f} ms/mask", file=sys.stderr)
    dem["ms_moi_mask"] = round(tong_ms / dem["moi"], 1) if dem["moi"] else None
    return ban_ghi, dem


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--image-size", type=int, default=512,
                    help="độ phân giải SAM 2 (512 ≈ 0,7 s/frame CPU; 1024 ≈ 5,5 s ⇒ 1 270 ô = ~2 h)")
    ap.add_argument("--checkpoint", default="samurai/sam2/checkpoints/sam2.1_hiera_tiny.pt")
    ap.add_argument("--model-cfg", default="configs/samurai/sam2.1_hiera_t.yaml")
    ap.add_argument("--limit", type=int, help="chỉ làm N ô đầu (để đo tốc độ)")
    ap.add_argument("--qc", action="store_true", help="chỉ IN danh sách mask cần xem lại, không chạy model")
    ap.add_argument("--metrics", help="file artifact JSON (mặc định <out>_metrics.json)")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    so_dong_tho = sum(1 for t in sorted(NHAN.glob("*.jsonl"))
                      for r in (json.loads(x) for x in t.read_text(encoding="utf-8").splitlines()
                                if x.strip())
                      if r.get("bbox_dung"))
    viec, bo_qua = thu_thap_muc_tieu()
    if args.limit:
        viec = viec[:args.limit]
    if not viec:
        print("không có ô GT nào dùng được (kiểm `data/nhan/*.jsonl` có `bbox_dung`)", file=sys.stderr)
        return 1

    if args.qc:
        man = out_dir / "manifest.jsonl"
        if not man.is_file():
            print(f"chưa có {man} — chạy không kèm --qc trước", file=sys.stderr)
            return 1
        recs = [json.loads(x) for x in man.read_text(encoding="utf-8").splitlines() if x.strip()]
        nghi = [r for r in recs if r["qc"]["nghi"]]
        print(f"{len(recs)} mask · {len(nghi)} cần xem lại")
        for r in nghi[:40]:
            print(f"  {r['phien']}#{r['buoc']:3d} {r['qc']}")
        return 0

    print(f"{len(viec)} ô sẽ sinh mask (image_size={args.image_size}); bỏ qua: {bo_qua}",
          file=sys.stderr)
    from src.tracker_engine import TrackerEngine
    t0 = time.time()
    engine = TrackerEngine.build_default(device="cpu", checkpoint=args.checkpoint,
                                         model_cfg=args.model_cfg, image_size=args.image_size)
    print(f"nạp model: {time.time() - t0:.1f} s", file=sys.stderr)

    # P2-8: `image_size` chỉ là YÊU CẦU — phải so với HIỆU LỰC (bài học "0/None ≠ đã đo").
    hieu_luc = getattr(engine, "image_size_hieu_luc", None)
    if hieu_luc is not None and int(hieu_luc) != int(args.image_size):
        print(f"LỖI: image_size hiệu lực {hieu_luc} ≠ yêu cầu {args.image_size} — không công bố số",
              file=sys.stderr)
        return 1

    van_tay = dau_van_tay(args.image_size, args.checkpoint, args.model_cfg)
    da_xoa = don_cache_neu_can(out_dir, van_tay)
    if da_xoa:
        print("vân tay nguồn/tham số đổi ⇒ đã xoá cache mask cũ", file=sys.stderr)

    t_lo = time.perf_counter()
    ban_ghi, dem = sinh_mask(engine, viec, out_dir, ghi_de=not args.limit)
    giay_tong = round(time.perf_counter() - t_lo, 1)
    man = out_dir / "manifest.jsonl"
    if not args.limit:
        man.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ban_ghi),
                       encoding="utf-8")

    # P2-6: phát ĐỦ 4 khoá (0 tường minh) — nếu chỉ phát cờ > 0 thì "0 rỗng / 0 tràn" trong log là suy
    # từ code, không đọc được từ artifact (bẫy "0/None ≠ đã đo").
    CO = ("rong", "nho", "tran", "cham_bien")
    dem_co = {k: sum(1 for r in ban_ghi if r["qc"][k]) for k in CO}
    so_nhieu_co = sum(1 for r in ban_ghi if sum(bool(r["qc"][k]) for k in CO) > 1)

    # P2-5: các con số đã công bố trong log phải SUY RA ĐƯỢC từ artifact.
    ty = sorted(r["qc"]["ty_le_dien_tich"] for r in ban_ghi if r["qc"]["dien_tich"])
    def _pct(xs, q):
        return round(float(xs[min(len(xs) - 1, int(q * len(xs)))]), 3) if len(xs) >= 30 else None
    phan_bo = {"n": len(ty),
               "median": round(float(sorted(ty)[len(ty) // 2]), 3) if ty else None,
               "p05": _pct(ty, 0.05), "p95": _pct(ty, 0.95),
               "ghi_chu": "p05/p95 chỉ phát khi n >= 30 (AGENTS §6)"}
    payload = {
        "schema": 1,
        "do_luc": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "lenh": " ".join(sys.argv),
        "git_rev": git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "git_dirty_code": bool(git("status", "--porcelain", "--", ".", ":!data")),
        "image_size_yeu_cau": args.image_size,
        "image_size_hieu_luc": getattr(engine, "image_size_hieu_luc", None),
        "checkpoint": args.checkpoint,
        "so_o_hop_le": len(viec),
        "so_mask": len(ban_ghi),
        "so_mask_moi_sinh": dem["moi"],
        "co_cache": dem["co_cache"],
        "loi_doc_frame": dem["loi_doc_frame"],
        "loi_mask": dem["loi_mask"],
        "ms_moi_mask": dem["ms_moi_mask"],
        "qc_dem": dem_co,
        "so_mask_nhieu_co": so_nhieu_co,
        "so_mask_nghi": sum(1 for r in ban_ghi if r["qc"]["nghi"]),
        "phan_bo_ty_le_dien_tich": phan_bo,
        "so_frame_khac_nhau": len({(r["phien"], r["frame_idx"]) for r in ban_ghi}),
        "so_phien": len({r["phien"] for r in ban_ghi}),
        "giay_tong": giay_tong,
        "dau_van_tay": van_tay,
        "da_xoa_cache_cu": da_xoa,
        "bo_qua_muc_tieu": bo_qua,
        "so_o_co_bbox": sum(bo_qua.values()) + len(viec),
        "so_dong_co_bbox_tho": so_dong_tho,
        "mat_do_gop_buoc": max(0, so_dong_tho - (sum(bo_qua.values()) + len(viec))),
        "ghi_chu_gop_buoc": (
            "Nhãn là append-only: một bước có thể có NHIỀU dòng có `bbox_dung`; nhãn/dòng CUỐI của bước "
            "mới là hiệu lực (`tong_hop` cũng gộp như vậy) ⇒ số hộp thô > số mask sinh được là bình "
            "thường, KHÔNG phải mất dữ liệu."),
        "chiet_giai": (
            "Đây là MASK GIẢ: SAM 2 tự cắt từ HỘP của người dùng, không phải GT do người tô. Dùng để "
            "mở rộng phép đo và làm dữ liệu sửa tay; KHÔNG dùng để tuyên bố chất lượng model (mask do "
            "chính model sinh). `qc_dem` đếm các ca nghi (rỗng / <20% / >150% diện tích hộp / chạm "
            "biên khung mà hộp không chạm) — phải xem bằng mắt trước khi coi là GT."),
    }
    # P2-9: lỗi model / đọc frame ⇒ KHÔNG công bố, và KHÔNG ghi đè manifest + artifact đã có.
    if dem["loi_mask"] or dem["loi_doc_frame"] or len(ban_ghi) < len(viec):
        print(f"KHÔNG CÔNG BỐ — lỗi model {dem['loi_mask']}, lỗi đọc frame {dem['loi_doc_frame']}, "
              f"mask {len(ban_ghi)}/{len(viec)}", file=sys.stderr)
        return 1

    if not args.limit:
        p = pathlib.Path(args.metrics) if args.metrics else out_dir.with_name(out_dir.name + "_metrics.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        tam = p.with_suffix(".json.tmp")
        tam.write_text(json.dumps(payload, ensure_ascii=False, indent=1, allow_nan=False),
                       encoding="utf-8")
        os.replace(tam, p)
        print(f"→ {p}")
    print(json.dumps({k: payload[k] for k in ("so_o_hop_le", "so_mask", "so_mask_moi_sinh",
                                              "loi_doc_frame", "loi_mask", "ms_moi_mask",
                                              "qc_dem", "so_mask_nghi")},
                     ensure_ascii=False, indent=1))
    return 0 if payload["so_mask"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
