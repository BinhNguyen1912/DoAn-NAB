"""
Lệnh chạy pipeline live end-to-end (ticket 04): VideoSource → TrackerEngine → overlay.

Cách chạy (env conda `samurai`):
  # Webcam live (hiển thị cửa sổ — chạy trên máy có camera + màn hình):
  python tools/run_live.py --source 0 --display
  # Camera điện thoại/IP qua RTSP:
  python tools/run_live.py --source rtsp://IP:554/stream --display
  # Video file (headless — in số liệu console, không mở cửa sổ):
  python tools/run_live.py --source data/video.mp4 --bbox data/dog_bbox_frame0.txt

Phím trong cửa sổ: q hoặc ESC để thoát đúng cách.
Số FPS/latency in ra console là THỰC ĐO trên máy (ADR-0002 — trung thực).
Chọn đối tượng bằng chuột là ticket 05; hiện tại dùng bbox truyền vào / mặc định giữa frame.
"""
import argparse
import os
import sys

import cv2

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import sam2.sam2_video_predictor as _vp          # noqa: E402

from src.tracker_engine import DEFAULT_CKPT, TrackerEngine  # noqa: E402
from src.live_pipeline import run_tracking                   # noqa: E402
from src.video_source import open_video_source               # noqa: E402

# Tắt progress bar tqdm của SAM 2 cho output console gọn
_vp.tqdm = lambda it, *a, **k: it

QUIT_KEYS = (ord("q"), 27)  # q / ESC


def _load_bbox(args, first_frame):
    """bbox từ --bbox (x,y,w,h) hoặc --bbox-file (file txt); mặc định = ô trung tâm."""
    text = None
    if args.bbox:
        text = args.bbox
    elif args.bbox_file and os.path.isfile(args.bbox_file):
        with open(args.bbox_file) as f:
            text = f.readline().strip()
    if text:
        x, y, w, h = (int(v) for v in text.split(","))
        return (x, y, x + w, y + h)
    h, w = first_frame.shape[:2]
    return (w // 2 - 40, h // 2 - 40, w // 2 + 40, h // 2 + 40)


def _guess_bbox_file(args):
    """Quy ước đồ án: video `data/abc.mp4` đi kèm bbox `data/abc_bbox_frame0.txt` nếu có."""
    if args.bbox is None and args.bbox_file is None:
        name = os.path.splitext(os.path.basename(str(args.source)))[0]
        neighbor = os.path.join("data", f"{name}_bbox_frame0.txt")
        if os.path.isfile(neighbor):
            args.bbox_file = neighbor


def main():
    ap = argparse.ArgumentParser(description="Live pipeline: nguồn video → SAMURAI → overlay")
    ap.add_argument("--source", required=True, help="index webcam (số) / rtsp://URL / đường dẫn file")
    ap.add_argument("--bbox", default=None, help="'x,y,w,h' frame 0")
    ap.add_argument("--bbox-file", default=None, help="file txt chứa 'x,y,w,h' frame 0")
    ap.add_argument("--display", action="store_true", help="mở cửa sổ OpenCV (mặc định headless)")
    ap.add_argument("--max-frames", type=int, default=None, help="giới hạn số frame xử lý")
    ap.add_argument("--ckpt", default=None, help="checkpoint SAM 2 (mặc định tiny trong samurai/)")
    args = ap.parse_args()

    if args.source.isdigit():
        args.source = int(args.source)
    _guess_bbox_file(args)

    engine = TrackerEngine.build_default(checkpoint=args.ckpt or DEFAULT_CKPT)

    def on_frame(img, result):
        if args.display:
            cv2.imshow("Camera AI - Tracking (SAMURAI)", img)
            key = cv2.waitKey(1) & 0xFF
            if key in QUIT_KEYS:
                return False
        print(f"[f{result.frame_idx}] bbox={result.bbox} ms={result.elapsed_ms:.0f}")
        return True

    try:
        # Đọc trước 1 frame để suy ra bbox mặc định (nguồn mở 2 lần — chấp nhận được với webcam)
        peek = open_video_source(args.source).open()
        first = peek.read()
        peek.close()
        if first is None:
            print("[LOI] nguồn không đưa được frame")
            raise SystemExit(1)
        bbox = _load_bbox(args, first)

        print("[pipeline] bắt đầu tracking... (q/ESC để thoát khi --display)")
        summary = run_tracking(
            source=args.source,
            engine=engine,
            bbox=bbox,
            on_frame=on_frame,
            max_frames=args.max_frames,
        )
    except KeyboardInterrupt:
        print("\n[pipeline] dừng bằng Ctrl+C — thoát sạch")
        raise SystemExit(0)
    finally:
        cv2.destroyAllWindows()

    print("=" * 60)
    print(f"[kết quả] {summary.total_frames} frame | mean={summary.mean_ms:.0f} ms | "
          f"p95={summary.p95_ms:.0f} ms | FPS hiệu dụng ≈ {summary.effective_fps:.2f}")
    print("(máy CPU laptop không GPU NVIDIA — số liệu trung thực theo ADR-0002)")


if __name__ == "__main__":
    main()