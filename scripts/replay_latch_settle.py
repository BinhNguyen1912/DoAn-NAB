"""Replay cổng "nghi đổi đối tượng" (có NHỚ) trên CSV đã có để đo chi phí ẩn overlay — KHÔNG model.

Vì sao có (24-11-2026): phiên `demoip_1124-125109` (246 frame) cho thấy cổng báo **đúng** ở f137
(ô nhảy sang tóc), rồi hệ **tự bám lại đúng cái thìa** ở t≈40 s — nhưng latch không có đường xoá nào
(`watch.reset()` chỉ có 3 chỗ gọi: `reacquired` · phím `r` · phím `c`, mà re-ID đang TẮT) ⇒
**109/246 = 44,3 % phiên** chỉ còn ô nét đứt. Người dùng: "nó chỉ nghi thôi, không focus lại".

Script này trả lời đúng một câu, tái lập được: **nếu cho cổng tự hạ mức sau `N` bước ổn định thì
mất bao nhiêu frame ẩn, và bao nhiêu frame chuyển sang "chưa xác minh"** — trên chính các phiên đã
ghi, với `settle_steps = 0` (hành vi cũ) làm mốc.

Hai đại lượng KHÁC nhau, không được lẫn:
  - `frame_an`       : frame **KHÔNG vẽ mask** (trạng thái `nghi`) — mất hình;
  - `frame_chua_xac_minh`: frame VẪN vẽ nhưng kiểu "chưa xác minh" (viền nét đứt, không tô, không
                          quỹ đạo) — không mất hình, nhưng không phải "đã kiểm".

Chạy:

    python scripts/replay_latch_settle.py --glob 'data/demoip_*_metrics.csv' --settle 8 \
        --out data/replay_latch_settle_2026-11-24.json

Giới hạn phải nói khi trích (script tự in): bbox được **dựng lại** từ `center_x/center_y/bbox_w/
bbox_h` trong CSV (CSV không lưu 4 mép), và `frame_shape` lấy từ tham số (mặc định 480×640) ⇒ bán
kính `search_window_radius` xấp xỉ, không bằng tuyệt đối lần chạy thật. Số này để **so sánh hai
luật trên cùng dữ liệu**, KHÔNG phải số của phiên live.
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.identity_guard import (  # noqa: E402
    TRANG_THAI_CHUA_XAC_MINH,
    TRANG_THAI_NGHI,
    IdentityWatch,
)

ZERO = (0, 0, 0, 0)


def doc_cot(path):
    """Đọc 1 CSV metrics ⇒ list dict (ô dựng lại từ tâm + kích thước; `mask_area > 0` = có mask)."""
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
            cx, cy = so("center_x"), so("center_y")
            w, h = so("bbox_w"), so("bbox_h")
            area = so("mask_area")
            if None in (cx, cy, w, h) or not w or not h:
                bbox = ZERO
            else:
                bbox = (int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2))
            out.append({
                "frame_idx": int(float(r.get("frame_idx") or 0)),
                "bbox": bbox,
                "co_mask": bool(area is not None and area > 0),
                "co_mask_area": area is not None,
            })
    return out


def replay(rows, settle_steps, frame_shape):
    """Chạy `IdentityWatch` trên chuỗi ô của CSV ⇒ số frame ở từng trạng thái + số lần bật.

    Luật nối ô y như `smooth_display`/`live_pipeline`: `prev` = ô TỐT gần nhất, mất dấu ⇒ `ZERO`
    (để khi vật xuất hiện lại không bị so với ô của nhiều giây trước).
    """
    watch = IdentityWatch(settle_steps=settle_steps)
    dem = {TRANG_THAI_NGHI: 0, TRANG_THAI_CHUA_XAC_MINH: 0}
    fires, prev = 0, None
    for r in rows:
        dang_nghi_truoc = watch.nghi
        watch.update(prev, r["bbox"], frame_shape, co_mask=r["co_mask"])
        if watch.nghi and not dang_nghi_truoc:
            fires += 1
        trang_thai = watch.trang_thai
        if trang_thai in dem:
            dem[trang_thai] += 1
        prev = r["bbox"] if r["co_mask"] else ZERO
    return {
        "n": len(rows),
        "fire": fires,
        "frame_an": dem[TRANG_THAI_NGHI],
        "frame_chua_xac_minh": dem[TRANG_THAI_CHUA_XAC_MINH],
    }


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _provenance():
    rev = _git("rev-parse", "--short", "HEAD")
    dirty_all = _git("status", "--porcelain") or ""
    dirty_code = _git("status", "--porcelain", "--", ".", ":!data") or ""
    return rev, bool(dirty_all), bool(dirty_code)


def tao_payload(phien, settle_list, frame_shape, args):
    rev, dirty, dirty_code = _provenance()
    tong = {}
    for s in settle_list:
        n = sum(p["n"] for p in phien)
        an = sum(p["lan_chay"][str(s)]["frame_an"] for p in phien)
        chua = sum(p["lan_chay"][str(s)]["frame_chua_xac_minh"] for p in phien)
        tong[str(s)] = {
            "so_phien": len(phien), "so_frame": n,
            "fire": sum(p["lan_chay"][str(s)]["fire"] for p in phien),
            "frame_an": an,
            "pct_frame_an": round(100.0 * an / n, 2) if n else None,
            "frame_chua_xac_minh": chua,
            "pct_frame_chua_xac_minh": round(100.0 * chua / n, 2) if n else None,
        }
    return {
        "git_rev": rev, "git_dirty": dirty, "git_dirty_code": dirty_code,
        "do_luc": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lenh": " ".join(sys.argv),
        "nguon": [p["ten"] for p in phien],
        "frame_shape": list(frame_shape),
        "settle_list": settle_list,
        "tong": tong,
        "phien": phien,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Replay cổng nghi trên CSV (không model).")
    ap.add_argument("--glob", default="data/demoip_*_metrics.csv")
    ap.add_argument("--settle", default="0,8,12", help="danh sách settle_steps (0 = hành vi cũ)")
    ap.add_argument("--frame-shape", default="480,640", help="H,W của khung (CSV không lưu)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    try:
        h, w = (int(v) for v in args.frame_shape.split(","))
    except ValueError:
        print("[LOI] --frame-shape phải là 'H,W'", file=sys.stderr)
        return 2
    settle_list = sorted({int(v) for v in args.settle.split(",") if v.strip()})
    if not settle_list or min(settle_list) < 0:
        print("[LOI] --settle phải là danh sách số >= 0", file=sys.stderr)
        return 2

    paths = sorted(Path(REPO_ROOT).glob(args.glob))
    if not paths:
        print(f"[LOI] không có CSV nào khớp {args.glob!r} — KHÔNG đo được (khác '0 lần báo')",
              file=sys.stderr)
        return 1

    phien = []
    for p in paths:
        rows = doc_cot(p)
        if not rows:
            continue
        phien.append({
            "ten": p.name,
            "n": len(rows),
            "co_mask_area": any(r["co_mask_area"] for r in rows),
            "lan_chay": {str(s): replay(rows, s, (h, w)) for s in settle_list},
        })
    if not phien:
        print("[LOI] CSV khớp mẫu nhưng KHÔNG có dòng dữ liệu — KHÔNG đo được", file=sys.stderr)
        return 1

    payload = tao_payload(phien, settle_list, (h, w), args)
    print(f"[latch] {len(phien)} phiên · {payload['tong'][str(settle_list[0])]['so_frame']} frame "
          f"(có cột mask_area: {sum(1 for p in phien if p['co_mask_area'])}/{len(phien)})")
    for s in settle_list:
        t = payload["tong"][str(s)]
        nhan = "hành vi CŨ" if s == 0 else f"settle {s} bước"
        print(f"[latch] {nhan:16s} | bật {t['fire']:3d} lần | ẨN {t['frame_an']:4d} frame "
              f"({t['pct_frame_an']}%) | CHƯA XÁC MINH {t['frame_chua_xac_minh']:4d} "
              f"({t['pct_frame_chua_xac_minh']}%)")
    print("[latch] GIỚI HẠN: ô DỰNG LẠI từ center/bbox_w/bbox_h; frame_shape theo tham số ⇒ "
          "bán kính cổng xấp xỉ. Dùng để SO SÁNH hai luật trên cùng dữ liệu, không phải số live.")
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(f"[latch] {args.out} (git_rev={payload['git_rev']}, "
              f"git_dirty_code={payload['git_dirty_code']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
