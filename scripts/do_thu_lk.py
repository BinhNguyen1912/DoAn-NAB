"""Đo OFFLINE chất lượng `LkBoxTracker` theo tham số — trả lời ticket #38 mà không đụng pipeline.

Vì sao có script này: `lk_ok_frac` đo được chỉ **0,093** (4/43 mẫu trong khung, `binh1` @192,
`vos_every 3`) ⇒ ~90 % thời gian ô người xem thấy là ô VOS cũ. Chẩn đoán thô cho thấy LK **không thiếu
điểm** (≈50/64) mà bị chặn bởi cửa chống-trôi `DEFAULT_MAX_MAD = 1.5` px. Trước khi sửa production
phải trả lời bằng SỐ: nới cửa đó ra thì LK bám tốt hơn thật, hay chỉ "ổn định hơn trên giấy" trong khi
ô bao trôi khỏi vật?

Cách đo (offline, không cần chạy phiên live): dùng CSV drift của một lần đo thật (có ô VOS ở từng lần
VOS) làm **mốc tham chiếu**, rồi với mỗi cặp `base → target` (target = lần VOS kế tiếp):

1. đặt `LkBoxTracker` tại frame `base` với ô VOS của `base`;
2. cho nó `update()` **một bước** trên frame `target` (đúng cơ chế pipeline: `reset(base)` + một update);
3. ghi `ok`, IoU(ô LK, ô VOS của `target`) và MAD của vector dịch.

Chỉ số để chọn tham số:

- `ok_frac` — tỉ lệ LK dám nhận (gần `lk_ok_frac` của pipeline);
- `iou_median_khi_ok` — nếu nới cửa mà chỉ số này **giảm**, tức LK nhận bừa (đúng thứ cửa MAD sinh ra
  để chặn — AGENTS §6);
- `ok_va_sai_frac` — tỉ lệ mẫu "LK nhận nhưng IoU < 0,5": nguy hiểm nhất (người xem thấy ô sai mà HUD
  không báo gì).

Chạy:

    python scripts/do_thu_lk.py --csv data/drift_samples_binh1_2026-11-19_123641.csv \\
        --source data/binh1.mp4 --out data/lk_thu_binh1_2026-11-19_metrics.json \\
        --max-mad 1.5 3 6 10 --grid 8 12

GIỚI HẠN phải đọc kèm: tham chiếu là **ô VOS**, không phải GT người gán ⇒ đây là "LK có khớp với model
không", KHÔNG phải "LK bám đúng vật". Muốn cái sau phải có mIoU vs GT (`docs/thuoc-do-bam-dung.md`).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.light_tracker import LkBoxTracker                          # noqa: E402
from src.live_tracking import _bbox_iou                              # noqa: E402

SAI_NGUONG = 0.5      # IoU dưới ngưỡng này = ô bao sai rõ ràng (người xem thấy lệch)


def doc_moc(csv_path: Path) -> dict[int, tuple[int, int, int, int]]:
    """`frame_idx` → ô VOS `(x1,y1,x2,y2)`. Dòng thiếu bbox (mask rỗng) bị bỏ."""
    moc = {}
    with csv_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                box = tuple(int(row[f"bbox_{k}"]) for k in ("x1", "y1", "x2", "y2"))
                frame = int(row["frame_idx"])
            except (KeyError, TypeError, ValueError):
                continue
            if box[2] > box[0] and box[3] > box[1]:
                moc[frame] = box
    return moc


def cap_ke(moc: dict, *, toi_da: int | None = None) -> list[tuple[int, int]]:
    """Các cặp `(base, target)` = hai lần VOS LIÊN TIẾP (đúng khoảng mà pipeline phải nội suy)."""
    frames = sorted(moc)
    cap = list(zip(frames, frames[1:]))
    return cap[:toi_da] if toi_da else cap


def do_mot_cau_hinh(*, cap, moc, gray_of, max_mad: float, grid: int) -> dict:
    """Đo một cấu hình `LkBoxTracker` trên toàn bộ cặp `base → target`."""
    ket_qua = []
    for base, target in cap:
        gray_base, gray_target = gray_of(base), gray_of(target)
        if gray_base is None or gray_target is None:
            continue
        x1, y1, x2, y2 = moc[base]
        tracker = LkBoxTracker(grid=grid, max_mad=max_mad)
        tracker.reset(gray_base, (x1, y1, x2 - x1, y2 - y1))
        moved, ok = tracker.update(gray_target)
        if ok:
            box = (moved[0], moved[1], moved[0] + moved[2], moved[1] + moved[3])
            iou = _bbox_iou(box, moc[target])
        else:
            box, iou = moc[base], 0.0        # pipeline phát ô BASE khi not-ok ⇒ so chính ô đó
        ket_qua.append({"base": base, "target": target, "ok": bool(ok),
                        "box": list(box), "iou": None if iou is None else round(float(iou), 4)})
    return tom_tat(ket_qua, max_mad=max_mad, grid=grid)


def tom_tat(ket_qua, *, max_mad: float, grid: int) -> dict:
    """Gộp số của một cấu hình — hàm THUẦN (test được, không cần video)."""
    n = len(ket_qua)
    ok = [r for r in ket_qua if r["ok"]]
    co_iou = [r for r in ket_qua if r["iou"] is not None]
    iou_ok = [r["iou"] for r in ok if r["iou"] is not None]
    iou_tat_ca = [r["iou"] for r in co_iou]
    sai_khi_ok = [v for v in iou_ok if v < SAI_NGUONG]

    def _median(values):
        if not values:
            return None
        sap = sorted(values)
        giua = len(sap) // 2
        return round(sap[giua] if len(sap) % 2 else (sap[giua - 1] + sap[giua]) / 2, 4)

    return {
        "max_mad": max_mad, "grid": grid, "n_cap": n,
        "ok_n": len(ok),
        "ok_frac": round(len(ok) / n, 3) if n else None,
        # Chỉ số quyết định: cửa MAD để LK nhận nhiều hơn NÊN làm IoU trung vị khi-ok giữ nguyên/tăng.
        "iou_median_khi_ok": _median(iou_ok),
        "iou_median_tat_ca": _median(iou_tat_ca),
        # "Nhận bừa": LK ok mà ô vẫn lệch hẳn vật ⇒ tệ hơn là báo mất dấu (HUD không cảnh báo gì).
        "ok_va_sai_n": len(sai_khi_ok),
        "ok_va_sai_frac": round(len(sai_khi_ok) / len(ok), 3) if ok else None,
        "mau": ket_qua,
    }


def _gray_reader(source: str):
    import cv2

    cap = cv2.VideoCapture(source)
    cache: dict[int, object] = {}

    def gray_of(frame: int):
        if frame not in cache:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
            ok, img = cap.read()
            cache[frame] = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if ok else None
        return cache[frame]

    gray_of.release = cap.release        # type: ignore[attr-defined]
    return gray_of


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", required=True, help="CSV drift của một lần đo thật (làm mốc ô VOS)")
    parser.add_argument("--source", required=True, help="clip đã dùng cho lần đo đó")
    parser.add_argument("--out", default="", help="artifact JSON (mặc định data/lk_thu_<ngày>_metrics.json)")
    parser.add_argument("--max-mad", type=float, nargs="+", default=[1.5, 3.0, 6.0, 10.0])
    parser.add_argument("--grid", type=int, nargs="+", default=[8, 12])
    parser.add_argument("--toi-da-cap", type=int, default=None, help="giới hạn số cặp (để chạy nhanh)")
    parser.add_argument("--frame-window", action="append", default=[], metavar="dau:cuoi",
                        help="chỉ đo trong khung vật còn trong khung (lặp được)")
    args = parser.parse_args(argv)

    moc = doc_moc(Path(args.csv))
    if not moc:
        raise SystemExit(f"[LOI] {args.csv} không có dòng nào có ô bao VOS")
    khung = []
    for text in args.frame_window:
        dau, _, cuoi = str(text).partition(":")
        if not dau.isdigit() or not cuoi.isdigit():
            raise SystemExit(f"--frame-window {text!r} phải là dau:cuoi")
        khung.append((int(dau), int(cuoi)))
    if khung:
        moc = {f: b for f, b in moc.items() if any(a <= f <= c for a, c in khung)}
        if not moc:
            raise SystemExit("[LOI] không còn mốc nào trong khung đã khai")

    cap = cap_ke(moc, toi_da=args.toi_da_cap)
    gray_of = _gray_reader(args.source)
    ket_qua = []
    try:
        for grid in args.grid:
            for max_mad in args.max_mad:
                kq = do_mot_cau_hinh(cap=cap, moc=moc, gray_of=gray_of,
                                     max_mad=max_mad, grid=grid)
                ket_qua.append(kq)
                print(f"max_mad {max_mad:>4} · grid {grid:>2} → ok {kq['ok_n']}/{kq['n_cap']} "
                      f"({kq['ok_frac']}) · IoU trung vị khi-ok {kq['iou_median_khi_ok']} · "
                      f"nhận-bừa {kq['ok_va_sai_n']} ({kq['ok_va_sai_frac']})")
    finally:
        gray_of.release()                # type: ignore[attr-defined]

    from scripts.measure_watchdog import _git_provenance

    rev, dirty, dirty_code, loi = _git_provenance()
    artifact = {
        "git_rev": rev, "git_dirty": dirty, "git_dirty_code": dirty_code, "git_loi": loi,
        "do_luc": datetime.now().isoformat(timespec="seconds"),
        "lenh": " ".join(["python scripts/do_thu_lk.py", f"--csv {args.csv}",
                          f"--source {args.source}", f"--max-mad {' '.join(map(str, args.max_mad))}",
                          f"--grid {' '.join(map(str, args.grid))}"]
                         + [f"--frame-window {w}" for w in args.frame_window]),
        "nguon_so": {"csv": args.csv, "clip": args.source,
                     "khung": [[a, b] for a, b in khung] or None, "n_moc": len(moc)},
        "dinh_nghia": ("IoU(ô LK sau MỘT bước từ base, ô VOS của target) — so với **ô VOS**, KHÔNG phải "
                       "GT người gán. `ok_va_sai_frac` = tỉ lệ mẫu LK nhận mà IoU < 0,5 (ô sai mà HUD "
                       "không báo)."),
        "sai_nguong_iou": SAI_NGUONG,
        "ket_qua": ket_qua,
    }
    out = Path(args.out) if args.out else REPO_ROOT / "data" / (
        f"lk_thu_{datetime.now():%Y-%m-%d}_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nGhi: {out}")
    if loi:                      # artifact không provenance ⇒ KHÔNG được thoát 0 (AGENTS §6)
        print(f"[LOI] không lấy được provenance: {loi}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
