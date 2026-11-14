"""
Lệnh chạy worker BÁM TRỰC TIẾP (chạy trong tiến trình riêng, có torch/SAM 2).

Chức năng: nạp engine SAMURAI rồi chạy `LiveTrackingSession` — đọc nguồn frame, bám đối tượng
           (chờ ô chọn do API ghi vào `bbox.json`), ghi `frame.jpg` + `status.json` ra `--out-dir`.
Input  : --source (0 | rtsp://… | http://… | đường dẫn video), --out-dir, --image-size, --max-fps.
Output : file trong --out-dir (frame.jpg, status.json, worker.log) + log console.
Lưu ý  : tool này CHẠY BẰNG python có torch (conda env samurai). API KHÔNG import nó.
         Ghi status "loading" NGAY khi khởi động để API biết worker còn sống trong lúc nạp model
         (20–60 s trên CPU) thay vì tưởng worker treo.
         Ctrl+C / SIGTERM → dừng sạch, ghi status "stopped".
"""

import argparse
import signal
import sys
import threading
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.live_tracking import (  # noqa: E402
    STATE_ERROR,
    STATE_LOADING,
    LiveTrackConfig,
    LiveTrackStats,
    LiveTrackingSession,
    session_exit_code,
    status_payload,
    write_json_atomic,
)


def _write_loading(out_dir: Path, message: str = "Đang nạp model...", *,
                   device: str = "") -> None:
    """Ghi trạng thái "loading" bằng CHÍNH payload của phiên chạy (một nguồn schema).

    `device` là thiết bị ĐỊNH chạy: người xem phải biết phiên này sẽ chạy CPU hay GPU ngay từ
    lúc nạp (nạp 20–240 s), không phải đọc `worker.log` (ticket 21).
    Mặc định `""` = **chưa biết** — cố tình KHÔNG mặc định `cpu`: ai gọi mà quên truyền thì file
    phải nói "chưa biết", không được khẳng định "cpu" (AGENTS §6; P3 review 12-11).
    """
    write_json_atomic(out_dir / "status.json",
                      status_payload(LiveTrackStats(state=STATE_LOADING, message=message,
                                                    device=device)))


def _cuda_available() -> bool:
    """Máy (tiến trình này) có CUDA không — `False` cả khi thiếu torch."""
    try:
        import torch
    except Exception:                # noqa: BLE001 — thiếu torch HOẶC torch hỏng (vd OSError libcudart)
        # Bắt rộng vì worker luôn có torch; nếu torch hỏng kiểu `OSError: libcudart.so.12` thì một
        # `except ImportError` sẽ để traceback làm status.json kẹt ở `loading` (P3 review 10-11).
        return False
    return bool(torch.cuda.is_available())


def _device_note(device: str) -> str:
    """Hậu tố log tên GPU thật (rỗng nếu CPU) — để log/artifact không phải đoán thiết bị."""
    if device != "cuda":
        return ""
    try:
        import torch
        return f" — {torch.cuda.get_device_name(0)}"
    except Exception:                # noqa: BLE001 — chỉ là dòng log
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Worker bám đối tượng trực tiếp (ghi frame.jpg + status.json cho API web)"
    )
    parser.add_argument("--source", required=True,
                        help="0 = webcam | rtsp://… | http://…/snapshot.jpg | đường dẫn video")
    parser.add_argument("--out-dir", required=True, help="thư mục chia sẻ với API (nên ở /dev/shm)")
    parser.add_argument("--image-size", type=int, default=None,
                        help="độ phân giải model (192 ≈ 10 FPS, 256 ≈ 6,5 FPS trên CPU)")
    parser.add_argument("--max-fps", type=float, default=30.0,
                        help="nhịp PHÁT frame (display). VOS có thể chậm hơn — LK lấp phần giữa")
    parser.add_argument("--vos-every", type=int, default=3,
                        help="chạy VOS mỗi N frame (1 = VOS mỗi frame, tắt LK; mask mới ở nhịp 1/N)")
    parser.add_argument("--mask-smoothing", type=float, default=1.0,
                        help="trọng số mask MỚI khi trộn theo thời gian (0-1]; 1.0 = tắt (mặc định, "
                             "đo 08-11: bật không cải thiện độ êm mà thêm trễ — data/live_2026-11-08_vos3_smoothing05_metrics.json")
    parser.add_argument("--trajectory-len", type=int, default=100)
    # KHÔNG dùng `choices`: `validate_device` chuẩn hoá hoa/thường + khoảng trắng và cho CÙNG một
    # câu lỗi với API/CLI khác (`--device CUDA` từng bị argparse từ chối bằng usage thô — P3 review 10-11).
    parser.add_argument("--device", default=None,
                        help="thiết bị chạy model: cpu (mặc định) | cuda (NVIDIA/Colab)")
    parser.add_argument("--stop-after-frames", type=int, default=None,
                        help="tự thoát sau N frame đã bám (dùng cho test/thử nhanh)")
    # Xuất mask tại vài frame để chấm mIoU vs GT gán tay (việc #6). Mặc định KHÔNG ghi gì.
    parser.add_argument("--dump-mask-frames", default="",
                        help='xuất mask tại các frame này, vd "0,50,120" (để chấm mIoU với GT)')
    parser.add_argument("--dump-mask-dir", default="",
                        help="thư mục ghi mask (mặc định <out-dir>/masks)")
    args = parser.parse_args()

    # Validate ở cửa vào: trước đây CLI clamp im lặng 0.0 → 0.05 còn schema API lại cho 0.0
    # (lỗi hợp đồng P2, review 08-11).
    if not 0.0 < args.mask_smoothing <= 1.0:
        parser.error("--mask-smoothing phải trong khoảng (0, 1]; 1.0 = tắt làm mượt")
    if args.vos_every < 1:
        parser.error("--vos-every phải >= 1")
    if args.max_fps <= 0:
        parser.error("--max-fps phải > 0")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    from src.device import normalize_device, validate_device  # không import torch ở module

    # Ghi "loading" TRƯỚC khi `_cuda_available()` (nó import torch, vài giây) để UI không coi worker
    # là treo — nhưng phải kèm thiết bị ĐỊNH chạy. `normalize_device` là hàm thuần nên không làm
    # chậm đường này; tên rác thì để nguyên văn (dưới đây báo `error` với message nêu tên đó).
    try:
        device_hint = normalize_device(args.device)
    except ValueError:
        device_hint = str(args.device)
    _write_loading(out_dir, device=device_hint)

    try:
        cuda_ok = _cuda_available()
        device = validate_device(args.device, cuda_available=cuda_ok)
    except ValueError as exc:
        # Lỗi ở CỬA VÀO: ghi status error để UI/watchdog thấy lý do, không nạp checkpoint 156 MB
        write_json_atomic(out_dir / "status.json", status_payload(
            LiveTrackStats(state=STATE_ERROR, device=device_hint, message=str(exc))))
        print(f"[LOI] {exc}", flush=True)
        return 2

    from src.tracker_engine import TrackerEngine  # import muộn: cần torch, chỉ trong worker

    print(f"[worker] nạp model (image_size={args.image_size or 'mặc định 1024'}, "
          f"device={device}{_device_note(device)})...", flush=True)
    engine = TrackerEngine.build_default(image_size=args.image_size, device=device)
    print(f"[worker] sẵn sàng | nguồn: {args.source} | out: {out_dir} | device={device}", flush=True)

    stop = threading.Event()

    def _handle(_signum, _frame):
        print("[worker] nhận tín hiệu dừng — thoát sạch", flush=True)
        stop.set()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    config = LiveTrackConfig(
        source=args.source,
        out_dir=out_dir,
        device=device,
        display_fps=args.max_fps,
        vos_every=args.vos_every,
        mask_smoothing=args.mask_smoothing,
        trajectory_len=args.trajectory_len,
        stop_after_frames=args.stop_after_frames,
        dump_mask_frames=args.dump_mask_frames,
        dump_mask_dir=args.dump_mask_dir,
    )
    stats = LiveTrackingSession(engine, config).run(stop)
    print(f"[worker] kết thúc: {stats.frames} frame phát, {stats.vos_runs} lần VOS | "
          f"display {stats.measured_fps} FPS | VOS {stats.vos_fps} FPS", flush=True)
    # Mã thoát là tín hiệu DUY NHẤT còn lại cho phụ huynh (systemd, subprocess runner, test): trả 0
    # cho một phiên kết thúc vì lỗi là nói dối, và `worker_source.health()` phân biệt "người dùng bấm
    # Dừng" với "chết vì lỗi" CHÍNH BẰNG mã thoát (14-11).
    if stats.state == STATE_ERROR:
        print(f"[LOI] phiên kết thúc vì lỗi: {stats.message}", flush=True)
    return session_exit_code(stats)


if __name__ == "__main__":
    sys.exit(main())
