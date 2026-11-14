"""
Đo chi phí từng tầng trong MỘT bước propagate của SAM 2 (encoder vs memory vs decoder).

Chức năng: bọc `forward` của các module con rồi chạy N frame để biết **thời gian đi đâu mất**.
    Không có bảng này thì mọi phương án "tăng tốc" đều là đoán.
Vì sao cần: đo 08-11-2026 cho thấy `image_encoder` chiếm 70-77 % chi phí mỗi frame — mọi
    đòn tối ưu khác (HUD, re-ID, vẽ mask) chỉ chạm được 3-10 %.
Kết quả đo trên `data/binh1.mp4` (steady-state, bỏ frame đầu):

    Tầng                  @160        @192        @256
    image_encoder        75,2 ms     90,0 ms     164,2 ms     (72 % / 70 % / 77 %)
    memory_attention     16,3        22,6        34,6         (15 % / 18 % / 16 %)
    mask_decoder         10,1         9,4        12,3         (10 % /  7 % /  6 %)
    memory_encoder        7,5         8,0        10,2         ( 7 % /  6 % /  5 %)
    prompt_encoder        1,7         1,3         1,8
    TỔNG                104,9       127,7       212,7

Hệ quả (phép tính "nếu encoder miễn phí"): @160 còn 30 ms → 33 FPS; @192 còn 38 ms → 26 FPS;
@256 còn 49 ms → 20 FPS. Tức **chỉ khi thay encoder bằng backbone mobile mới có cửa 25-30 FPS**.

Lưu ý: `memory_attention` còn được gọi bên trong `_prepare_memory_conditioned_features`, nên
bảng này in riêng dòng đó để thấy phần bị tính hai lần — đừng cộng thẳng các dòng.

Chạy: .venv/bin/python -m scripts.profile_stages 192 12
"""
import argparse
import os
import statistics
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tracker_engine import TrackerEngine  # noqa: E402

_SUBMODULES = ("image_encoder", "memory_attention", "memory_encoder",
               "sam_mask_decoder", "sam_prompt_encoder")


def _instrument(predictor) -> dict:
    """Bọc forward của các module con; trả dict tích luỹ thời gian (giây)."""
    acc = {}

    def wrap(obj, name):
        original = obj.forward

        def timed(*args, **kwargs):
            t0 = time.perf_counter()
            out = original(*args, **kwargs)
            acc[name] = acc.get(name, 0.0) + (time.perf_counter() - t0)
            return out

        obj.forward = timed

    for name in _SUBMODULES:
        module = getattr(predictor, name, None)
        if module is not None:
            wrap(module, name.replace("sam_", ""))
    return acc


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo chi phí từng tầng SAM 2")
    parser.add_argument("--image-size", type=int, default=192)
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--source", default="data/binh1.mp4")
    # Ô CHAI của data/binh1.mp4. Bản cũ 104,308,209,287 phủ KHUÔN MẶT (audit 14-11 —
    # docs/demo-clip-va-o-chon.md), nên mọi bảng "ms từng tầng" trước đó đo trên mặt.
    parser.add_argument("--bbox", default="300,275,150,410")
    args = parser.parse_args()

    engine = TrackerEngine.build_default(device="cpu", image_size=args.image_size)
    acc = _instrument(engine._predictor)

    x1, y1, x2, y2 = (int(v) for v in args.bbox.split(","))
    cap = cv2.VideoCapture(args.source)
    ok, frame = cap.read()
    if not ok:
        print(f"[LOI] không đọc được {args.source}")
        return 1
    engine.start(frame, (x1, y1, x2, y2))

    per_frame = []
    for _ in range(args.frames):
        ok, frame = cap.read()
        if not ok:
            break
        t0 = time.perf_counter()
        engine.process(frame)
        per_frame.append((time.perf_counter() - t0) * 1000)
    cap.release()
    if not per_frame:
        print("[LOI] không có frame nào được xử lý")
        return 1

    total = statistics.mean(per_frame)
    print(f"\n=== image_size {args.image_size}: {total:.1f} ms/frame "
          f"(mean {len(per_frame)} frame) ===")
    for name, seconds in sorted(acc.items(), key=lambda kv: -kv[1]):
        ms = seconds / len(per_frame) * 1000
        print(f"  {name:26} {ms:7.1f} ms  {100 * ms / total:5.1f} %")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
