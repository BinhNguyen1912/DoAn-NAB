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
    STATE_LOADING,
    LiveTrackConfig,
    LiveTrackingSession,
    write_json_atomic,
)


def _write_loading(out_dir: Path, message: str = "Đang nạp model...") -> None:
    write_json_atomic(out_dir / "status.json", {
        "state": STATE_LOADING, "frames": 0, "measured_fps": 0.0, "inference_ms": 0.0,
        "lost_streak": 0, "bbox": [], "message": message,
    })


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Worker bám đối tượng trực tiếp (ghi frame.jpg + status.json cho API web)"
    )
    parser.add_argument("--source", required=True,
                        help="0 = webcam | rtsp://… | http://…/snapshot.jpg | đường dẫn video")
    parser.add_argument("--out-dir", required=True, help="thư mục chia sẻ với API (nên ở /dev/shm)")
    parser.add_argument("--image-size", type=int, default=None,
                        help="độ phân giải model (192 ≈ 10 FPS, 256 ≈ 6,5 FPS trên CPU)")
    parser.add_argument("--max-fps", type=float, default=15.0,
                        help="nhịp ĐỌC frame tối đa (model có thể chậm hơn — số FPS thật ghi ở status)")
    parser.add_argument("--trajectory-len", type=int, default=100)
    parser.add_argument("--stop-after-frames", type=int, default=None,
                        help="tự thoát sau N frame đã bám (dùng cho test/thử nhanh)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_loading(out_dir)

    from src.tracker_engine import TrackerEngine  # import muộn: cần torch, chỉ trong worker

    print(f"[worker] nạp model (image_size={args.image_size or 'mặc định 1024'})...", flush=True)
    engine = TrackerEngine.build_default(image_size=args.image_size)
    print(f"[worker] sẵn sàng | nguồn: {args.source} | out: {out_dir}", flush=True)

    stop = threading.Event()

    def _handle(_signum, _frame):
        print("[worker] nhận tín hiệu dừng — thoát sạch", flush=True)
        stop.set()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    config = LiveTrackConfig(
        source=args.source,
        out_dir=out_dir,
        max_fps=args.max_fps,
        trajectory_len=args.trajectory_len,
        stop_after_frames=args.stop_after_frames,
    )
    stats = LiveTrackingSession(engine, config).run(stop)
    print(f"[worker] kết thúc: {stats.frames} frame, FPS đo {stats.measured_fps}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
