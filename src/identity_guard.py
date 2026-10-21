"""
Phát hiện "đổi danh tính" (identity switch) — chọn mặt A, A bị che rồi nó nhảy sang mặt B.

Chức năng: hàm thuần so sánh **ô bao của lần suy luận trước** với **lần hiện tại**; nếu tâm nhảy
quá xa trong một bước (không thể là chuyển động thật) thì trả True để hệ thống **cảnh báo** người
dùng bấm `r` chọn lại.

Input  : prev_bbox, cur_bbox (x1,y1,x2,y2) theo toạ độ frame gốc; frame_shape (H, W);
         max_jump_ratio = ngưỡng nhảy tối đa, tính theo đường chéo khung (mặc định 0.25 = 25%).
Output : bool — True nếu nghi ngờ đã bám sang đối tượng khác.
Lưu ý  : đây là **cảnh báo**, không phải sửa lỗi. Re-identification (nhận lại đúng người sau khi
         bị che) cần mô hình nhận dạng riêng — spec xếp ngoài phạm vi. Ô bao rỗng (mất dấu)
         không bị coi là "đổi danh tính".
"""
import math

DEFAULT_MAX_JUMP_RATIO = 0.25


def _center(bbox):
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def is_suspect_switch(prev_bbox, cur_bbox, frame_shape,
                      max_jump_ratio=DEFAULT_MAX_JUMP_RATIO):
    """True nếu tâm ô bao nhảy xa hơn `max_jump_ratio` × đường chéo khung trong 1 bước."""
    if not prev_bbox or not cur_bbox:
        return False
    if tuple(prev_bbox) == (0, 0, 0, 0) or tuple(cur_bbox) == (0, 0, 0, 0):
        return False
    h, w = frame_shape[0], frame_shape[1]
    diagonal = math.hypot(w, h)
    (px, py), (cx, cy) = _center(prev_bbox), _center(cur_bbox)
    jump = math.hypot(cx - px, cy - py)
    return jump > max_jump_ratio * diagonal
