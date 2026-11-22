"""Sinh clip test chiếc remote trắng và bộ GT mask chuẩn (Ticket 04)."""

import json
from pathlib import Path
import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
GT_DIR = REPO_ROOT / "docs" / "gt" / "remote_trang"


def generate_remote_dataset():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GT_DIR.mkdir(parents=True, exist_ok=True)

    num_frames = 30
    h, w = 240, 320
    video_path = DATA_DIR / "remote_trang.mp4"

    # Định nghĩa chuyển động của remote (w_obj=32, h_obj=80)
    w_obj, h_obj = 32, 80

    frames = []
    gt_masks = []
    frame_manifests = []

    out = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (w, h))

    for i in range(num_frames):
        # Nền sáng / tường be (235, 238, 240) BGR
        frame = np.full((h, w, 3), (235, 238, 240), dtype=np.uint8)

        # Mô phỏng gờ tường / mép cửa ở x=250: (215, 220, 225)
        cv2.line(frame, (250, 0), (250, h), (215, 220, 225), 2)
        # Mô phỏng công tắc / mảng tường sáng ở (260, 50, 290, 80)
        cv2.rectangle(frame, (260, 50), (290, 80), (245, 248, 250), -1)

        mask = np.zeros((h, w), dtype=np.uint8)

        if 0 <= i <= 9:
            # Di chuyển mượt từ x=50 đến x=95
            rx = int(50 + i * 5)
            ry = 80
            has_obj = True
            occl = 0.0
        elif 10 <= i <= 15:
            # Che khuất một phần (50%)
            rx = int(95 + (i - 9) * 4)
            ry = 80
            has_obj = True
            occl = 0.5
        elif 16 <= i <= 20:
            # Mất dấu hoàn toàn / rời khung
            has_obj = False
            rx, ry = 0, 0
            occl = 1.0
        else: # 21 <= i <= 29
            # Tái xuất hiện ở x=160 đến x=200
            rx = int(160 + (i - 21) * 5)
            ry = 80
            has_obj = True
            occl = 0.0

        if has_obj:
            # Vẽ remote: hình chữ nhật trắng (255, 255, 255)
            cv2.rectangle(frame, (rx, ry), (rx + w_obj, ry + h_obj), (255, 255, 255), -1)
            # Nút bấm nhỏ trên remote
            cv2.circle(frame, (rx + 16, ry + 20), 4, (225, 228, 230), -1)
            cv2.circle(frame, (rx + 16, ry + 40), 4, (225, 228, 230), -1)

            # Mask GT chuẩn của remote
            mask[ry:ry + h_obj, rx:rx + w_obj] = 255

            if occl > 0:
                # Vật che màu xám (100, 100, 100)
                che_w = int(w_obj * occl)
                cv2.rectangle(frame, (rx, ry), (rx + che_w, ry + h_obj), (100, 100, 100), -1)
                # Phần bị che không còn thuộc mask nhìn thấy
                mask[ry:ry + h_obj, rx:rx + che_w] = 0

            bbox_xywh = [rx, ry, w_obj, h_obj]
        else:
            bbox_xywh = [0, 0, 0, 0]

        out.write(frame)
        frames.append(frame)
        gt_masks.append(mask)

        # Lưu ảnh mask GT
        gt_path = GT_DIR / f"gt_{i:06d}.png"
        cv2.imwrite(str(gt_path), mask)

        frame_manifests.append({
            "frame_idx": i,
            "bbox_xywh": bbox_xywh,
        })

    out.release()

    index_data = {
        "clip": "data/remote_trang.mp4",
        "ten": "remote_trang",
        "nguoi_gan": "SyntheticDatasetGenerator",
        "dang_gt": "silhouette",
        "phuong_phap_gt": "synthetic_exact",
        "frames": frame_manifests,
    }
    (GT_DIR / "index.json").write_text(json.dumps(index_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[dataset] Đã tạo video {video_path} và GT tại {GT_DIR} ({num_frames} frames)")


if __name__ == "__main__":
    generate_remote_dataset()
