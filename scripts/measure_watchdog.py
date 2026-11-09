"""
Đo WATCHDOG phiên live: nguồn chết giữa phiên thì API mất bao lâu để báo lỗi?

Chức năng: dựng API (uvicorn) + một phiên live thật, chờ `running`, rồi **giết nguồn** và đo 3 thứ:
           thời gian tới `state=error`, message người dùng thấy, thời gian luồng MJPEG đóng.
Input  : --mode (worker | raw), --clip/--bbox/--image-size (worker), --snapshot (raw), --lan, --port.
Output : JSON (`data/watchdog_<ngày>_metrics.json` cho `worker`, `data/watchdog_raw_<ngày>_…` cho
         `raw`) có `git_rev`, `git_dirty`, `lenh`, `do_luc` + từng lần chạy; in bảng tóm tắt.
Lưu ý  : hai ca có bản chất khác nhau, ĐỪNG trộn số:
         - `worker` (mode `track`): `kill -9` tiến trình worker ⇒ bắt bằng `proc.poll()`, **~0,1 s**;
         - `raw` (webcam/relay): tắt server ảnh ⇒ chỉ biết qua "không có frame", nên chờ ngưỡng
           `STALE_S` của `OpenCvFrameSource` (**~3 s**) mới kết luận.
         Script CHẠY worker thật (cần torch + checkpoint SAM 2) ở mode `worker`, nhưng chỉ kiểm tra
         **phản ứng của API**, không đánh giá chất lượng bám — không được trích FPS/mIoU từ file này.
"""

import argparse
import functools
import http.server
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

NGUONG_DANG_KY_TRUOC_S = 2.0     # plan 08-11: API phải chuyển `error` ≤ 2 s sau khi worker chết
POLL_S = 0.02


def _get(base, path, timeout=5.0):
    with urllib.request.urlopen(base + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(base, path, payload):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base + path, data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_up(base, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            _get(base, "/health", timeout=1.0)
            return True
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.2)
    return False


class _StreamProbe(threading.Thread):
    """Đọc luồng MJPEG tới khi server đóng kết nối; ghi lại số byte + mốc thời gian."""

    def __init__(self, base, started_at):
        super().__init__(daemon=True)
        self.base = base
        self.started_at = started_at
        self.bytes = 0
        self.closed_at = None
        self.error = None

    def run(self):
        try:
            with urllib.request.urlopen(self.base + "/api/live/stream", timeout=30) as response:
                while True:
                    chunk = response.read(4096)
                    if not chunk:
                        break
                    self.bytes += len(chunk)
        except Exception as exc:                      # noqa: BLE001 — đóng kết nối cũng là "kết thúc"
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            self.closed_at = time.perf_counter()


def _read_pid(live_dir):
    try:
        return int((Path(live_dir) / "worker.pid").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _wait_running(base, timeout=240.0):
    """Chờ phiên live vào `running` (worker nạp model 20–60 s trên CPU)."""
    deadline = time.time() + timeout
    status = {}
    while time.time() < deadline:
        status = _get(base, "/api/live/status")
        if status.get("state") == "running":
            return status
        if status.get("state") == "error":
            raise RuntimeError(f"phiên live lỗi ngay khi mở: {status.get('message')}")
        time.sleep(0.1)
    raise RuntimeError(f"phiên live không vào `running` trong {timeout:.0f}s: {status}")


def _one_run(base, args, live_dir):
    """Một lần thí nghiệm: mở phiên → kill -9 worker → đo phản ứng của API."""
    started_at = time.perf_counter()
    _post(base, "/api/live/start", {
        "source": args.clip, "mode": "track", "bbox": dict(zip("xywh", args.bbox)),
        "image_size": args.image_size, "vos_every": args.vos_every,
    })
    running = _wait_running(base)
    load_s = round(time.perf_counter() - started_at, 1)

    pid = None
    for _ in range(100):                       # pidfile do adapter ghi ngay sau khi spawn
        pid = _read_pid(live_dir)
        if pid:
            break
        time.sleep(0.05)
    if not pid:
        raise RuntimeError(f"không thấy {Path(live_dir) / 'worker.pid'}")

    probe = _StreamProbe(base, time.perf_counter())
    probe.start()
    time.sleep(0.5)                            # để luồng thật sự có frame rồi mới giết
    stream_bytes_before_kill = probe.bytes

    killed_at = time.perf_counter()
    os.kill(pid, signal.SIGKILL)
    error_at = None
    message = ""
    while time.perf_counter() - killed_at < 10.0:
        status = _get(base, "/api/live/status")
        if status.get("state") != "running":
            error_at = time.perf_counter()
            message = status.get("message", "")
            break
        time.sleep(POLL_S)
    probe.join(timeout=15.0)
    _post(base, "/api/live/stop", {})

    return {
        "load_s": load_s,
        "pid": pid,
        "frames_truoc_khi_giet": running.get("frames"),
        "byte_luong_truoc_khi_giet": stream_bytes_before_kill,
        "state_sau_khi_giet": status.get("state"),
        "message": message,
        "tg_bao_error_ms": round((error_at - killed_at) * 1000, 1) if error_at else None,
        "tg_dong_luong_ms": (round((probe.closed_at - killed_at) * 1000, 1)
                             if probe.closed_at else None),
        "luong_dong_kieu": probe.error or "EOF (server đóng kết nối)",
        # Ngưỡng đăng ký trước KHÁC nhau cho hai ca (xem docstring đầu file)
        **_verdict(error_at, killed_at, NGUONG_DANG_KY_TRUOC_S),
    }


def _verdict(error_at, killed_at, nguong_s):
    """(that_bai, vuot_nguong) cho một lần đo — "không phát hiện được" là THẤT BẠI, không phải đạt.

    Trước đây `vuot_nguong = error_at and ...` ⇒ khi hết 15 s vẫn `running` (hỏng NẶNG NHẤT) thì
    `False` ⇒ artifact ghi `so_lan_vuot_nguong = 0` và script thoát 0. Đúng bẫy "0/None ≠ đã đo"
    (AGENTS §6) nên phải tách hai khái niệm: `that_bai` = không đo được phản ứng.
    """
    if error_at is None:
        return True, True
    return False, (error_at - killed_at) > nguong_s


def _is_dirty_outside_data(porcelain: str) -> bool:
    """Có file nào khác `data/` bị đổi so với commit không? (tái lập số ⇔ False)

    Bỏ `data/` vì chính file artifact là thứ đang được ghi lại — nếu tính nó thì lần đo nào cũng
    "bẩn" một cách vô nghĩa. File code MỚI chưa track vẫn được tính (là code, không phải data).
    """
    for line in porcelain.splitlines():
        path = line[3:].strip()
        if path and not path.startswith("data/"):
            return True
    return False


def _git_provenance():
    """(git_rev, git_dirty, git_dirty_code, git_loi) — KHÔNG ném khi thiếu git/hỏng repo.

    Vì sao tách hàm: nhánh lỗi từng làm `git_dirty_code` không được gán ⇒ `UnboundLocalError` nuốt
    mất cả 3 lần đo ngay trước khi ghi artifact (review độc lập 09-11, P2). Có test riêng.

    `git_loi` (chuỗi lý do hoặc None): không có provenance thì artifact phải NÓI RA và script thoát
    1 — ghi `git_rev: ""` rồi thoát 0 là "artifact trông hợp lệ" (review vòng 2, P2). Bắt rộng
    `Exception` vì git có thể ném `UnicodeDecodeError` khi locale/tiếng Việt lạ — ném lúc đó là ném
    SAU KHI đo xong, đúng chỗ lỗi cũ muốn bịt.
    """
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT),
                             capture_output=True, text=True, check=True).stdout.strip()
        changed = subprocess.run(["git", "status", "--porcelain"], cwd=str(_REPO_ROOT),
                                 capture_output=True, text=True).stdout
    except Exception as exc:                           # noqa: BLE001 — provenance không được ném
        return None, None, None, f"{type(exc).__name__}: {exc}"
    if not rev:
        return None, None, None, "git rev-parse trả rỗng"
    return rev, bool(changed.strip()), _is_dirty_outside_data(changed), None


class _SnapshotServer:
    """Server tĩnh phục vụ `snapshot.jpg` (giả lập relay camera `scripts/win_camera_relay.py`).

    Vì sao cần: để đo watchdog của mode `raw` bằng nguồn THẬT qua mạng — tắt server là "rút camera",
    đúng ca mà `OpenCvFrameSource.health()` phải phát hiện.
    """

    def __init__(self, directory, port):
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _one_run_raw(base, args, snapshot_port):
    """Một lần thí nghiệm mode `raw`: mở phiên từ relay ảnh → TẮT relay → đo phản ứng của API."""
    url = f"http://127.0.0.1:{snapshot_port}/{Path(args.snapshot).name}"
    server = _SnapshotServer(Path(args.snapshot).parent, snapshot_port).start()
    try:
        started_at = time.perf_counter()
        _post(base, "/api/live/start", {"source": url, "mode": "raw"})
        running = _wait_running(base)
        load_s = round(time.perf_counter() - started_at, 1)

        probe = _StreamProbe(base, time.perf_counter())
        probe.start()
        time.sleep(0.5)
        bytes_before = probe.bytes

        killed_at = time.perf_counter()
        server.stop()                       # "rút camera": từ đây nguồn không trả frame nữa

        error_at, message = None, ""
        while time.perf_counter() - killed_at < 15.0:
            status = _get(base, "/api/live/status")
            if status.get("state") != "running":
                error_at = time.perf_counter()
                message = status.get("message", "")
                break
            time.sleep(POLL_S)
        probe.join(timeout=20.0)
        _post(base, "/api/live/stop", {})
    finally:
        server.stop()

    return {
        "load_s": load_s,
        "frames_truoc_khi_giet": running.get("frames"),
        "byte_luong_truoc_khi_giet": bytes_before,
        "state_sau_khi_giet": status.get("state"),
        "message": message,
        "tg_bao_error_ms": round((error_at - killed_at) * 1000, 1) if error_at else None,
        "tg_dong_luong_ms": (round((probe.closed_at - killed_at) * 1000, 1)
                             if probe.closed_at else None),
        "luong_dong_kieu": probe.error or "EOF (server đóng kết nối)",
        # `frames` của API chỉ đếm khi NỘI DUNG frame đổi; relay phục vụ đúng MỘT file ảnh nên
        # luôn là 0 — ghi rõ để không ai đọc thành "chưa từng có frame" (review vòng 2, P3).
        "ghi_chu_frames": "frames đếm khung hình ĐỔI nội dung; relay phục vụ 1 ảnh tĩnh ⇒ 0 là bình "
                          "thường, KHÔNG phải 'nguồn không ra frame'",
        # Ngưỡng đăng ký trước KHÁC nhau cho hai ca (xem docstring đầu file)
        **_verdict(error_at, killed_at, args.nguong_s),
    }


def _exit_code(runs, loi, git_loi) -> int:
    """Mã thoát: 0 CHỈ KHI đo được phản ứng trong ngưỡng và có provenance (review vòng 2, P2).

    Trước đây: lần đo không phát hiện được lỗi (`that_bai`) và nhánh git lỗi đều trả 0 ⇒ CI/log
    người đọc bằng `&&` sẽ thấy "đạt" trong khi artifact hoặc không có số, hoặc không có `git_rev`.
    """
    if loi or git_loi:
        return 1
    return 1 if any(r.get("that_bai") or r.get("vuot_nguong") for r in runs) else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Đo phản ứng của API khi nguồn live chết (watchdog)")
    parser.add_argument("--mode", choices=("worker", "raw"), default="worker",
                        help="worker = kill -9 worker (mode track) · raw = tắt relay ảnh (mode raw)")
    parser.add_argument("--nguong-s", type=float, default=None,
                        help="ngưỡng đăng ký trước (mặc định 2 s cho worker, 5 s cho raw)")
    parser.add_argument("--snapshot", default="data/demo_input_frames/00000.jpg",
                        help="ảnh JPEG để làm relay (mode raw)")
    parser.add_argument("--clip", default="data/binh1.mp4")
    parser.add_argument("--bbox", default="104,308,209,287",
                        help="x,y,w,h trong khung gốc (mặc định: ô của binh1 trong ./run reid)")
    parser.add_argument("--image-size", type=int, default=192)
    parser.add_argument("--vos-every", type=int, default=3)
    parser.add_argument("--lan", type=int, default=3, help="số lần chạy (mỗi lần kill worker một lần)")
    parser.add_argument("--port", type=int, default=8021)
    parser.add_argument("--out-dir", default="/dev/shm/doan-live-watchdog")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    args.bbox = tuple(int(v) for v in args.bbox.split(","))
    if len(args.bbox) != 4:
        parser.error("--bbox phải là x,y,w,h")
    if args.nguong_s is None:
        # worker: `proc.poll()` nên phải nhanh (plan 08-11 ghi ≤ 2 s). raw: chỉ biết qua "không có
        # frame" ⇒ ngưỡng là STALE_S 3 s (+ chờ mạng), đăng ký trước 5 s.
        args.nguong_s = 2.0 if args.mode == "worker" else 5.0
    snapshot_port = args.port + 1

    if args.out:
        out = Path(args.out)
    else:
        kind = "watchdog" if args.mode == "worker" else "watchdog_raw"
        out = _REPO_ROOT / "data" / f"{kind}_{datetime.now():%Y-%m-%d}_metrics.json"
    base = f"http://127.0.0.1:{args.port}"
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, DOAN_LIVE_DIR=args.out_dir)

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.main:app", "--host", "127.0.0.1",
         "--port", str(args.port), "--log-level", "warning"],
        cwd=str(_REPO_ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=(_REPO_ROOT / "data" / "watchdog_api.log").open("w"),
    )
    runs, error = [], None
    try:
        if not _wait_up(base):
            raise RuntimeError("API không khởi động được (xem data/watchdog_api.log)")
        for index in range(args.lan):
            viet = "kill -9 worker" if args.mode == "worker" else "tắt relay ảnh"
            print(f"[{index + 1}/{args.lan}] {viet} rồi đo…", flush=True)
            if args.mode == "worker":
                runs.append(_one_run(base, args, args.out_dir))
            else:
                runs.append(_one_run_raw(base, args, snapshot_port))
    except Exception as exc:                          # noqa: BLE001 — ghi lỗi vào artifact
        error = f"{type(exc).__name__}: {exc}"
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    git_rev, git_dirty, git_dirty_code, git_loi = _git_provenance()

    errors = [r["tg_bao_error_ms"] for r in runs if r["tg_bao_error_ms"] is not None]
    result = {
        "do_luc": datetime.now().isoformat(timespec="seconds"),
        "git_rev": git_rev,
        "git_dirty": git_dirty,
        "git_dirty_code": git_dirty_code,
        "git_loi": git_loi,
        "ghi_chu_git_rev": "git_rev = commit chứa CODE sinh ra số; CHỈ ĐƯỢC commit thêm docs/data sau "
                           "đó (không sửa code) thì số mới tái lập được. `git_dirty` = có file nào "
                           "khác commit đó (kể cả file mới chưa track); `git_dirty_code` = như trên "
                           "NHƯNG bỏ qua `data/` (đo lại lần nữa thì chính file artifact bị sửa — "
                           "không phải code bẩn). Tái lập được ⇔ `git_dirty_code == false`. "
                           "`git_loi` khác null ⇒ KHÔNG có provenance (artifact không được trích).",
        "moi_truong": "WSL laptop CPU (Intel Iris Xe, không GPU rời), torch CPU, SAM 2.1 tiny, "
                      f"image_size {args.image_size}" if args.mode == "worker" else
                      "WSL laptop CPU, mode `raw`: relay ảnh JPEG qua HTTP (localhost)",
        "lenh": "python scripts/measure_watchdog.py " + " ".join(sys.argv[1:]),
        "nguong_dang_ky_truoc": {
            "nguon": ("docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md (≤ 2 s cho worker)"
                      if args.mode == "worker" else
                      "review 09-11 P3: mode `raw` phải tự báo lỗi; ngưỡng chọn trước là 5 s vì chỉ "
                      "biết qua 'không có frame' (STALE_S = 3 s)"),
            "dieu_kien": f"giết nguồn giữa phiên (mode {args.mode}) ⇒ /api/live/status trả `error` ≤ "
                         f"{args.nguong_s:.0f} s, message nêu lý do, luồng MJPEG đóng",
        },
        "thiet_lap": ({"clip": args.clip, "bbox_xywh": list(args.bbox),
                       "image_size": args.image_size, "vos_every": args.vos_every,
                       "so_lan": args.lan} if args.mode == "worker" else
                      {"snapshot": args.snapshot, "so_lan": args.lan}),
        "ket_qua": runs,
        "tom_tat": {
            "n": len(runs),
            "tg_bao_error_ms": {"min": min(errors) if errors else None,
                                "max": max(errors) if errors else None,
                                "mean": round(sum(errors) / len(errors), 1) if errors else None},
            "so_lan_vuot_nguong": sum(1 for r in runs if r["vuot_nguong"]),
            "so_lan_khong_phat_hien": sum(1 for r in runs if r.get("that_bai")),
            "so_lan_luong_khong_dong": sum(1 for r in runs if r["tg_dong_luong_ms"] is None),
            "message_mau": runs[0]["message"] if runs else "",
        },
        "loi": error,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\nmode {args.mode} · ngưỡng đăng ký trước {args.nguong_s:.0f} s")
    print("| lần | nạp | state | báo error | đóng luồng | message |")
    print("|---|---|---|---|---|---|")
    for index, run in enumerate(runs, 1):
        print(f"| {index} | {run['load_s']}s | {run['state_sau_khi_giet']} | "
              f"{run['tg_bao_error_ms']} ms | {run['tg_dong_luong_ms']} ms | {run['message']} |")
    print(f"\nGhi: {out}")
    if git_loi:
        print(f"[CANH BAO] không lấy được provenance git: {git_loi}")
    thieu = [i for i, r in enumerate(runs, 1) if r.get("that_bai")]
    if thieu:
        print(f"[THAT BAI] không phát hiện được lỗi trong 15 s ở lần {thieu} — "
              "lỗi nặng nhất lại từng được ghi là 'không vượt ngưỡng'")
    if error:
        print(f"[LOI] {error}")
    return _exit_code(runs, error, git_loi)
    return 0


if __name__ == "__main__":
    sys.exit(main())
