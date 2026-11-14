"""
`./run democheck` — kiểm tra TRƯỚC buổi demo, 9 mục, **không nạp model**, mục tiêu ≤ 120 s.

Chức năng: soi đúng những thứ đã từng làm hỏng buổi demo (hoặc làm "demo chạy được" thành lời nói
           suông): checkpoint có mặt, clip demo mở được, `web/dist` không cũ hơn `web/src`, API sống,
           cổng trống, không còn tệp phiên cũ, nguồn video đọc được frame, frame có ĐỔI (relay đứng
           hình), và commit đang chạy (để số đo buổi demo truy được về mã nguồn).
Input  : --source (mặc định lấy từ configs/default.yaml), --checkpoint, --port, --out-dir,
         --bbox x,y,w,h (cho `--full`), --full (diễn tập thật: dựng API, mở phiên `track`, kiểm
         frame tăng + `mask_fps > 0` — **có** nạp model nên chậm), --base-url, --timeout.
Output : bảng 9 dòng ra stdout (`OK`/`LỖI`/`CẢNH BÁO`), mã thoát 0 nếu mọi mục bắt buộc đều đạt.
Lưu ý  : "OK" ở mục nguồn chỉ có nghĩa *"đọc được frame lúc kiểm"*, **không** phải "bám đúng vật" —
         điều đó chỉ đo được bằng `scripts/measure_live_relay.py` + mIoU, không phải bằng preflight.
         Mục kéo ô chọn trên **camera thật** là việc của người: script in ra 3 bước tay ở cuối.
"""

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_PORT = 8010
MODEL_LOAD_TIMEOUT_S = 260.0        # worker nạp model 20–240 s (AGENTS §6) — preflight không được chặt hơn


@dataclass
class Check:
    """Một mục kiểm. `bat_buoc=False` = chỉ cảnh báo, không làm đỏ buổi demo."""

    ten: str
    ok: bool
    chi_tiet: str
    bat_buoc: bool = True

    @property
    def nhan(self) -> str:
        if self.ok:
            return "OK     "
        return "LỖI    " if self.bat_buoc else "CẢNH BÁO"


def verdict(checks) -> int:
    """Mã thoát: 1 khi có mục BẮT BUỘC không đạt. Mục cảnh báo không bao giờ làm đỏ."""
    return 0 if all(c.ok for c in checks if c.bat_buoc) else 1


# ── Từng mục kiểm. Hàm nhận tham số tiêm được (http/probe) để test không cần mạng/webcam ──────────


def check_checkpoint(path: Path) -> Check:
    path = Path(path)
    if path.is_file() and path.stat().st_size > 0:
        mb = path.stat().st_size / 1e6
        return Check("checkpoint SAM 2", True, f"{path} ({mb:.0f} MB)")
    return Check("checkpoint SAM 2", False,
                 f"KHÔNG thấy {path} — chạy ./run setup hoặc trỏ --checkpoint")


def check_clip(path: Path, min_frames: int = 100) -> Check:
    """Clip demo: mở được + đủ frame. Không mở thì buổi demo chết ngay giây đầu."""
    import cv2

    path = Path(path)
    if not path.is_file():
        return Check("clip demo", False, f"KHÔNG thấy {path}")
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return Check("clip demo", False, f"không mở được {path} (codec/đường dẫn?)")
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok or frame is None:
        return Check("clip demo", False, f"{path} mở được nhưng KHÔNG đọc ra frame nào")
    shape = f"{frame.shape[1]}×{frame.shape[0]}"
    if n and n < min_frames:
        return Check("clip demo", False, f"{path.name}: {n} frame < {min_frames} — demo quá ngắn",
                     bat_buoc=False)
    return Check("clip demo", True, f"{path.name} {shape} {n or '?'} frame")


def check_webbuild(web_dist: Path, web_src: Path) -> Check:
    """`web/dist` phải mới hơn `web/src` — dist cũ làm e2e "PASS" trên mã cũ (đã gặp 12-11)."""
    index = Path(web_dist) / "index.html"
    if not index.is_file():
        return Check("web/dist", False, f"chưa build ({index} không có) — chạy ./run web")
    src_files = [p.stat().st_mtime for p in Path(web_src).rglob("*") if p.is_file()]
    if not src_files:
        return Check("web/dist", True, f"{index.parent} (không có {web_src} để so độ mới)",
                     bat_buoc=False)
    newest = max(src_files)
    if index.stat().st_mtime < newest:
        return Check("web/dist", False,
                     "dist CŨ hơn web/src — chạy lại ./run web (dist cũ ⇒ demo chạy mã cũ)",
                     bat_buoc=False)
    kb = index.stat().st_size / 1024
    return Check("web/dist", True, f"{index.parent} (index.html {kb:.1f} KB)")


def check_api(base_url: str, http_json, bat_buoc: bool = False) -> Check:
    payload = http_json(f"{base_url.rstrip('/')}/health", timeout=2.0)
    if payload is None:
        return Check("API /health", False,
                     f"không trả lời ở {base_url} — chạy ./run api {DEFAULT_PORT} trước khi demo",
                     bat_buoc=bat_buoc)
    return Check("API /health", True, json.dumps(payload, ensure_ascii=False)[:80])


def check_port(port: int, owned: bool = False, api_alive: bool = False) -> Check:
    """Cổng phải trống để `./run api` tự dựng được — TRỪ KHI thứ đang giữ cổng chính là API của ta.

    `owned=True`: `--full` vừa dựng API đó. `api_alive=True`: `/health` trên cổng đã trả lời ⇒ đây
    đúng là trạng thái chuẩn bị demo (API đang chạy), cảnh báo "cổng bận" ở đây là báo oan và mâu
    thuẫn với chính mục `API /health`.
    """
    if owned:
        return Check("cổng API", True, f"{port} do democheck tự dựng cho --full")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        busy = sock.connect_ex(("127.0.0.1", int(port))) == 0
    if busy and api_alive:
        return Check("cổng API", True, f"{port} đang phục vụ API của ta")
    if busy:
        return Check("cổng API", False,
                     f"{port} đang bận nhưng KHÔNG trả /health — tiến trình lạ giữ cổng, tắt trước",
                     bat_buoc=False)
    return Check("cổng API", True, f"{port} trống")


def check_stale_state(out_dir: Path) -> Check:
    """Rác phiên trước trong thư mục chia sẻ.

    **Đừng** cảnh báo `bbox.json`: `WorkerFrameSource._prepare_dir()` xoá `bbox.json`/`frame.jpg`/
    `status.json`/pidfile trước MỖI lần start (`worker_source.py:51,217`) ⇒ nó không bao giờ làm
    phiên sau bám sai, và cảnh báo nó biến preflight thành "luôn có 1 cảnh báo" sau mỗi buổi demo
    (review độc lập 14-11, P2).

    Thứ đáng cảnh báo là **worker mồ côi**: pidfile còn sống ⇒ có tiến trình đang giữ webcam, phiên
    mới sẽ tranh thiết bị ("Device busy", AGENTS §6). Và `state = loading|running` còn trong
    `status.json` ⇒ phiên trước chưa dọn.
    """
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return Check("tệp phiên cũ", True, f"{out_dir} chưa có (sẽ tạo khi chạy)")
    notes = []
    pidfile = out_dir / "worker.pid"
    pid = None
    try:
        pid = int(pidfile.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = None
    if pid and _pid_alive(pid):
        notes.append(f"worker.pid = {pid} CÒN SỐNG (worker mồ côi đang giữ nguồn?)")
    status = out_dir / "status.json"
    if status.is_file():
        try:
            data = json.loads(status.read_text(encoding="utf-8"))
            if data.get("state") in ("loading", "running", "tracking", "waiting_selection"):
                notes.append(f"status.json còn '{data.get('state')}' (phiên trước chưa dọn)")
        except (OSError, ValueError):
            notes.append("status.json hỏng")
    if notes:
        return Check("tệp phiên cũ", False, "; ".join(notes) + " — dọn trước khi demo", bat_buoc=False)
    extra = f", worker.pid {pid} đã chết" if pid else ""
    return Check("tệp phiên cũ", True, f"{out_dir} sạch{extra}")


def _pid_alive(pid: int) -> bool:
    """PID còn sống? (`os.kill(pid, 0)`: PermissionError = sống nhưng không phải của ta.)"""
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def probe_source(source, read_frames, n: int = 8, timeout_s: float = 8.0):
    """Đọc MỘT lần rồi dùng cho cả mục "đọc được" lẫn "frame có đổi".

    Hai lần đọc riêng là hai lần mở nguồn — với webcam/relay, lần thứ hai tranh thiết bị với lần
    thứ nhất và chính preflight sinh ra lỗi "Device busy" mà nó định phát hiện.
    """
    began = time.perf_counter()
    frames, err = read_frames(source, n, timeout_s)
    return frames, err, (time.perf_counter() - began) * 1000


def check_source_frames(source, frames, err, took_ms, n: int = 8, timeout_s: float = 8.0) -> Check:
    """Đọc được `n` frame trong `timeout_s` (webcam bận/relay chết/đường dẫn sai đều rơi ở đây)."""
    if err:
        return Check("nguồn video", False, f"{source}: {err}")
    if len(frames) < n:
        return Check("nguồn video", False,
                     f"{source}: chỉ {len(frames)}/{n} frame trong {timeout_s:.0f} s")
    return Check("nguồn video", True, f"{source}: {len(frames)} frame / {took_ms:.0f} ms")


def check_source_moving(frames) -> Check:
    """Frame phải ĐỔI: relay/camera đứng hình vẫn "đọc được" nhưng demo sẽ là ảnh chết."""
    import numpy as np

    if len(frames) < 2:
        return Check("frame có đổi", False, "cần ≥ 2 frame để so")
    a, b = frames[0], frames[-1]
    if getattr(a, "shape", None) != getattr(b, "shape", None):
        # Đổi kích thước giữa hai frame là BẤT THƯỜNG (nguồn đổi độ phân giải/cắt khung), không phải
        # bằng chứng "nguồn sống" ⇒ cảnh báo, không tính là đạt.
        return Check("frame có đổi", False,
                     "kích thước frame đổi giữa hai lần đọc — nguồn đang đổi cấu hình?", bat_buoc=False)
    diff = float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())
    if diff < 0.01:
        return Check("frame có đổi", False,
                     "hai frame GIỐNG HỆT nhau — nguồn đứng hình (relay treo/ảnh tĩnh)?",
                     bat_buoc=False)
    return Check("frame có đổi", True, f"khác biệt trung bình {diff:.2f}/255")


def check_git(provenance) -> Check:
    """Không chặn, nhưng in ra để mọi số đo buổi demo truy được về một commit cụ thể."""
    rev, dirty, dirty_code, err = provenance()
    if err:
        return Check("mã nguồn", False, f"không lấy được git: {err}", bat_buoc=False)
    if dirty_code:
        return Check("mã nguồn", False, f"{rev[:7]} — cây BẨN (số đo không tái lập được)",
                     bat_buoc=False)
    return Check("mã nguồn", True, f"{rev[:7]}{' (bẩn trong data/)' if dirty else ' — sạch'}")


def _start_api(port: int, timeout_s: float = 25.0):
    """Dựng API tại chỗ cho `--full` (diễn tập phải tự chứa: người dùng không phải mở 2 terminal).

    Trả `Popen` hoặc `None` (không dựng được). Log vào `data/democheck_server.log` để khi hỏng còn
    đọc được lý do — dựng API thất bại mà im lặng là kiểu hỏng tệ nhất trước giờ demo.
    """
    import subprocess

    log = _REPO_ROOT / "data" / "democheck_server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    handle = log.open("wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(_REPO_ROOT), stdout=handle, stderr=subprocess.STDOUT,
    )
    proc._log_handle = handle            # giữ để đóng sau khi kill (không rò fd)
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        if proc.poll() is not None:
            return proc                  # chết ngay: để mục API báo lỗi kèm đường dẫn log
        if _http_json(f"http://127.0.0.1:{port}/health", timeout=1.0) is not None:
            return proc
        time.sleep(0.5)
    return proc


def _stop_api(proc) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:                    # noqa: BLE001 — dọn dẹp không được ném
        try:
            proc.kill()
        except Exception:                # noqa: BLE001
            pass
    handle = getattr(proc, "_log_handle", None)
    if handle is not None:
        try:
            handle.close()
        except Exception:                # noqa: BLE001
            pass


# ── I/O thật (tách khỏi các hàm trên để test tiêm bản giả) ───────────────────────────────


def _http_json(url, timeout=2.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _http_post(url, payload, timeout=5.0):
    """Trả `(body, lỗi)`. Ca hỏng của `--full` ("Device busy", bbox ngoài khung, worker error) trả
    **400 kèm `detail`** — nuốt thân lỗi là ném đi đúng câu giải thích mà preflight tồn tại để đưa."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}"), None
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail")
        except Exception:                            # noqa: BLE001 — thân lỗi không phải JSON
            detail = exc.reason
        return None, f"HTTP {exc.code}: {detail}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def read_frames(source, n, timeout_s):
    """Đọc `n` frame từ nguồn thật qua factory duy nhất (`src/video_source.py`)."""
    from src.video_source import open_video_source

    frames = []
    src = None
    try:
        src = open_video_source(source).open()
        deadline = time.perf_counter() + timeout_s
        while len(frames) < n and time.perf_counter() < deadline:
            frame = src.read()
            if frame is None:
                time.sleep(0.05)
                continue
            frames.append(frame)
    except Exception as exc:                        # noqa: BLE001 — preflight không được ném
        return frames, f"{type(exc).__name__}: {exc}"
    finally:
        if src is not None:
            try:
                src.close()
            except Exception:                       # noqa: BLE001
                pass
    return frames, None


def _provenance():
    from scripts.measure_watchdog import _git_provenance

    return _git_provenance()


def _default_source() -> str:
    """Nguồn mặc định lấy từ config (một nguồn sự thật với `./run demo`), lỗi thì trả '0'."""
    try:
        import yaml

        data = yaml.safe_load((_REPO_ROOT / "configs" / "default.yaml").read_text(encoding="utf-8"))
        return str((data or {}).get("source") or "0")
    except Exception:                               # noqa: BLE001
        return "0"


def _default_checkpoint() -> Path:
    """Checkpoint từ `configs/default.yaml` (nguồn sự thật — README hướng dẫn đổi sang `small`/`base`);
    `tiny` chỉ là fallback khi không đọc được config."""
    try:
        import yaml

        data = yaml.safe_load((_REPO_ROOT / "configs" / "default.yaml").read_text(encoding="utf-8"))
        value = (data or {}).get("checkpoint")
        if value:
            path = Path(str(value))
            return path if path.is_absolute() else _REPO_ROOT / path
    except Exception:                               # noqa: BLE001
        pass
    return _REPO_ROOT / "samurai" / "sam2" / "checkpoints" / "sam2.1_hiera_tiny.pt"


def _out_dir(_source: str) -> Path:
    """Thư mục chia sẻ worker↔API — dùng CHUNG hàm với adapter, không tự đoán đường dẫn."""
    from src.api.adapters.worker_source import live_dir

    return Path(live_dir())


def _is_clip(source) -> bool:
    """Nguồn có phải CLIP demo (file video) không — dùng chung định nghĩa với `_rewind`."""
    from src.video_source import looks_like_file

    from src.video_source import FILE_SUFFIXES

    return looks_like_file(source) and Path(str(source)).suffix.lower() in FILE_SUFFIXES


def run_checks(args) -> list:
    """9 mục kiểm + (tuỳ chọn) diễn tập `--full`. Tách khỏi `main()` để test gọi thẳng."""
    source = args.source or _default_source()
    frames, err, took_ms = probe_source(source, read_frames, timeout_s=args.timeout)
    api_ok = _http_json(f"{args.base_url.rstrip('/')}/health", timeout=2.0) is not None
    checks = [
        check_checkpoint(Path(args.checkpoint) if args.checkpoint else _default_checkpoint()),
        check_clip(Path(source)) if _is_clip(source)
        else Check("clip demo", True, f"nguồn {source} — không phải clip, bỏ qua"),
        check_webbuild(_REPO_ROOT / "web" / "dist", _REPO_ROOT / "web" / "src"),
        check_api(args.base_url, _http_json, bat_buoc=args.full),
        check_port(args.port, owned=bool(getattr(args, "port_owned", False)),
                   api_alive=api_ok),
        check_stale_state(Path(args.out_dir) if args.out_dir else _out_dir(source)),
        check_source_frames(source, frames, err, took_ms, timeout_s=args.timeout),
        check_source_moving(frames),
        check_git(_provenance),
    ]
    if args.full:
        checks.append(_rehearsal(args, source))
    return checks


def _rehearsal(args, source) -> Check:
    """Diễn tập THẬT: mở phiên `track` qua API, chờ `running`, kiểm frame tăng + `mask_fps > 0`.

    Đây là mục **có nạp model** (~20–240 s) — mục đích là chứng minh đường ống sống, không phải đo
    chất lượng bám (xem docstring đầu file).
    """
    base = args.base_url.rstrip("/")
    if not args.bbox:
        # Hộp mặc định rất dễ nằm trên NỀN ⇒ phiên "chạy được" nhưng bám sai, và người đọc dễ trích
        # nhầm nó thành "bám đúng" (AGENTS §6, ca Colab 13-11). Bắt chọn tay, 10 giây.
        return Check("diễn tập phiên", False,
                     "--full cần --bbox x,y,w,h (ô chọn trên vật thật; hộp mặc định hay rơi vào nền)")
    try:
        x, y, w, h = (int(v) for v in str(args.bbox).split(","))
    except ValueError:
        return Check("diễn tập phiên", False, f"--bbox phải là x,y,w,h; nhận {args.bbox!r}")
    bbox = {"x": x, "y": y, "w": w, "h": h}
    # `POST /api/live/start` **chặn tới khi model nạp xong** (`routes.py:190` → `live.start()` →
    # `WorkerFrameSource.start()` → `_wait_first_frame()`), đo trên máy này **3,4–4,1 s** với tiny;
    # checkpoint `small`/`base`, cache lạnh hoặc `image_size` lớn thì vượt xa. Timeout 5 s của
    # `_http_post` (mặc định) sẽ báo hỏng oan VÀ để phiên sống tiếp phía server — chính là ca
    # "không ai gửi stop" (review độc lập 14-11, P0). Dùng cùng mức với vòng chờ `running`.
    timeout = max(30.0, float(args.full_timeout))
    started, start_err = _http_post(f"{base}/api/live/start",
                                    {"source": str(source), "mode": "track", "bbox": bbox},
                                    timeout=timeout)
    if started is None:
        # Timeout KHÔNG có nghĩa là server không dựng phiên: nó có thể đang/chạy xong sau lưng ta.
        # Gửi stop best-effort để không bỏ lại worker giữ webcam.
        _http_post(f"{base}/api/live/stop", {})
        return Check("diễn tập phiên", False,
                     f"POST /api/live/start thất bại ở {base}: {start_err} (timeout {timeout:.0f} s)")
    # `finally` gửi stop: phiên live **không** được sống tiếp sau khi preflight kết thúc (giữ webcam,
    # bỏ lại worker mồ côi nếu API không do chính script dựng). Đã start được thì phải dọn được.
    try:
        status = _wait_running(base, args.full_timeout)
        if status.get("state") == "error":
            return Check("diễn tập phiên", False, str(status.get("message") or "worker báo lỗi"))
        if status.get("state") != "running":
            return Check("diễn tập phiên", False,
                         f"không vào `running` sau {args.full_timeout:.0f} s "
                         f"(state={status.get('state')!r})")
        first = int(status.get("frames") or 0)
        time.sleep(args.sample_s)
        status = _http_json(f"{base}/api/live/status") or {}
    finally:
        _http_post(f"{base}/api/live/stop", {})
    # Phiên có thể CHẾT trong lúc lấy mẫu: `frames`/`mask_fps` khi đó là số "dính" từ trước khi chết
    # ⇒ kiểm `state` TRƯỚC khi kết luận "OK" (review độc lập 14-11, P1).
    if status.get("state") != "running":
        return Check("diễn tập phiên", False,
                     f"phiên đổi trạng thái trong {args.sample_s:.0f} s lấy mẫu: "
                     f"state={status.get('state')!r} — {status.get('message') or 'không có message'}")
    gained = int(status.get("frames") or 0) - first
    mask_fps = status.get("mask_fps") or 0
    if gained <= 0:
        return Check("diễn tập phiên", False, f"`running` nhưng không thêm frame nào trong "
                                              f"{args.sample_s:.0f} s")
    if not float(mask_fps):
        return Check("diễn tập phiên", False,
                     f"{gained} frame nhưng mask_fps = 0 — mask không về (model/vos_every?)")
    return Check("diễn tập phiên", True,
                 f"+{gained} frame / {args.sample_s:.0f} s, mask {float(mask_fps):.1f} FPS, "
                 f"bbox {bbox}")


def _wait_running(base: str, timeout_s: float) -> dict:
    """Chờ tới `running`; trả trạng thái CUỐI (để caller tự quyết error/timeout)."""
    deadline = time.perf_counter() + timeout_s
    status = {}
    while time.perf_counter() < deadline:
        status = _http_json(f"{base}/api/live/status") or {}
        if status.get("state") in ("error", "running"):
            return status
        time.sleep(1.0)
    return status


MANUAL_STEPS = """\
3 bước TAY không tự động hoá được (làm 1 lần trước khi thi):
  1. `./run api 8010` rồi mở http://127.0.0.1:8010/ — kéo chuột chọn vật, bấm Gửi.
  2. Nguồn `0` (webcam thật qua relay): kéo chuột + bấm Bật phát, nhìn luồng MJPEG chạy.
  3. Sau khi Dừng: tải CSV và mở `data/live_*/status.json` xem có `vos_ms`, `mask_fps`.
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra trước buổi demo (không nạp model).")
    parser.add_argument("--source", help="nguồn video (mặc định: configs/default.yaml)")
    parser.add_argument("--checkpoint")
    parser.add_argument("--base-url", default=f"http://127.0.0.1:{DEFAULT_PORT}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--out-dir")
    parser.add_argument("--timeout", type=float, default=8.0, help="giây cho mục nguồn video")
    parser.add_argument("--full", action="store_true", help="diễn tập thật (NẠP MODEL, chậm)")
    parser.add_argument("--bbox", help="x,y,w,h cho --full")
    parser.add_argument("--full-timeout", type=float, default=MODEL_LOAD_TIMEOUT_S)
    parser.add_argument("--sample-s", type=float, default=10.0)
    args = parser.parse_args(argv)

    server = None
    try:
        if args.full and _http_json(f"{args.base_url.rstrip('/')}/health") is None:
            # `--full` tự dựng API: diễn tập mà bắt người dùng mở terminal thứ hai thì trên thực tế
            # người ta sẽ bỏ qua bước diễn tập (và đó đúng là bước cần nhất trước buổi thi).
            args.base_url = f"http://127.0.0.1:{args.port}"
            print(f"[democheck] API chưa chạy — tự dựng ở cổng {args.port} "
                  f"(log: data/democheck_server.log)")
            server = _start_api(args.port)
            args.port_owned = server is not None and server.poll() is None
        checks = run_checks(args)
    finally:
        # Bọc CẢ đoạn dựng API: Ctrl-C/ngoại lệ trong `_start_api` cũng không để uvicorn mồ côi
        # (review độc lập 14-11, P2).
        _stop_api(server)
    print(f"\n=== democheck ({len(checks)} mục) ===")
    for c in checks:
        print(f"  {c.nhan} {c.ten:18s} {c.chi_tiet}")
    bad = [c for c in checks if not c.ok and c.bat_buoc]
    warn = [c for c in checks if not c.ok and not c.bat_buoc]
    print(f"\n{len(checks) - len(bad) - len(warn)} OK · {len(warn)} cảnh báo · {len(bad)} LỖI")
    if bad:
        print("CHƯA DEMO ĐƯỢC — sửa các mục LỖI ở trên.")
    elif not args.full:
        print("Preflight ĐẠT. Còn `--full` (diễn tập có nạp model) + 3 bước tay dưới đây.")
    print("\n" + MANUAL_STEPS)
    return verdict(checks)


if __name__ == "__main__":
    sys.exit(main())
