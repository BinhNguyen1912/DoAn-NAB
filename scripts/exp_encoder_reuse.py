"""
Thí nghiệm: bỏ encode lại MỖI frame (dùng lại đặc trưng cũ cho K-1 frame).

Chức năng: trả lời "nếu không encode lại ảnh mỗi frame thì nhanh bao nhiêu, chất lượng
    mất bao nhiêu?" — đo bằng ms/frame + IoU ô bao trên fixture tổng hợp (đáp án biết trước).
Vì sao cần: đo 08-11-2026 cho thấy `image_encoder` chiếm **70-77 %** chi phí một frame
    (90/127,7 ms @192; 164/212,7 ms @256) và nó chạy lại ở MỌI frame.
Cách làm: bọc `_get_image_feature` của predictor — frame không chia hết cho K sẽ dùng lại
    đặc trưng đã encode của frame gần nhất (K=1 = hành vi gốc).
Kết quả đo @192, fixture 20 frame (08-11-2026):

    K   ms/frame   FPS    IoU TB   IoU min
    1      111,8    8,9     0,966     0,926
    2       75,2   13,3     0,840     0,694
    3       67,0   14,9     0,756     0,528
    4       62,9   15,9     0,667     0,399
    6       75,1   13,3     0,562     0,221

→ Trần của thủ thuật này là **~16 FPS** và đã mất 31-33 % IoU ở K=4. Không đạt 25-30 FPS.

Chạy: .venv/bin/python -m scripts.exp_encoder_reuse 192 20
"""
import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.synthetic_video import generate_tracking_sequence  # noqa: E402
from src.tracker_engine import TrackerEngine  # noqa: E402


def iou(a, b) -> float:
    """IoU hai ô bao (x1, y1, x2, y2)."""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def run_one(image_size: int, num_frames: int, k: int):
    """Chạy 1 cấu hình K; trả (ms/frame, IoU TB, IoU thấp nhất)."""
    engine = TrackerEngine.build_default(device="cpu", image_size=image_size)
    predictor = engine._predictor
    original = predictor._get_image_feature

    if k > 1:
        def patched(inference_state, frame_idx, batch_size):
            source = frame_idx - (frame_idx % k)     # frame được encode thật
            if source != frame_idx and source in inference_state["cached_features"]:
                return original(inference_state, source, batch_size)
            return original(inference_state, frame_idx, batch_size)

        predictor._get_image_feature = patched

    fixture = generate_tracking_sequence(num_frames=num_frames)
    t0 = time.perf_counter()
    result = engine.start(fixture.frames[0], fixture.bboxes[0])
    elapsed = [(time.perf_counter() - t0) * 1000]
    ious = [iou(result.bbox, fixture.bboxes[0])]

    for i in range(1, num_frames):
        t0 = time.perf_counter()
        result = engine.process(fixture.frames[i])
        elapsed.append((time.perf_counter() - t0) * 1000)
        ious.append(iou(result.bbox, fixture.bboxes[i]))

    steady = elapsed[1:]        # bỏ frame đầu (init + encode lần đầu)
    return statistics.mean(steady), statistics.mean(ious), min(ious)


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo ảnh hưởng của việc dùng lại encoder")
    parser.add_argument("--image-size", type=int, default=192)
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--ks", type=int, nargs="+", default=[1, 2, 3, 4, 6])
    args = parser.parse_args()

    print(f"image_size {args.image_size} | fixture {args.frames} frame | "
          "encoder dùng lại mỗi K frame")
    print(f"{'K':>2} {'ms/frame':>9} {'FPS':>6} {'IoU TB':>7} {'IoU min':>8}")
    for k in args.ks:
        ms, mean_iou, min_iou = run_one(args.image_size, args.frames, k)
        print(f"{k:>2} {ms:>9.1f} {1000 / ms:>6.1f} {mean_iou:>7.3f} {min_iou:>8.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
