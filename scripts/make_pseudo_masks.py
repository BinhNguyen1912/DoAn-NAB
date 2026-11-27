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
- `shape_la`: mask trả về không phải 2 chiều / rỗng chiều (ca lạ ⇒ tính là nghi, bỏ kiểm biên).
Mỗi cờ đều ghi vào manifest + đếm trong artifact (AGENTS §6: "0/None ≠ đã đo").

    python scripts/make_pseudo_masks.py --limit 8            # thử 8 ô, đo ms/mask
    python scripts/make_pseudo_masks.py --image-size 512     # chạy đủ (mặc định 512)
    python scripts/make_pseudo_masks.py --qc                 # chỉ in danh sách mask cần xem lại
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from build_verifier_dataset import doc_nhan_hieu_luc  # noqa: E402  (một định nghĩa "nhãn hiệu lực")
from tools import label_ui as L  # noqa: E402             (một định nghĩa "bước → frame")

DATA = ROOT / "data"
NHAN = DATA / "nhan"
DEFAULT_OUT = DATA / "gt_pseudo"

NHO, TRAN = 0.20, 1.50          # ngưỡng QC theo tỉ lệ diện tích mask / diện tích hộp
SAT_MEP = 2                     # hộp cách mép khung ≤ 2 px thì coi là "hộp cũng sát mép" (xem `qc`)


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


def don_cache_neu_can(out_dir: pathlib.Path, van_tay: str, cho_xoa: bool = False) -> int:
    """Xoá mask của lần chạy trước nếu vân tay khác. Trả **số file PNG đã xoá**.

    Chỉ dọn khi `out_dir` đúng là thư mục cache do script này tạo (có `.dau_van_tay`) hoặc đang rỗng:
    bản trước xoá **mọi** thư mục con của `--out` mà không kiểm ⇒ `--out data` xoá `data/nhan`, `--out .`
    xoá cả `src/`, `.git/` (review độc lập 27-11, P1). `--limit` không được gọi hàm này.

    `cho_xoa=False` (mặc định) ⇒ vân tay đổi thì **TỪ CHỐI** chứ không xoá: vân tay gồm `mtime_ns` của
    `data/nhan/*.jsonl` nên chỉ cần gán thêm MỘT nhãn là vân tay đổi, và lần chạy đầy đủ kế tiếp sẽ
    xoá sạch mask cũ (kể cả mask đã sửa tay) mà không ai bấm gì ⇒ bảo vệ phải nằm ở chỗ XOÁ, không
    phải ở công thức vân tay. Muốn xoá thật thì truyền `--xoa-cache` (review độc lập vòng 4, P1).
    """
    tep = out_dir / ".dau_van_tay"
    da_co_van_tay = tep.is_file()
    cu = tep.read_text(encoding="utf-8").strip() if da_co_van_tay else None
    if cu == van_tay:
        return 0
    con = list(out_dir.iterdir()) if out_dir.is_dir() else []
    # Đếm **mọi** entry, không chỉ thư mục con: bản trước chỉ chặn khi có thư mục con ⇒ `--out docs/task`
    # (chỉ có file) được chấp nhận, bị đóng dấu vân tay, rồi lần sau bị coi là cache để xoá (review
    # 27-11 vòng 2, P2).
    if con and not da_co_van_tay:
        raise ValueError(
            f"{out_dir} có {len(con)} entry nhưng KHÔNG có `.dau_van_tay` ⇒ không dám coi là thư mục "
            f"cache để xoá ({', '.join(c.name for c in con[:3])}…). Dùng `--out` mới hoặc xoá tay.")
    so_file = sum(1 for d in con if d.is_dir() for _ in d.rglob("*.png"))   # chỉ đếm PNG, đếm trước khi xoá
    if so_file and not cho_xoa:
        raise ValueError(
            f"vân tay nguồn/tham số đổi ⇒ lần chạy này SẼ XOÁ {so_file} mask trong {out_dir} (kể cả mask "
            f"đã sửa tay). Chạy lại với `--xoa-cache` nếu thật sự muốn sinh lại từ đầu, hoặc dùng `--out` "
            f"mới. Vân tay gồm mtime của `data/nhan/*.jsonl` nên chỉ cần thêm một nhãn là đổi.")
    for d in con:                             # giữ file ở gốc (manifest/artifact không nằm ở đây)
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    tep.write_text(van_tay, encoding="utf-8")
    return so_file


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
    """Cờ nghi ngờ cho một mask. Trả dict — `rong` là cờ boolean, số liệu để đọc lại.

    `cham_bien` coi mép HỘP là "sát mép khung" khi cách ≤ `SAT_MEP` px (2 px: hộp do người vẽ trên ảnh
    phóng to rồi làm tròn về pixel video nên hộp "chạm" mép thường lệch 1–2 px — ngưỡng 1 px báo oan 63
    ca trên 1 251 mask, đo 27-11).
    """
    mask = np.asarray(mask)
    dien_tich = int(mask.sum())
    x1, y1, x2, y2 = box
    d_h = max(1, (x2 - x1) * (y2 - y1))
    ty = dien_tich / d_h
    co = {"rong": dien_tich == 0, "nho": 0 < ty < NHO, "tran": ty > TRAN,
          "ty_le_dien_tich": round(ty, 3), "dien_tich": dien_tich, "dien_tich_hop": d_h}
    # Mask 2 chiều là hợp đồng của model và của `imread`, NHƯNG shape rỗng/lệch chiều sẽ làm
    # `mask[0, :]` ném IndexError giữa lô (mất cả 1 251 mask vì một ca lạ). Báo cờ riêng thay vì
    # đoán; cờ này cũng vào `nghi` để ca lạ không lọt khỏi danh sách cần xem lại (review 27-11, P3).
    co["shape_la"] = bool(mask.ndim != 2 or mask.size == 0)
    if co["shape_la"]:
        co["cham_bien"] = False
        co["nghi"] = True
        return co
    # So theo TỪNG PHÍA: mask chạm mép nào thì chỉ bỏ qua nếu mép HỘP tương ứng cũng sát mép đó.
    # Bản đầu dùng OR 4 phía ⇒ hộp chạm đáy (y2 = cao-1) làm BỎ SÓT mask tràn sang trái/phải/trên
    # (review độc lập 26-11, P2).
    phia = {"tren": mask[0, :].any(), "duoi": mask[-1, :].any(),
            "trai": mask[:, 0].any(), "phai": mask[:, -1].any()}
    hop_sat = {"tren": y1 <= SAT_MEP, "duoi": y2 >= cao - SAT_MEP,
               "trai": x1 <= SAT_MEP, "phai": x2 >= rong - SAT_MEP}
    co["cham_bien"] = any(phia[k] and not hop_sat[k] for k in phia)
    co["nghi"] = co["rong"] or co["nho"] or co["tran"] or co["cham_bien"]
    return co


def thu_thap_muc_tieu() -> tuple[list[dict], dict, dict]:
    """Mọi (phiên, bước) có `bbox_dung` ⇒ (việc cần làm, đếm lý do BỊ BỎ, đếm DÒNG nhãn).

    Đếm là bắt buộc: `so_o_hop_le` là mẫu số SAU lọc, nên nếu không đếm thì câu "1 490 ô → 1 251" không
    kiểm được và `loi_* = 0` bị đọc thành "không mất gì" (review độc lập 26-11, P2).

    Lý do bỏ phải **tách đơn vị**: `file` đếm theo *phiên* (không đọc được CSV/video ⇒ không biết phiên
    đó có bao nhiêu bước), `buoc` đếm theo *bước*. Bản trước gộp hai đơn vị vào một dict rồi cộng dồn ⇒
    một phiên thiếu CSV chỉ bị trừ 1 còn 59 bước của nó bị tính thành "gộp bước" (review 27-11, P2).
    """
    viec = []
    bo_qua: dict[str, dict[str, int]] = {"file": {}, "buoc": {}}
    dong_theo_buoc: dict[tuple[str, int], int] = {}

    def bo(muc: str, khoa: str) -> None:
        bo_qua[muc][khoa] = bo_qua[muc].get(khoa, 0) + 1

    for tep in sorted(NHAN.glob("*.jsonl")):
        phien = tep.stem
        for dong in tep.read_text(encoding="utf-8").splitlines():
            if not dong.strip():
                continue
            try:
                r = json.loads(dong)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("bbox_dung") and r.get("nhan") and isinstance(r.get("buoc"), int):
                k = (phien, r["buoc"])
                dong_theo_buoc[k] = dong_theo_buoc.get(k, 0) + 1
        csv_p = DATA / f"{phien}_metrics.csv"
        if not csv_p.is_file():
            bo("file", "thieu_csv")
            continue
        try:
            d = L.doc_phien_cached(csv_p)
        except (OSError, ValueError):
            bo("file", "csv_hong")
            continue
        mo = L._mo_video(phien)
        if not mo:
            bo("file", "thieu_video")
            continue
        fps, video_rong, video_cao = mo[1], mo[3], mo[4]
        for buoc, r in sorted(doc_nhan_hieu_luc(tep).items()):
            box = r.get("bbox_dung")
            if not box:
                if (phien, buoc) in dong_theo_buoc:   # bước TỪNG có hộp nhưng nhãn CUỐI bỏ hộp
                    bo("buoc", "nhan_cuoi_khong_co_hop")
                continue
            if not 0 <= buoc < len(d["frames"]):
                bo("buoc", "buoc_ngoai_dai")
                continue
            box = [int(round(float(v))) for v in box]
            if not o_hop_le(box, video_rong, video_cao):
                bo("buoc", "hop_khong_hop_le")
                continue
            idx, _loi = L.chi_so_khung(phien, buoc)
            if idx is None:
                bo("buoc", "khong_anh_xa_duoc_frame")
                continue
            viec.append({"phien": phien, "buoc": buoc, "frame_idx": idx, "box": box,
                         "nhan": r.get("nhan"), "video_rong": video_rong,
                         "video_cao": video_cao, "fps": fps,
                         "check_do": r.get("che_do")})
    return viec, bo_qua, dem_dong(dong_theo_buoc, viec)


def dem_dong(dong_theo_buoc: dict[tuple[str, int], int], viec: list[dict]) -> dict:
    """Đối chiếu 1 490 DÒNG nhãn với 1 251 BƯỚC sinh được mask — hai đơn vị khác nhau, phải tách.

    `trung_lap` = dòng của bước CÒN hiệu lực bị dòng sau thay thế; `cua_buoc_bi_bo` = dòng của bước
    không sinh được mask (nhãn cuối bỏ hộp, hộp sai, không ánh xạ được frame). `tho − trung_lap −
    cua_buoc_bi_bo == số bước làm được` ⇒ câu "1 490 ô → 1 251 mask" kiểm được bằng số học.
    """
    tho = sum(dong_theo_buoc.values())
    # Khử trùng theo bước: một bước xuất hiện 2 lần trong `viec` sẽ làm `trung_lap` phồng (review 27-11
    # vòng 2, P3) — hôm nay không xảy ra nhưng chặn bằng code rẻ hơn là tin vào đường đi.
    khoa = {(v["phien"], v["buoc"]) for v in viec}
    giu = sum(dong_theo_buoc.get(k, 0) for k in khoa)
    return {"tho": tho, "trung_lap": giu - len(khoa), "cua_buoc_bi_bo": tho - giu}


def sinh_mask(engine, viec: list[dict], out_dir: pathlib.Path, ghi_de: bool) -> tuple[list, dict]:
    """Chạy SAM 2 cho từng mục tiêu. Trả (bản ghi, đếm)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ban_ghi, dem = [], {"co_cache": 0, "moi": 0, "loi_doc_frame": 0, "loi_mask": 0, "loi_shape": 0,
                        "loi_ghi": 0}
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
        # Mask lệch chiều KHÔNG được đi tiếp: `cv2.imwrite` NHẬN cả mảng 1-D và 3-D (đo 27-11:
        # chỉ shape rỗng/scalar mới ném) ⇒ đi tiếp là ghi ra PNG SAI mà `qc` đã báo cờ. Ca lạ phải
        # thành LỖI của riêng nó (đếm + bỏ) để cổng "không công bố" bắt được, không làm chết cả lô
        # (review độc lập vòng 4, P1).
        if mask.ndim != 2 or mask.size == 0:
            dem["loi_shape"] += 1
            if dem["loi_shape"] <= 3:
                print(f"  LỖI shape mask {phien}#{buoc}: {mask.shape}", file=sys.stderr)
            continue
        rec = dict(v)
        rec["qc"] = qc(mask, v["box"], v["video_rong"], v["video_cao"])
        if ghi_de:
            thu_muc.mkdir(parents=True, exist_ok=True)
            # `cv2.imwrite` trả False khi đĩa đầy/quyền hỏng; bỏ qua giá trị trả thì artifact công bố
            # `so_mask` > số PNG thật trên đĩa mà `loi_* = 0` (review 27-11, P2).
            # Ghi qua file tạm rồi `os.replace`: Ctrl-C/đĩa đầy giữa đường không để lại PNG cụt mang
            # ĐÚNG tên cache (lần sau sẽ đọc nửa ảnh và không bao giờ sinh lại). Đuôi phải là `.png`
            # để `cv2.imwrite` chọn codec (review 27-11 vòng 2, P3).
            tam = dich.with_name(dich.stem + ".tmp.png")
            if not cv2.imwrite(str(tam), (mask.astype(np.uint8) * 255)):
                dem["loi_ghi"] += 1
                tam.unlink(missing_ok=True)
                if dem["loi_ghi"] <= 3:
                    print(f"  LỖI ghi {tam}", file=sys.stderr)
                continue
            os.replace(tam, dich)
            rec["mask"] = str(dich.relative_to(out_dir))
        tong_ms += (time.perf_counter() - t0) * 1000
        dem["moi"] += 1
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
    ap.add_argument("--xoa-cache", action="store_true",
                    help="CHO PHÉP xoá mask cũ khi vân tay nguồn/tham số đổi (mặc định: từ chối)")
    ap.add_argument("--metrics", help="file artifact JSON (mặc định <out>_metrics.json)")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    viec, bo_qua, dem_dong_nhan = thu_thap_muc_tieu()
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
        # `.get` thay vì chỉ mục: manifest do bản CŨ (hoặc dòng rách) không có `qc` thì `--qc` phải
        # NÓI RA số bản ghi thiếu, không chết bằng `KeyError` + traceback (review 27-11 vòng 2, P3).
        thieu_qc = [r for r in recs if not isinstance(r.get("qc"), dict)]
        nghi = [r for r in recs if isinstance(r.get("qc"), dict) and r["qc"].get("nghi")]
        print(f"{len(recs)} mask · {len(nghi)} cần xem lại"
              + (f" · {len(thieu_qc)} bản ghi KHÔNG có qc (manifest cũ?)" if thieu_qc else ""))
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
    so_da_xoa = 0
    if not args.limit:      # `--limit` chỉ đo tốc độ ⇒ không được xoá cache (review 27-11, P1)
        try:
            so_da_xoa = don_cache_neu_can(out_dir, van_tay, cho_xoa=args.xoa_cache)
        except ValueError as e:
            print(f"LỖI: {e} — không công bố số", file=sys.stderr)
            return 1
        if so_da_xoa:
            print(f"vân tay nguồn/tham số đổi ⇒ đã xoá {so_da_xoa} mask cũ", file=sys.stderr)

    t_lo = time.perf_counter()
    ban_ghi, dem = sinh_mask(engine, viec, out_dir, ghi_de=not args.limit)
    giay_tong = round(time.perf_counter() - t_lo, 1)
    man = out_dir / "manifest.jsonl"

    # P2-6: phát ĐỦ 4 khoá (0 tường minh) — nếu chỉ phát cờ > 0 thì "0 rỗng / 0 tràn" trong log là suy
    # từ code, không đọc được từ artifact (bẫy "0/None ≠ đã đo").
    CO = ("rong", "nho", "tran", "cham_bien", "shape_la")
    dem_co = {k: sum(1 for r in ban_ghi if r["qc"][k]) for k in CO}
    so_nhieu_co = sum(1 for r in ban_ghi if sum(bool(r["qc"][k]) for k in CO) > 1)

    # P2-5: các con số đã công bố trong log phải SUY RA ĐƯỢC từ artifact.
    ty = sorted(r["qc"]["ty_le_dien_tich"] for r in ban_ghi if r["qc"]["dien_tich"])
    def _pct(xs, q):
        return round(float(xs[min(len(xs) - 1, int(q * len(xs)))]), 3) if len(xs) >= 30 else None
    phan_bo = {"n": len(ty),
               "median": round(float(sorted(ty)[len(ty) // 2]), 3) if ty else None,
               "p05": _pct(ty, 0.05), "p95": _pct(ty, 0.95),
               "ghi_chu": "n = số mask KHÔNG rỗng; p05/p95 chỉ phát khi n >= 30 (AGENTS §6)"}
    payload = {
        "schema": 2,        # v2: qc_dem thêm `shape_la`; thêm `loi_shape` + `phien_ban_sinh`
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
        "loi_shape": dem["loi_shape"],
        "loi_ghi": dem["loi_ghi"],
        "ms_moi_mask": dem["ms_moi_mask"],
        "ghi_chu_ms_moi_mask": ("đo từ ngay trước `engine.start()` tới sau khi ghi PNG + qc; KHÔNG gồm "
                               "đọc frame/seek và không gồm lần chạy đọc cache ⇒ đọc kèm `do_toc_do`"),
        "do_toc_do": dem["moi"] > 0,
        "qc_dem": dem_co,
        "so_mask_nhieu_co": so_nhieu_co,
        "so_mask_nghi": sum(1 for r in ban_ghi if r["qc"]["nghi"]),
        "phan_bo_ty_le_dien_tich": phan_bo,
        "so_frame_khac_nhau": len({(r["phien"], r["frame_idx"]) for r in ban_ghi}),
        "so_phien": len({r["phien"] for r in ban_ghi}),
        "giay_tong": giay_tong,
        "ghi_chu_giay_tong": ("gồm cả thời gian đọc cache; khi `do_toc_do` false thì đây KHÔNG phải thời "
                              "gian sinh mask (đừng lấy giay_tong / so_mask ra làm ms/mask)"),
        "dau_van_tay": van_tay,
        "ghi_chu_pham_vi_dau_van_tay": (
            "vân tay KHÔNG gồm: nội dung checkpoint (đổi ruột cùng đường dẫn), `src/tracker_engine.py`, "
            "và đường prompt→mask; CÓ gồm `mtime` của nhãn/CSV/video nên chỉ cần gán thêm một nhãn là "
            "đổi ⇒ đọc `sinh_luc.jsonl` để biết mask được sinh bằng rev/checkpoint/image_size nào."),
        "phien_ban_sinh": None,     # điền SAU cổng "không công bố": dòng provenance của lần SINH mask
        "ghi_chu_phien_ban_sinh": (
            "`null` = lần chạy này KHÔNG sinh mask mới (chỉ đọc cache hoặc `--limit`) ⇒ KHÔNG có dòng "
            "provenance cho mask cũ, và artifact KHÔNG được suy ra nó là rev này; nguồn duy nhất "
            "là `sinh_luc.jsonl` (một dòng mỗi lần sinh mới)."),
        "so_mask_da_xoa": so_da_xoa,
        "da_xoa_cache_cu": so_da_xoa > 0,
        "bo_qua_file": bo_qua["file"],
        "bo_qua_buoc": bo_qua["buoc"],
        # Hai đại lượng KHÁC luật, đừng gộp thành một số (review 27-11 vòng 2, P3).
        "so_buoc_co_hop_hieu_luc": len(viec),
        "so_buoc_tung_co_hop": len(viec) + sum(bo_qua["buoc"].values()),
        "so_dong_co_bbox_tho": dem_dong_nhan["tho"],
        "so_dong_trung_lap": dem_dong_nhan["trung_lap"],
        "so_dong_cua_buoc_bi_bo": dem_dong_nhan["cua_buoc_bi_bo"],
        "ghi_chu_dem_dong": (
            "`so_dong_co_bbox_tho − so_dong_trung_lap − so_dong_cua_buoc_bi_bo` = số BƯỚC sinh được mask. "
            "Nhãn là append-only nên một bước có thể có NHIỀU dòng có `bbox_dung`: dòng CUỐI mới hiệu lực "
            "(`tong_hop` gộp như vậy) ⇒ `trung_lap` là dòng bị thay thế, KHÔNG phải mất dữ liệu. "
            "`bo_qua_file` đếm theo PHIÊN (không biết số bước của phiên đó), `bo_qua_buoc` đếm theo BƯỚC."),
        "chiet_giai": (
            "Đây là MASK GIẢ: SAM 2 tự cắt từ HỘP của người dùng, không phải GT do người tô. Dùng để "
            "mở rộng phép đo và làm dữ liệu sửa tay; KHÔNG dùng để tuyên bố chất lượng model (mask do "
            "chính model sinh). `qc_dem` đếm các ca nghi (rỗng / <20% / >150% diện tích hộp / chạm "
            "biên khung mà hộp không chạm) — phải xem bằng mắt trước khi coi là GT."),
    }
    # P2-9: lỗi model / đọc frame / GHI file ⇒ KHÔNG công bố, và KHÔNG ghi đè manifest + artifact đã có.
    # `manifest.jsonl` phải nằm DƯỚI cổng này: ghi trước thì một lần chạy lỗi để lại manifest rách và
    # `--qc` sau đó in theo bản rách (review 27-11 vòng 2, P2).
    if (dem["loi_mask"] or dem["loi_shape"] or dem["loi_doc_frame"] or dem["loi_ghi"]
            or len(ban_ghi) < len(viec)):
        # In ĐỦ mọi lỗi mà cổng đang xét: bản trước bỏ sót `loi_shape` ⇒ cổng có, thông điệp không
        # (review độc lập vòng 5, P2) ⇒ người đọc log thấy "lỗi model 0, lỗi ghi 0" mà không hiểu vì
        # sao không công bố.
        print(f"KHÔNG CÔNG BỐ — lỗi model {dem['loi_mask']}, lỗi shape {dem['loi_shape']}, "
              f"lỗi đọc frame {dem['loi_doc_frame']}, lỗi ghi {dem['loi_ghi']}, "
              f"mask {len(ban_ghi)}/{len(viec)}", file=sys.stderr)
        return 1

    # Nguồn gốc của mask ĐÃ SINH: lần chạy chỉ đọc cache khai `git_rev` của CHÍNH NÓ còn
    # `so_mask_moi_sinh = 0` ⇒ không chỗ nào trong repo ghi rev/checkpoint/image_size đã tạo ra 1 251
    # PNG (review độc lập vòng 4, P1). Một dòng mỗi lần có sinh mới; KHÔNG đưa nội dung file này vào
    # `dau_van_tay` (đưa vào thì mỗi lần ghi lại tự phá vân tay ⇒ xoá cache).
    if dem["moi"] > 0 and not args.limit:
        dong = {"do_luc": payload["do_luc"], "git_rev": payload["git_rev"],
                "git_dirty_code": payload["git_dirty_code"],
                "image_size_hieu_luc": payload["image_size_hieu_luc"],
                "checkpoint": args.checkpoint, "model_cfg": args.model_cfg,
                "so_mask_moi_sinh": dem["moi"], "qc_schema": payload["schema"]}
        with (out_dir / "sinh_luc.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(dong, ensure_ascii=False) + "\n")
        payload["phien_ban_sinh"] = dong

    if not args.limit:
        man.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ban_ghi),
                       encoding="utf-8")

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
