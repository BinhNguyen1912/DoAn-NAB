"""
Bộ sinh ảnh giả lập cho test (fixture "ô vuông di chuyển").

Chức năng: sinh chuỗi frame numpy (không dùng video file) mô phỏng một đối tượng
hình vuông màu đặc di chuyển theo quỹ đạo tuyến tính biết trước, làm nền để test
TrackerEngine (ticket trong spec `camera-ai-realtime`) mà không cần commit dữ liệu nặng.

Input  : tham số số frame, kích thước frame, kích thước ô, vị trí/vận tốc đầu,
         danh sách frame bị che khuất.
Output : TrackingFixture gồm:
         - frames  : (N, H, W, 3) uint8
         - bboxes  : (N, 4) (x1, y1, x2, y2) — đáp án đúng, tiếp tục tính cả khi ô bị che
         - occluded: (N,) bool — frame nào ô bị che khuất
Lưu ý  : hàm thuần, không random, chạy ngay trên CPU không cần model.
"""
from dataclasses import dataclass

import numpy as np

# Màu nền (xám đậm) và màu ô vuông (cam) — cố định để test so khớp pixel độc lập.
BACKGROUND_COLOR = (40, 40, 40)
SQUARE_COLOR = (0, 140, 255)


@dataclass
class TrackingFixture:
    """Kết quả sinh: chuỗi frame + đáp án quỹ đạo + cờ che khuất."""

    frames: np.ndarray   # (N, H, W, 3) uint8
    bboxes: tuple        # N phần tử (x1, y1, x2, y2)
    occluded: np.ndarray  # (N,) bool
    frame_size: tuple    # (H, W)


def generate_tracking_sequence(
    num_frames=20,
    frame_size=(240, 320),
    square_size=40,
    start=(20, 20),
    velocity=(4, 2),
    occlusion_frames=(),
    occlusion_fraction=1.0,
):
    """Sinh chuỗi frame giả lập + đáp án quỹ đạo. Xem docstring module.

    occlusion_fraction: phần đối tượng bị che ở các frame trong `occlusion_frames`
        (1.0 = che hoàn toàn — mặc định; 0.5 = che một nửa; 0.0 = không che).
        Dùng để đo "duy trì bám bắt khi bị **che khuất một phần**" (tên đề tài).
    """
    height, width = frame_size
    x, y = start

    # Kiểm tra sớm: toàn bộ quỹ đạo phải nằm trong frame (báo lỗi cấu hình rõ ràng),
    # tránh sinh âm thầm frame mà ô vuông bị cắt mất mép — làm test sai lệch.
    for i in range(num_frames):
        xi = x + i * velocity[0]
        yi = y + i * velocity[1]
        if xi < 0 or yi < 0 or xi + square_size > width or yi + square_size > height:
            raise ValueError(
                f"Quỹ đạo tràn frame: frame {i} bbox ({xi}, {yi}, {xi + square_size}, {yi + square_size}) "
                f"nằm ngoài frame {frame_size}. Hãy giảm velocity/num_frames hoặc đổi start."
            )

    frames = np.zeros((num_frames, height, width, 3), dtype=np.uint8)
    bboxes = []
    occluded = np.zeros(num_frames, dtype=bool)

    for i in range(num_frames):
        frames[i, :, :] = BACKGROUND_COLOR
        x1, y1 = x, y
        x2, y2 = x + square_size, y + square_size
        frames[i, y1:y2, x1:x2, :] = SQUARE_COLOR
        if i in occlusion_frames:
            occluded[i] = True          # ô "lý thuyết" vẫn có vị trí, nhưng bị che một phần/toàn bộ
            cover_w = int(round((x2 - x1) * float(occlusion_fraction)))
            if cover_w > 0:             # vẽ "vật cản" che từ trái sang (như bàn tay che nửa mặt)
                frames[i, y1:y2, x1:x1 + cover_w, :] = BACKGROUND_COLOR
        bboxes.append((x1, y1, x2, y2))
        x += velocity[0]
        y += velocity[1]

    return TrackingFixture(frames=frames, bboxes=tuple(bboxes), occluded=occluded, frame_size=frame_size)