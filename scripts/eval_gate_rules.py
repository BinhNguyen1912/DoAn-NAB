"""Chấm các LUẬT của cổng "nghi đổi đối tượng" trên CSV đã ghi — KHÔNG model, không đụng runtime.

Vì sao có (24-11-2026): người dùng báo **"di chuyển vật nhanh quá thì bị nghi"**. Kiểm bằng ảnh phiên
`demoip_1124-144057` (f47/f48): cái thìa **vẫn nằm trong ô** ⇒ báo oan thật. Trước khi sửa thuật toán
phải trả lời được: **luật mới giảm được bao nhiêu lần báo oan, và có BỎ SÓT ca báo đúng nào không** —
trên chính các phiên đã ghi, không phải bằng cảm giác.

Ba luật được chấm (tất cả dùng cùng `IdentityWatch` + `settle_steps`):

  `hien_tai`  — `search_window_radius` như đang ship: `min(max(0,10·diag, 1,5·max(w,h)), 0,25·diag)`.
  `theo_dt`   — trần bán kính NỚI THEO THỜI GIAN: `cap = max(0,25·diag, TOC_DO_TOI_DA × dt)` với
                `dt` = `latency_ms` của frame (khoảng cách giữa 2 lần VOS; 1 worker ⇒ xấp xỉ đúng).
                Vì sao: ngưỡng hiện tại tính **px/bước**, nên máy càng chậm (bước càng dài) thì cùng một
                tốc độ tay càng dễ vượt ngưỡng oan.
  `theo_dt_va_dien_tich` — như `theo_dt`, CỘNG điều kiện `mask_area` phải đổi trong dải
                [`AREA_BAND_THAP`, `AREA_BAND_CAO`] × trung vị 5 mẫu trước. Vì sao thử: cú nhảy báo oan
                trùng với mask TRÀN nền (f48 ×2,9 · f82 ×4,0 · f92 ×3,3).

Chạy:

    python scripts/eval_gate_rules.py --glob 'data/demoip_*_metrics.csv' \
        --out data/eval_gate_rules_2026-11-24_metrics.json

ĐỌC SỐ CHO ĐÚNG (script tự in lại các cảnh báo này):
  - `ca_dung` = các (phiên, frame) ĐÃ BIẾT là báo đúng (kiểm bằng ảnh). Hiện chỉ có **1** ca có đủ cột
    để chấm ⇒ **không** kết luận được "giảm báo oan mà không bỏ sót" theo nghĩa thống kê; chỉ nói được
    "ca đúng đã biết còn bắt hay không".
  - `ca_sai` = các (phiên, frame) ĐÃ BIẾT là báo oan (kiểm bằng ảnh). Hiện có **1** ca.
  - Phiên thiếu cột `bbox_w/bbox_h/mask_area` bị **loại khỏi mẫu số** (ô dựng lại rỗng ⇒ cổng không thể
    bật) — cùng luật với `scripts/replay_latch_settle.py`.
  - `dt` lấy từ `latency_ms` của CSV: đó là thời gian suy luận của frame, **xấp xỉ** khoảng cách giữa 2
    lần VOS trên đường `--smooth` (1 worker). Không phải timestamp thật ⇒ số `theo_dt` là **so sánh
    tương đối giữa hai luật trên cùng dữ liệu**, không phải số của phiên live.
"""
import argparse
import csv
import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.identity_guard import (  # noqa: E402
    DEFAULT_SETTLE_STEPS,
    TRANG_THAI_CHUA_XAC_MINH,
    TRANG_THAI_NGHI,
    IdentityWatch,
    search_window_radius,
)

ZERO = (0, 0, 0, 0)
FRAME_SHAPE = (480, 640)          # relay/webcam demo; CSV không lưu kích thước khung
TOC_DO_TOI_DA = 1500.0            # px/s — tay cầm vật lia ngang khung 640 px trong ~0,4 s
AREA_BAND_THAP = 0.55             # mask nhỏ hơn 0,55× trung vị trước ⇒ co bất thường
AREA_BAND_CAO = 2.20              # mask lớn hơn 2,20× ⇒ tràn nền (đo f48 ×2,9 · f82 ×4,0)

# Ca ĐÃ KIỂM BẰNG **Ô VẼ TỪ CSV LÊN FRAME** (không đọc ô vàng trên HUD — HUD vẽ kết quả của bước
# KHÁC, đã làm tôi kết luận sai 1 lần). Ảnh: `data/tmp_an/v2_*/v3_*.png`, tên theo `frame_idx`.
#
# NGỮ NGHĨA NHÃN = "danh tính vật bị bám có ĐỔI không" (đúng tên cổng "nghi đổi đối tượng"):
#   DUNG     = ô đi sang VẬT KHÁC           -> cổng báo là ĐÚNG
#   BAM_LAI  = ô đi TỪ nền VỀ ĐÚNG vật      -> danh tính không đổi, cổng báo là SAI (nhưng lỗi thật
#              là cổng báo MUỘN: nó không báo lúc ô trôi khỏi vật)
#   TROI     = ô đi TỪ vật SANG NỀN         -> danh tính không "đổi", nhưng hệ đang bám vùng vô nghĩa
CA_DUNG = [("demoip_1124-125109_metrics.csv", 137)]     # ô trên TÓC, thìa ở x≈310 (ảnh v3_125109_f137)
CA_SAI = [
    ("demoip_1124-141352_metrics.csv", 29),             # ô VỀ ĐÚNG thìa, trước ở nền (v2_/v3_ f29)
    ("demoip_1124-144057_metrics.csv", 48),             # ô ở NỀN 139x397, mask tràn 2,9x (v2_f48)
    ("demoip_1124-144057_metrics.csv", 97),             # ô VỀ ĐÚNG thìa, trước ở nền (v3_f97)
]


def doc_cot(path):
    """CSV ⇒ list dict: ô (dựng lại từ tâm + kích thước), mask_area, dt ước lượng."""
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            def so(k):
                v = r.get(k)
                if v is None or v == "":
                    return None
                try:
                    return float(v)
                except ValueError:
                    return None
            cx, cy, w, h = so("center_x"), so("center_y"), so("bbox_w"), so("bbox_h")
            if None in (cx, cy, w, h) or not w or not h:
                bbox = ZERO
            else:
                bbox = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            out.append({
                "frame_idx": int(float(r.get("frame_idx") or 0)),
                "ghi_nghi": (r.get("nghi_doi_tuong") or "").strip(),
                "bbox": bbox,
                "mask_area": so("mask_area"),
                "dt": (so("latency_ms") or 0.0) / 1000.0,
            })
    return out


TRAN_TOI_DA_RATIO = 0.35          # trần bán kính khi bước VOS dài (280 px ở 640×480)


def _tam(bbox):
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def _nhay(prev, cur, dt, luat, van_toc=(0.0, 0.0)):
    """True nếu bước này là cú nhảy theo LUẬT đang chấm.

    `hien_tai`            : bán kính cố định như đang ship (0,10·diag … trần 0,25·diag).
    `theo_dt`             : bán kính = clamp(TỐC_ĐỘ×dt, bán_kính_gốc, 0,35·diag) — bước VOS càng dài
                            (máy chậm) thì càng nới, nhưng không vượt 280 px.
    `van_toc_lich_su`     : dự đoán `expected = prev + v` với `v` = trung vị Δ tâm 3 bước TRƯỚC —
                            đi đều nhanh thì KHÔNG bị coi là nhảy; đổi hướng đột ngột thì vẫn bị.
    `theo_dt_va_dien_tich`: `theo_dt` + điều kiện `mask_area` ngoài dải (đo được là BỎ SÓT ca đúng).
    """
    if not prev or not cur or tuple(prev) == ZERO or tuple(cur) == ZERO:
        return False
    goc = search_window_radius(prev, FRAME_SHAPE)
    diag = math.hypot(*FRAME_SHAPE[::-1])
    px, py = _tam(prev)
    cx, cy = _tam(cur)
    ex, ey = px, py
    if luat == "hien_tai":
        ban_kinh = goc
    elif luat in ("theo_dt", "theo_dt_va_dien_tich"):
        ban_kinh = min(max(goc, TOC_DO_TOI_DA * dt), TRAN_TOI_DA_RATIO * diag)
    elif luat.startswith("chi_khi_cham_"):
        # LUẬT MỚI (từ ảnh 24-11): 2 ca OAN xảy ra ở bước NHANH (131–158 ms ⇒ 1 738–3 607 px/s), 2 ca
        # ĐÚNG ở bước CHẬM (293–352 ms ⇒ 813–870 px/s). Nên: chỉ báo khi tốc độ tâm ≤ ngưỡng.
        # CƠ SỞ: một cú nhảy "nhanh bất thường" là dấu hiệu vật THẬT SỰ đi nhanh (mask bám đúng), còn
        # đổi vật thường xảy ra khi tay đang chậm (vật bị mất dấu / che). CHỈ 4 ca nhãn, 2 phiên, khác
        # tải máy ⇒ đây là GIẢ THUYẾT, phải xác nhận trên phiên live mới.
        nguong = float(luat.rsplit("_", 1)[1])
        ban_kinh = goc
        toc_do = math.hypot(cx - px, cy - py) / dt if dt > 0 else float("inf")
        return math.hypot(cx - px, cy - py) > ban_kinh and toc_do <= nguong
    elif luat == "van_toc_lich_su":
        ban_kinh = goc
        ex, ey = px + van_toc[0], py + van_toc[1]
    else:
        raise ValueError(luat)
    return math.hypot(cx - ex, cy - ey) > ban_kinh


def _dien_tich_bat_thuong(areas, i):
    """`mask_area[i]` có nằm ngoài dải [0,55; 2,20] × trung vị 5 mẫu TRƯỚC không (None = chưa đủ mẫu)."""
    truoc = [a for a in areas[max(0, i - 5):i] if a]
    if not truoc or areas[i] is None:
        return None
    med = statistics.median(truoc)
    if med <= 0:
        return None
    ti_le = areas[i] / med
    return not (AREA_BAND_THAP <= ti_le <= AREA_BAND_CAO)


def chay(rows, luat, settle_steps=DEFAULT_SETTLE_STEPS):
    """Phát lại chuỗi ô ⇒ số lần báo / frame ẩn / frame "chưa xác minh" / frame báo của luật."""
    watch = IdentityWatch(settle_steps=settle_steps)
    areas = [r["mask_area"] for r in rows]
    dem = {TRANG_THAI_NGHI: 0, TRANG_THAI_CHUA_XAC_MINH: 0}
    fires, prev = [], None
    watch_frames = []
    tam_hist = []                      # tâm của các bước CÓ mask, mới nhất ở cuối
    for i, r in enumerate(rows):
        co_mask = r["mask_area"] is not None and r["mask_area"] > 0
        van_toc = (0.0, 0.0)
        if len(tam_hist) >= 2:
            d = [(tam_hist[j][0] - tam_hist[j-1][0], tam_hist[j][1] - tam_hist[j-1][1])
                 for j in range(max(1, len(tam_hist) - 3), len(tam_hist))]
            van_toc = (statistics.median(dx for dx, _ in d), statistics.median(dy for _, dy in d))
        nhay = _nhay(prev, r["bbox"], r["dt"], luat, van_toc=van_toc)
        if nhay and luat == "theo_dt_va_dien_tich":
            nhay = bool(_dien_tich_bat_thuong(areas, i))
        dang_nghi_truoc = watch.nghi
        # `nhay` của LUẬT đang chấm được TRUYỀN VÀO state machine thật (`IdentityWatch`), không chép
        # lại state machine ở script (hai bản sẽ trôi khỏi nhau).
        watch.update(prev if prev else ZERO, r["bbox"], FRAME_SHAPE, co_mask=co_mask, nhay=nhay)
        if watch.nghi and not dang_nghi_truoc:
            fires.append(r["frame_idx"])
        watch_frames.append(watch.trang_thai)
        if watch.trang_thai in dem:
            dem[watch.trang_thai] += 1
        prev = r["bbox"] if co_mask else ZERO
        if co_mask:
            tam_hist.append(_tam(r["bbox"]))
        else:
            tam_hist.clear()           # mất dấu ⇒ vận tốc cũ vô nghĩa
    # `duoi` = frame `chua_xac_minh` SAU lần báo CUỐI. Đây mới là chi phí người xem thấy: `chua_xac_minh`
    # không có đường tự xoá (chỉ `r`/`c`/reacquire) nên một cú nhảy ở nửa sau là cả phần còn lại của
    # phiên mất mask tô + mất quỹ đạo. Đo 24-11 (`144057`): 77,6 % phiên không có mask tin cậy
    # trong khi chỉ 17,3 % frame "ẩn" — nếu chỉ đọc `frame_an` thì đánh giá thấp chi phí 4,5 lần.
    duoi = 0
    if fires:
        # lần báo cuối ⇒ đếm từ frame đó tới hết phiên những frame đang `chua_xac_minh`
        # (`nghi` tự hết sau `settle` bước nên đuôi thật nằm ở `chua_xac_minh`)
        i_cuoi = max(i for i, f in enumerate(watch_frames)
                     if watch_frames[max(0, i - 1)] != TRANG_THAI_CHUA_XAC_MINH
                     and watch_frames[i] == TRANG_THAI_CHUA_XAC_MINH) if any(
            f == TRANG_THAI_CHUA_XAC_MINH for f in watch_frames) else None
        if i_cuoi is not None:
            duoi = sum(1 for f in watch_frames[i_cuoi:] if f == TRANG_THAI_CHUA_XAC_MINH)
    return {"fire": len(fires), "fire_frames": fires, "duoi": duoi,
            "frame_an": dem[TRANG_THAI_NGHI],
            "frame_chua_xac_minh": dem[TRANG_THAI_CHUA_XAC_MINH]}


def khop_nhan(rows, settle_steps=DEFAULT_SETTLE_STEPS):
    """% frame mà phát lại với LUẬT HIỆN TẠI khớp cột `nghi_doi_tuong` đã ghi của phiên.

    Vì sao cần: pool CSV trộn ≥3 hành vi cổng (ẩn-vĩnh-viễn trước 24-11 · `settle_steps=8` · re-ID
    bật/tắt). Gộp chúng lại rồi công bố "% frame ẩn" là đo một thứ không tồn tại — review độc lập
    24-11 đo được chỉ **3/14** phiên khớp 100 % (nặng nhất 423 vs 16 frame ẩn). Chỉ phiên khớp 100 %
    mới được dùng để SO SÁNH luật; phiên lệch vẫn dùng được làm NHÃN nhưng không dùng làm chi phí.
    """
    watch = IdentityWatch(settle_steps=settle_steps)
    ghi = [r.get("ghi_nghi", "") in ("1", "True", "true") for r in rows]
    if ghi is None:
        return None, 0
    lai, prev = [], None
    for r in rows:
        co_mask = r["mask_area"] is not None and r["mask_area"] > 0
        watch.update(prev if prev else ZERO, r["bbox"], FRAME_SHAPE, co_mask=co_mask)
        lai.append(watch.nghi)
        prev = r["bbox"] if co_mask else ZERO
    n = sum(1 for a, b in zip(ghi, lai) if a == b)
    return round(100.0 * n / len(rows), 1), len(rows)


def doc_danh_sach_dong_bang(path):
    """Danh sách tên phiên được phép dùng để SO SÁNH CHI PHÍ, đọc từ file đã commit.

    Vì sao phải đóng băng: nếu lọc "phiên khớp 100 %" bằng CHÍNH luật đang chấm thì đổi luật ⇒ nhiều
    phiên rớt khỏi mẫu số ⇒ chi phí **tự rẻ đi** mà không ai sửa gì (review độc lập 24-11, P1).
    """
    if not path.exists():
        return None
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("phien", []))
    except (OSError, ValueError):
        return None


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Chấm luật cổng nghi trên CSV (không model).")
    ap.add_argument("--glob", default="data/demoip_*_metrics.csv")
    ap.add_argument("--settle", type=int, default=DEFAULT_SETTLE_STEPS)
    ap.add_argument("--out", default=None)
    ap.add_argument("--config-list", default="data/eval_gate_config_list.json",
                    help="danh sách phiên ĐÓNG BĂNG dùng để so sánh chi phí")
    args = ap.parse_args(argv)

    paths = sorted(Path(REPO_ROOT).glob(args.glob))
    if not paths:
        print(f"[LOI] không có CSV nào khớp {args.glob!r}", file=sys.stderr)
        return 1

    luat_list = ["hien_tai", "theo_dt", "van_toc_lich_su", "theo_dt_va_dien_tich",
                 "chi_khi_cham_600", "chi_khi_cham_900", "chi_khi_cham_1200", "chi_khi_cham_1500"]
    phien, bo_qua = [], 0
    for p in paths:
        rows = doc_cot(p)
        if not rows:
            bo_qua += 1
            continue
        if not any(r["mask_area"] is not None for r in rows):
            bo_qua += 1
            continue                    # thiếu cột ⇒ ô rỗng ⇒ cổng không thể bật
        khop, _ = khop_nhan(rows, args.settle)
        phien.append({
            "ten": p.name,
            "n": len(rows),
            "khop_pct": khop,
            "luat": {k: chay(rows, k, args.settle) for k in luat_list},
        })
    if not phien:
        print("[LOI] không phiên nào ĐO ĐƯỢC (thiếu cột mask_area)", file=sys.stderr)
        return 1

    # SO SÁNH CHI PHÍ chỉ trên nhóm phiên ĐÓNG BĂNG (cùng một hành vi cổng)
    dong_bang = doc_danh_sach_dong_bang(Path(REPO_ROOT) / args.config_list)
    if dong_bang is None:
        dung_config = [p for p in phien if p.get("khop_pct") == 100.0]
        Path(REPO_ROOT, args.config_list).write_text(
            json.dumps({"phien": sorted(p["ten"] for p in dung_config),
                        "ghi_chu": "sinh tự động từ các phiên khớp 100 % với cột nghi_doi_tuong",
                        "do_luc": time.strftime("%Y-%m-%dT%H:%M:%S")},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[cong] ĐÓNG BĂNG danh sách {len(dung_config)} phiên vào {args.config_list} "
              f"— từ lần sau danh sách này KHÔNG phụ thuộc luật đang chấm")
    else:
        dung_config = [p for p in phien if p["ten"] in dong_bang]
        print(f"[cong] dùng danh sách ĐÓNG BĂNG {args.config_list}: {len(dung_config)}/"
              f"{len(dong_bang)} phiên có mặt")
    nhom = dung_config or phien
    n_nhom = sum(p["n"] for p in nhom)
    tong = {}
    for k in luat_list:
        an = sum(p["luat"][k]["frame_an"] for p in nhom)
        cxm = sum(p["luat"][k]["frame_chua_xac_minh"] for p in nhom)
        tong[k] = {
            "so_phien": len(nhom), "so_frame": n_nhom,
            "fire": sum(p["luat"][k]["fire"] for p in nhom),
            "frame_an": an,
            "pct_frame_an": round(100.0 * an / n_nhom, 2),
            "frame_chua_xac_minh": cxm,
            "pct_frame_chua_xac_minh": round(100.0 * cxm / n_nhom, 2),
            "pct_frame_khong_tin_cay": round(100.0 * (an + cxm) / n_nhom, 2),
            "duoi": sum(p["luat"][k]["duoi"] for p in nhom),
            "pct_duoi": round(100.0 * sum(p["luat"][k]["duoi"] for p in nhom) / n_nhom, 2),
            "phien_co_bao": sum(1 for p in nhom if p["luat"][k]["fire"]),
        }

    def _bat(k, ca):
        for ten, f in ca:
            for p in phien:
                if p["ten"] == ten:
                    if f in p["luat"][k]["fire_frames"]:
                        return True
                    # ca báo đúng có thể nằm GIỮA một đợt latch đã bật từ frame trước ⇒ chấp nhận
                    # nếu có lần báo trong vòng `settle` frame trước đó.
                    return any(0 < f - g <= args.settle for g in p["luat"][k]["fire_frames"])
        return None                      # None = không có dữ liệu để chấm

    for k in luat_list:
        tong[k]["bat_ca_dung"] = {
            f"{t}#{f}": _bat(k, [(t, f)]) for t, f in CA_DUNG}
        tong[k]["bat_ca_sai"] = {
            f"{t}#{f}": _bat(k, [(t, f)]) for t, f in CA_SAI}

    rev = _git("rev-parse", "--short", "HEAD")
    dirty_code = bool(_git("status", "--porcelain", "--", ".", ":!data"))
    payload = {
        "git_rev": rev, "git_dirty_code": dirty_code,
        "lenh": " ".join(sys.argv), "do_luc": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "frame_shape": list(FRAME_SHAPE), "settle_steps": args.settle,
        "tham_so": {"toc_do_toi_da_px_s": TOC_DO_TOI_DA,
                    "area_band": [AREA_BAND_THAP, AREA_BAND_CAO]},
        "ca_dung": CA_DUNG, "ca_sai": CA_SAI,
        "so_phien_doc_duoc": len(phien), "so_phien_bo_qua": bo_qua,
        "so_phien_khop_100pct": len(dung_config),
        "ghi_chu_nhan": "NHÃN TẠM: ca 'SAI' (144057#48) có phép thử SUY BIẾN (ô phủ 18% khung) — "
                        "chưa có nhãn theo luật fill>=0.5 viết trước; xem docstring CA_SAI.",
        "tong": tong, "phien": phien,
    }

    print(f"[cong] {len(phien)} phiên ĐỌC ĐƯỢC (bỏ {bo_qua} phiên thiếu cột `mask_area`); "
          f"nhóm SO SÁNH CHI PHÍ = **{len(nhom)} phiên / {n_nhom} frame** "
          f"(mọi số dưới đây cùng mẫu số này)")
    lech = [(p["ten"], p["khop_pct"]) for p in phien if p.get("khop_pct") is not None
            and p["khop_pct"] != 100.0]
    if lech:
        print(f"[cong] {len(lech)} phiên LỆCH (config khác: trước 24-11 / re-ID bật-tắt / settle khác) "
              f"— chỉ dùng làm NHÃN, KHÔNG dùng làm chi phí. Khớp thấp nhất: "
              f"{min(lech, key=lambda t: t[1])[0]} {min(t[1] for t in lech)}%")
    for k in luat_list:
        t = tong[k]
        print(f"  {k:22s} | báo {t['fire']:3d} lần | ẨN {t['frame_an']:4d} "
              f"({t['pct_frame_an']:5.2f}%) | chưa xác minh {t['frame_chua_xac_minh']:4d} "
              f"({t['pct_frame_chua_xac_minh']:5.2f}%) | KHÔNG tin cậy "
              f"{t['pct_frame_khong_tin_cay']:5.2f}% | ĐUÔI {t['duoi']:4d} ({t['pct_duoi']:5.2f}%) | "
              f"phiên có báo {t['phien_co_bao']:2d}/{t['so_phien']} | bắt ca ĐÚNG "
              f"{sum(1 for v in t['bat_ca_dung'].values() if v)}/{len(CA_DUNG)}")
    print(f"[cong] GIỚI HẠN: {len(CA_DUNG)} ca ĐÚNG + {len(CA_SAI)} ca SAI (nhãn SAI là GIẢ THUYẾT — "
          "phép thử ảnh của nó suy biến) ⇒ CHỈ kết luận được 'luật này có BỎ ca đúng nào không', KHÔNG "
          "kết luận được 'ít báo oan hơn' (CI95 của tỉ lệ FP với n=23 lần báo là ±19 pp). "
          "`dt` lấy từ `latency_ms` (xấp xỉ) ⇒ số `theo_dt` chỉ để SO SÁNH hai luật trên cùng dữ liệu. "
          "`FRAME_SHAPE` là GIẢ ĐỊNH 640×480: run_info.json chưa ghi width/height.")
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[cong] {args.out} (git_rev={rev}, git_dirty_code={dirty_code})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
