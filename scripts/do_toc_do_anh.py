#!/usr/bin/env python3
"""Đo tốc độ cắt ảnh từng bước của UI gán nhãn (`GET /anh`) và ghi artifact có provenance.

Vì sao cần: log 25-11 công bố "62–346 ms lần đầu / 9 ms khi cache" **không kèm file số** — AGENTS §6
đòi `git_rev` + `git_dirty_code` + `lenh` + `do_luc` thì con số mới được trích vào báo cáo.

    python scripts/do_toc_do_anh.py --phien demoip_1125-121456 --out data/labelui_anh_2026-11-25_metrics.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import label_ui as L  # noqa: E402


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              check=False).stdout.strip()
    except OSError:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phien", required=True)
    ap.add_argument("--buoc", default="0,1,2,10,50,100,141,200,250,294",
                    help="danh sách bước (phẩy); bước ngoài dải bị bỏ")
    ap.add_argument("--lan", type=int, default=3, help="số lần lặp mỗi bước (mặc định 3)")
    ap.add_argument("--out", help="file JSON artifact")
    args = ap.parse_args()

    buoc = [int(b) for b in args.buoc.split(",") if b.strip()]
    d = L.doc_phien_cached(L.DATA_DIR / f"{args.phien}_metrics.csv")
    buoc = [b for b in buoc if 0 <= b < len(d["frames"])]

    # Cache SẠCH trước khi đo "lần đầu", nếu không sẽ đo nhầm toàn số cache.
    thu_muc = L.THU_MUC_NHAN / L.ANH_DIR_NAME / args.phien
    shutil.rmtree(thu_muc, ignore_errors=True)
    L._CAP.clear()

    lan_dau, da_cache, kich_thuoc = [], [], []
    for b in buoc:
        for k in range(args.lan):
            t0 = time.perf_counter()
            du_lieu, loi = L.anh_buoc(args.phien, b)
            ms = (time.perf_counter() - t0) * 1000
            if loi or not du_lieu:
                print(f"LỖI bước {b}: {loi}", file=sys.stderr)
                return 1
            kich_thuoc.append(len(du_lieu))
            (lan_dau if k == 0 else da_cache).append(round(ms, 1))

    def thong_ke(xs: list[float]) -> dict:
        # KHÔNG có `p95` khi n nhỏ: với n = 10–20, `int(0.95*n)` = n-1 ⇒ "p95" chính là MAX
        # (review vòng 2, P3-1: đừng trích nó như đuôi phân bố). Chỉ in p95 khi n >= 100.
        if not xs:
            return {"n": 0}
        xs_sap = sorted(xs)
        out = {"n": len(xs), "mean_ms": round(statistics.fmean(xs), 1),
               "min_ms": xs_sap[0], "max_ms": xs_sap[-1]}
        if len(xs_sap) >= 100:
            out["p95_ms"] = round(xs_sap[int(0.95 * len(xs_sap))], 1)
        return out

    # Ảnh SONG SONG (prefetch của UI: 4 ảnh kế mỗi lần bấm ←/→): đo thời gian + chứng minh chỉ mở
    # MỘT `VideoCapture` (FFmpeg không thread-safe — review vòng 2, P2-6).
    import concurrent.futures
    shutil.rmtree(thu_muc, ignore_errors=True)
    L._CAP.clear()
    so_mo = []
    that = L.cv2.VideoCapture if hasattr(L, "cv2") else None
    import cv2
    that = cv2.VideoCapture

    class Dem:
        def __init__(self, *a, **k):
            so_mo.append(1)
            self._c = that(*a, **k)
        def __getattr__(self, n):
            return getattr(self._c, n)

    cv2.VideoCapture = Dem
    try:
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            ds = list(ex.map(lambda b: L.anh_buoc(args.phien, b), buoc[:8]))
        song_song_ms = (time.perf_counter() - t0) * 1000
    finally:
        cv2.VideoCapture = that
    assert all(d and not e for d, e in ds), "có ảnh song song bị lỗi"

    payload = {
        "song_song": {"so_request": len(ds), "tong_ms": round(song_song_ms, 1),
                      "so_capture_mo": len(so_mo),
                      "chiet_giai": "8 request đồng thời trên 8 bước khác nhau; `so_capture_mo` phải = 1"},
        "do_luc": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "lenh": " ".join(sys.argv),
        "git_rev": git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "git_dirty_code": bool(git("status", "--porcelain", "--", ".", ":!data")),
        "phien": args.phien,
        "so_buoc_do": len(buoc),
        "so_lan_moi_buoc": args.lan,
        "lan_dau_ms": thong_ke(lan_dau),
        "da_cache_ms": thong_ke(da_cache),
        "kich_thuoc_jpeg_b": {"mean": round(statistics.fmean(kich_thuoc)),
                              "min": min(kich_thuoc), "max": max(kich_thuoc)},
        "chiet_giai": ("`lan_dau` = bước CHƯA có cache (seek + decode + nén + ghi); `da_cache` = đọc "
                       "file. Đo trên máy này, không GPU; số tuyệt đối phụ thuộc tải máy (AGENTS §6: "
                       "chỉ trích theo TỈ LỆ nếu không có loadavg)."),
        "loadavg_1m": (pathlib.Path("/proc/loadavg").read_text().split()[0]
                       if pathlib.Path("/proc/loadavg").is_file() else None),
        "cpu_count": __import__("os").cpu_count(),
    }
    print(json.dumps({k: payload[k] for k in ("lan_dau_ms", "da_cache_ms", "kich_thuoc_jpeg_b")},
                     ensure_ascii=False, indent=1))
    if args.out:
        p = pathlib.Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"→ {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
