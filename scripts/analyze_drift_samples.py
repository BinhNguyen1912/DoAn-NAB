"""
Phân tích các file `data/drift_samples_*.csv` thành một artifact có provenance (ticket 15).

Chức năng: đọc TỪNG DÒNG mẫu drift của các lần đo (`scripts/measure_live_relay.py` sinh ra), tính
           phân vị cuộn 200 mẫu, **tỉ lệ cửa sổ báo động**, **độ trễ phát hiện**, và (tuỳ chọn) phép
           đối chứng cảnh TĨNH; rồi ghi 1 artifact JSON + in bảng ra stdout.
Input  : các file CSV (mặc định: mọi `data/drift_samples_*.csv`), `--window`, `--static <glob>`.
Output : `data/drift_series_<mốc>_metrics.json` (git_rev/git_dirty_code/lenh/do_luc + số từng file).
Lưu ý  : `None` = CHƯA ĐO, không phải 0 (AGENTS §6). `drift_iou` là **độ tự nhất quán** của ô bao
         đang hiển thị, KHÔNG phải độ chính xác — đừng trích nó thành "chất lượng bám".
"""

import argparse
import glob
import json
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.measure_watchdog import _git_provenance  # noqa: E402 — dùng lại provenance đã có test
from src.drift_samples import (  # noqa: E402
    WINDOW,
    read_samples,
    static_control,
    summarize,
)


def _meta_for(csv_path: Path):
    """Provenance của lần đo sinh ra CSV (`<tên>.meta.json` bên cạnh) — thiếu thì `None`, không đoán."""
    meta_path = csv_path.with_name(csv_path.name.replace(".csv", ".meta.json"))
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def analyze_file(csv_path: Path, *, window: int = WINDOW, static: bool = False,
                 windows=()) -> dict:
    """Một file mẫu → dict số liệu (hàm thuần ngoài việc đọc file; test bằng CSV trong `tmp_path`).

    `windows` (danh sách cửa sổ) ⇒ thêm mục `theo_cua_so`: độ trễ phát hiện của p05 **luôn** xấp xỉ
    bằng độ dài cửa sổ (chưa đủ `W` mẫu thì chưa có p05 nào để so), nên phải quét nhiều cửa sổ mới
    nói được "đổi cửa sổ thì đánh đổi gì" thay vì báo một con số của một lựa chọn tuỳ ý.
    """
    rows = read_samples(csv_path)
    ket_qua = summarize(rows, window=window)
    info = _meta_for(csv_path)
    ket_qua.update({
        "file": str(csv_path.relative_to(_REPO_ROOT)) if csv_path.is_relative_to(_REPO_ROOT)
                else str(csv_path),
        "git_rev": (info or {}).get("git_rev"),
        "git_dirty_code": (info or {}).get("git_dirty_code"),
        "device_worker_log": (info or {}).get("device_worker_log"),
        "thiet_lap": (info or {}).get("thiet_lap"),
        "co_meta": info is not None,
    })
    if windows:
        # Chỉ đưa các đại lượng THẬT SỰ phụ thuộc cửa sổ. `drift_iou_p05` KHÔNG nằm ở đây: nó tính
        # trên toàn dãy (xem `dinh_nghia`), nhân bản nó vào từng cửa sổ sẽ khiến người đọc kết luận
        # sai "p05 không phụ thuộc cửa sổ" (review độc lập 13-11, P2).
        ket_qua["theo_cua_so"] = {
            str(size): {key: value for key, value in summarize(rows, window=size).items()
                        if key in ("bao_dong_070", "bao_dong_030", "phat_hien")}
            for size in windows
        }
    if static:
        ket_qua["doi_chung_canh_tinh"] = static_control(rows)
    return ket_qua


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", default=[], help="file CSV (mặc định: data/drift_samples_*.csv)")
    parser.add_argument("--static", default="",
                        help="glob các file là CẢNH TĨNH (đối chứng bookkeeping) — tách khỏi clip thật")
    parser.add_argument("--window", type=int, default=WINDOW,
                        help=f"cửa sổ phân vị (mặc định {WINDOW} = _STAT_WINDOW của phiên live)")
    parser.add_argument("--windows", type=int, nargs="*", default=[],
                        help="quét thêm các cửa sổ khác (ghi vào `theo_cua_so`) — độ trễ phát hiện "
                             "xấp xỉ bằng độ dài cửa sổ nên phải quét mới thấy đánh đổi")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    files = [Path(name) for name in args.files] or sorted(
        Path(name) for name in glob.glob(str(_REPO_ROOT / "data" / "drift_samples_*.csv")))
    if not files:
        print("[LOI] không có file drift_samples_*.csv nào — chạy scripts/measure_live_relay.py trước")
        return 1
    static_pattern = args.static
    if static_pattern and not Path(static_pattern).is_absolute():
        static_pattern = str(_REPO_ROOT / static_pattern)
    static_files = ({Path(name).resolve() for name in glob.glob(static_pattern)}
                    if static_pattern else set())

    ket_qua = []
    for path in files:
        la_tinh = path.resolve() in static_files
        ket_qua.append(analyze_file(path, window=args.window, static=la_tinh,
                                    windows=args.windows))

    stamp = datetime.now().astimezone()
    git_rev, git_dirty, git_dirty_code, git_loi = _git_provenance()
    artifact = {
        "do_luc": stamp.isoformat(timespec="seconds"),
        "git_rev": git_rev,
        "git_dirty": git_dirty,
        "git_dirty_code": git_dirty_code,
        "git_loi": git_loi,
        "ghi_chu_git_rev": "Tái lập được ⇔ `git_dirty_code == false`. `git_loi` khác null ⇒ KHÔNG có "
                           "provenance, đừng trích file này.",
        "lenh": "python scripts/analyze_drift_samples.py " + " ".join(sys.argv[1:]),
        "cua_so": args.window,
        "cua_so_quet": args.windows,
        "dinh_nghia": {
            "n_mau_drift": "số dòng có `drift_iou` (mẫu ô bao suy biến bị BỎ ĐO, không phải 0)",
            "drift_iou_p05": "p05 trên TOÀN DÃY mẫu của lần đo — KHÁC p05 của 200 mẫu CUỐI trong "
                              "status.json (cùng định nghĩa phân vị, khác tập mẫu)",
            "bao_dong_070": "tỉ lệ cửa sổ có p05 < 0,70 — trên clip KHOẺ đây chính là tỉ lệ BÁO OAN",
            "bao_dong_030": "tỉ lệ cửa sổ có p05 < 0,30 (ngưỡng cờ chẩn đoán đề xuất trong plan 09-11)",
            "phat_hien": "số mẫu từ mẫu xấu đầu tiên (< 0,5) tới cửa sổ đầu tiên có p05 < 0,30",
            "empty_frac": "tỉ lệ lần VOS trả mask RỖNG (mất dấu) trong các dòng có cột `empty`",
            "p05_thap_va_empty": "điều kiện tiên quyết của ticket 14: cửa sổ p05 < 0,30 MÀ mask rỗng "
                                 "< 3 % (có ⇒ mới được thêm cờ chẩn đoán 'LK nội suy lệch')",
        },
        "canh_bao": "`drift_iou` là độ tự nhất quán của ô bao đang hiển thị, KHÔNG phải độ chính xác "
                    "bám (AGENTS §6). Muốn nói chất lượng phân đoạn phải dùng mIoU vs GT.",
        "file": ket_qua,
    }
    out = Path(args.out) if args.out else (
        _REPO_ROOT / "data" / f"drift_series_{stamp:%Y-%m-%d_%H%M%S}_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("| file | n mẫu | mean | p05 | mask rỗng | báo 0,70 | báo 0,30 | phát hiện sau |")
    print("|---|---|---|---|---|---|---|---|")
    for item in ket_qua:
        phat_hien = item["phat_hien"]["phat_hien_sau_mau"]
        print(f"| {Path(item['file']).name} | {item['n_mau_drift']} | {item['drift_iou_mean']} | "
              f"{item['drift_iou_p05']} | {item['empty_frac']} | "
              f"{item['bao_dong_070']['ti_le_bao']} | {item['bao_dong_030']['ti_le_bao']} | "
              f"{'null' if phat_hien is None else phat_hien} |")
    for item in ket_qua:
        if "doi_chung_canh_tinh" in item:
            control = item["doi_chung_canh_tinh"]
            print(f"\nĐối chứng cảnh tĩnh {Path(item['file']).name}: đạt={control['dat']} "
                  f"n={control['n']} p05={control['drift_iou_p05']} "
                  f"{' · '.join(control['ly_do']) or ''}")
    thieu_meta = [item["file"] for item in ket_qua if not item["co_meta"]]
    if thieu_meta:
        print(f"\n[CANH BAO] thiếu `.meta.json` (không có provenance riêng của lần đo): {thieu_meta}")
    print(f"Ghi: {out}")
    if git_loi:
        print(f"[CANH BAO] không lấy được provenance git: {git_loi}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
