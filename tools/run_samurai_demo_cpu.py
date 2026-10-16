"""
Runner chạy SAMURAI trên CPU (máy không có CUDA / NVIDIA).
Mô phỏng scripts/demo.py của repo yanchris11/samurai nhưng:
  - device: cpu (demo.py gốc hardcode "cuda:0")
  - không dùng torch.autocast("cuda") (chỉ hợp lệ trên GPU)
  - cho phép --max_frames (trim video để chạy nhanh khi test)
  - đo thời gian từng frame → in FPS trung bình
  - lưu video output + jpg các frame kết quả để kiểm tra trực quan

Dùng cho bài toán: xác nhận repo SAMURAI chạy thành công trước khi refactor.
"""
import argparse
import os
import os.path as osp
import time

import cv2
import numpy as np
import torch

from sam2.build_sam import build_sam2_video_predictor


def determine_model_cfg(model_path):
    if "large" in model_path:
        return "configs/samurai/sam2.1_hiera_l.yaml"
    elif "base_plus" in model_path:
        return "configs/samurai/sam2.1_hiera_b+.yaml"
    elif "small" in model_path:
        return "configs/samurai/sam2.1_hiera_s.yaml"
    elif "tiny" in model_path:
        return "configs/samurai/sam2.1_hiera_t.yaml"
    else:
        raise ValueError("Unknown model size in path!")


def load_txt(gt_path):
    """File txt chứa 1 dòng duy nhất: bbox frame đầu dạng x,y,w,h
    (SAM 2 nhận input dạng x1,y1,x2,y2)."""
    with open(gt_path, "r") as f:
        line = f.readline().strip()
    x, y, w, h = map(int, line.split(","))
    return (x, y, x + w, y + h)


def extract_frames_if_needed(video_path, max_frames, out_dir):
    """Trích N frame đầu của video thành thư mục JPG (load_video_frames hỗ trợ sẵn,
    không cần decord). Trả về (dir_path, so_frame). max_frames<=0 → toàn bộ."""
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    n = 0
    while max_frames is None or max_frames <= 0 or n < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imwrite(osp.join(out_dir, f"{n:05d}.jpg"), frame)
        n += 1
    cap.release()
    if n == 0:
        raise RuntimeError(f"Không đọc được frame nào từ {video_path}")
    print(f"[frames] đã trích {n} frames của '{osp.basename(video_path)}' → {out_dir}")
    return out_dir, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video_path", required=True)
    ap.add_argument("--txt_path", required=True, help="txt bbox frame đầu: x,y,w,h")
    ap.add_argument("--model_path", default=None, help="mặc định: tiny (nhanh nhất cho CPU)")
    ap.add_argument("--video_output_path", default="samurai_cpu_demo.mp4")
    ap.add_argument("--save_frames_dir", default=None, help="thư mục lưu jpg frame kết quả")
    ap.add_argument("--max_frames", type=int, default=0, help="số frame tối đa (0 = tất cả)")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    model_path = args.model_path or "sam2/checkpoints/sam2.1_hiera_tiny.pt"
    # sửa path tương đối theo repo root nếu chạy từ nơi khác
    if not osp.isfile(model_path):
        alt = osp.join("sam2", model_path)
        if osp.isfile(alt):
            model_path = alt
    model_cfg = determine_model_cfg(model_path)
    print(f"[model] cfg={model_cfg} | ckpt={model_path} | device={args.device}")

    frames_dir, total_frames = extract_frames_if_needed(
        args.video_path, args.max_frames, "/mnt/d/DOAN-NAB/data/demo_input_frames"
    )
    bbox = load_txt(args.txt_path)
    print(f"[prompt] bbox (x1,y1,x2,y2) frame 0 = {bbox}")

    predictor = build_sam2_video_predictor(model_cfg, model_path, device=args.device)

    if args.save_frames_dir:
        os.makedirs(args.save_frames_dir, exist_ok=True)

    frame_times = []
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = None

    with torch.inference_mode():
        t0 = time.time()
        state = predictor.init_state(
            frames_dir, offload_video_to_cpu=True, offload_state_to_cpu=True
        )
        print(f"[init_state] {state['num_frames']} frames | {time.time()-t0:.1f}s")

        # click chuột hay box đều được — dùng box như demo chính thức của SAMURAI
        predictor.add_new_points_or_box(state, box=bbox, frame_idx=0, obj_id=0)
        print("[prompt] đã thêm bbox prompt ở frame 0, bắt đầu propagate...")

        for frame_idx, object_ids, masks in predictor.propagate_in_video(state):
            tf = time.time()
            frame_times.append(tf)

            mask = (masks[0][0] > 0.0).cpu().numpy()  # (1,H,W) → (H,W)
            non_zero = np.argwhere(mask)
            if len(non_zero) == 0:
                box_vis = (0, 0, 0, 0)
            else:
                y_min, x_min = non_zero.min(axis=0).tolist()
                y_max, x_max = non_zero.max(axis=0).tolist()
                box_vis = (x_min, y_min, x_max - x_min, y_max - y_min)

            img = cv2.imread(osp.join(frames_dir, f"{frame_idx:05d}.jpg"))

            mask_img = np.zeros_like(img)
            mask_img[mask] = (255, 0, 0)
            img = cv2.addWeighted(img, 1, mask_img, 0.25, 0)
            x, y, w, h = box_vis
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 0), 2)
            cv2.putText(img, f"f={frame_idx}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            if writer is None:
                height, width = img.shape[:2]
                writer = cv2.VideoWriter(args.video_output_path, fourcc, 30, (width, height))
            writer.write(img)
            if args.save_frames_dir and (frame_idx % 30 == 0 or frame_idx == state["num_frames"] - 1):
                cv2.imwrite(osp.join(args.save_frames_dir, f"frame_{frame_idx:04d}.jpg"), img)

    if writer is not None:
        writer.release()

    n_done = len(frame_times)
    if n_done > 1:
        per_frame = np.diff(frame_times)
        print("=" * 50)
        print(f"Frames xử lý: {n_done} | Tổng: {frame_times[-1]-frame_times[0]:.1f}s")
        print(f"FPS trung bình: {1/per_frame.mean():.2f} | ms/frame: {per_frame.mean()*1000:.0f} (CPU)")


_FRAME_CAP = {}

def get_frame(video_path, idx):
    """Đọc frame idx từ file (cache video mở)."""
    if video_path not in _FRAME_CAP:
        cap = cv2.VideoCapture(video_path)
        _FRAME_CAP[video_path] = cap
    cap = _FRAME_CAP[video_path]
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ret, frame = cap.read()
    return frame if ret else np.zeros((720, 1280, 3), np.uint8)


if __name__ == "__main__":
    main()