"""
Đo `empty_frac_window` (tỉ lệ lần VOS trả mask RỖNG trong 200 lần chạy GẦN NHẤT) trên các clip có sẵn.

Chức năng: chạy `tools/live_worker.py` cho từng clip + ô chọn, đọc `status.json`, ghi artifact JSON có
           `git_rev`/`git_dirty_code`/`lenh`/`do_luc` + bảng tóm tắt ra stdout.
Input  : --clip (nhiều lần): `tên=đường_dẫn:x,y,w,h`; --image-size, --vos-every, --frames, --out.
Output : `data/empty_window_<ngày>_metrics.json`.
`--expect-lost <clip>`: khai clip KỲ VỌNG có mất dấu — CHỈ clip được khai mới bị chấm đạt/không đạt
         (tiêu chí đăng ký trước). Clip không khai: in số, ghi `ky_vong: "không đặt"`, **không** bị
         coi là hỏng (thực tế khác giả định chưa nói không phải lỗi đo). Không khai clip nào ⇒ lần
         chạy là **CHỈ ĐO**, artifact ghi `ket_luan = "chỉ đo…"` + in cảnh báo, để không ai đọc
         artifact thành "đã đạt". Mỗi lần chạy ghi đè cùng một file artifact — muốn giữ nhiều lần thì
         truyền `--out data/empty_window_<ngày>_run<N>.json`.
`--expect-keep <clip>`: ngược lại — clip PHẢI **không** mất dấu (`empty_frac_window = 0`).
Lưu ý  : ô chọn (bbox) là **đầu vào của phép đo** — sai bbox thì số vô nghĩa (đo 09-11: `binh2` dùng
         bbox của `binh1` cho `empty_frac_window = 0`, đúng bbox của `binh2` cho **0,17**).
         Đây là phép **đếm sự kiện**, không phải phân vị: `empty_runs` là bộ đếm trọn đời (không
         giảm), `empty_frac_window` mới là "hiện tại đang mất dấu bao nhiêu".
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.measure_watchdog import _git_provenance  # noqa: E402 — provenance đã có test riêng

# Ngưỡng số mẫu cửa sổ: dưới mức này tỉ lệ **chưa đo được** (None), không phải 0.
_EMPTY_WINDOW_MIN = 5

# Các trường lấy từ `status.json` — giữ cả `None` (chưa đo) để không biến thành 0,0.
FIELDS = ("state", "device", "frames", "vos_runs", "measured_fps", "vos_fps", "vos_ms", "lk_ms",
          "empty_runs", "empty_frac_window", "empty_window_n", "mask_drops", "lost_streak",
          "drift_iou", "drift_iou_p05", "drift_n", "mask_age_p95", "age_n")


def parse_clip(spec: str) -> tuple[str, str, tuple[int, int, int, int]]:
    """`tên=đường_dẫn:x,y,w,h` → (tên, đường dẫn, bbox). Ném ValueError nếu sai định dạng."""
    try:
        name, rest = spec.split("=", 1)
        path, bbox = rest.rsplit(":", 1)
        x, y, w, h = (int(v) for v in bbox.replace(" ", "").split(","))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"--clip sai định dạng: {spec!r} (cần tên=đường_dẫn:x,y,w,h)") from exc
    return name, path, (x, y, w, h)


def _row_from_status(status: dict, name: str, path: str, bbox) -> dict:
    """Dựng dòng số từ `status.json`. `co_truong_empty_window` phải tính từ **status THÔ**: nếu
    tính từ `row` (sau `row.update`) thì khoá luôn TỒN TẠI với giá trị `None` ⇒ nhánh "worker bản cũ
    không ghi khoá" không bao giờ chạy (review 09-11 vòng 3, P2)."""
    row = {"clip": name, "path": path, "bbox_xywh": list(bbox),
           "co_truong_empty_window": "empty_frac_window" in status}
    row.update({key: status.get(key) for key in FIELDS})
    return row


def summarize(rows: list) -> dict:
    """Tóm tắt thuần (test headless): mỗi clip lấy dòng số + kết luận có/không mất dấu THEO CỬA SỔ.

    `empty_frac_window is None` ⇒ **chưa đủ mẫu**, không được coi là 0 (bẫy AGENTS §6).
    """
    per_clip = {}
    for row in rows:
        name = row["clip"]
        frac = row.get("empty_frac_window")
        per_clip[name] = {
            # `row.get(...)` = dòng dựng tay (test) vẫn suy ra được từ chính nó.
            "co_truong_empty_window": row.get("co_truong_empty_window",
                                              "empty_frac_window" in row),
            "empty_runs": row.get("empty_runs"),
            "empty_frac_window": frac,
            "empty_window_n": row.get("empty_window_n"),
            "drift_iou_p05": row.get("drift_iou_p05"),
            "drift_n": row.get("drift_n"),
            "mask_age_p95": row.get("mask_age_p95"),
            "dang_mat_dau": (None if frac is None else frac > 0),
        }
    return per_clip


def _gan_ky_vong(per_clip: dict, expect: dict) -> dict:
    """Ghi `ky_vong` cho MỌI clip (`True` nếu được khai bằng `--expect-lost`, chuỗi `"không đặt"`
    nếu không) để hình dạng artifact ổn định — clip được khai mà thiếu khoá sẽ làm script đọc
    artifact `KeyError`."""
    for name in per_clip:
        per_clip[name]["ky_vong"] = True if name in expect else "không đặt"
    return per_clip


def _chua_du_mau(per_clip: dict) -> list:
    """Clip nào `empty_frac_window is None` ⇒ **chưa đủ mẫu** = phép đo KHÔNG hoàn tất, kể cả clip
    không khai kỳ vọng. (Bản trước chỉ bắt ca này cho clip được khai ⇒ `--frames 3 --vos-every 3`
    cho 2 lần VOS, `empty_frac_window = None` mà vẫn exit 0 — review 09-11 vòng 3, P2.)"""
    return [f"{name}: chưa đủ mẫu cửa sổ (`empty_window_n` = "
            f"{(per_clip[name].get('empty_window_n') or 0)} < {_EMPTY_WINDOW_MIN}) — chưa đo được"
            for name in per_clip if per_clip[name]["empty_frac_window"] is None]


def _frame_shortfall(rows: list, frames: int) -> list:
    """Lần chạy "sạch" nhưng NGẮN (nguồn chết giữa đường) không phải phép đo hoàn tất."""
    return [f"{row['clip']}: chỉ chạy được {row.get('frames')}/{frames} frame "
            "(nguồn ngắn/chết giữa đường) — không phải phép đo hoàn tất"
            for row in rows if (row.get("frames") or 0) < frames]


def _ket_luan(problems: list, expect: dict) -> str:
    """Một dòng kết luận ghi vào artifact — để không ai đọc "không có lý do hỏng" thành "đã đạt"
    khi chưa hề khai tiêu chí nào."""
    if problems:
        return "KHÔNG ĐẠT: " + " | ".join(problems)
    if not expect:
        return ("CHỈ ĐO — không khai `--expect-lost` nào ⇒ lần chạy này KHÔNG kiểm chứng gì, "
                "chỉ có số")
    return "đạt"


def _verdict(per_clip: dict, expect: dict) -> list:
    """Danh sách lý do KHÔNG đạt — `expect` = {tên_clip: True/False} "có mất dấu hay không".

    CHỈ xét clip có trong `expect` (tức clip người chạy đã khai bằng `--expect-lost`). Clip không
    khai là "kỳ vọng KHÔNG ĐẶT": đo xong in số, **không** biến "thực tế khác giả định chưa nói" thành
    lỗi đo (review 09-11 vòng 2, P2 — cùng lớp bẫy "0/None ≠ đã đo" nhưng ngược chiều).
    Vẫn là lỗi đo: worker thoát mã ≠ 0, thiếu `status.json`, clip không có số, chưa đủ mẫu.
    """
    problems = []
    for name, want in expect.items():
        got = per_clip.get(name)
        if got is None:
            problems.append(f"{name}: không có số")
            continue
        if got["dang_mat_dau"] is None:
            if not got.get("co_truong_empty_window"):
                problems.append(f"{name}: worker KHÔNG ghi `empty_frac_window` (bản cũ?)")
            else:
                problems.append(f"{name}: chưa đủ mẫu (`empty_window_n` = {got['empty_window_n']})")
        elif got["dang_mat_dau"] != want:
            problems.append(f"{name}: kỳ vọng mất dấu = {want}, đo được {got['dang_mat_dau']} "
                            f"(tỉ lệ {got['empty_frac_window']})")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", action="append", required=True,
                        help="tên=đường_dẫn:x,y,w,h (lặp lại được)")
    parser.add_argument("--image-size", type=int, default=192)
    parser.add_argument("--vos-every", type=int, default=3)
    parser.add_argument("--frames", type=int, default=900)
    parser.add_argument("--expect-lost", action="append", default=[],
                        help="tên clip KỲ VỌNG có mất dấu (tiêu chí đăng ký trước). CHỈ clip được "
                             "khai mới bị chấm; clip không khai chỉ in số. Không khai clip nào ⇒ "
                             "lần chạy là CHỈ ĐO (không kiểm chứng gì)")
    parser.add_argument("--expect-keep", action="append", default=[],
                        help="tên clip PHẢI KHÔNG mất dấu (`empty_frac_window` = 0) — để khẳng định "
                             "clip khoẻ vẫn khoẻ, không chỉ khai clip xấu")
    parser.add_argument("--timeout-s", type=float, default=900.0,
                        help="giới hạn thời gian mỗi lần chạy worker")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    clips = [parse_clip(spec) for spec in args.clip]
    rows, errors = [], []
    for name, path, bbox in clips:
        out_dir = Path(f"/dev/shm/doan_empty_window_{name}")
        out_dir.mkdir(parents=True, exist_ok=True)
        # Xoá `status.json` của lần trước: nếu worker lần này chết trước khi ghi, đọc lại file cũ sẽ
        # báo số của PHIÊN TRƯỚC (bẫy `_prepare_dir` đã gặp trong `worker_source`).
        (out_dir / "status.json").unlink(missing_ok=True)
        (out_dir / "bbox.json").write_text(
            json.dumps({"x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3]}), encoding="utf-8")
        cmd = [sys.executable, "tools/live_worker.py", "--source", path, "--out-dir", str(out_dir),
               "--image-size", str(args.image_size), "--max-fps", "30",
               "--vos-every", str(args.vos_every), "--stop-after-frames", str(args.frames)]
        print(f"[{name}] chạy {args.frames} frame…", flush=True)
        try:
            result = subprocess.run(cmd, cwd=str(_REPO_ROOT), capture_output=True, text=True,
                                    timeout=args.timeout_s)
        except subprocess.TimeoutExpired:
            errors.append(f"{name}: worker quá {args.timeout_s:.0f} s chưa xong")
            continue
        if result.returncode != 0:
            lines = (result.stderr or "").strip().splitlines() or ["(không có stderr)"]
            errors.append(f"{name}: worker thoát mã {result.returncode} — {lines[-1]}")
            continue
        try:
            status = json.loads((out_dir / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # Ghi lỗi rồi ĐI TIẾP để artifact vẫn là bằng chứng của lần hỏng (không traceback).
            errors.append(f"{name}: không đọc được status.json ({type(exc).__name__}: {exc})")
            continue
        if status.get("state") == "error":
            # `tools/live_worker.py` trả 0 kể cả khi luồng VOS chết ⇒ mã thoát KHÔNG đủ.
            errors.append(f"{name}: worker ghi `state=error` — "
                          f"{status.get('message') or '(không có message)'}")
            continue
        rows.append(_row_from_status(status, name, path, bbox))

    per_clip = summarize(rows)
    # Chỉ clip ĐƯỢC KHAI mới có kỳ vọng; clip khác in số và ghi "không đặt".
    expect = {name: True for name in args.expect_lost}
    expect.update({name: False for name in args.expect_keep})
    per_clip = _gan_ky_vong(per_clip, expect)
    problems = _verdict(per_clip, expect)
    ket_luan = _ket_luan(problems, expect)
    if ket_luan != "đạt":
        print(f"⚠ {ket_luan}", flush=True)

    problems += _chua_du_mau(per_clip) + _frame_shortfall(rows, args.frames)

    git_rev, git_dirty, git_dirty_code, git_loi = _git_provenance()
    artifact = {
        "do_luc": datetime.now().isoformat(timespec="seconds"),
        "git_rev": git_rev,
        "git_dirty": git_dirty,
        "git_dirty_code": git_dirty_code,
        "git_loi": git_loi,
        "ghi_chu": "`mask_drops`/`mask_holds` ≡ 0 khi `mask_smoothing = 1.0` (mặc định của script "
                   "này) — KHÔNG suy ra được gì từ chúng. `empty_runs` = bộ đếm TRỌN ĐỜI (không "
                   "giảm); `empty_frac_window` = tỉ lệ lần VOS "
                   "trả mask rỗng trong 200 lần GẦN NHẤT (None = chưa đủ mẫu). `drift_iou_p05` là "
                   "ĐỘ TỰ NHẤT QUÁN, không phải độ chính xác. Ô chọn (bbox) là đầu vào của phép đo.",
        "lenh": "python scripts/measure_empty_window.py " + " ".join(sys.argv[1:]),
        "moi_truong": "WSL laptop CPU (Iris Xe), torch CPU, SAM 2.1 tiny",
        "thiet_lap": {"image_size": args.image_size, "vos_every": args.vos_every,
                      "frames": args.frames},
        "ket_luan": ket_luan,
        "ket_qua": rows,
        "tom_tat": per_clip,
        "ky_vong": expect,
        "ly_do_khong_dat": problems,
        "loi": errors,
    }
    out = Path(args.out) if args.out else (
        _REPO_ROOT / "data" / f"empty_window_{datetime.now():%Y-%m-%d}_metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n| clip | empty_runs (trọn đời) | empty_frac_window (200 gần nhất) | drift p05 (n) | "
          "mask_age_p95 |")
    print("|---|---|---|---|---|")
    for name, row in per_clip.items():
        print(f"| {name} | {row['empty_runs']} | {row['empty_frac_window']} "
              f"(n={row['empty_window_n']}) | {row['drift_iou_p05']} ({row['drift_n']}) | "
              f"{row['mask_age_p95']} ms |")
    print(f"\nGhi: {out}")
    if git_loi:
        print(f"[CANH BAO] không lấy được provenance git: {git_loi}")
    for message in problems:
        print(f"[THAT BAI] {message}")
    for message in errors:
        print(f"[LOI] {message}")
    return 0 if (not problems and not errors and not git_loi) else 1


if __name__ == "__main__":
    sys.exit(main())
