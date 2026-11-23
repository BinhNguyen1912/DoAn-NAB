"""Replay các luật "mask đang bám KHÔNG còn là vật" trên CSV đã có — KHÔNG đụng runtime, KHÔNG model.

Vì sao có script này (23-11-2026): ba lần liên tiếp trong cùng một ngày, cùng một luật (điểm tin cậy
sụt) được ba người báo ba con số khác nhau — `31/3 829 = 0,81 %`, `22/32 phiên · ẩn 51,1 %`,
`75 lần / 5 298 frame` — và **không con số nào tái lập được** khi chạy lại trên chính CSV đã commit.
Không tái lập được thì không được đưa lên slide, và cũng không được dùng để bác một hướng.

Script này chỉ làm một việc: **một luật khai tường minh → một bảng số tái lập được**, kèm provenance
(`git_rev`/`git_dirty_code`/`lenh`/`do_luc`) như mọi artifact đo khác (AGENTS §6).

Hai đại lượng KHÁC NHAU và không được lẫn (lỗi đã xảy ra):
  - `fire`      : số LẦN luật bật (mỗi lần = 1 chuỗi `run` frame liên tiếp thoả điều kiện);
  - `an_frame`  : số frame **bị ẩn overlay** nếu cổng có NHỚ (latch) — mọi frame từ lần bật ĐẦU tới
                  hết phiên. `score` là tín hiệu **xung** (tự hồi sau khi mask đã trôi sang vùng khác),
                  nên "số lần báo" nhỏ không có nghĩa "ít frame bị ảnh hưởng" — hai số lệch nhau 18×.

Chạy:

    python scripts/replay_gate.py --glob 'data/demoip_*_metrics.csv' \
        --score-abs 2.0 --score-rel 0.7 --run 6 --win 90 --lag 10 \
        --out data/replay_gate_2026-11-23.json

Luật:
  - `abs` : frame có `score <= --score-abs` VÀ `mask_area > 0` (mask còn đó — khác "mất dấu" đã có);
  - `rel` : frame có `score <= --score-rel × median(score[i-win .. i-lag])` (baseline TRƯỚC, không
            dùng mẫu của chính frame đó ⇒ không rò rỉ tương lai). `lag >= 1` là bắt buộc.
  - cả hai: phải có `--run` frame LIÊN TIẾP thoả thì mới tính là một lần bật (chống nhấp nháy).

Giới hạn phải nói khi trích (script tự in ra): cửa sổ baseline `win + lag` frame ⇒ **nửa đầu phiên
mù** với phiên ngắn (trung vị phiên `demoip` chỉ ~112 frame); và CSV cũ (11 cột) **không có** cột
`mask_area`/`track_cos` ⇒ trên các phiên đó luật `abs`/`rel` tính theo `score` trần (không lọc được
"mask còn to"), nên script đếm riêng `n_co_mask_area`.
"""
import argparse
import csv
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── hàm THUẦN (test không cần CSV thật) ─────────────────────────────────────────────────────


def doc_cot(path):
    """Đọc 1 CSV metrics ⇒ `list[dict]` chỉ với các cột cần (thiếu cột ⇒ `None`)."""
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
            out.append({
                "frame_idx": int(float(r.get("frame_idx") or 0)),
                "score": so("score"),
                "mask_area": so("mask_area"),
            })
    return out


def co_mask_area(rows) -> bool:
    """CSV này có cột `mask_area` dùng được không (CSV 11 cột cũ thì KHÔNG)."""
    return any(r["mask_area"] is not None for r in rows)


def baseline_truot(scores, win, lag):
    """Trung vị của `win` mẫu **trước** frame i một khoảng `lag` (không dùng mẫu tương lai).

    `None` khi chưa đủ mẫu — KHÔNG lấy mẫu của chính frame i (rò rỉ tương lai, làm "trễ 0 frame"
    trở thành lời tiên tri: frame sụt kéo trung vị xuống nên luôn "bắt đúng ngay").
    """
    if lag < 1:
        raise ValueError("lag phải >= 1: dùng mẫu của chính frame ⇒ rò rỉ tương lai")
    out = []
    for i in range(len(scores)):
        dau = i - lag - win
        cuoi = i - lag
        # CHỈ dùng khi cửa sổ ĐẦY ĐỦ (`win` mẫu, kết thúc `lag` frame trước i): lấy cửa sổ ngắn ở
        # đầu phiên rồi coi là "đã có baseline" là bịa độ tin cậy (nửa đầu phiên phải là MÙ).
        if dau < 0 or cuoi <= 0:
            out.append(None)
            continue
        cua_so = [s for s in scores[dau:cuoi] if s is not None]
        out.append(statistics.median(cua_so) if cua_so else None)
    return out


def co_latch(flags, run):
    """Đánh dấu `run` frame LIÊN TIẾP thoả ⇒ trả `[True]` tại frame BẮT ĐẦU mỗi chuỗi."""
    fires, dem = [], 0
    for i, ok in enumerate(flags):
        dem = dem + 1 if ok else 0
        if dem == run:
            fires.append(i - run + 1)
    return fires


def co_abs(rows, nguong):
    flags = []
    for r in rows:
        s, a = r["score"], r["mask_area"]
        flags.append(s is not None and s <= nguong and (a is None or a > 0))
    return flags


def co_rel(rows, ti_le, win, lag):
    scores = [r["score"] for r in rows]
    base = baseline_truot(scores, win, lag)
    flags = []
    for r, b in zip(rows, base):
        s, a = r["score"], r["mask_area"]
        ok = (s is not None and b is not None and b > 0 and s <= ti_le * b
              and (a is None or a > 0))
        flags.append(ok)
    return flags


def frame_bi_an(fires, n):
    """Số frame bị ẩn nếu cổng có NHỚ: từ lần bật ĐẦU tiên tới hết phiên."""
    return 0 if not fires else n - fires[0]


def fp_khi_mask_to(rows, fires, ti_le=0.7):
    """Số lần bật mà ở frame đó mask VẪN TO (≥ `ti_le` × trung vị `mask_area` của phiên).

    Đây là "báo oan" theo nghĩa hẹp nhất (mask còn to mà cổng nói mask sai) — cần thiết vì
    `mIoU` không đo được frame nào là "ẩn oan". `None` khi CSV thiếu cột `mask_area`.
    """
    dien_tich = [r["mask_area"] for r in rows if r["mask_area"] is not None]
    if not dien_tich:
        return None
    med = statistics.median(dien_tich)
    if med <= 0:
        return 0
    return sum(1 for i in fires
               if rows[i]["mask_area"] is not None and rows[i]["mask_area"] >= ti_le * med)


# ── provenance ──────────────────────────────────────────────────────────────────────────────


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _provenance():
    """`git_rev` + `git_dirty_code` (bẩn **bỏ qua `data/`** — cùng quy ước `src/metrics_logger`)."""
    rev = _git("rev-parse", "--short", "HEAD")
    try:
        dirty_all = _git("status", "--porcelain") or ""
        dirty_code = _git("status", "--porcelain", "--", ".", ":!data") or ""
    except (OSError, subprocess.SubprocessError):
        return rev, None, None
    return rev, bool(dirty_all), bool(dirty_code)


# ── main ────────────────────────────────────────────────────────────────────────────────────


def tong_hop(paths, args):
    """Chạy cả hai luật trên từng CSV ⇒ `(danh_sach_phien, tong)`."""
    phien = []
    for p in paths:
        rows = doc_cot(p)
        if not rows:
            continue
        n = len(rows)
        f_abs = co_latch(co_abs(rows, args.score_abs), args.run)
        f_rel = co_latch(co_rel(rows, args.score_rel, args.win, args.lag), args.run)
        phien.append({
            "ten": Path(p).name,
            "n": n,
            "co_mask_area": co_mask_area(rows),
            "fire_abs": len(f_abs),
            "fire_rel": len(f_rel),
            "frame_an_abs": frame_bi_an(f_abs, n),
            "frame_an_rel": frame_bi_an(f_rel, n),
            "fp_khi_mask_to_rel": fp_khi_mask_to(rows, f_rel),
            "fire_rel_dau": f_rel[:3],
        })
    return phien


def tao_payload(phien, args, paths):
    rev, dirty, dirty_code = _provenance()
    n_tong = sum(p["n"] for p in phien)
    fire_abs = sum(p["fire_abs"] for p in phien)
    fire_rel = sum(p["fire_rel"] for p in phien)
    an_rel = sum(p["frame_an_rel"] for p in phien)
    fp_rel = sum(p["fp_khi_mask_to_rel"] or 0 for p in phien)
    return {
        "git_rev": rev, "git_dirty": dirty, "git_dirty_code": dirty_code,
        "do_luc": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lenh": " ".join(sys.argv),
        "nguon": [Path(p).name for p in paths],
        "luat": {"score_abs": args.score_abs, "score_rel": args.score_rel,
                 "run": args.run, "win": args.win, "lag": args.lag,
                 "fp_mask_to_ti_le": 0.7},
        "tong": {
            "so_phien": len(phien), "so_frame": n_tong,
            "so_phien_co_mask_area": sum(1 for p in phien if p["co_mask_area"]),
            "fire_abs": fire_abs,
            "fire_rel": fire_rel,
            "phien_bao_abs": sum(1 for p in phien if p["fire_abs"]),
            "phien_bao_rel": sum(1 for p in phien if p["fire_rel"]),
            # `an_rel`/`n_tong` = tỉ lệ frame bị ảnh hưởng NẾU cổng có NHỚ (xem docstring)
            "pct_frame_an_rel": round(100.0 * an_rel / n_tong, 2) if n_tong else None,
            "fp_khi_mask_to_rel": fp_rel,
            "pct_fp_tren_frame": round(100.0 * fp_rel / n_tong, 2) if n_tong else None,
        },
        "phien": phien,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Replay luật 'mask sai' trên CSV đã có (không model).")
    ap.add_argument("--glob", default="data/demoip_*_metrics.csv", help="mẫu đường dẫn CSV")
    ap.add_argument("--score-abs", type=float, default=2.0, help="luật tuyệt đối: score <= X")
    ap.add_argument("--score-rel", type=float, default=0.7, help="luật tương đối: score <= X*median")
    ap.add_argument("--run", type=int, default=6, help="số frame LIÊN TIẾP để tính 1 lần bật")
    ap.add_argument("--win", type=int, default=90, help="cửa sổ baseline (frame)")
    ap.add_argument("--lag", type=int, default=10, help="bỏ `lag` frame sát trước (chống rò rỉ)")
    ap.add_argument("--out", default=None, help="file JSON kết quả")
    args = ap.parse_args(argv)

    if args.run < 1:
        print("[LOI] --run phải >= 1", file=sys.stderr)
        return 2
    if args.lag < 1:
        print("[LOI] --lag phải >= 1 (dùng mẫu của chính frame ⇒ rò rỉ tương lai)", file=sys.stderr)
        return 2

    paths = sorted(Path().glob(args.glob))
    if not paths:
        print(f"[LOI] không có CSV nào khớp {args.glob!r} — KHÔNG đo được (khác '0 lần báo')",
              file=sys.stderr)
        return 1
    phien = tong_hop(paths, args)
    if not phien:
        print("[LOI] các CSV khớp mẫu nhưng KHÔNG có dòng dữ liệu nào — KHÔNG đo được",
              file=sys.stderr)
        return 1

    payload = tao_payload(phien, args, [Path(p) for p in paths])
    t = payload["tong"]
    print(f"[replay] {t['so_phien']} phiên · {t['so_frame']} frame "
          f"(có cột mask_area: {t['so_phien_co_mask_area']}/{t['so_phien']})")
    print(f"[replay] luật tuyệt đối score<={args.score_abs}: {t['fire_abs']} lần bật · "
          f"{t['phien_bao_abs']}/{t['so_phien']} phiên")
    print(f"[replay] luật tương đối score<={args.score_rel}×median[{args.win},{args.lag}]: "
          f"{t['fire_rel']} lần bật · {t['phien_bao_rel']}/{t['so_phien']} phiên · "
          f"ẨN {t['pct_frame_an_rel']}% frame NẾU LATCH")
    if t["pct_fp_tren_frame"] is not None:
        print(f"[replay] báo oan (mask còn ≥0,7×trung vị) ở lần bật: {t['fp_khi_mask_to_rel']} "
              f"({t['pct_fp_tren_frame']}% tổng frame)")
    print("[replay] GIỚI HẠN: cửa sổ baseline "
          f"{args.win}+{args.lag} frame ⇒ nửa đầu phiên NGẮN là mù; CSV cũ thiếu "
          "`mask_area` ⇒ không lọc được 'mask còn to'")
    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(f"[replay] {args.out} (git_rev={payload['git_rev']}, "
              f"git_dirty_code={payload['git_dirty_code']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
