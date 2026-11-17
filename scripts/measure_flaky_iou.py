"""
Đo phân bố IoU của test `test_process_theo_frames_iou_dat_o_cac_frame_mau` (ticket #22).

Vì sao cần: test đó từng ĐỎ khi chạy `./run testall` (10-11) nhưng xanh khi chạy riêng. `AGENTS.md` §6
ghi **SAM 2 không tất định** ⇒ trước khi "sửa test" phải biết IoU ở các frame mẫu thực sự dao động bao
nhiêu so với ngưỡng 0,5. Script này chạy đúng fixture của test N lần (engine mới mỗi lần) và ghi
`IoU(frame 2, 5, 9)` + `score` ra artifact có provenance.

Vì sao KHÔNG nới ngưỡng: nới ngưỡng cho xanh là che mất một tín hiệu thật nếu IoU tụt vì mask trôi.
Ngược lại, nếu phân bố IoU cách ngưỡng rất xa thì ngưỡng 0,5 đang đúng và test chỉ đỏ oan dưới tải ⇒
cách sửa là tách khỏi làn nhanh / chạy lại, không phải hạ ngưỡng.

Cách dùng:
    python scripts/measure_flaky_iou.py --lan 10 --out data/flaky_iou_2026-11-17_metrics.json

Input : checkpoint trong `configs/default.yaml` (mặc định SAM 2.1 tiny), fixture tổng hợp của
        `src/synthetic_video.py` (`generate_tracking_sequence`) — KHÔNG cần video/dữ liệu nặng.
Output: artifact JSON: mỗi lần chạy là 1 dòng `{lan, iou: {2, 5, 9}, score, ms}` + tóm tắt
        `iou[f]` (mean/std/min/max, số lần dưới ngưỡng 0,5), `git_rev`/`git_dirty_code`/`lenh`/`do_luc`.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Cùng ngưỡng với test (0,5) — đây là TIÊU CHÍ CẦN ĐO, không phải thứ được nới ra ở đây.
NGUONG_IOU = 0.5
FRAME_MAU = (2, 5, 9)


def _git() -> tuple[str | None, bool | None, str | None]:
    """`git_rev`, `git_dirty_code` (bẩn NGOÀI `data/`), `git_loi` — artifact phải tái lập được."""
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, capture_output=True,
                             text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=_REPO_ROOT,
                                capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, OSError) as exc:
        return None, None, str(exc)
    for line in status.splitlines():
        if line.strip() and not line[3:].startswith(("data/", "docs/media/")):
            return rev, True, None
    return rev, False, None


def mot_lan(engine) -> dict:
    """Chạy ĐÚNG kịch bản của test trên một engine mới ⇒ IoU ở các frame mẫu."""
    from src.synthetic_video import generate_tracking_sequence
    from tests.test_tracker_engine import iou   # DÙNG CHÍNH hàm chấm của test, không viết lại

    fx = generate_tracking_sequence(num_frames=10, frame_size=(240, 320), square_size=40,
                                    start=(60, 60))
    bat_dau = time.perf_counter()
    res0 = engine.start(fx.frames[0], fx.bboxes[0])
    iou_theo_frame = {0: round(float(iou(res0.bbox, fx.bboxes[0])), 4)}
    diem_so = [float(res0.score)]
    for i in range(1, 10):
        res = engine.process(fx.frames[i])
        iou_theo_frame[i] = round(float(iou(res.bbox, fx.bboxes[i])), 4)
        diem_so.append(float(res.score))
    return {
        "iou": {f: iou_theo_frame[f] for f in FRAME_MAU},
        "iou_tat_ca": iou_theo_frame,
        "score_min": round(min(diem_so), 4),
        "ms": round((time.perf_counter() - bat_dau) * 1000.0, 1),
    }


def tom_tat(lan: list[dict]) -> dict:
    """Thống kê từng frame mẫu + đếm số lần DƯỚI ngưỡng (đó là tần suất đỏ của test)."""
    ra = {}
    for f in FRAME_MAU:
        gia_tri = [lan_i["iou"][f] for lan_i in lan]
        ra[str(f)] = {
            "n": len(gia_tri),
            "mean": round(statistics.mean(gia_tri), 4),
            "std": round(statistics.stdev(gia_tri), 4) if len(gia_tri) > 1 else None,
            "min": round(min(gia_tri), 4),
            "max": round(max(gia_tri), 4),
            "so_lan_duoi_nguong": sum(1 for v in gia_tri if v < NGUONG_IOU),
        }
    ra["nguong"] = NGUONG_IOU
    return ra


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Đo phân bố IoU của test tracker_engine (ticket #22).")
    ap.add_argument("--lan", type=int, default=10, help="số lần chạy (>= 3 mới nói được gì)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    if args.lan < 1:
        print("[LOI] --lan phải >= 1", file=sys.stderr)
        return 2

    from src.tracker_engine import TrackerEngine

    engine = TrackerEngine.build_default()          # nạp model MỘT lần (đắt), engine reset mỗi lần
    lan: list[dict] = []
    for i in range(args.lan):
        ket = mot_lan(engine)
        lan.append({"lan": i + 1, **ket,
                    "duoi_nguong": [f for f, v in ket["iou"].items() if v < NGUONG_IOU]})
        print(f"[lan {i + 1}/{args.lan}] IoU " + " · ".join(
            f"f{f}={ket['iou'][f]}" for f in FRAME_MAU) + f" · {ket['ms']} ms", flush=True)

    rev, dirty, loi = _git()
    payload = {
        "do_luc": datetime.now().astimezone().isoformat(timespec="seconds"),
        "lenh": " ".join([str(Path(sys.argv[0])), *sys.argv[1:]]),
        "git_rev": rev, "git_dirty_code": dirty, "git_loi": loi,
        "test": "tests/test_tracker_engine.py::TestTrackerEngineStreaming"
                "::test_process_theo_frames_iou_dat_o_cac_frame_mau",
        "fixture": "generate_tracking_sequence(10, (240,320), 40, start=(60,60))",
        "ghi_chu": "IoU bbox vs GT tổng hợp. SAM 2 KHÔNG tất định (AGENTS §6) ⇒ so sánh chỉ có nghĩa "
                   "trong cùng một lần đo; `so_lan_duoi_nguong > 0` = tần suất đỏ của test.",
        "tat_ca": tom_tat(lan),
        "lan": lan,
    }
    out = Path(args.out) if args.out else _REPO_ROOT / "data" / (
        f"flaky_iou_{datetime.now():%Y-%m-%d}_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[xong] {out}")
    tong_duoi = sum(v["so_lan_duoi_nguong"] for k, v in payload["tat_ca"].items() if k != "nguong")
    print(f"[ket-luan] {tong_duoi} lượt-dưới-ngưỡng / {args.lan * len(FRAME_MAU)} lượt đo "
          f"(ngưỡng {NGUONG_IOU}, {args.lan} lần chạy)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
