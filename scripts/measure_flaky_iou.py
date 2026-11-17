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
Output: artifact JSON: mỗi lần chạy là 1 dòng
        `{lan, iou: {2, 5, 9}, iou_tat_ca, score_min, tong_ms, min_iou, duoi_nguong}` + tóm tắt
        `iou[f]` (mean/std/min/max, số lần dưới ngưỡng 0,5), `min_iou_moi_lan` (cổng mà test dùng:
        min trên {0, 2, 5, 9} — KHÔNG phải chỉ {2, 5, 9}), `cau_hinh` (checkpoint + `image_size`
        yêu cầu/hiệu lực + device) và `git_rev`/`git_dirty_code`/`lenh`/`do_luc`.

`tong_ms` = thời gian CẢ kịch bản 10 frame (không phải per-frame, không cùng định nghĩa với
`TrackingResult.elapsed_ms`) — tên cũ `ms` mời đọc nhầm 10×, sửa theo P3 review 17-11.
"""

from __future__ import annotations

import argparse
import json
import math
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


def _checkpoint_tu_config() -> str | None:
    """Tên checkpoint trong `configs/default.yaml` — artifact phải gắn số đo với MODEL nào."""
    try:
        from src.config import load_config

        return Path(str(load_config()["checkpoint"])).name
    except Exception:                       # noqa: BLE001 — thiếu config không được làm chết phép đo
        return None


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
    # `NaN`/`inf` lọt vào JSON là `NaN`/`Infinity` (không phải JSON hợp lệ) ⇒ `JSON.parse` của trình
    # duyệt chết, đúng bẫy đã sửa cho p05 ở ticket #23. Không hữu hạn ⇒ `None` + cỡ mẫu.
    huu_han = [v for v in diem_so if math.isfinite(v)]
    score_min = round(min(huu_han), 4) if huu_han else None
    return {
        "iou": {f: iou_theo_frame[f] for f in FRAME_MAU},
        "iou_tat_ca": iou_theo_frame,
        "score_min": score_min,
        "score_n": len(huu_han),
        # Cổng mà TEST dùng là min trên {0, 2, 5, 9} — không phải chỉ 3 frame mẫu (P3 review 17-11).
        "min_iou": round(min(iou_theo_frame.values()), 4),
        "tong_ms": round((time.perf_counter() - bat_dau) * 1000.0, 1),
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
    # Đại lượng QUYẾT ĐỊNH test đỏ là min trên {0, 2, 5, 9} của TỪNG lần chạy, không phải "có frame
    # mẫu nào dưới ngưỡng" (một frame mẫu có thể đạt trong khi frame 0 trượt) — P3 review 17-11.
    min_moi_lan = [lan_i["min_iou"] for lan_i in lan if lan_i.get("min_iou") is not None]
    ra["min_iou_moi_lan"] = {
        "n": len(min_moi_lan),
        "min": round(min(min_moi_lan), 4) if min_moi_lan else None,
        "so_lan_duoi_nguong": sum(1 for v in min_moi_lan if v < NGUONG_IOU),
    }
    return ra


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Đo phân bố IoU của test tracker_engine (ticket #22).")
    ap.add_argument("--lan", type=int, default=10, help="số lần chạy (>= 3 mới nói được gì)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    if args.lan < 3:
        # `n = 1` thì "0/3 lượt dưới ngưỡng" là câu vô nghĩa (AGENTS §6: "n < 2 không kết luận").
        # Từ chối hẳn thay vì cảnh báo rồi chạy: artifact có `n = 1` sẽ bị trích như "ổn định".
        print(f"[LOI] --lan {args.lan}: cần >= 3 mới nói được gì về tần suất đỏ (mỗi lần ~45-75 s)",
              file=sys.stderr)
        return 2

    from src.tracker_engine import TrackerEngine

    # CHỤP PROVENANCE TRƯỚC KHI ĐO. Bản đầu tiên gọi `_git()` ở CUỐI vòng lặp ⇒ artifact khai một
    # `git_rev`/`git_dirty_code` chỉ đúng ở thời điểm KẾT THÚC, có thể chưa tồn tại lúc bắt đầu
    # (P1 review 17-11). Số đo trên cây bẩn/đổi giữa lúc đo là số không tái lập được (AGENTS §6).
    rev_truoc, dirty_truoc, loi_truoc = _git()
    if loi_truoc:
        print(f"[LOI] không lấy được provenance git: {loi_truoc}", file=sys.stderr)
        return 2
    if dirty_truoc:
        print("[LOI] cây BẨN (khác data/ và docs/media/) — commit code trước rồi mới đo; số trên cây "
              "bẩn không tái lập được (AGENTS §6)", file=sys.stderr)
        return 2

    engine = TrackerEngine.build_default()          # nạp model MỘT lần (đắt)
    cau_hinh = {
        "checkpoint": _checkpoint_tu_config(),
        "image_size_yeu_cau": getattr(engine, "image_size", None),
        "image_size_hieu_luc": getattr(engine, "image_size_hieu_luc", None),
        "device": getattr(engine, "device", None),
    }
    lan: list[dict] = []
    for i in range(args.lan):
        # `reset()` TƯỜNG MINH: `start()` cũng tự reset, nhưng nếu ai bỏ auto-reset đó thì 10 lần đo
        # sẽ chạy trên state cũ mà không ai biết (P3 review 17-11).
        engine.reset()
        ket = mot_lan(engine)
        lan.append({"lan": i + 1, **ket,
                    "duoi_nguong": [f for f, v in ket["iou"].items() if v < NGUONG_IOU]})
        print(f"[lan {i + 1}/{args.lan}] IoU " + " · ".join(
            f"f{f}={ket['iou'][f]}" for f in FRAME_MAU)
            + f" · min {ket['min_iou']} · {ket['tong_ms'] / 1000:.1f} s", flush=True)

    rev, dirty, loi = _git()
    if loi or rev != rev_truoc or dirty:
        print(f"[LOI] code ĐỔI trong lúc đo (rev {str(rev_truoc)[:7]} → {str(rev)[:7]}, dirty={dirty}) "
              "⇒ KHÔNG ghi artifact; chạy lại trên cây sạch", file=sys.stderr)
        return 2
    payload = {
        "do_luc": datetime.now().astimezone().isoformat(timespec="seconds"),
        "lenh": " ".join([str(Path(sys.argv[0])), *sys.argv[1:]]),
        "git_rev": rev, "git_dirty_code": dirty, "git_loi": loi,
        "test": "tests/test_tracker_engine.py::TestTrackerEngineStreaming"
                "::test_process_theo_frames_iou_dat_o_cac_frame_mau",
        "fixture": "generate_tracking_sequence(10, (240,320), 40, start=(60,60))",
        "ghi_chu": "IoU bbox vs GT tổng hợp. SAM 2 KHÔNG tất định (AGENTS §6) ⇒ so sánh chỉ có nghĩa "
                   "trong cùng một lần đo; `so_lan_duoi_nguong > 0` = tần suất đỏ của test.",
        "cau_hinh": cau_hinh,
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
