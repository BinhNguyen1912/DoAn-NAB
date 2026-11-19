"""Phát lại ĐÚNG cơ chế hybrid cho vài cặp (base → frame) trong một CSV drift.

Vì sao có script này (review độc lập PR #48, vòng 1 + 2): bảng "ô đang hiển thị ở frame X là gì"
trong log 19-11 được tính bằng một đoạn code dán tay, nên **không tái lập được bằng lệnh** — trái
quy ước "số công bố phải tái lập được". Bản dán tay đầu tiên còn **sai cơ chế**: nó chain
`LkBoxTracker.update()` qua nhiều frame (sai số tích luỹ), trong khi pipeline thật
(`src/live_tracking.py:847-856`) làm thế này ở **mỗi** frame phát:

    self._interp.reset(base_gray, base_bbox)      # base = lần VOS GẦN NHẤT
    bbox, ok = self._interp.update(gray)          # đúng MỘT bước
    if not ok: return base_result                 # LK fail ⇒ phát ô của base

Script in `lk_ok`, `bbox_hien_thi` và `IoU(bbox_hien_thi, VOS@frame)` theo **cùng công thức**
`_bbox_iou` của pipeline (toạ độ bao gồm, +1) để so được với cột `drift_iou` của CSV.

GIỚI HẠN phải đọc kèm: đường live là **đa luồng**, nên `base` tại lúc *phát* một frame phụ thuộc việc
kết quả VOS trước đó đã kịp về hay chưa. Script chạy tuần tự nên `lk_ok`/`bbox_hien_thi` là **của bản
phát lại**, không phải số đo của phiên. Chỉ những dòng có `khop_csv = True` mới chứng minh được cơ chế;
dòng `False` nghĩa là **bản phát lại không tái lập** được phiên đó (đừng trích).

Ví dụ (bảng trong `docs/task/19-11-2026-p05-theo-khung-va-mo-ticket-14.md`):

    python scripts/replay_lk_frame.py --csv data/drift_samples_binh1_2026-11-14_141609.csv \
        --source data/binh1.mp4 --cap 48:51 51:57 66:69 105:108 252:255
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:                              # chạy trực tiếp từ mọi CWD
    sys.path.insert(0, str(REPO_ROOT))

from src.light_tracker import LkBoxTracker                      # noqa: E402
from src.live_tracking import _bbox_iou                          # noqa: E402


def read_rows(path: Path) -> dict[int, dict]:
    """`frame_idx` → dòng CSV (giữ nguyên chuỗi; chuyển kiểu ở nơi dùng)."""
    with path.open(encoding="utf-8") as fh:
        return {int(r["frame_idx"]): r for r in csv.DictReader(fh)}


def box_of(row: dict) -> tuple[int, int, int, int]:
    return (int(row["bbox_x1"]), int(row["bbox_y1"]), int(row["bbox_x2"]), int(row["bbox_y2"]))


def _xywh(box) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    return (x1, y1, x2 - x1, y2 - y1)


def replay_pair(gray_of, rows: dict[int, dict], base: int, frame: int) -> dict:
    """Một cặp base→frame theo đúng cơ chế pipeline (`reset(base)` + MỘT `update`).

    `gray_of(frame)` trả ảnh xám của frame video (hoặc `None` nếu không đọc được).
    """
    if base not in rows or frame not in rows:
        raise KeyError(f"CSV không có dòng cho frame {base} hoặc {frame}")
    base_box = box_of(rows[base])
    gray_base = gray_of(base)
    gray_frame = gray_of(frame)
    if gray_base is None or gray_frame is None:
        raise RuntimeError(f"không đọc được frame {base} hoặc {frame} từ nguồn")
    interp = LkBoxTracker()
    interp.reset(gray_base, _xywh(base_box))
    moved, ok = interp.update(gray_frame)
    # `not ok` ⇒ pipeline phát ô của BASE (không bịa vị trí mới)
    hien_thi = (moved[0], moved[1], moved[0] + moved[2], moved[1] + moved[3]) if ok else base_box
    vos = box_of(rows[frame])
    iou = _bbox_iou(hien_thi, vos)
    csv_value = rows[frame].get("drift_iou") or None
    csv_value = float(csv_value) if csv_value not in (None, "") else None
    return {
        "base": base, "frame": frame, "lk_ok": bool(ok),
        "base_box": base_box, "bbox_hien_thi": hien_thi, "vos_box": vos,
        "iou": None if iou is None else round(iou, 4), "csv_drift": csv_value,
        # Dung sai 0,001: đủ để nói "khớp" mà không nhận số chỉ trùng đến 2 chữ số
        "khop_csv": csv_value is not None and iou is not None and abs(iou - csv_value) <= 0.001,
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

    gray_of.release = cap.release          # type: ignore[attr-defined]
    return gray_of


def parse_pairs(texts) -> list[tuple[int, int]]:
    pairs = []
    for text in texts:
        dau, _, cuoi = str(text).partition(":")
        if not dau.isdigit() or not cuoi.isdigit() or int(cuoi) <= int(dau):
            raise SystemExit(f"--cap {text!r} phải là base:frame với frame > base")
        pairs.append((int(dau), int(cuoi)))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", required=True, help="CSV drift (có bbox_x1..bbox_y2, drift_iou)")
    parser.add_argument("--source", required=True, help="nguồn video đã dùng cho lần đo đó")
    parser.add_argument("--cap", nargs="+", default=[], metavar="base:frame",
                        help="cặp cần phát lại; bỏ trống = mọi cặp liên tiếp trong CSV")
    args = parser.parse_args()

    rows = read_rows(Path(args.csv))
    frames = sorted(rows)
    pairs = parse_pairs(args.cap) if args.cap else list(zip(frames, frames[1:]))
    gray_of = _gray_reader(args.source)
    print(f"{'base→frame':>11} {'lk_ok':>6} {'bbox_hien_thi':>22} {'VOS@frame':>22} "
          f"{'IoU':>6} {'CSV':>7} khớp")
    khop = tong = 0
    try:
        for base, frame in pairs:
            r = replay_pair(gray_of, rows, base, frame)
            tong += 1
            khop += int(r["khop_csv"])
            hien = ",".join(str(v) for v in r["bbox_hien_thi"])
            vos = ",".join(str(v) for v in r["vos_box"])
            print(f"{base:>5}→{frame:<5} {str(r['lk_ok']):>6} {hien:>22} {vos:>22} "
                  f"{r['iou']!s:>6} {r['csv_drift']!s:>7} {'CÓ' if r['khop_csv'] else 'KHÔNG'}")
    finally:
        gray_of.release()                  # type: ignore[attr-defined]
    print(f"\n{khop}/{tong} cặp phát lại KHỚP `drift_iou` của CSV (|Δ| ≤ 0,001).")
    print("Cặp KHÔNG khớp = bản phát lại không tái lập được phiên (đường đa luồng: `base` tại lúc "
          "phát phụ thuộc VOS trước đã về chưa) ⇒ chỉ được trích các cặp 'CÓ'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
