"""
Ghi video GỐC từ camera (không HUD, không model) để phân tích offline.

Chức năng: mở camera/video, ghi NGUYÊN frame gốc ra mp4 — dùng để (a) phân tích cảnh thật
    bằng code (đo tách vật này với vật khác), (b) so sánh khách quan với video HUD.
Input : --source (mặc định 0 = webcam), --seconds (mặc định 10), --out (mặc định
        data/raw_<MMDD-HHMMSS>.mp4), --fps (mặc định lấy từ nguồn, không có thì 30).
Output: file mp4 frame gốc; in số frame/giây đã ghi + đường dẫn.
Lưu ý : KHÔNG nạp model, KHÔNG vẽ gì → chạy được trên máy yếu, không tranh CPU với demo.
        Cùng lúc KHÔNG chạy song song với ./run fast/demo trên cùng một camera.
"""
import argparse
import datetime
import os
import sys
import time

import cv2

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.video_source import open_video_source  # noqa: E402  (cần sys.path ở trên)


def _stamp():
    return datetime.datetime.now().strftime("%m%d-%H%M%S")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ghi video GỐC (không HUD) để phân tích offline")
    ap.add_argument("--source", default="0", help="0 = webcam, hoặc đường dẫn file/URL")
    ap.add_argument("--seconds", type=float, default=10.0, help="ghi bao nhiêu giây (mặc định 10)")
    ap.add_argument("--out", default=None, help="file mp4 ra (mặc định data/raw_<moc-gio>.mp4)")
    ap.add_argument("--fps", type=float, default=None, help="fps ghi (mặc định theo nguồn/30)")
    ap.add_argument("--no-display", action="store_true",
                    help="không mở cửa sổ preview (mặc định MỞ để bạn thấy khung hình đang ghi)")
    args = ap.parse_args(argv)

    source = int(args.source) if str(args.source).isdigit() else args.source
    out = args.out or os.path.join(REPO_ROOT, "data", f"raw_{_stamp()}.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    # Dùng VideoSource của repo (không dùng cv2.VideoCapture trực tiếp): trên WSL, OpenCV 5
    # chọn backend sai → read() treo rồi trả False (lỗi thật 29-10: ghi được 0 frame).
    try:
        src = open_video_source(source)
        src.open()
    except Exception as exc:
        print(f"[LOI] không mở được nguồn {args.source}: {type(exc).__name__}: {exc}")
        return 1
    # API của VideoSource: frame_size (W,H) + source_fps (không phải .width/.fps)
    try:
        src_fps = float(src.source_fps)
    except Exception:
        src_fps = 0.0
    fps = float(args.fps or (src_fps if src_fps > 1 else 30.0))
    w, h = (int(v) for v in src.frame_size)
    writer = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not writer.isOpened():
        print(f"[LOI] không ghi được video tới {out}")
        return 1

    print(f"[raw] nguồn={args.source} {w}x{h} @ {fps:.0f} fps → {out}")
    print(f"[raw] ghi {args.seconds:.0f} giây — cử động vật như lúc demo; Ctrl-C để dừng sớm")
    t0 = time.monotonic()
    n = 0
    show = not args.no_display
    win = "Ghi frame goc (q de dung)"
    try:
        while time.monotonic() - t0 < args.seconds:
            frame = src.read()
            if frame is None:
                print("[LOI] nguồn hết frame / mất kết nối")
                break
            writer.write(frame)
            n += 1
            if show:
                # Chuỗi cv2.putText phải ASCII (font Hershey không có glyph dấu tiếng Việt)
                view = frame.copy()
                cv2.putText(view, f"REC {n} f | {time.monotonic() - t0:.1f}s",
                            (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                cv2.putText(view, "q: stop", (8, 48), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (0, 0, 255), 1)
                cv2.imshow(win, view)
                if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
                    print("[raw] dừng theo phím q")
                    break
    except KeyboardInterrupt:
        print("\n[raw] dừng theo yêu cầu")
    finally:
        writer.release()
        src.close()
        if show:
            try:
                cv2.destroyWindow(win)
            except cv2.error:
                pass

    dur = time.monotonic() - t0
    print(f"[raw] xong: {n} frame trong {dur:.1f}s (thực {n / max(dur, 1e-6):.1f} fps) → {out}")
    print("[raw] phân tích: mọi chỉ số của file này KHÔNG có HUD → dùng được để đo đạc bằng code")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
