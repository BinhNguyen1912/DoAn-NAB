# 46: Mask tràn nền cùng tông: 32 % frame mask to gấp ≥2,5× vật, 63,5 % ô chạm mép khung

**What to build:** Đo phiên `demoip_1123-144505` (re-ID tắt, 194 frame): mask **trôi sang nền be cùng tông** (tường/mặt bàn), không phải "mất dấu":

| chỉ số | số đo |
|---|---|
| frame `mask_area` > 2,5× vật thật (5 776 px) | **63/194 = 32 %**, bắt đầu f96 |
| ô bao chạm ≥1 mép khung | **115/181 = 63,5 %** (`bbox_h` = 479 = hết chiều cao khung) |
| `mask_area` p90 / max | 31 898 / 38 866 px (**5,5× / 6,7×** vật) |
| `score` < 0 | 44 frame (23 %), từ f133 — 11 frame TRƯỚC khi cổng nghi bắt |
| cổng nghi bắt ở | f144 (trễ 48 frame so với lúc mask bắt đầu tràn ở f96) |

Đây là lỗi gốc còn lại sau khi tắt re-ID; cổng nghi chỉ là "phanh tay" bắt quá muộn.

Việc này đổi **thuật toán** (thêm ràng buộc hình học/diện tích lên mask) ⇒ theo AGENTS §9.2 phải lập plan 3 ý kiến trước khi code. Ticket này giữ chỗ cho plan + triển khai.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Plan `docs/plan/24-11-2026-*.md` có 3 ý kiến + vòng phản biện + quyết định kèm lý do bác phương án còn lại
- [ ] Phương án được chọn có tiêu chí nghiệm thu BẰNG SỐ trên cả 2 clip GT (`binh1` 0,7794 và `clip_be2` 0,8754 là mốc hiện tại)
- [ ] Đo lại được trên chính phiên `demoip_1123-144505` đã có CSV (32 % frame mask > 2,5× vật ⇒ phải giảm)
