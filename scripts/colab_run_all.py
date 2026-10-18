"""
Chạy TOÀN BỘ pipeline trên Colab GPU bằng 1 lệnh (dành cho người không muốn bấm từng cell).

Chức năng: tự làm lần lượt
  1. clone SAMURAI (nếu chưa có) + cài package `sam2` + `loguru` (nếu thiếu)
  2. tải checkpoint SAM 2.1 tiny (nếu thiếu/hỏng) + kiểm tra dung lượng > 100 MB
  3. chuẩn bị video: dùng `data/input.mp4` nếu có, không thì sinh video test 720p
  4. chạy `tools/run_live.py` với cấu hình nhanh nhất cho GPU (image_size 512 + reanchor)
  5. in số liệu GPU + đóng gói kết quả vào `data/colab_results.zip` để tải 1 lần

Input  : --device cuda|cpu (mặc định cuda), --image-size, --reanchor-every, --max-frames,
         --video, --bbox, --skip-setup (bỏ qua clone/pip/checkpoint — dùng khi test local).
Output : data/out_gpu.mp4, data/gpu_metrics.csv, data/gpu_summary.json, data/colab_results.zip
Lưu ý  : idempotent — chạy lại không tải lại checkpoint/nếu đã có; lỗi mạng được báo rõ.
"""
import argparse
import datetime
import glob
import json
import os
import subprocess
import sys
import urllib.request
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CKPT = os.path.join(REPO_ROOT, "samurai", "sam2", "checkpoints", "sam2.1_hiera_tiny.pt")
CKPT_URL = "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt"
CKPT_MIN_BYTES = 100_000_000
SAMURAI_REPO = "https://github.com/yangchris11/samurai.git"


def run(cmd, **kw):
    """Chạy lệnh shell, in ra để người dùng theo dõi."""
    print(f"[setup] $ {' '.join(cmd)}")
    return subprocess.run(cmd, text=True, **kw)


def checkpoint_ok(path=CKPT):
    """Checkpoint tồn tại và đủ lớn (file 0 byte từng làm hỏng cả phiên Colab)."""
    return os.path.isfile(path) and os.path.getsize(path) > CKPT_MIN_BYTES


def ensure_checkpoint(path=CKPT, url=CKPT_URL):
    if checkpoint_ok(path):
        print(f"[setup] checkpoint OK: {os.path.getsize(path) / 1e6:.1f} MB")
        return
    print("[setup] đang tải checkpoint (~156 MB)…")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    urllib.request.urlretrieve(url, path)
    size = os.path.getsize(path)
    if size < CKPT_MIN_BYTES:
        raise RuntimeError(f"tải checkpoint hỏng: {size} bytes — kiểm tra mạng rồi chạy lại")
    print(f"[setup] checkpoint OK: {size / 1e6:.1f} MB")


def ensure_samurai(install=True):
    """Clone SAMURAI (không vendor trong Git) + cài sam2/loguru nếu thiếu."""
    samurai_dir = os.path.join(REPO_ROOT, "samurai")
    if not os.path.isdir(os.path.join(samurai_dir, "sam2")):
        print("[setup] clone SAMURAI…")
        run(["git", "clone", "-q", "--depth", "1", SAMURAI_REPO, samurai_dir], check=True)
    if not install:
        return
    try:
        import sam2  # noqa: F401
        print("[setup] package sam2 đã cài")
    except ImportError:
        print("[setup] cài sam2 + loguru…")
        run([sys.executable, "-m", "pip", "install", "-q", "loguru"], check=True)
        run([sys.executable, "-m", "pip", "install", "-q", "-e",
             os.path.join(samurai_dir, "sam2")], check=True)


def ensure_video(path, synthetic=True, frames=60):
    """Dùng video có sẵn; nếu không có thì sinh video test 720p (ô vuông di chuyển)."""
    if os.path.isfile(path):
        print(f"[setup] dùng video: {path}")
        return path
    if not synthetic:
        raise FileNotFoundError(f"không thấy video '{path}' — hãy upload lên hoặc bỏ --no-synthetic")
    from src.synthetic_video import generate_tracking_sequence
    import cv2
    print(f"[setup] sinh video test 1280x720 ({frames} frame)…")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fx = generate_tracking_sequence(num_frames=frames, frame_size=(720, 1280),
                                    square_size=120, start=(200, 200), velocity=(14, 6))
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 25, (1280, 720))
    for f in fx.frames:
        out.write(f)
    out.release()
    print(f"[setup] video test: bbox frame 0 = {fx.bboxes[0]}")
    return path


def write_run_info(tag, args, out_dir="data"):
    """Ghi lại commit + tham số đã dùng để sinh số liệu → biết số liệu có CŨ so với code không.

    Nhờ file này, khi mở lại báo cáo sau vài tuần bạn so `git_rev` với `git log -1` hiện tại:
    giống nhau = số liệu còn đúng; khác = đã sửa code, cần chạy lại Colab.
    """
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        rev = "unknown"
    info = {
        "tag": tag,
        "git_rev": rev,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "device": args.device,
        "image_size": args.image_size,
        "reanchor_every": args.reanchor_every,
        "bbox": args.bbox,
        "video": os.path.basename(str(args.video)),
        "max_frames": args.max_frames,
    }
    path = os.path.join(out_dir, f"{tag}_run_info.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(f"[done] ghi thông tin lần chạy → {path} (git_rev={rev})")
    return path


def zip_results(out_dir, zip_path, tag="gpu"):
    files = sorted(glob.glob(os.path.join(out_dir, f"out_{tag}*.mp4"))
                   + glob.glob(os.path.join(out_dir, f"{tag}_*.csv"))
                   + glob.glob(os.path.join(out_dir, f"{tag}_*.json")))   # gồm cả {tag}_run_info.json
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in files:
            zf.write(f, arcname=os.path.basename(f))
    print(f"[done] đóng gói {len(files)} file → {zip_path}")
    return zip_path


def main():
    ap = argparse.ArgumentParser(description="Chạy toàn bộ pipeline trên Colab GPU bằng 1 lệnh")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--image-size", type=int, default=512,
                    help="độ phân giải vào của model (512 = nhanh nhất cho demo)")
    ap.add_argument("--reanchor-every", type=int, default=10,
                    help="reset memory mỗi N frame (giữ độ trễ không tăng dần)")
    ap.add_argument("--max-frames", type=int, default=None)
    ap.add_argument("--video", default=os.path.join(REPO_ROOT, "data", "input.mp4"))
    ap.add_argument("--bbox", default="200,200,120,120",
                    help="ô chọn đối tượng ở frame 0 (x,y,w,h)")
    ap.add_argument("--no-synthetic", action="store_true", help="không sinh video test")
    ap.add_argument("--skip-setup", action="store_true",
                    help="bỏ clone/pip/checkpoint (dùng khi chạy local đã cài đủ)")
    ap.add_argument("--tag", default=None,
                    help="tiền tố tên file kết quả (mặc định: 'gpu' khi --device cuda, "
                         "'cpu' khi cpu — để chạy local không ghi đè số liệu GPU thật)")
    args = ap.parse_args()

    os.chdir(REPO_ROOT)
    if not args.skip_setup:
        ensure_samurai(install=True)
        ensure_checkpoint()
    video = ensure_video(args.video, synthetic=not args.no_synthetic)

    tag = args.tag or ("gpu" if args.device == "cuda" else "cpu")
    summary_path = f"data/{tag}_summary.json"
    cmd = [sys.executable, "tools/run_live.py",
           "--source", video,
           "--device", args.device,
           "--image-size", str(args.image_size),
           "--record", f"data/out_{tag}.mp4",
           "--metrics-csv", f"data/{tag}_metrics.csv",
           "--metrics-summary", summary_path]
    if args.reanchor_every:
        cmd += ["--reanchor-every", str(args.reanchor_every)]
    if args.max_frames:
        cmd += ["--max-frames", str(args.max_frames)]
    if args.bbox:
        cmd += ["--bbox", args.bbox]
    print("[run]", " ".join(cmd), flush=True)
    rc = run(cmd).returncode
    if rc != 0:
        raise SystemExit(f"pipeline lỗi (mã {rc}) — xem log phía trên")

    if os.path.isfile(summary_path):
        s = json.load(open(summary_path, encoding="utf-8"))
        print(f"\n=== SỐ LIỆU THẬT ({args.device}) ===")
        for k, v in s.items():
            print(f"  {k:20} {round(v, 3) if isinstance(v, float) else v}")

    write_run_info(tag, args)
    zip_results("data", f"data/colab_{tag}_results.zip", tag=tag)
    print(f"\nTải về máy: mở panel Files → chuột phải data/colab_{tag}_results.zip → Download")
    print(f"(hoặc: from google.colab import files; files.download('data/colab_{tag}_results.zip'))")


if __name__ == "__main__":
    main()
