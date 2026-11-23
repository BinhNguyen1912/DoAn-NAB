"""Tỉ lệ diện tích ô bao so với mức "bình thường" của chính phiên — **CHỈ ĐỂ CHẨN ĐOÁN**.

Vì sao có module này (plan `docs/plan/24-11-2026-chong-tran-nen-cung-tong-chot.md`, việc 4):
lỗi "mask tràn sang nền cùng tông" (32 % frame phiên `demoip_1123-144505`, `mask_area` tới **6,7×**
vật) hiện chỉ chứng minh được bằng cách **đọc tay CSV**. Không có cột thì mọi kết luận về tràn là
miêu tả bằng lời — đúng lỗi đã gặp với `center_x/center_y` trước 21-11.

⚠️ **ĐÂY KHÔNG PHẢI MỘT CỔNG.** Plan 24-11 đã chốt **KHÔNG** nối luật diện tích vào `IdentityWatch`
vì mỗi cổng là một latch không tự hồi: phiên `144505` sẽ thành **98/194 = 50,5 %** frame mang ô nét
đứt (tràn bắt đầu f96) thay vì 25,8 %, mà không thêm thông tin nào cho người xem. Module này chỉ
GHI SỐ; quyết định bật cổng cần đủ 3 điều kiện ghi trong plan.

Vì sao EMA chứ không phải trung vị cả phiên: EMA chạy được **trực tuyến** (không cần biết tương lai),
và α = 0,03 ở 6,3 bước/s cho hằng số thời gian ≈ 1/0,03 ≈ **33 bước ≈ 5 s** — cùng bậc với độ dài
một cú đưa vật qua khung.
"""

EMA_ALPHA = 0.03          # hằng số thời gian ≈ 33 bước ≈ 5 s ở 6,3 bước/s
MIN_BBOX_AREA = 64        # ô nhỏ hơn 8×8 px thì không đủ tin để làm mốc (nhiễu số nguyên)


class BboxAreaWatch:
    """EMA diện tích ô bao + tỉ lệ hiện tại. Thuần số học, không I/O, không phụ thuộc frame."""

    def __init__(self, alpha: float = EMA_ALPHA, min_area: int = MIN_BBOX_AREA):
        self.alpha = float(alpha)
        self.min_area = int(min_area)
        self.ema = None       # None = CHƯA có mốc (đừng ghi 0 — "chưa đo" khác "đo được 0")

    def update(self, bbox_w, bbox_h):
        """(w, h) → tỉ lệ `dien_tich / EMA` của frame này. `None` = chưa đủ dữ liệu / ô không hợp lệ.

        Frame đầu: EMA = diện tích frame đó ⇒ tỉ lệ 1,0 (mốc). Ô rỗng (mất dấu) **không** cập nhật
        EMA — nếu cập nhật, một chuỗi mất dấu sẽ kéo mốc về 0 rồi mọi frame sau đều "tràn".
        """
        try:
            w, h = int(bbox_w or 0), int(bbox_h or 0)
        except (TypeError, ValueError):
            return None
        dien_tich = w * h
        if dien_tich < self.min_area:
            return None
        if self.ema is None:
            self.ema = float(dien_tich)
            return 1.0
        ti_le = dien_tich / self.ema if self.ema > 0 else None
        self.ema = (1.0 - self.alpha) * self.ema + self.alpha * dien_tich
        return ti_le
