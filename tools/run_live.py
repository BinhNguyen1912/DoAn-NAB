"""
Lệnh chạy pipeline live end-to-end: VideoSource → TrackerEngine → PromptSelector → overlay.

Cách chạy (env conda `samurai`):
  # Webcam live + chọn đối tượng bằng chuột (chạy trên máy có camera + màn hình):
  python tools/run_live.py --source 0 --display
  # Camera điện thoại/IP qua RTSP:
  python tools/run_live.py --source rtsp://IP:554/stream --display
  # Video file (headless — in số liệu console, không mở cửa sổ):
  python tools/run_live.py --source data/video.mp4 --bbox data/dog_bbox_frame0.txt

Phím trong cửa sổ (--display):
  - kéo chuột vẽ ô quanh đối tượng → thả chuột → track khởi động từ ô đó
  - r          : dừng track, quay về chế độ chọn lại trên frame hiện tại
  - q hoặc ESC : thoát đúng cách
  (chỉ định --bbox thì track ngay, không cần kéo; vẫn bấm r để chọn lại bằng chuột)

--record FILE : ghi video mp4 bản đã overlay (HUD mask + ô bao + quỹ đạo + FPS).
Số FPS/latency in ra console là THỰC ĐO trên máy (ADR-0002 — trung thực).
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
from src.live_pipeline import run_interactive, run_tracking  # noqa: E402
from src.prompt_selector import PromptSelector               # noqa: E402
from src.video_source import open_video_source               # noqa: E402
from src.visualizer import Visualizer                        # noqa: E402

# Tắt progress bar tqdm của SAM 2 cho output console gọn
_vp.tqdm = lambda it, *a, **k: it

WINDOW_NAME = "Camera AI - SAMURAI (keo chuot chon doi tuong)"


def _make_visualizer(args, record_size=None, record_fps=30.0):
    """Tạo Visualizer (HUD luôn bật); nếu --record chỉ định thì bật ghi mp4.

    record_size=None → mở trì hoãn ở update() đầu tiên (display mode không biết trước
    kích thước frame — headless truyền thẳng từ peek).
    """
    viz = Visualizer(max_trajectory=args.max_trajectory)
    if args.record:
        if viz.open_recorder(args.record, fps=record_fps, frame_size=record_size):
            print(f"[pipeline] ghi video: {args.record} ({record_fps:.0f} fps)")
        else:
            print(f"[LOI] không ghi được video tới {args.record} — chạy không ghi")
    return viz


def _make_metrics(args):
    """Tạo MetricsLogger nếu --metrics-csv; tắt thì trả None (không log)."""
    if not args.metrics_csv:
        return None
    from src.metrics_logger import MetricsLogger
    print(f"[pipeline] ghi metrics: {args.metrics_csv} (+summary JSON nếu --metrics-summary)")
    return MetricsLogger()


def _finish_metrics(metrics, args, total):
    """Xuất CSV + (tuỳ chọn) summary JSON khi phiên xong."""
    if metrics is None:
        return
    metrics.write_csv(args.metrics_csv)
    if args.metrics_summary:
        metrics.write_summary_json(args.metrics_summary)
    s = metrics.summary()
    print(f"[metrics] {s['total_frames']} frame | mean={s['mean_latency_ms']:.0f} ms | "
          f"p95={s['p95_latency_ms']:.0f} ms | mất dấu {s['lost_count']}/{s['total_frames']} "
          f"({s['lost_ratio']:.0%}) | score tb={s['mean_score']:.2f}")


def _load_bbox(args, first_frame=None):
    """bbox từ --bbox (x,y,w,h) hoặc --bbox-file (file txt).

    Interactive (--display): trả None khi không chỉ định → người dùng kéo chuột chọn.
    Headless: mặc định = ô trung tâm của frame đầu.
    """
    text = None
    if args.bbox:
        text = args.bbox
    elif args.bbox_file and os.path.isfile(args.bbox_file):
        with open(args.bbox_file) as f:
            text = f.readline().strip()
    if text:
        x, y, w, h = (int(v) for v in text.split(","))
        return (x, y, x + w, y + h)
    if first_frame is None:
        return None
    h, w = first_frame.shape[:2]
    return (w // 2 - 40, h // 2 - 40, w // 2 + 40, h // 2 + 40)


def _guess_bbox_file(args):
    """Quy ước đồ án: video `data/abc.mp4` đi kèm bbox `data/abc_bbox_frame0.txt` nếu có."""
    if args.bbox is None and args.bbox_file is None:
        name = os.path.splitext(os.path.basename(str(args.source)))[0]
        neighbor = os.path.join("data", f"{name}_bbox_frame0.txt")
        if os.path.isfile(neighbor):
            args.bbox_file = neighbor


def _run_display(engine, args):
    """Chế độ --display: cửa sổ OpenCV, kéo chuột chọn đối tượng + phím r chọn lại (ticket 05)."""
    selector = PromptSelector(frame_shape=(480, 640, 3))  # shape thật được bind lại khi chạy
    armed_bbox = _load_bbox(args, first_frame=None)

    try:
        cv2.namedWindow(WINDOW_NAME)
        cv2.setMouseCallback(WINDOW_NAME, selector.on_mouse)

        if armed_bbox:
            print(f"[pipeline] bbox chỉ định sẵn {armed_bbox} — track ngay (r để chọn lại bằng chuột)")
        else:
            print("[pipeline] kéo chuột vẽ ô quanh đối tượng → thả chuột để bám; r chọn lại; q/ESC thoát")

        def on_display(img, mode):
            cv2.imshow(WINDOW_NAME, img)
            return cv2.waitKey(1) & 0xFF

        def on_result(result):
            print(f"[f{result.frame_idx}] bbox={result.bbox} ms={result.elapsed_ms:.0f}")

        viz = _make_visualizer(args)  # kích thước biết ở frame đầu → mở trì hoãn
        metrics = _make_metrics(args)
        summary = run_interactive(
            source=args.source,
            engine=engine,
            selector=selector,
            display=on_display,
            max_frames=args.max_frames,
            preselect_bbox=armed_bbox,
            on_result=on_result,
            visualizer=viz,
            metrics=metrics,
        )
        _finish_metrics(metrics, args, summary.processed)
    except KeyboardInterrupt:
        print("\n[pipeline] dừng bằng Ctrl+C — thoát sạch")
        raise SystemExit(0)
    finally:
        viz.close_recorder()
        cv2.destroyAllWindows()

    print("=" * 60)
    print(f"[kết quả] {summary.processed} frame đã track "
          f"(chọn lại bằng phím r không tính thêm phiên)")
    print("(số ms từng frame in trong vòng lặp; máy CPU không GPU — trung thực theo ADR-0002)")


def _run_headless(engine, args):
    """Chế độ mặc định (không --display): chạy hết nguồn, in số liệu console."""
    try:
        # Đọc trước 1 frame để suy ra bbox mặc định (nguồn mở 2 lần — chấp nhận được với webcam)
        peek = open_video_source(args.source).open()
        first = peek.read()
        peek_fps = peek.source_fps  # đọc trước khi close (sau đó thuộc tính chết)
        peek.close()
        if first is None:
            print("[LOI] nguồn không đưa được frame")
            raise SystemExit(1)
        bbox = _load_bbox(args, first)

        # FPS ghi video: lấy từ nguồn (camera/file báo sai thì --record-fps đè)
        record_fps = args.record_fps or (peek_fps if peek_fps > 0 else 30.0)
        viz = _make_visualizer(args, record_size=(first.shape[1], first.shape[0]),
                               record_fps=record_fps)
        print("[pipeline] bắt đầu tracking... (headless)")
        metrics = _make_metrics(args)
        summary = run_tracking(
            source=args.source,
            engine=engine,
            bbox=bbox,
            max_frames=args.max_frames,
            visualizer=viz,
            metrics=metrics,
        )
        viz.close_recorder()
        _finish_metrics(metrics, args, summary.total_frames)
    except KeyboardInterrupt:
        print("\n[pipeline] dừng bằng Ctrl+C — thoát sạch")
        raise SystemExit(0)

    print("=" * 60)
    print(f"[kết quả] {summary.total_frames} frame | mean={summary.mean_ms:.0f} ms | "
          f"p95={summary.p95_ms:.0f} ms | FPS hiệu dụng ≈ {summary.effective_fps:.2f}")
    print("(máy CPU laptop không GPU NVIDIA — số liệu trung thực theo ADR-0002)")


def main():
    ap = argparse.ArgumentParser(description="Live pipeline: nguồn video → SAMURAI → chọn đối tượng bằng chuột")
    ap.add_argument("--source", required=True, help="index webcam (số) / rtsp://URL / đường dẫn file")
    ap.add_argument("--bbox", default=None, help="'x,y,w,h' frame 0 (headless: mặc định giữa frame; display: track ngay)")
    ap.add_argument("--bbox-file", default=None, help="file txt chứa 'x,y,w,h' frame 0")
    ap.add_argument("--display", action="store_true",
                    help="mở cửa sổ OpenCV + kéo chuột chọn đối tượng (mặc định headless)")
    ap.add_argument("--max-frames", type=int, default=None, help="giới hạn số frame xử lý")
    ap.add_argument("--record", default=None, help="ghi video mp4 HUD ra file này (mặc định tắt)")
    ap.add_argument("--record-fps", type=float, default=None,
                    help="fps file ghi (headless: mặc định lấy nguồn; display: 30)")
    ap.add_argument("--max-trajectory", type=int, default=100,
                    help="số điểm quỹ đạo tối đa (deque giới hạn bộ nhớ)")
    ap.add_argument("--metrics-csv", default=None,
                    help="ghi metrics từng frame ra CSV (ticket 07)")
    ap.add_argument("--metrics-summary", default=None,
                    help="ghi summary JSON (mean/p95/tỷ lệ mất dấu) — cần --metrics-csv")
    ap.add_argument("--ckpt", default=None, help="checkpoint SAM 2 (mặc định tiny trong samurai/)")
    args = ap.parse_args()

    if args.source.isdigit():
        args.source = int(args.source)
    _guess_bbox_file(args)

    engine = TrackerEngine.build_default(checkpoint=args.ckpt or DEFAULT_CKPT)

    if args.display:
        _run_display(engine, args)
    else:
        _run_headless(engine, args)


if __name__ == "__main__":
    main()