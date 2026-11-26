#!/usr/bin/env python3
"""Dựng dataset cho BỘ KIỂM "hệ bám đúng hay sai" (verifier) từ nhãn người dán.

Vì sao có script này
--------------------
`data/nhan/*.jsonl` chứa ~6 000 **bước** có phán quyết (đúng / sai / mất dấu / không có vật). Đó là
nhãn cho *cả bước*, không phải mask. Nhưng nó đủ để dạy một bộ phân loại nhỏ trả lời câu:
*cái ô/mask hệ đang vẽ ở frame này có đúng là vật không?* — đúng thứ chặn ca "bám sang tường cùng
tông" (AGENTS §6: đo 21-11, mask-cos của vùng SAI 0,752–0,989 nằm trong dải ca đúng ⇒ **không có
ngưỡng cos nào tách được**; phải học từ dữ liệu).

Ba loại mẫu (quan trọng: loại 3 chống cho mô hình học mẹo "tường phẳng = sai")
--------------------------------------------------------------------------------
- `pos_sys`  : bước nhãn `dung`  ⇒ cắt **ô hệ đang vẽ** (từ CSV) ⇒ nhãn **1**
- `neg_sys`  : bước nhãn `sai`   ⇒ cắt **ô hệ đang vẽ** (vùng SAI)   ⇒ nhãn **0**
- `pos_gt`   : bước có `bbox_dung` (ô NGƯỜI vẽ quanh vật thật) ⇒ nhãn **1**

Nếu chỉ có `pos_sys`/`neg_sys` thì mô hình học "vùng có texture ≠ vùng trơn" là đủ điểm cao, mà đó
không phải điều ta muốn. `pos_gt` buộc mô hình phải coi *vật thật* là dương **kể cả** trong phiên mà
hệ đang bám sai.

Không dùng
----------
- `khong_co_vat` (vật đã ra khỏi khung — không có gì để cắt), `bo_qua`.
- `mat_dau`: hệ không vẽ gì ⇒ KHÔNG có ô của hệ để cắt. Nhưng nếu có `bbox_dung` thì vẫn sinh `pos_gt`
  (vật còn trong khung, người dán chỉ đúng chỗ) — đó là mẫu dương khó nhất.

Chống rò rỉ
-----------
Tách **theo phiên** (một phiên chỉ nằm ở train HAY val), không tách theo frame: các frame trong cùng
phiên gần như trùng nhau (cùng vật, cùng nền) nên tách theo frame sẽ cho điểm val đẹp giả.

Số liệu và mọi thứ khác đều ghi vào artifact có `git_rev` + `git_dirty_code` + `lenh` + `do_luc`
(AGENTS §6: số không có provenance thì không được trích).

    python scripts/build_verifier_dataset.py                       # dựng dataset + in số
    python scripts/build_verifier_dataset.py --out data/verifier    # chọn thư mục
    python scripts/build_verifier_dataset.py --ti-le-val 0.25       # đổi tỉ lệ phiên val
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

import cv2  # noqa: E402

from tools import label_ui as L  # noqa: E402  (dùng CHUNG phép ánh xạ bước→frame, không viết lại)

DATA = ROOT / "data"
NHAN = DATA / "nhan"
CROP = 64          # cạnh ảnh ra (px)
MARGIN = 0.15      # nới ô thêm 15% mỗi phía để có ngữ cảnh — bám sai thường lệch nửa ô
NHAN_DUNG, NHAN_SAI = "dung", "sai"


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=False).stdout.strip()
    except OSError:
        return ""


def doc_nhan_hieu_luc(tep: pathlib.Path) -> dict[int, dict]:
    """(phien, buoc) → nhãn CUỐI (append-only: dòng cuối là nhãn hiệu lực, khớp `--tong-hop`)."""
    ra: dict[int, dict] = {}
    for dong in tep.read_text(encoding="utf-8").splitlines():
        if not dong.strip():
            continue
        try:
            r = json.loads(dong)
        except ValueError:
            continue
        if not isinstance(r, dict) or r.get("buoc") is None or not r.get("nhan"):
            continue
        ra[int(r["buoc"])] = r
    return ra


def o_he_dang_ve(f: dict) -> list[int] | None:
    """Ô của HỆ tại bước đó (`doc_phien` đã dựng từ `center_x/y` + `bbox_w/h`).

    `None` khi CSV KHÔNG có cỡ ô — 46/78 CSV trong `data/` sinh **trước 21-11**, lúc `CSV_HEADER`
    chưa có `bbox_w/bbox_h` (xem `src/metrics_logger.py`). Với các phiên đó không dựng lại được vùng
    hệ đang vẽ ⇒ chỉ còn mẫu `pos_gt`, KHÔNG được bịa ô từ trung vị phiên khác.
    """
    b = f.get("bbox")
    if not b or len(b) != 4:
        return None
    x1, y1, x2, y2 = (float(v) for v in b)
    if not all(v == v and abs(v) != float("inf") for v in (x1, y1, x2, y2)):
        return None
    if x2 - x1 <= 1 or y2 - y1 <= 1:
        return None
    return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]


def noi_o(box: list[int], rong: int, cao: int, margin: float = MARGIN) -> tuple[int, int, int, int]:
    """Nới ô rồi KẸP vào khung; trả None nếu sau khi kẹp không còn diện tích."""
    x1, y1, x2, y2 = box
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    x1, y1 = int(x1 - mx), int(y1 - my)
    x2, y2 = int(x2 + mx), int(y2 + my)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(rong, x2), min(cao, y2)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return (0, 0, 0, 0)
    return (x1, y1, x2, y2)


def dau_van_tay(margin: float, ti_le_val: float = 0.25, chia_theo: str = "ngay") -> str:
    """Vân tay của (tham số cắt + NGUỒN). Cache ảnh dùng lại theo `{loai}_b{buoc}` nên nếu không có
    cái này: đổi `--margin` hoặc CSV được sinh lại (buoc dịch) ⇒ phục vụ **ảnh cũ + nhãn mới** mà
    artifact vẫn ghi tham số mới (review độc lập 26-11, P2).

    Đọc `mtime_ns` + `size` của MỌI CSV và video có nhãn ⇒ nguồn đổi là vân tay đổi.
    """
    h = hashlib.sha256(f"crop={CROP}|margin={margin}|val={ti_le_val}|chia={chia_theo}|".encode())
    for tep in sorted(NHAN.glob("*.jsonl")):
        phien = tep.stem
        for f in (DATA / f"{phien}_metrics.csv", DATA / f"{phien}.mp4"):
            try:
                st = f.stat()
                h.update(f"{f.name}:{st.st_mtime_ns}:{st.st_size};".encode())
            except OSError:
                h.update(f"{f.name}:-;".encode())
    return h.hexdigest()[:16]


def don_cache_neu_can(out_dir: pathlib.Path, van_tay: str) -> bool:
    """Xoá `train/`+`val/` của lần dựng trước nếu vân tay khác. Trả True nếu ĐÃ xoá."""
    tep = out_dir / ".dau_van_tay"
    cu = tep.read_text(encoding="utf-8").strip() if tep.is_file() else None
    if cu == van_tay:
        return False
    import shutil
    for con in ("train", "val"):
        shutil.rmtree(out_dir / con, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    tep.write_text(van_tay, encoding="utf-8")
    return cu is not None


def nhom_cua(phien: str, chia_theo: str) -> str:
    """Nhóm dùng để chia train/val.

    `ngay` (mặc định): tiền tố NGÀY trong tên phiên (`demoip_1124-141352` ⇒ `1124`). Cần vì chia
    theo phiên **không** cách ly cảnh: 6/6 phiên val từng có phiên CÙNG NGÀY ở train (cùng phòng,
    cùng vật, cùng ánh sáng) ⇒ điểm val là **cận trên**, không phải "phiên chưa thấy" (review độc
    lập 26-11 vòng 2).
    `phien`: mỗi phiên một nhóm (giữ để so sánh hai cách chia).
    """
    if chia_theo != "ngay":
        return phien
    # `demoip_1124-141352` → `1124`; `fast_1029-193552` → `1029`; tên không có ngày ⇒ giữ nguyên
    duoi = phien.split("_", 1)[1] if "_" in phien else phien
    return duoi.split("-", 1)[0] if "-" in duoi else phien


def tach(nhom: str, ti_le_val: float) -> str:
    """train/val theo NHÓM (ngày hoặc phiên), tất định theo tên — chạy lại ra y hệt."""
    h = int(hashlib.sha256(nhom.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "val" if h < ti_le_val else "train"


def dung_dataset(out_dir: pathlib.Path, ti_le_val: float, margin: float,
                 chia_theo: str = "ngay") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    van_tay = dau_van_tay(margin, ti_le_val, chia_theo)
    da_xoa = don_cache_neu_can(out_dir, van_tay)
    mong_doi, bo_qua, thieu_video, nhieu_nguoi = [], {}, [], {}

    for tep in sorted(NHAN.glob("*.jsonl")):
        phien = tep.stem
        csv_p = DATA / f"{phien}_metrics.csv"
        if not csv_p.is_file():
            thieu_video.append(f"{phien} (thiếu CSV)")
            continue
        try:
            d = L.doc_phien_cached(csv_p)
        except (OSError, ValueError) as e:
            thieu_video.append(f"{phien} ({e})")
            continue
        if not L._mo_video(phien):
            thieu_video.append(f"{phien} (không mở được video)")
            continue
        _, fps, n_frame, rong, cao = L._mo_video(phien)
        nhan = doc_nhan_hieu_luc(tep)
        nhom = nhom_cua(phien, chia_theo)
        split = tach(nhom, ti_le_val)
        # Gộp nhãn theo `buoc` là BỎ người dán ("dòng cuối thắng"). Hôm nay mọi phiên chỉ 1 người,
        # nhưng khi có người thứ 2 (đúng quy trình 2 người của repo) thì trộn 2 phán quyết mà IM LẶNG
        # ⇒ phải lộ ra (review 26-11, P2).
        nguoi = {str(r.get("nguoi_gan") or "") for r in nhan.values()} - {""}
        if len(nguoi) > 1:
            nhieu_nguoi[phien] = sorted(nguoi)

        for buoc, r in nhan.items():
            nhan_b = r.get("nhan")
            if nhan_b in ("khong_co_vat", "bo_qua"):
                bo_qua[nhan_b] = bo_qua.get(nhan_b, 0) + 1
                continue
            if not 0 <= buoc < len(d["frames"]):
                bo_qua["buoc-ngoai-dai"] = bo_qua.get("buoc-ngoai-dai", 0) + 1
                continue
            idx, loi = L.chi_so_khung(phien, buoc)
            if idx is None:
                bo_qua[f"khong-anh-xa-duoc: {loi}"] = bo_qua.get(f"khong-anh-xa-duoc: {loi}", 0) + 1
                continue
            f = d["frames"][buoc]

            # Đếm ĐÚNG lý do bị bỏ: 46/78 CSV sinh trước 21-11 không có `bbox_w/h` ⇒ mất rất nhiều
            # mẫu. Không đếm thì không ai audit được "vì sao chỉ có 414 âm" (review 26-11, P2).
            if nhan_b in (NHAN_DUNG, NHAN_SAI) and o_he_dang_ve(f) is None:
                khoa = f"{nhan_b}-khong-co-o-he"
                bo_qua[khoa] = bo_qua.get(khoa, 0) + 1
            if nhan_b == "mat_dau" and not r.get("bbox_dung"):
                bo_qua["mat_dau-khong-co-GT"] = bo_qua.get("mat_dau-khong-co-GT", 0) + 1

            for loai, box, nhan_so in (
                ("pos_sys", o_he_dang_ve(f) if nhan_b == NHAN_DUNG else None, 1),
                ("neg_sys", o_he_dang_ve(f) if nhan_b == NHAN_SAI else None, 0),
                ("pos_gt", list(r["bbox_dung"]) if r.get("bbox_dung") else None, 1),
            ):
                if not box:
                    continue
                h = noi_o(box, rong, cao, margin)
                if h == (0, 0, 0, 0):
                    bo_qua[f"{loai}-ô-rỗng"] = bo_qua.get(f"{loai}-ô-rỗng", 0) + 1
                    continue
                mong_doi.append({"phien": phien, "buoc": buoc, "frame_idx": idx,
                                 "loai": loai, "nhan": nhan_so, "nhan_nguoi": nhan_b,
                                 "o_cat": list(h), "split": split, "nhom": nhom})

    # Cắt ảnh TẦN TỰ dưới một khoá: OpenCV/FFmpeg không thread-safe cho một VideoCapture
    # (AGENTS §6: prefetch song song từng làm `Assertion fctx->async_lock failed` và abort tiến trình).
    da_cat, loi_cat = 0, 0
    for m in mong_doi:
        mo = L._mo_video(m["phien"])
        if not mo:
            loi_cat += 1
            continue
        cap, _, n, rong, cao = mo
        thu_muc = out_dir / m["split"] / m["phien"]
        thu_muc.mkdir(parents=True, exist_ok=True)
        dich = thu_muc / f"{m['loai']}_b{m['buoc']:05d}.jpg"
        m["anh"] = str(dich.relative_to(out_dir))
        if dich.is_file() and dich.stat().st_size > 0:
            da_cat += 1
            continue
        with L._CAP_LOCK:
            if not cap.set(cv2.CAP_PROP_POS_FRAMES, m["frame_idx"]):
                loi_cat += 1
                continue
            # `set()` có thể trả True mà vẫn đứng ở keyframe gần nhất ⇒ phải ĐỌC LẠI vị trí, nếu không
            # crop của frame KHÁC được ghi với nhãn của bước này, im lặng (review 26-11 vòng 2, P2).
            vi_tri = int(round(cap.get(cv2.CAP_PROP_POS_FRAMES) or m["frame_idx"]))
            if abs(vi_tri - m["frame_idx"]) > 1:
                loi_cat += 1
                continue
            ok, khung = cap.read()
        if not ok or khung is None:
            loi_cat += 1
            continue
        x1, y1, x2, y2 = m["o_cat"]
        cat = khung[y1:y2, x1:x2]
        if cat.size == 0:
            loi_cat += 1
            continue
        cat = cv2.resize(cat, (CROP, CROP), interpolation=cv2.INTER_AREA)
        if not cv2.imwrite(str(dich), cat, [int(cv2.IMWRITE_JPEG_QUALITY), 92]):
            loi_cat += 1
            continue
        da_cat += 1

    mau = [m for m in mong_doi if m.get("anh") and (out_dir / m["anh"]).is_file()]
    co_mau = {m["phien"] for m in mau}
    phien_0_mau = sorted({p.stem for p in NHAN.glob("*.jsonl")} - co_mau)
    manifest = out_dir / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in mau),
                        encoding="utf-8")

    def dem(khoa, loc=lambda m: True):
        ra: dict = {}
        for m in mau:
            if loc(m):
                k = m[khoa]
                ra[k] = ra.get(k, 0) + 1
        return ra

    return {
        "so_mau": len(mau),
        "so_mau_du_kien": len(mong_doi),
        "cat_loi": loi_cat,
        "theo_split": dem("split"),
        "theo_nhan": dem("nhan"),
        "theo_loai": dem("loai"),
        "theo_split_va_nhan": {
            f"{s}/{v}": sum(1 for m in mau if m["split"] == s and m["nhan"] == v)
            for (s, v) in sorted({(m["split"], m["nhan"]) for m in mau})},
        "so_phien": len({m["phien"] for m in mau}),
        "phien_thieu_video": thieu_video,
        # Phiên có nhãn mà ra 0 mẫu (CSV cũ không có ô của hệ + không vẽ ô GT) — im lặng chỗ này làm
        # "số phiên dùng được" không kiểm được (review 26-11, P2).
        "phien_0_mau": phien_0_mau,
        "phien_nhieu_nguoi_dan": nhieu_nguoi,
        "bo_qua": bo_qua,
        "crop_px": CROP,
        "margin": margin,
        "dau_van_tay": van_tay,
        "chia_theo": chia_theo,
        "so_nhom": {"train": len({m["nhom"] for m in mau if m["split"] == "train"}),
                    "val": len({m["nhom"] for m in mau if m["split"] == "val"})},
        "da_xoa_cache_cu": da_xoa,
        "ti_le_val": ti_le_val,
        "manifest": str(manifest.relative_to(ROOT)) if manifest.is_relative_to(ROOT) else str(manifest),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/verifier", help="thư mục ra (mặc định data/verifier)")
    ap.add_argument("--ti-le-val", type=float, default=0.25, help="tỉ lệ PHIÊN dành cho val")
    ap.add_argument("--margin", type=float, default=MARGIN, help="nới ô trước khi cắt (0.15 = 15%%)")
    ap.add_argument("--chia-theo", choices=("ngay", "phien"), default="ngay",
                    help="chia train/val theo NGÀY (mặc định, cách ly cảnh) hay theo từng phiên")
    ap.add_argument("--metrics", help="file JSON artifact (mặc định: <out>_metrics.json)")
    args = ap.parse_args()

    t0 = time.time()
    out_dir = (ROOT / args.out) if not pathlib.Path(args.out).is_absolute() else pathlib.Path(args.out)
    kq = dung_dataset(out_dir, args.ti_le_val, args.margin, args.chia_theo)
    payload = {
        "schema": 1,
        "do_luc": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "lenh": " ".join(sys.argv),
        "git_rev": git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        # Bẩn chỉ vì `data/` (dataset/artifact sinh ra) thì KHÔNG tính là bẩn mã — đúng quy ước
        # `git_dirty_code` của repo để số đo còn tái lập được.
        "git_dirty_code": bool(git("status", "--porcelain", "--", ".", ":!data")),
        "giay": round(time.time() - t0, 1),
        "chiet_giai": (
            "pos_sys = ô HỆ vẽ ở bước nhãn 'dung' (nhãn 1); neg_sys = ô HỆ vẽ ở bước nhãn 'sai' "
            "(nhãn 0); pos_gt = ô NGƯỜI vẽ (bbox_dung) ở bất kỳ bước nào có nó (nhãn 1 — chống mẹo "
            "'tường phẳng = sai'). Tách train/val THEO PHIÊN bằng sha256(tên phiên) ⇒ chạy lại ra y "
            "hệt, và cùng một phiên không nằm ở cả hai phía. Nhãn là phán quyết của MỘT người "
            "(`binh`) cho CẢ bước, không phải mask — hạn chế này phải nêu khi trích số."),
        **kq,
    }
    p = pathlib.Path(args.metrics) if args.metrics else out_dir.with_name(out_dir.name + "_metrics.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps({k: payload[k] for k in ("so_mau", "so_mau_du_kien", "cat_loi", "theo_split",
                                              "theo_nhan", "theo_loai", "so_phien", "giay")},
                     ensure_ascii=False, indent=1))
    if kq["phien_thieu_video"]:
        print(f"BỎ QUA {len(kq['phien_thieu_video'])} phiên (thiếu CSV/video): "
              f"{kq['phien_thieu_video'][:3]}…", file=sys.stderr)
    print(f"→ {p}")
    return 0 if kq["so_mau"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
