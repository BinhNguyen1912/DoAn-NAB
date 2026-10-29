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
--config FILE : đọc cấu hình từ YAML (configs/default.yaml) — flag CLI đè file.
Số FPS/latency in ra console là THỰC ĐO trên máy (ADR-0002 — trung thực).
"""
import argparse
import os
import sys

import cv2

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Tắt progress bar tqdm của SAM 2 cho output console gọn.
# Import có bảo vệ: `sam2` cài từ upstream (không vendor trong Git) → máy/CI chưa cài
# sam2 vẫn import được module này (CLI test bằng engine giả chạy được trong CI).
try:
    import sam2.sam2_video_predictor as _vp          # noqa: E402

    _vp.tqdm = lambda it, *a, **k: it
except ImportError:  # sam2 chưa cài — chỉ ảnh hưởng việc ẩn progress bar khi chạy thật
    pass

from src.tracker_engine import TrackerEngine                 # noqa: E402
from src.live_pipeline import QUIT_KEYS, run_interactive, run_tracking  # noqa: E402
from src.smooth_display import run_smooth_display             # noqa: E402
from src.prompt_selector import PromptSelector               # noqa: E402
from src.config import REPO_ROOT, load_config, merge_cli_overrides, resolve_checkpoint  # noqa: E402
from src.video_source import open_video_source               # noqa: E402
from src.visualizer import Visualizer                        # noqa: E402

WINDOW_NAME = "Camera AI - SAMURAI (keo chuot chon doi tuong)"


def _make_reid_session(engine, args):
    """Dựng ReIdSession khi bật re-ID (ADR-0003); None nếu tắt. Thiều model → báo lỗi có hướng dẫn."""
    if not getattr(args, "reid", False):
        return None
    from src.reid import FaceEmbedder, ReIdSession

    def _abs(path):
        return path if os.path.isabs(path) else os.path.join(REPO_ROOT, path)

    detector, recognizer = _abs(args.reid_detector_model), _abs(args.reid_recognizer_model)
    cue = getattr(args, "reid_cue", "face")
    embedder = None
    if cue in ("face", "both"):
        missing = [p for p in (detector, recognizer) if not os.path.isfile(p)]
        if missing:
            if cue == "face":
                print(f"[LOI] thiếu model khuôn mặt: {missing[0]}\n"
                      f"  → tải theo docs/adr/0003 (đặt vào models/face/), rồi chạy lại")
                raise SystemExit(1)
            # cue=both mà thiếu model mặt → vẫn chạy được bằng cue vật thể
            print("[re-ID] thiếu model khuôn mặt → lùi về cue vật thể (object)")
            cue = "object"
        else:
            from src.reid import FaceEmbedder
            embedder = FaceEmbedder(detector, recognizer,
                                    min_face_px=args.reid_min_face_px,
                                    min_score=args.reid_min_detect_score)
    print(f"[re-ID] bật cue={cue}: ngưỡng cosine mặt={args.reid_threshold}, "
          f"ngưỡng vật thể={getattr(args, 'reid_obj_threshold', 0.6)}, "
          f"đóng băng sau {args.lost_after_frames} frame mất dấu")
    return ReIdSession(engine, embedder, threshold=args.reid_threshold,
                       lost_after_frames=args.lost_after_frames, ref_max=args.reid_ref_max,
                       min_face_px=args.reid_min_face_px, min_score=args.reid_min_detect_score,
                       cue=cue, obj_threshold=getattr(args, "reid_obj_threshold", 0.6),
                       obj_ncc_min=getattr(args, "reid_obj_ncc_min", 0.0),
                       lost_score_threshold=getattr(args, "lost_score_threshold", 0.0),
                       reacquire_confirm=getattr(args, "reid_confirm", 2),
                       verify_frames=getattr(args, "reid_verify", 2))


def _window_closed(window_name, seen_visible=None, max_misses=3):
    """True nếu người dùng đã đóng cửa sổ bằng nút X (OpenCV không tự thoát chương trình).

    Lưu ý WSLg/X11-từ-xa: cửa sổ được map TRỄ vài trăm ms sau `imshow` đầu tiên, và có thể
    báo "không thấy" một hai frame khi cửa sổ đang được vẽ lại/di chuyển → nếu tin ngay thì
    chương trình tự thoát trước khi người dùng kịp kéo chuột (lỗi thật 27-10-2026).
    Vì vậy: (a) chỉ coi là đóng khi cửa sổ TỪNG hiện ra, và (b) phải "không thấy" liên tiếp
    `max_misses` lần mới kết luận.

    seen_visible: dict trạng thái dùng chung ({"ok": bool, "miss": int}); bỏ trống thì giữ
    hành vi cũ (tin ngay lần đầu).
    """
    try:
        visible = cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE)
    except cv2.error:
        return True          # cửa sổ đã bị huỷ hẳn
    if visible >= 1:
        if seen_visible is not None:
            seen_visible["ok"] = True
            seen_visible["miss"] = 0
        return False
    if seen_visible is None:
        return True
    if not seen_visible.get("ok"):
        return False         # chưa từng thấy cửa sổ → đang map trễ, chưa phải đóng
    seen_visible["miss"] = int(seen_visible.get("miss", 0)) + 1
    return seen_visible["miss"] >= max_misses


def _device_note(device):
    """Câu ghi chú nêu đúng phần cứng đã chạy (CPU laptop hay GPU)."""
    if device == "cuda":
        try:
            import torch
            return f"GPU {torch.cuda.get_device_name(0)}"
        except Exception:
            return "GPU CUDA"
    return "máy CPU (không GPU NVIDIA)"


def _make_visualizer(args, record_size=None, record_fps=30.0):
    """Tạo Visualizer (HUD luôn bật); nếu --record chỉ định thì bật ghi mp4.

    record_size=None → mở trì hoãn ở update() đầu tiên (display mode không biết trước
    kích thước frame — headless truyền thẳng từ peek).
    """
    viz = Visualizer(max_trajectory=args.max_trajectory,
                     show_trajectory=getattr(args, "show_trajectory", True))
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


def _finish_metrics(metrics, args):
    """Xuất CSV + (tuỳ chọn) summary JSON — gọi trong finally để Ctrl+C không mất số liệu.

    Nếu phiên KHÔNG có frame nào (mở camera lỗi, Ctrl+C quá sớm) thì **không ghi**, để không
    ghi đè kết quả tốt của lần chạy trước bằng file rỗng (bug gặp 21-10).
    """
    if metrics is None:
        return
    if not metrics.records:
        print("[metrics] chưa có frame nào — không ghi file (giữ nguyên kết quả lần chạy trước)")
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
    viz = None
    metrics = None
    interrupted = False

    try:
        cv2.namedWindow(WINDOW_NAME)
        cv2.setMouseCallback(WINDOW_NAME, selector.on_mouse)

        if armed_bbox:
            print(f"[pipeline] bbox chỉ định sẵn {armed_bbox} — track ngay (r để chọn lại bằng chuột)")
        else:
            print("[pipeline] kéo chuột vẽ ô quanh đối tượng → thả chuột để bám; r chọn lại; q/ESC thoát")

        seen_visible = {"ok": False}

        def on_display(img, mode):
            cv2.imshow(WINDOW_NAME, img)
            key = cv2.waitKey(1) & 0xFF
            if _window_closed(WINDOW_NAME, seen_visible):
                print("[pipeline] cửa sổ đã đóng — thoát")
                return QUIT_KEYS[0]
            return key

        def on_result(result):
            print(f"[f{result.frame_idx}] bbox={result.bbox} ms={result.elapsed_ms:.0f}")

        viz = _make_visualizer(args)  # kích thước biết ở frame đầu → mở trì hoãn
        metrics = _make_metrics(args)
        reid_session = _make_reid_session(engine, args)
        if args.smooth:
            print("[pipeline] chế độ MƯỢT: video ~30 FPS, overlay cập nhật mỗi lần suy luận "
                  "(HUD hiện tuổi overlay)")
            summary = run_smooth_display(
                source=args.source,
                engine=engine,
                selector=selector,
                display=on_display,
                max_frames=args.max_frames,
                preselect_bbox=armed_bbox,
                on_result=on_result,
                visualizer=viz,
                metrics=metrics,
                reid_session=reid_session,
            )
        else:
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
                reanchor_every=args.reanchor_every,
                reid_session=reid_session,
            )
    except KeyboardInterrupt:
        interrupted = True
        print("\n[pipeline] dừng bằng Ctrl+C — thoát sạch")
    finally:
        # Ctrl+C cũng phải giữ lại số liệu đã đo + video đã ghi (demo hay dừng kiểu này)
        if viz is not None:
            viz.close_recorder()
        if metrics is not None:
            _finish_metrics(metrics, args)
        cv2.destroyAllWindows()

    if interrupted:
        raise SystemExit(0)

    print("=" * 60)
    print(f"[kết quả] {summary.processed} frame đã track "
          f"(chọn lại bằng phím r không tính thêm phiên)")
    print(f"(số ms từng frame in trong vòng lặp; {_device_note(args.device)} — ADR-0002)")


def _run_headless(engine, args):
    """Chế độ mặc định (không --display): chạy hết nguồn, in số liệu console."""
    viz = None
    metrics = None
    interrupted = False
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
        reid_session = _make_reid_session(engine, args)
        summary = run_tracking(
            source=args.source,
            engine=engine,
            bbox=bbox,
            max_frames=args.max_frames,
            visualizer=viz,
            metrics=metrics,
            reanchor_every=args.reanchor_every,
            reid_session=reid_session,
        )
    except KeyboardInterrupt:
        interrupted = True
        print("\n[pipeline] dừng bằng Ctrl+C — thoát sạch")
    finally:
        # Ctrl+C cũng phải giữ lại số liệu đã đo + video đã ghi
        if viz is not None:
            viz.close_recorder()
        if metrics is not None:
            _finish_metrics(metrics, args)

    if interrupted:
        raise SystemExit(0)

    print("=" * 60)
    print(f"[kết quả] {summary.total_frames} frame | mean={summary.mean_ms:.0f} ms | "
          f"p95={summary.p95_ms:.0f} ms | FPS hiệu dụng ≈ {summary.effective_fps:.2f}")
    print(f"({_device_note(args.device)} — số liệu thực đo theo ADR-0002)")


def main():
    ap = argparse.ArgumentParser(
        description="Live/headless pipeline: nguồn video → SAMURAI → HUD + metrics",
        epilog=("Cấu hình: --config configs/default.yaml (checkpoint, nguồn, ghi mp4, "
                "metrics) — flag CLI đè giá trị file YAML."),
    )
    ap.add_argument("--config", default=None, help="file YAML (VD configs/default.yaml)")
    ap.add_argument("--source", default=None,
                    help="index webcam (số) / rtsp://URL / đường dẫn file (mặc định lấy config)")
    ap.add_argument("--bbox", default=None, help="'x,y,w,h' frame 0 (headless: mặc định giữa frame; display: track ngay)")
    ap.add_argument("--bbox-file", default=None, help="file txt chứa 'x,y,w,h' frame 0")
    ap.add_argument("--display", action="store_true",
                    help="mở cửa sổ OpenCV + kéo chuột chọn đối tượng (mặc định headless)")
    ap.add_argument("--max-frames", type=int, default=None, help="giới hạn số frame xử lý")
    ap.add_argument("--record", default=None, help="ghi video mp4 HUD ra file này (đè config)")
    ap.add_argument("--record-fps", type=float, default=None,
                    help="fps file ghi (headless: mặc định lấy nguồn; display: 30)")
    ap.add_argument("--max-trajectory", type=int, default=None,
                    help="số điểm quỹ đạo tối đa (đè config)")
    ap.add_argument("--smooth", action="store_true",
                    help="hiển thị tách luồng: video ~30 FPS, overlay cập nhật mỗi lần suy luận "
                         "(HUD ghi tuổi overlay) — dùng cho demo mượt")
    ap.add_argument("--device", default=None, choices=["cpu", "cuda"],
                    help="thiết bị chạy model: cpu (mặc định) | cuda (Colab GPU/máy NVIDIA)")
    ap.add_argument("--mask-threshold", type=float, default=None,
                    help="ngưỡng logit của mask (0 = như model trả; 0.5–2.0 = cắt rìa mờ, "
                         "mask co lại — dùng khi mask 'ăn' cả tóc/viền)")
    ap.add_argument("--hide-trajectory", action="store_true",
                    help="KHÔNG vẽ đường quỹ đạo (màu tím) — chỉ giữ mặt nạ + ô bao + HUD")
    ap.add_argument("--postprocess", action="store_true",
                    help="bật bước fill_holes của SAM 2 (mặc định TẮT: hết cảnh báo lỗi GPU, "
                         "số đo CPU/GPU so sánh được)")
    ap.add_argument("--image-size", type=int, default=None,
                    help="độ phân giải đầu vào của model (512 = nhanh ~5-6x trên CPU; "
                         "mặc định giữ 1024 của config SAM 2)")
    ap.add_argument("--reanchor-every", type=int, default=None,
                    help="N>0: reset + chọn lại bbox mỗi N frame (nhanh hơn trên CPU, "
                         "đánh đổi memory dài hạn; mặc định tắt)")
    ap.add_argument("--reid", action="store_true",
                    help="bật tái nhận diện khuôn mặt: mất dấu thì ĐÓNG BĂNG, quay lại thì "
                         "tự bám lại đúng người (ADR-0003; cần model trong models/face/)")
    ap.add_argument("--reid-threshold", type=float, default=None,
                    help="ngưỡng cosine SFace để coi là cùng người (mặc định 0.363)")
    ap.add_argument("--lost-after-frames", type=int, default=None,
                    help="số frame mask rỗng liên tiếp trước khi đóng băng (mặc định 2)")
    ap.add_argument("--reid-min-face-px", type=int, default=None,
                    help="cạnh nhỏ nhất của ô mặt để dùng làm mẫu/ứng viên (mặc định 40)")
    ap.add_argument("--reid-ref-max", type=int, default=None,
                    help="số mẫu tham chiếu giữ lại (mặc định 8)")
    ap.add_argument("--reid-cue", default=None, choices=["face", "object", "both"],
                    help="cue tái nhận diện: face (mặt), object (đặc trưng vật thể — dùng được "
                         "cho remote TV), both (thử mặt trước, không khớp thì thử vật thể)")
    ap.add_argument("--reid-obj-threshold", type=float, default=None,
                    help="ngưỡng cosine đặc trưng vật thể để nhận lại (mặc định 0.6, phải hiệu chỉnh)")
    ap.add_argument("--reid-obj-ncc-min", type=float, default=None,
                    help="cổng NCC tối thiểu cho vật ít màu/texture (mặc định 0 = tắt; "
                         "đo: cùng vật 1,000 vs vật đen khác 0,897)")
    ap.add_argument("--lost-score-threshold", type=float, default=None,
                    help="score ≤ ngưỡng này coi như mất dấu (mặc định 0; chống SAM 2 "
                         "tưởng tượng mask khi vật đã rời khung)")
    ap.add_argument("--reid-confirm", type=int, default=None,
                    help="số frame liên tiếp phải khớp cùng một chỗ mới nhận lại (mặc định 2)")
    ap.add_argument("--reid-verify", type=int, default=None,
                    help="số frame kiểm chứng sau khi nhận lại (mặc định 2; fail → về LOST)")
    ap.add_argument("--metrics-csv", default=None,
                    help="ghi metrics từng frame ra CSV (đè config)")
    ap.add_argument("--metrics-summary", default=None,
                    help="ghi summary JSON (mean/p95/tỷ lệ mất dấu) — cần --metrics-csv")
    ap.add_argument("--ckpt", default=None, help="checkpoint SAM 2 (đè config)")
    args = ap.parse_args()

    # --- hợp nhất cấu hình: defaults < YAML (--config) < CLI (--flag chỉ định) ---
    cfg = load_config(args.config)
    cfg = merge_cli_overrides(cfg, {
        "checkpoint": args.ckpt,
        "source": args.source,
        "max_trajectory": args.max_trajectory,
        "reanchor_every": args.reanchor_every,
        "image_size": args.image_size,
        "device": args.device,
        "smooth_display": args.smooth or None,
        "show_trajectory": (False if args.hide_trajectory else None),
        "mask_threshold": args.mask_threshold,
        "max_frames": args.max_frames,
        "record_path": args.record,
        "record_fps": args.record_fps,
        "metrics_csv": args.metrics_csv,
        "metrics_summary": args.metrics_summary,
        "reid_enabled": (True if args.reid else None),
        "reid_threshold": args.reid_threshold,
        "lost_after_frames": args.lost_after_frames,
        "reid_min_face_px": args.reid_min_face_px,
        "reid_ref_max": args.reid_ref_max,
        "reid_cue": args.reid_cue,
        "reid_obj_threshold": args.reid_obj_threshold,
        "reid_obj_ncc_min": args.reid_obj_ncc_min,
        "lost_score_threshold": args.lost_score_threshold,
        "reid_reacquire_confirm": args.reid_confirm,
        "reid_verify_frames": args.reid_verify,
    })
    checkpoint = resolve_checkpoint(cfg["checkpoint"])
    if cfg["source"] is None:
        print("[LOI] chưa chỉ định nguồn — truyền --source hoặc đặt 'source:' trong file config")
        raise SystemExit(1)
    args.source = cfg["source"]
    if isinstance(args.source, str) and args.source.isdigit():
        args.source = int(args.source)
    args.max_trajectory = cfg["max_trajectory"]
    args.reanchor_every = cfg["reanchor_every"]
    args.image_size = cfg["image_size"]
    args.device = cfg["device"]
    args.smooth = bool(args.smooth or cfg["smooth_display"])
    args.show_trajectory = cfg["show_trajectory"] and not args.hide_trajectory
    args.mask_threshold = cfg["mask_threshold"]
    args.max_frames = cfg["max_frames"]
    args.record_fps = cfg["record_fps"]
    # bật ghi: --record chỉ định, hoặc record_enabled trong config
    args.record = args.record or (cfg["record_path"] if cfg["record_enabled"] else None)
    args.metrics_csv = args.metrics_csv or cfg["metrics_csv"]
    args.metrics_summary = args.metrics_summary or cfg["metrics_summary"]
    args.reid = bool(args.reid or cfg["reid_enabled"])
    args.reid_threshold = cfg["reid_threshold"]
    args.lost_after_frames = cfg["lost_after_frames"]
    args.reid_min_face_px = cfg["reid_min_face_px"]
    args.reid_min_detect_score = cfg["reid_min_detect_score"]
    args.reid_ref_max = cfg["reid_ref_max"]
    args.reid_cue = cfg["reid_cue"]
    args.reid_obj_threshold = cfg["reid_obj_threshold"]
    args.reid_obj_ncc_min = cfg["reid_obj_ncc_min"]
    args.lost_score_threshold = cfg["lost_score_threshold"]
    args.reid_confirm = cfg["reid_reacquire_confirm"]
    args.reid_verify = cfg["reid_verify_frames"]
    args.reid_detector_model = cfg["reid_detector_model"]
    args.reid_recognizer_model = cfg["reid_recognizer_model"]
    if args.reid and args.reanchor_every:
        print("[re-ID] tắt --reanchor-every: re-anchor chọn lại ô cũ sẽ phá trạng thái "
              "mất dấu/nhận lại (ADR-0003)")
        args.reanchor_every = None

    _guess_bbox_file(args)

    if args.image_size:
        print(f"[pipeline] model image_size={args.image_size} (nhanh hơn trên CPU, "
              f"đánh đổi chi tiết vật thể nhỏ)")
    device = args.device or "cpu"
    if device == "cuda":
        import torch
        if not torch.cuda.is_available():
            print("[LOI] --device cuda nhưng máy không có GPU CUDA (kiểm tra: Colab → Runtime → "
                  "Change runtime type → GPU)")
            raise SystemExit(1)
        print(f"[pipeline] device=cuda ({torch.cuda.get_device_name(0)})")
    engine = TrackerEngine.build_default(checkpoint=checkpoint, model_cfg=cfg["model_cfg"],
                                         image_size=args.image_size, device=device,
                                         apply_postprocessing=args.postprocess,
                                         mask_threshold=args.mask_threshold)

    if args.display:
        _run_display(engine, args)
    else:
        _run_headless(engine, args)


if __name__ == "__main__":
    main()