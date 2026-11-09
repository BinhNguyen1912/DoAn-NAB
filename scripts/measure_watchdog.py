"""
Đo WATCHDOG phiên live bằng WORKER THẬT: `kill -9` worker giữa phiên thì API mất bao lâu để báo lỗi?

Chức năng: dựng API (uvicorn) + phiên live mode=track trên clip thật, chờ `running`, `kill -9` tiến
           trình worker, rồi đo 3 thứ: thời gian tới `state=error`, message người dùng thấy, và thời
           gian luồng MJPEG đóng (client không bị treo).
Input  : --clip, --bbox, --image-size, --lan (số lần chạy), --port.
Output : JSON (mặc định `data/watchdog_<ngày>_metrics.json`) có `git_rev`, `git_dirty`, `lenh`,
         `do_luc` + từng lần chạy; in bảng tóm tắt ra console.
Lưu ý  : script CHẠY worker thật (cần torch + checkpoint SAM 2) nhưng chỉ để kiểm tra **phản ứng của
         API**, không đánh giá chất lượng bám — không được trích FPS/mIoU từ file này.
         Trước khi sửa watchdog (08-11), worker chết ⇒ API vẫn báo `running` mãi và luồng chỉ đóng
         sau `idle_timeout` 5 s; đó là lý do phép đo này tồn tại.
"""

import argparse
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
        "vuot_nguong": bool(error_at and (error_at - killed_at) > NGUONG_DANG_KY_TRUOC_S),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo phản ứng của API khi worker live chết (watchdog)")
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

    out = Path(args.out) if args.out else (
        _REPO_ROOT / "data" / f"watchdog_{datetime.now():%Y-%m-%d}_metrics.json")
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
            print(f"[{index + 1}/{args.lan}] kill -9 worker rồi đo…", flush=True)
            runs.append(_one_run(base, args, args.out_dir))
    except Exception as exc:                          # noqa: BLE001 — ghi lỗi vào artifact
        error = f"{type(exc).__name__}: {exc}"
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    try:
        git_rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT),
                                 capture_output=True, text=True, check=True).stdout.strip()
        git_dirty = bool(subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=str(_REPO_ROOT), capture_output=True, text=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        git_rev, git_dirty = "", None

    errors = [r["tg_bao_error_ms"] for r in runs if r["tg_bao_error_ms"] is not None]
    result = {
        "do_luc": datetime.now().isoformat(timespec="seconds"),
        "git_rev": git_rev,
        "git_dirty": git_dirty,
        "ghi_chu_git_rev": "git_rev = commit chứa CODE sinh ra số; CHỈ ĐƯỢC commit thêm docs/data sau "
                           "đó (không sửa code) thì số mới tái lập được. `git_dirty` = có thay đổi "
                           "trên file ĐÃ THEO DÕI so với commit đó (file artifact mới chưa track "
                           "không tính — chính nó là thứ đang được ghi).",
        "moi_truong": "WSL laptop CPU (Intel Iris Xe, không GPU rời), torch CPU, SAM 2.1 tiny, "
                      f"image_size {args.image_size}",
        "lenh": "python scripts/measure_watchdog.py " + " ".join(sys.argv[1:]),
        "nguong_dang_ky_truoc": {
            "nguon": "docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md (viết TRƯỚC khi chạy)",
            "dieu_kien": f"kill -9 worker giữa phiên ⇒ /api/live/status trả `error` ≤ "
                         f"{NGUONG_DANG_KY_TRUOC_S:.0f} s, message nêu lý do, luồng MJPEG đóng",
        },
        "thiet_lap": {"clip": args.clip, "bbox_xywh": list(args.bbox),
                      "image_size": args.image_size, "vos_every": args.vos_every,
                      "so_lan": args.lan},
        "ket_qua": runs,
        "tom_tat": {
            "n": len(runs),
            "tg_bao_error_ms": {"min": min(errors) if errors else None,
                                "max": max(errors) if errors else None,
                                "mean": round(sum(errors) / len(errors), 1) if errors else None},
            "so_lan_vuot_nguong": sum(1 for r in runs if r["vuot_nguong"]),
            "so_lan_luong_khong_dong": sum(1 for r in runs if r["tg_dong_luong_ms"] is None),
            "message_mau": runs[0]["message"] if runs else "",
        },
        "loi": error,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n| lần | nạp | state | báo error | đóng luồng | message |")
    print("|---|---|---|---|---|---|")
    for index, run in enumerate(runs, 1):
        print(f"| {index} | {run['load_s']}s | {run['state_sau_khi_giet']} | "
              f"{run['tg_bao_error_ms']} ms | {run['tg_dong_luong_ms']} ms | {run['message']} |")
    print(f"\nGhi: {out}")
    if error:
        print(f"[LOI] {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
