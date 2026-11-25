#!/usr/bin/env python3
"""Dựng BỘ DỮ LIỆU MẪU cho E2E của UI gán nhãn — để `./run labeluie2e` không phụ thuộc `data/`.

Vì sao cần: `data/*` bị `.gitignore` (video demo nặng), nên bản e2e trỏ vào một phiên thật
(`data/demoip_1125-121456_metrics.csv` + `_web.mp4`) chỉ chạy được **trên máy đã quay phiên đó**.
Trên clone sạch/CI nó đỏ với "Option not found" — đúng bài học AGENTS §6 (`test_bench_gpu_binh2` từng
đỏ vì đọc `data/binh2.mp4` không được track). Ở đây tự sinh CSV + mp4 nhỏ (mặc định 300 frame / 30 s @10 fps).

Chạy (thường do `./run labeluie2e` gọi):
    python scripts/make_labelui_fixture.py --out-dir /tmp/labelui_data
In ra đường dẫn CSV để script e2e dùng làm `PHIEN`.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:          # chạy trực tiếp `python scripts/...` vẫn import được `src`
    sys.path.insert(0, str(REPO_ROOT))

TEN = "e2e_labelui"


def tao(out_dir: Path, so_frame: int = 300, fps: int = 10) -> Path:
    """Ghi `e2e_labelui_metrics.csv` + `e2e_labelui_web.mp4` vào `out_dir`; trả đường dẫn CSV.

    CSV cố tình có một bước **RẤT DÀI** (2 000 ms ở bước 150) để UI hiện được cảnh báo "lệch bước":
    tổng latency ≈ 31,9 s còn video 30,0 s ⇒ hệ số bù ≈ 0,94, và khoảng trống quanh bước đó ≈ 1,9 s
    (đứng giữa hai bước là lệch ~0,94 s > ngưỡng 0,5 s của cảnh báo).
    """
    import cv2
    import numpy as np

    from src.worker import transcode_for_web

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    video = out_dir / f"{TEN}_web.mp4"
    tam = out_dir / f"{TEN}_goc.mp4"
    w, h = 320, 240
    # OpenCV chỉ ghi được `mp4v` — codec này **Chrome KHÔNG phát được** (đúng bug e2e 08-11:
    # "codec mp4v không phát được"). Nên ghi mp4v rồi chuyển mã bằng chính hàm của repo, để file mẫu
    # có cùng định dạng H.264 với `data/*_web.mp4` thật.
    ghi = cv2.VideoWriter(str(tam), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not ghi.isOpened():
        raise SystemExit(f"không mở được VideoWriter cho {tam}")
    try:
        for i in range(so_frame):
            khung = np.full((h, w, 3), 40, dtype=np.uint8)
            # Vật LUÔN nằm trong khung: `i*5` chạy ra ngoài 320 px từ frame ~52 ⇒ bbox CSV vô nghĩa với
            # 80 % frame mẫu (review vòng 2, P3-5).
            x = 20 + (i % 52) * 5
            cv2.rectangle(khung, (x, 90), (x + 40, 150), (30, 200, 240), -1)   # "vật" màu vàng
            cv2.rectangle(khung, (x, 90), (x + 40, 150), (255, 255, 255), 1)   # viền = "ô của hệ"
            cv2.putText(khung, f"#{i}", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
            ghi.write(khung)
    finally:
        ghi.release()
    if not tam.is_file() or tam.stat().st_size < 1000:
        raise SystemExit(f"video mẫu không được ghi: {tam}")
    ra = transcode_for_web(tam, video)
    tam.unlink(missing_ok=True)
    if not ra or not video.is_file() or video.stat().st_size < 1000:
        raise SystemExit("chuyển mã H.264 thất bại (thiếu ffmpeg?) — Chrome sẽ KHÔNG phát được mp4v")

    csv_path = out_dir / f"{TEN}_metrics.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        wcsv = csv.writer(f)
        # Đúng các cột `src/metrics_logger.py` ghi ra (phần mà UI đọc) — thiếu cột là bug thật.
        wcsv.writerow(["frame_idx", "latency_ms", "center_x", "center_y", "bbox_w", "bbox_h",
                       "mask_area", "nghi_doi_tuong"])
        for i in range(so_frame):
            lat = 2000.0 if i == 150 else 100.0
            x = 20 + (i % 52) * 5
            wcsv.writerow([i, lat, x + 20, 120, 40, 60, 2400, "1" if i == 30 else ""])
    return csv_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dựng CSV + mp4 mẫu cho E2E UI gán nhãn.")
    ap.add_argument("--out-dir", required=True, help="thư mục data tạm (chứa e2e_labelui_metrics.csv + _web.mp4)")
    ap.add_argument("--so-frame", type=int, default=300)
    ap.add_argument("--fps", type=int, default=10)
    a = ap.parse_args(argv)
    p = tao(Path(a.out_dir), a.so_frame, a.fps)
    print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
