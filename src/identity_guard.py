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


def search_window_radius(bbox, frame_shape, lk_velocity=None,
                         motion_scale=1.5, min_ratio=0.10,
                         max_jump_ratio=DEFAULT_MAX_JUMP_RATIO) -> float:
    """Tính bán kính dịch chuyển tối đa hợp lý cho đối tượng.

    Dựa trên kích thước đối tượng (size = max(w, h)) và vận tốc Lucas-Kanade.
    Tránh trường hợp vật thể nhỏ bị nhảy 100-150 px sang tường mà ngưỡng 25% đường chéo
    khung (200 px) vẫn bỏ lọt (ca remote máy lạnh trắng 21-11).
    """
    if not bbox or tuple(bbox) == (0, 0, 0, 0):
        return 0.0
    h, w = frame_shape[0], frame_shape[1]
    diagonal = math.hypot(w, h)
    w_obj = abs(bbox[2] - bbox[0])
    h_obj = abs(bbox[3] - bbox[1])
    size_obj = max(w_obj, h_obj)

    ratio_factor = max_jump_ratio / DEFAULT_MAX_JUMP_RATIO
    effective_min_ratio = min(min_ratio, max_jump_ratio)
    radius = max(effective_min_ratio * diagonal, motion_scale * size_obj * ratio_factor)
    if lk_velocity is not None:
        vx, vy = float(lk_velocity[0]), float(lk_velocity[1])
        radius += math.hypot(vx, vy)

    return min(radius, max_jump_ratio * diagonal)


def is_suspect_switch(prev_bbox, cur_bbox, frame_shape,
                      max_jump_ratio=DEFAULT_MAX_JUMP_RATIO,
                      lk_velocity=None,
                      use_search_window=True):
    """True nếu tâm ô bao nhảy ra ngoài bán kính chuyển động hợp lý (search window)."""
    if not prev_bbox or not cur_bbox:
        return False
    if tuple(prev_bbox) == (0, 0, 0, 0) or tuple(cur_bbox) == (0, 0, 0, 0):
        return False
    (px, py), (cx, cy) = _center(prev_bbox), _center(cur_bbox)
    expected_x, expected_y = px, py
    if lk_velocity is not None:
        expected_x += float(lk_velocity[0])
        expected_y += float(lk_velocity[1])

    jump = math.hypot(cx - expected_x, cy - expected_y)

    if use_search_window:
        radius = search_window_radius(prev_bbox, frame_shape, lk_velocity=lk_velocity,
                                      max_jump_ratio=max_jump_ratio)
        return jump > radius

    h, w = frame_shape[0], frame_shape[1]
    diagonal = math.hypot(w, h)
    return jump > max_jump_ratio * diagonal


DEFAULT_CLEAR_KEY = "c"

# Ba trạng thái của cổng nghi (24-11). Vì sao phải có trạng thái THỨ BA:
#   `ok`            — bám bình thường, vẽ mask đầy đủ (tin cậy).
#   `nghi`          — vừa có cú nhảy vô lý: KHÔNG vẽ mask, chỉ vẽ ô nét đứt (luật 21-11).
#   `chua_xac_minh` — sau `settle_steps` bước bám ổn định (không nhảy, mask còn) mà KHÔNG ai xác
#                     nhận: VẪN vẽ nhưng ở kiểu "chưa xác minh" (viền mask nét đứt, không tô,
#                     không quỹ đạo) — không phải kiểu tin cậy.
# Đo 24-11 (phiên `demoip_1124-125109`, 246 frame): cổng báo ĐÚNG ở f137 (ô nhảy sang tóc) rồi
# **tự bám lại đúng cái thìa ở t≈40 s**, nhưng latch không có đường xoá nào (chỉ `r`/`c`/reacquire —
# re-ID đang TẮT) ⇒ **109/246 = 44,3 % phiên** chỉ có ô nét đứt, người dùng nói "nó chỉ nghi thôi".
TRANG_THAI_OK = "ok"
TRANG_THAI_NGHI = "nghi"
TRANG_THAI_CHUA_XAC_MINH = "chua_xac_minh"

# 8 bước VOS ≈ 1,3 s (4,5 bước/s) … 1,8 s (6,3 bước/s). Đủ để KHÔNG hạ ngay ở cú nhảy thứ hai
# (nhấp nháy) và đủ ngắn để phiên demo không chết. Số này KHÔNG phải ngưỡng an toàn: nó chỉ đổi
# kiểu vẽ (ấn/hiện), không biến vùng đáng ngờ thành "đã kiểm" — muốn tin cậy thì phải `c`/`r`.
DEFAULT_SETTLE_STEPS = 8

# "VẬT RỜI KHUNG RỒI VÀO LẠI" KHÔNG PHẢI "ĐỔI ĐỐI TƯỢNG" (đo 24-11, phiên `demoip_1124-193026`).
# Người dùng báo: *"ra khung khoảng 10 s, đưa vào lại thì bị nghi, từ đó không nhận diện lại nữa"*.
# Đọc CSV phiên đó: `mask_area = 0` **15 frame liền** (f248–262) ⇒ f263 model trả lại mask đầu tiên
# nhưng chỉ **559 px** (0,346× `bbox_area_ref` — một mẩu rác, không phải vật) ⇒ f264 trả mask thật
# 24 100 px ở chỗ khác ⇒ cổng chấm "nhảy" giữa MẨU RÁC và VẬT, báo nghi, rồi latch giữ tới hết phiên:
# **140/404 = 34,7 %** phiên KHÔNG TIN CẬY, trong đó **132 frame = 32,7 %** là `chua_xac_minh` (ô nét
# đứt, không tô) và 8 frame đầu là `nghi` ⇒ người dùng thấy "không nhận diện lại nữa". Trước đó cùng
# phiên còn 5 đoạn mất dấu dài 8–22 frame.
# Vì sao 3 (và BIÊN MỎNG tới đâu): 1–2 frame rỗng là **nhấp nháy**. Hai ca báo ĐÚNG đã biết sát ngưỡng:
# `125109#137` vắng **1** frame, `121732#178` vắng **2** frame liền (f176–177) ⇒ ngưỡng 2 sẽ MẤT ca
# `121732#178`, ngưỡng 3 giữ 7/7. Đây KHÔNG phải "ngưỡng an toàn", chỉ là ranh giới giữa "nhấp nháy"
# và "vắng" — muốn nói "3 là đúng" phải có thêm ca nhãn (nợ V0 của plan 24-11).
DEFAULT_LOST_RESET_STREAK = 3

# Số bước ĐẦU của phiên bám mới mà cổng KHÔNG chấm nhảy. Vì sao > 1: bước đầu sau khi vắng (**f263**)
# đã tự khỏi bị chấm (mốc = ô rỗng), nhưng bước THỨ HAI (**f264**) lại lấy mẩu rác f263 làm mốc ⇒ cần
# 2 bước. Sau đó mốc là một ô thật (mask 24k px) nên chấm lại là đúng.
DEFAULT_REACQ_GRACE_STEPS = 2


class IdentityWatch:
    """Cổng "nghi đổi đối tượng" **CÓ NHỚ** (latch) — báo một lần thì giữ trạng thái nghi.

    Vì sao phải nhớ (đo 21-11 trên phiên `demoip_1121-121732`): cổng nhảy báo ĐÚNG ở f178 khi hệ bám
    sang cửa/tường be cùng tông, nhưng sau cú nhảy đó chuyển động lại **mượt** ⇒ `is_suspect_switch`
    KHÔNG báo lại lần nào nữa, và hệ vẫn vẽ mask SAI thêm **65 frame**. Cảnh báo một lần mà không nhớ
    là cảnh báo vô dụng: người dùng đang nhìn màn hình, không đọc console.

    Đo chi phí báo (replay 18 phiên, 2 973 frame, `data/jump_gate_replay_2026-11-21_metrics.json`):
    cổng chỉ báo **21 lần = 0,71 %** số frame ⇒ ẩn ô khi nghi là rẻ.

    Đây KHÔNG phải "tự sửa": hệ không bao giờ tự tuyên bố vùng đáng ngờ là "đã kiểm". Đã đo:
    `track_cos` KHÔNG phân biệt được vùng sai cùng tông (dải 0,752–0,989 nằm trong dải ca đúng) nên
    không thể tự phán quyết; thứ duy nhất tự làm được là **hạ mức hiển thị** từ "ẩn sạch" xuống
    "vẽ kiểu chưa xác minh" khi đường bám đã ổn định lại (xem `TRANG_THAI_CHUA_XAC_MINH`).
    """

    def __init__(self, max_jump_ratio=DEFAULT_MAX_JUMP_RATIO,
                 settle_steps=DEFAULT_SETTLE_STEPS,
                 lost_reset_streak=DEFAULT_LOST_RESET_STREAK,
                 reacq_grace_steps=DEFAULT_REACQ_GRACE_STEPS):
        """`settle_steps`: số bước ổn định để hạ `nghi` → `chua_xac_minh`. 0 = TẮT (hành vi cũ:
        ẩn tới hết phiên, chỉ `r`/`c` mới xoá) — dùng để tái lập số của các phiên trước 24-11.

        `lost_reset_streak`: số bước LIÊN TIẾP không có mask để coi là **vật đã rời khung** ⇒ lần có
        mask kế tiếp là **phiên bám mới** (xoá nghi + không chấm nhảy `reacq_grace_steps` bước đầu).
        0 = TẮT (hành vi trước 24-11 tối: mẩu rác sau khi vắng bị dùng làm mốc).
        """
        self.max_jump_ratio = float(max_jump_ratio)
        self.settle_steps = max(0, int(settle_steps))
        self.lost_reset_streak = max(0, int(lost_reset_streak))
        self.reacq_grace_steps = max(0, int(reacq_grace_steps))
        self._trang_thai = TRANG_THAI_OK
        self._settle = 0
        self._lost = 0          # số bước liên tiếp KHÔNG có mask
        self._grace = 0         # số bước đầu phiên bám mới còn miễn chấm nhảy

    @property
    def tai_bam(self) -> bool:
        """Đang trong `reacq_grace_steps` bước đầu của phiên bám mới (cổng MIỄN chấm nhảy)."""
        return self._grace > 0

    @property
    def trang_thai(self) -> str:
        return self._trang_thai

    @property
    def nghi(self) -> bool:
        """Đang CHẶN vẽ mask (chỉ ở trạng thái `nghi`; `chua_xac_minh` thì vẫn vẽ, kiểu khác)."""
        return self._trang_thai == TRANG_THAI_NGHI

    @property
    def chua_xac_minh(self) -> bool:
        """Đã bám ổn định lại nhưng CHƯA ai xác nhận ⇒ vẽ kiểu "chưa xác minh"."""
        return self._trang_thai == TRANG_THAI_CHUA_XAC_MINH

    @property
    def vua_bao(self) -> bool:
        """Bước vừa rồi cổng **thật sự** kết luận "đổi đối tượng" (không bị miễn chấm).

        Đường in cảnh báo/banner phải đọc cờ này thay vì tự gọi `is_suspect_switch` lần nữa:
        nếu không, sửa state machine mà người dùng vẫn thấy WARN + banner (đo 24-11, phiên
        `demoip_1124-193026`: cổng miễn chấm nhưng `_switch_warning` tự chấm lại ⇒ vẫn báo).
        """
        return self._vua_bao

    def update(self, prev_bbox, cur_bbox, frame_shape, lk_velocity=None,
               co_mask=True, nhay=None, buoc_moi=True) -> bool:
        """Cập nhật bằng một bước VOS; trả True nếu ĐANG CHẶN vẽ mask (trạng thái `nghi`).

        `co_mask` = bước này model THẬT SỰ trả mask (không rỗng). Chỉ đếm bước ổn định khi có mask:
        mask rỗng nghĩa là hệ không có gì để tin, hạ mức lúc đó là vẽ một vùng không tồn tại.

        `nhay` = quyết định "bước này có phải cú nhảy" do BÊN NGOÀI tính (mặc định `None` = dùng
        `is_suspect_switch`). Có mặt để `scripts/eval_gate_rules.py` chấm các LUẬT khác nhau trên CÙNG
        máy trạng thái — nếu script tự chép lại state machine thì hai bản sẽ trôi khỏi nhau (bài học
        "test chép lại logic" trong repo).

        `buoc_moi` = **đây là một BƯỚC VOS mới**, không phải một frame hiển thị lặp lại cùng kết quả.
        Bắt buộc phải phân biệt (review độc lập 24-11, P1): đường web (`live_tracking`) gọi hàm này
        MỖI frame phát, mà `vos_every=3` ⇒ cùng một kết quả VOS được lặp ~3,5 lần (29,8 FPS hiển thị /
        8,5 VOS mỗi giây). Khi đó `lost_reset_streak=3` co lại còn ~1 bước VOS (một VOS rỗng là reset ⇒
        mất ca "nhấp nháy" `125109#137`) và `reacq_grace_steps=2` hết hạn TRƯỚC bước VOS kế (⇒ đúng cú
        "mẩu rác 559 px → vật 24 100 px" vẫn bị chấm và vẫn báo). `buoc_moi=False` ⇒ hàm KHÔNG đổi
        trạng thái gì: cùng một kết quả VOS không mang thêm thông tin về danh tính.
        """
        self._vua_bao = False          # cờ của BƯỚC NÀY (reset đầu mỗi `update`)
        if not buoc_moi:
            return self.nghi
        # --- "Vật rời khung rồi vào lại" ≠ "đổi đối tượng" (24-11) ---------------------------
        # Đếm bước vắng; khi mask trở lại sau `lost_reset_streak` bước vắng thì đó là PHIÊN BÁM MỚI:
        # xoá nghi (đường lui duy nhất khi re-ID tắt) và miễn chấm nhảy vài bước đầu, vì mốc so sánh
        # lúc đó là **mẩu rác của lần dò lại** chứ không phải vật (đo: f263 = 559 px = 0,346× tham chiếu).
        if not co_mask:
            self._lost += 1
        else:
            if self.lost_reset_streak > 0 and self._lost >= self.lost_reset_streak:
                self.reset()                       # về `ok` + xoá `_lost`/`_grace`
                self._grace = self.reacq_grace_steps
            self._lost = 0

        if nhay is None:
            nhay = is_suspect_switch(prev_bbox, cur_bbox, frame_shape,
                                    max_jump_ratio=self.max_jump_ratio,
                                    lk_velocity=lk_velocity)
        if self._grace > 0:
            # Mốc chưa đáng tin ⇒ KHÔNG chấm (và KHÔNG in cảnh báo — xem `vua_bao`).
            self._grace -= 1
            return self.nghi
        if nhay:
            # Cú nhảy MỚI luôn đưa về `nghi` (kể cả đang `chua_xac_minh`) và đếm lại từ 0.
            self._trang_thai = TRANG_THAI_NGHI
            self._settle = 0
            self._vua_bao = True
            return self.nghi
        if self._trang_thai == TRANG_THAI_NGHI:
            if not co_mask:
                self._settle = 0          # mất dấu: chưa có gì ổn định để nói
            elif self.settle_steps > 0:
                self._settle += 1
                if self._settle >= self.settle_steps:
                    self._trang_thai = TRANG_THAI_CHUA_XAC_MINH
                    self._settle = 0
        return self.nghi

    def reset(self) -> None:
        """Xoá trạng thái nghi (về `ok`) — người dùng chọn lại (`r`) / xác nhận (`c`) / reacquire."""
        self._trang_thai = TRANG_THAI_OK
        self._settle = 0
        self._lost = 0
        self._grace = 0
        self._vua_bao = False
