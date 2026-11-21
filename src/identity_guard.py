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


DEFAULT_CLEAR_KEY = "c"


class IdentityWatch:
    """Cổng "nghi đổi đối tượng" **CÓ NHỚ** (latch) — báo một lần thì giữ trạng thái nghi.

    Vì sao phải nhớ (đo 21-11 trên phiên `demoip_1121-121732`): cổng nhảy báo ĐÚNG ở f178 khi hệ bám
    sang cửa/tường be cùng tông, nhưng sau cú nhảy đó chuyển động lại **mượt** ⇒ `is_suspect_switch`
    KHÔNG báo lại lần nào nữa, và hệ vẫn vẽ mask SAI thêm **65 frame**. Cảnh báo một lần mà không nhớ
    là cảnh báo vô dụng: người dùng đang nhìn màn hình, không đọc console.

    Đo chi phí báo (replay 18 phiên, 2 973 frame, `data/jump_gate_replay_2026-11-21_metrics.json`):
    cổng chỉ báo **21 lần = 0,71 %** số frame ⇒ ẩn ô khi nghi là rẻ.

    Đây KHÔNG phải "tự sửa": hệ chỉ **ngừng vẽ** vùng đang bám (không bịa chỗ bám) và xin người dùng
    quyết định (`r` chọn lại, `c` = "vẫn đúng, tiếp tục"). Đã đo: `track_cos` KHÔNG phân biệt được
    vùng sai cùng tông (dải 0,752–0,989 nằm trong dải ca đúng) nên không thể tự phán quyết.
    """

    def __init__(self, max_jump_ratio=DEFAULT_MAX_JUMP_RATIO):
        self.max_jump_ratio = float(max_jump_ratio)
        self._nghi = False

    @property
    def nghi(self) -> bool:
        """Đang ở trạng thái nghi đổi đối tượng (đã báo và CHƯA được xoá)."""
        return self._nghi

    def update(self, prev_bbox, cur_bbox, frame_shape) -> bool:
        """Cập nhật bằng một bước VOS; trả True nếu ĐANG nghi (kể cả các frame sau cú nhảy)."""
        if is_suspect_switch(prev_bbox, cur_bbox, frame_shape,
                             max_jump_ratio=self.max_jump_ratio):
            self._nghi = True
        return self._nghi

    def reset(self) -> None:
        """Xoá trạng thái nghi — gọi khi người dùng chọn lại (`r`) hoặc xác nhận (`c`)."""
        self._nghi = False
