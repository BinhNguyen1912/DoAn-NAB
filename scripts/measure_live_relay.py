"""
Đo ĐƯỜNG DEMO THẬT: webcam Windows → relay HTTP → API live → bám đối tượng → mask.

Chức năng: dựng API (uvicorn) + mở phiên live `mode=track` trên nguồn **ảnh camera thật** (relay
           `scripts/cam_relay.sh` phục vụ `/snapshot.jpg`), chờ tới `running`, lấy mẫu
           `/api/live/status` trong N giây, chụp vài frame đã overlay mask, rồi ghi 1 artifact JSON
           có `git_rev` + `lenh` + `do_luc` và bảng tóm tắt ra stdout.
Input  : --source (URL snapshot của relay hoặc đường dẫn video), --bbox x,y,w,h (ô chọn đối tượng),
         --image-size, --vos-every, --seconds, --port, --out, --frame-dir,
         --device cpu|cuda (10-11: chạy model trên GPU của đường LIVE — trước đó đường live bị
         ghim CPU vì worker không nhận `device`; số FPS đo ra phải ghi kèm thiết bị).
Output : `data/live_web_relay_<ngày>_metrics.json` (đuôi `_metrics.json` để `.gitignore` cho qua, đúng
         quy ước artifact của repo) + ảnh `data/live_web_relay_<ngày>/frame*.jpg` (**không** commit ảnh:
         repo không giữ binary trong `data/`).
Lưu ý  : đây là **bằng chứng "camera thật đã chạy"**, không phải benchmark chất lượng bám.
         Số `drift_iou` ở đây là độ tự nhất quán của ô bao (xem AGENTS §6) — cấm gọi là độ chính xác.
         Bbox do người chọn tay trên ảnh camera; nếu khung cảnh không có vật rõ thì SAM 2 vẫn bám
         vùng đó (kết quả chỉ nói "đường ống chạy được", không nói "bám đúng vật").
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.measure_watchdog import _git_provenance  # noqa: E402 — dùng lại provenance đã có test
from src.device import ENV_VAR, device_from_env  # noqa: E402 — cùng nguồn sự thật với API/worker

POLL_S = 0.5
WAIT_RUNNING_S = 240.0     # nạp model SAM 2 trên CPU: 20–60 s, chừa rộng cho máy đang tải


def _get(base, path, timeout=5.0):
    with urllib.request.urlopen(base + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(base, path, payload, timeout=600.0):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base + path, data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # KHÔNG để mất thân lỗi: API trả `{"detail": "..."}` là lý do THẬT (ví dụ xin `cuda` mà máy
        # không có GPU). Bản trước ném `HTTPError: 400` trơn ⇒ artifact ghi lỗi vô nghĩa
        # (đã gặp thật khi đo nhánh GPU-live 10-11).
        body = exc.read().decode("utf-8", "replace").strip()
        raise RuntimeError(f"POST {path} → HTTP {exc.code}: {body[:500]}") from exc


def _get_bytes(base, path, timeout=10.0):
    with urllib.request.urlopen(base + path, timeout=timeout) as response:
        return response.read()


def _wait_up(base, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            _get(base, "/health", timeout=1.0)
            return True
        except (urllib.error.URLError, OSError, ValueError):
            time.sleep(0.2)
    return False


def _wait_running(base, timeout=WAIT_RUNNING_S):
    deadline = time.time() + timeout
    status = {}
    while time.time() < deadline:
        status = _get(base, "/api/live/status")
        if status.get("state") == "running":
            return status
        if status.get("state") == "error":
            raise RuntimeError(f"phiên live lỗi ngay khi mở: {status.get('message')}")
        time.sleep(0.2)
    raise RuntimeError(f"phiên live không vào `running` trong {timeout:.0f}s: {status}")


def summarize(samples) -> dict:
    """Tóm tắt danh sách mẫu `/api/live/status` — hàm THUẦN (test headless được).

    Nguyên tắc: `None` (chưa đo) KHÔNG được đổi thành 0. `drift_iou`/`mask_age_p95` chỉ có nghĩa
    khi `drift_n`/`age_n` > 0; số mẫu được ghi kèm để người đọc không trích nhầm (AGENTS §6).

    Chỉ tóm tắt **đúng những trường API có** (`LiveStatusResponse`): thêm `display_fps` (nhịp HUD —
    nguồn gốc con số "29,9 FPS" trong báo cáo). `drift_*`/`mask_age_p95` **không** nằm trong API ⇒
    lấy từ `status.json` ở `worker_status`, để artifact không có khoá "trông như đã đo" mà luôn
    `None` (review độc lập nhánh bằng chứng, P2).
    """
    frames = [s.get("frames") or 0 for s in samples]
    # Chỉ lấy mẫu CÓ số: thiếu trường ⇒ `None`, không được biến thành `0,0` (bẫy "0 ≠ chưa đo").
    fps = [s["measured_fps"] for s in samples if s.get("measured_fps") is not None]
    mask_fps = [s["mask_fps"] for s in samples if s.get("mask_fps") is not None]
    display_fps = [s["display_fps"] for s in samples if s.get("display_fps") is not None]
    states = [s.get("state") for s in samples]
    return {
        "n_mau": len(samples),
        "state_cuoi": states[-1] if states else None,
        "frames_dau": frames[0] if frames else 0,
        "frames_cuoi": frames[-1] if frames else 0,
        "measured_fps_max": round(max(fps), 1) if fps else None,
        "display_fps_max": round(max(display_fps), 1) if display_fps else None,
        "display_fps_cuoi": round(display_fps[-1], 1) if display_fps else None,
        "mask_fps_max": round(max(mask_fps), 1) if mask_fps else None,
        "mask_fps_cuoi": round(mask_fps[-1], 1) if mask_fps else None,
        "empty_runs_cuoi": samples[-1].get("empty_runs") if samples else None,
        "message_cuoi": samples[-1].get("message", "") if samples else "",
    }


def _is_ancestor(rev: str) -> bool:
    """`rev` có phải tổ tiên của HEAD không (provenance chỉ có nghĩa khi `git show <rev>` chạy được)."""
    try:
        done = subprocess.run(["git", "merge-base", "--is-ancestor", rev, "HEAD"],
                              cwd=str(_REPO_ROOT), capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return True                                   # không kết luận được ⇒ đừng chặn
    return done.returncode == 0


def _ten_clip(source: str) -> str:
    """Tên clip để đặt file mẫu: `data/binh1.mp4` → `binh1`; nguồn mạng → `relay`.

    Dùng cho tên file `drift_samples_<clip>_<mốc>.csv` (ticket 15) — phải đọc được bằng mắt khi liệt
    kê `data/`, nên bỏ mọi ký tự ngoài chữ/số.
    """
    if "://" in source:
        return "relay"
    stem = Path(source).stem or "clip"
    return re.sub(r"[^0-9A-Za-z_-]+", "_", stem)


def _luu_mau_drift(out_dir, clip: str, stamp: datetime, meta: dict) -> dict:
    """Chép `drift_samples.csv` của phiên ra `data/drift_samples_<clip>_<mốc>.csv` + `.meta.json`.

    Vì sao phải chép ra `data/`: file gốc nằm trong `out_dir` = `/dev/shm` (tmpfs) — runtime tắt là
    mất, đúng thứ đã xảy ra với `worker.log` trên Colab ngày 12-11. `.meta.json` đi kèm để dãy mẫu
    mang `git_rev`/`lenh`/`do_luc` (AGENTS §6): số đo không có provenance thì không được trích.
    """
    nguon = Path(out_dir) / "drift_samples.csv"
    if not nguon.exists():
        return {"csv": None, "meta": None, "n_dong": 0,
                "ly_do": "phiên không ghi mẫu drift nào (xem `tom_tat`/`worker_status`)"}
    dich = _REPO_ROOT / "data" / f"drift_samples_{clip}_{stamp:%Y-%m-%d_%H%M%S}.csv"
    dich.write_text(nguon.read_text(encoding="utf-8"), encoding="utf-8")
    from src.drift_samples import read_samples      # import muộn: script phải chạy được cả khi lỗi
    meta_path = dich.with_name(dich.name.replace(".csv", ".meta.json"))
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = read_samples(dich)

    def _tuong_doi(path):
        try:
            return str(path.relative_to(_REPO_ROOT))
        except ValueError:
            return str(path)

    return {"csv": _tuong_doi(dich), "meta": _tuong_doi(meta_path),
            "n_dong": len(rows), "ly_do": None}


def _worker_telemetry(out_dir) -> dict:
    """Đọc thẳng `status.json` của worker — những số KHÔNG đi qua API live (`drift_*`, tuổi mask).

    Vì sao cần: `/api/live/status` mang 10 trường nhưng **không** có `drift_iou`/`drift_iou_p05`/
    `mask_age_p95`; ba số đó chỉ nằm trong `status.json` của worker. Artifact "camera thật chạy được"
    nên ghi cả hai nguồn, và ghi `None` trung thực khi worker chưa đo.
    """
    path = Path(out_dir) / "status.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    keys = ("state", "device", "frames", "vos_runs", "measured_fps", "vos_fps", "vos_ms", "lk_ms",
            "drift_iou", "drift_iou_p05", "drift_n", "mask_age_ms", "mask_age_total_ms",
            "mask_age_p95", "age_n", "stability", "stability_n", "stability_shown",
            "stability_shown_n", "empty_runs", "mask_holds", "mask_drops", "lost_streak")
    return {key: data.get(key) for key in keys if key in data}


def _tail_file(path, *, limit: int = 4000):
    """Đuôi của một file log (None nếu không có) — để artifact TỰ CHẨN ĐOÁN khi worker chết.

    Vì sao cần (12-11): artifact chỉ ghi `worker dừng khi khởi động (mã 1) — xem
    /dev/shm/…/worker.log`, mà runtime Colab bị xoá là log đó biến mất ⇒ người đọc artifact không
    bao giờ biết worker chết vì gì. Nay nguyên văn đuôi log nằm ngay trong JSON.
    """
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return text if len(text) <= limit else "…(cắt bớt)…\n" + text[-limit:]


def _worker_device(out_dir) -> str | None:
    """Thiết bị mà WORKER thực sự dùng, đọc từ `worker.log` (dòng `[worker] sẵn sàng ... device=…`).

    Vì sao không lấy từ tham số: tham số là *yêu cầu*, còn log là *sự thật đã chạy*. Nếu hai số
    lệch nhau thì artifact phải thấy được (ví dụ quên đặt biến môi trường ⇒ worker chạy CPU).
    """
    try:
        text = (Path(out_dir) / "worker.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    found = re.findall(r"device=(cpu|cuda)", text)
    return found[-1] if found else None


def _ly_do_thiet_bi(device_yeu_cau: str, device_worker_log: str | None) -> list:
    """Lý do artifact KHÔNG được trích vì thiết bị: None = chưa đo, khác = đo trên máy khác.

    AGENTS §6: `null` không phải "đã đo". Một "baseline CPU" thật ra là GPU (hoặc ngược lại) làm mọi
    con số FPS trong báo cáo bị gán sai thiết bị — đúng thứ nhánh này sinh ra để diệt.
    """
    if device_worker_log is None:
        return ["không đọc được thiết bị từ worker.log (worker chết trước khi in, hoặc log bản cũ)"]
    if device_worker_log != device_yeu_cau:
        return [f"thiết bị LỆCH: yêu cầu {device_yeu_cau!r} nhưng worker chạy {device_worker_log!r}"]
    return []


def _ket_qua(ok: bool, error, git_loi, device_reasons) -> bool:
    """Lần đo này có dùng được làm BẰNG CHỨNG không (một chỗ duy nhất, để test khoá được).

    `ok` = điều kiện đo đạt; `error` = lỗi giữa phiên; `git_loi` = không có provenance tái lập;
    `device_reasons` = thiết bị chưa đọc được hoặc LỆCH yêu cầu. Bất kỳ cái nào xấu ⇒ `False`.
    """
    return bool(ok and not error and not git_loi and not device_reasons)


def _ma_thoat(ket_qua: bool) -> int:
    """Mã thoát của script: 0 ⇔ `ket_qua` True (phải khớp artifact, không được lệch)."""
    return 0 if ket_qua else 1


def _verdict(summary: dict) -> tuple[bool, list]:
    """(đạt, danh sách lý do) — điều kiện đăng ký trước của "đường demo thật chạy được"."""
    reasons = []
    if summary.get("state_cuoi") != "running":
        reasons.append(f"state_cuoi = {summary.get('state_cuoi')!r} (cần 'running')")
    if (summary.get("frames_cuoi") or 0) <= 0:
        reasons.append("frames = 0 (không có frame nào tới browser)")
    if (summary.get("measured_fps_max") or 0.0) <= 0.0:
        reasons.append("measured_fps = 0")
    if (summary.get("mask_fps_max") or 0.0) <= 0.0:
        reasons.append("mask_fps = 0 (mask chưa được cập nhật ⇒ không phải mode track)")
    return (not reasons), reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True,
                        help="URL ảnh camera thật (vd http://<win>:8090/snapshot.jpg)")
    parser.add_argument("--bbox", default="", help="x,y,w,h — ô chọn đối tượng (bắt buộc mode track)")
    parser.add_argument("--image-size", type=int, default=192)
    parser.add_argument("--vos-every", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--out", default="")
    parser.add_argument("--frame-dir", default="")
    parser.add_argument("--out-dir", default="/dev/shm/doan-live-relay")
    parser.add_argument("--device", default=None, choices=["cpu", "cuda"],
                        help="thiết bị chạy model của phiên live (API chuyển xuống worker). "
                             "Đo trên GPU PHẢI có cờ này để artifact biết số FPS là của máy nào")
    args = parser.parse_args()

    bbox = [int(v) for v in args.bbox.replace(",", " ").split()] if args.bbox else []
    if len(bbox) != 4:
        parser.error("--bbox phải là x,y,w,h (đây là mode track)")

    stamp = datetime.now().astimezone()   # có offset: WSL chạy UTC, tên file theo giờ VN
    out = Path(args.out) if args.out else (
        # Có GIỜ: chạy lần hai trong ngày từng ghi đè artifact đang được trích trong báo cáo (P3).
        _REPO_ROOT / "data" / f"live_web_relay_{stamp:%Y-%m-%d_%H%M%S}_metrics.json")
    frame_dir = Path(args.frame_dir) if args.frame_dir else out.parent / f"live_web_relay_{stamp:%Y-%m-%d}"
    base = f"http://127.0.0.1:{args.port}"
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    # Xoá `status.json` của lần trước: nếu lần này API bận/không vào `running`, đọc lại file cũ sẽ
    # gán số của PHIÊN KHÁC cho lần đo này (review độc lập nhánh bằng chứng, P2).
    (Path(args.out_dir) / "status.json").unlink(missing_ok=True)
    # Cùng lý do với dãy mẫu drift: CSV còn lại của phiên trước sẽ bị chép ra `data/` như "số của
    # lần đo này" (ticket 15).
    (Path(args.out_dir) / "drift_samples.csv").unlink(missing_ok=True)
    env = dict(os.environ, DOAN_LIVE_DIR=args.out_dir)
    # Thiết bị: `--device` > `$CAMERA_AI_DEVICE` của shell > cpu. PHẢI ghim lại env cho tiến trình
    # con theo đúng giá trị artifact khai: shell đã `export CAMERA_AI_DEVICE=cuda` mà ta lại chạy
    # KHÔNG `--device` thì child sẽ chạy GPU trong khi artifact ghi "cpu" ⇒ "baseline CPU" giả
    # (P2 review 10-11).
    device_yeu_cau = args.device or device_from_env()
    env["CAMERA_AI_DEVICE"] = device_yeu_cau
    if args.device is None and not os.environ.get(ENV_VAR):
        env.pop("CAMERA_AI_DEVICE", None)      # không ai yêu cầu ⇒ đừng thêm biến vào môi trường con

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.main:app", "--host", "127.0.0.1",
         "--port", str(args.port), "--log-level", "warning"],
        cwd=str(_REPO_ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=(_REPO_ROOT / "data" / "live_relay_api.log").open("w"),
    )

    samples, frames_saved, frame_errors, error = [], [], [], None
    started_at = time.perf_counter()
    try:
        if not _wait_up(base):
            raise RuntimeError("API không khởi động được (xem data/live_relay_api.log)")
        print(f"[1/3] mở phiên live trên {args.source} (mode=track, bbox={bbox})…", flush=True)
        _post(base, "/api/live/start", {
            "source": args.source, "mode": "track",
            "bbox": dict(zip("xywh", bbox)),
            "image_size": args.image_size, "vos_every": args.vos_every,
        })
        _wait_running(base)          # ném lỗi nếu phiên không vào `running`
        load_s = round(time.perf_counter() - started_at, 1)
        print(f"[2/3] đang chạy (nạp {load_s}s) — lấy mẫu {args.seconds:.0f}s…", flush=True)

        frame_dir.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + args.seconds
        index = 0
        while time.time() < deadline:
            samples.append(_get(base, "/api/live/status"))
            if index < 3 and samples[-1].get("frames", 0) > 0:
                try:
                    path = frame_dir / f"frame{index + 1}.jpg"
                    path.write_bytes(_get_bytes(base, "/api/live/frame"))
                    try:      # `--out` tương đối ⇒ đường dẫn cũng tương đối
                        frames_saved.append(str(path.resolve().relative_to(_REPO_ROOT)))
                    except ValueError:
                        frames_saved.append(str(path))
                    index += 1
                except (urllib.error.URLError, OSError) as exc:
                    frame_errors.append(f"frame{index + 1}: {type(exc).__name__}")
            time.sleep(POLL_S)
        summary = summarize(samples)
        print("[3/3] dừng phiên…", flush=True)
        _post(base, "/api/live/stop", {})
    except Exception as exc:                          # noqa: BLE001 — ghi lỗi vào artifact
        error = f"{type(exc).__name__}: {exc}"
        summary = summarize(samples)
    finally:
        # Dừng phiên bằng API (idempotent): nhánh lỗi trước đây chỉ terminate uvicorn, worker chạy
        # `start_new_session` chỉ được reaped nhờ lifespan ⇒ SIGKILL sau `wait(10)` là mồ côi camera.
        try:
            _post(base, "/api/live/stop", {})
        except Exception:                             # noqa: BLE001 — API có thể đã chết
            pass
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    ok, reasons = _verdict(summary)
    device_log = _worker_device(args.out_dir)
    device_reasons = _ly_do_thiet_bi(device_yeu_cau, device_log)
    reasons = reasons + device_reasons
    git_rev, git_dirty, git_dirty_code, git_loi = _git_provenance()
    if git_rev and not _is_ancestor(git_rev):
        git_loi = (f"`git_rev = {git_rev[:7]}` KHÔNG phải tổ tiên của HEAD — nhánh đã rebase sau khi "
                   "đo ⇒ không tái lập được từ clone mới (đo lại)")
    # Dãy mẫu drift (ticket 15): chép ra `data/` + provenance, rồi phân tích ngay để báo cáo có số
    # "phát hiện sau bao nhiêu mẫu" / "% cửa sổ báo oan" thay vì chỉ mean/p05.
    drift = _luu_mau_drift(args.out_dir, _ten_clip(args.source), stamp, {
        "do_luc": stamp.isoformat(timespec="seconds"),
        "git_rev": git_rev,
        "git_dirty": git_dirty,
        "git_dirty_code": git_dirty_code,
        "git_loi": git_loi,
        "ghi_chu": "Mỗi dòng = 1 kết quả VOS của luồng worker (frame_idx, seq, vos_ms, empty, "
                   "drift_iou, bbox); `n_dong == vos_runs - 1` vì engine.start() không có nội suy "
                   "để so. Ô TRỐNG = chưa đo, KHÔNG phải 0 (AGENTS §6).",
        "lenh": "python scripts/measure_live_relay.py " + " ".join(sys.argv[1:]),
        "nguon": args.source,
        "thiet_lap": {"bbox_xywh": bbox, "image_size": args.image_size,
                      "vos_every": args.vos_every, "seconds": args.seconds},
        "device_yeu_cau": device_yeu_cau,
        "device_worker_log": device_log,
    })
    series = None
    if drift["csv"]:
        # Đặt bí danh: `summarize` là hàm tóm tắt mẫu `/api/live/status` của chính script này.
        from src.drift_samples import read_samples, summarize as summarize_series
        series = summarize_series(read_samples(_REPO_ROOT / drift["csv"]))
    artifact = {
        "do_luc": stamp.isoformat(timespec="seconds"),
        "git_rev": git_rev,
        "git_dirty": git_dirty,
        "git_dirty_code": git_dirty_code,
        "git_loi": git_loi,
        "ghi_chu_git_rev": "Tái lập được ⇔ `git_dirty_code == false`. `git_loi` khác null ⇒ KHÔNG có "
                           "provenance, đừng trích file này.",
        "lenh": "python scripts/measure_live_relay.py " + " ".join(sys.argv[1:]),
        "device_yeu_cau": device_yeu_cau,
        "device_worker_log": device_log,
        "ghi_chu_device": "`device_worker_log` là thiết bị THẬT (đọc từ worker.log); lệch với "
                          "`device_yeu_cau` ⇒ số FPS ở đây là của máy khác với ý định — đừng trích.",
        "moi_truong": ("WSL laptop CPU (Iris Xe), torch CPU, SAM 2.1 tiny" if device_yeu_cau == "cpu"
                       else f"device={device_yeu_cau} (xem device_worker_log để "
                            "biết worker thật sự dùng gì)")
                      + "; nguồn = " + args.source,
        "nguon": args.source,
        "thiet_lap": {"bbox_xywh": bbox, "image_size": args.image_size,
                      "vos_every": args.vos_every, "seconds": args.seconds},
        "dieu_kien_dang_ky_truoc": "state=running, frames>0, measured_fps>0, mask_fps>0 "
                                   "(đường camera thật chạy được — KHÔNG phải mục tiêu FPS)",
        # `ket_qua` = "lần đo này dùng được làm bằng chứng": điều kiện đo đạt **và** không có lỗi
        # giữa phiên **và** có provenance (review độc lập nhánh này, P2).
        "ket_qua": _ket_qua(ok, error, git_loi, device_reasons),
        "dat_dieu_kien_do_luong": ok,
        "ly_do_khong_dat": reasons,
        "tom_tat": summary,
        "worker_status": _worker_telemetry(args.out_dir),
        # Chuỗi mẫu drift: đường dẫn + số dòng + phân tích (KHÔNG có file ⇒ `csv=None`, `n_dong=0`
        # — đừng đọc thành "0 mẫu đã đo").
        "drift_samples_csv": drift["csv"],
        "drift_samples_meta": drift["meta"],
        "drift_samples_n_dong": drift["n_dong"],
        "drift_samples_ly_do": drift["ly_do"],
        "drift_series": series,
        "anh_frame": frames_saved,
        "anh_frame_loi": frame_errors,
        "mau_cuoi": samples[-3:],
        "n_mau": len(samples),
        "loi": error,
        # Log là BẰNG CHỨNG khi lỗi: worker chết ⇒ đuôi log của nó là thứ duy nhất nói vì sao.
        "worker_log": _tail_file(Path(args.out_dir) / "worker.log"),
        "api_log": _tail_file(_REPO_ROOT / "data" / "live_relay_api.log"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\nnguồn: {args.source}")
    print("| trường | giá trị |\n|---|---|")
    for key, value in summary.items():
        print(f"| {key} | {value} |")
    worker = artifact["worker_status"]
    if worker:
        print(f"\nstatus.json của worker: drift_n={worker.get('drift_n')} · "
              f"drift_iou={worker.get('drift_iou')} · p05={worker.get('drift_iou_p05')} · "
              f"mask_age_p95={worker.get('mask_age_p95')} · empty_runs={worker.get('empty_runs')}")
        print(f"  thiết bị: yêu cầu={artifact['device_yeu_cau']} · worker log={artifact['device_worker_log']}")
        print(f"  ổn định hiển thị: stability_shown={worker.get('stability_shown')} "
              f"(n={worker.get('stability_shown_n')}; null = CHƯA ĐO)")
    print(f"Ảnh: {frames_saved or '(không chụp được)'}")
    if series:
        print(f"\nDãy mẫu drift ({drift['csv']}, {drift['n_dong']} dòng): "
              f"mean={series['drift_iou_mean']} · p05={series['drift_iou_p05']} · "
              f"mask rỗng={series['empty_frac']}")
        print(f"  cửa sổ {series['bao_dong_070']['cua_so']} mẫu, p05 < 0,70: "
              f"{series['bao_dong_070']['n_bao']}/{series['bao_dong_070']['n_cua_so']} "
              f"(tỉ lệ báo {series['bao_dong_070']['ti_le_bao']})")
        print(f"  phát hiện: sau {series['phat_hien']['phat_hien_sau_mau']} mẫu kể từ mẫu xấu đầu "
              f"(null = chưa có mẫu xấu nào hoặc chưa đủ cửa sổ)")
    else:
        print(f"Dãy mẫu drift: KHÔNG có ({drift['ly_do']})")
    print(f"Ghi: {out}")
    if git_loi:
        print(f"[CANH BAO] không lấy được provenance git: {git_loi}")
    if error:
        print(f"[LOI] {error}")
    elif not artifact["ket_qua"]:
        # In cả lý do THIẾT BỊ: bản trước chỉ in khi `not ok` ⇒ ca "worker chạy khác thiết bị yêu cầu"
        # có `ket_qua=false` mà terminal im lặng và script thoát 0 (P2 review 10-11).
        print("[THAT BAI] " + "; ".join(reasons or ["xem `loi`/`git_loi` trong artifact"]))
    return _ma_thoat(artifact["ket_qua"])


if __name__ == "__main__":
    sys.exit(main())
