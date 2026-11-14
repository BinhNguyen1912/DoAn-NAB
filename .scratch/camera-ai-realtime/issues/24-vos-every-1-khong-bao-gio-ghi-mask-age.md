# 24: `vos_every = 1` không bao giờ ghi `mask_age_total_ms` (HUD im lặng ở cấu hình đơn luồng)

**What to build:** `_note_mask_age` chỉ được gọi ở đường **có luồng VOS** (`_result_threaded`). Đường
`vos_every = 1` chạy inline (`_after_vos`) nên `mask_age_total_ms = None` suốt phiên ⇒ HUD (#8) không
hiện tuổi mask, và `bang_cau_hinh --every 1` / `ab --b vos_every=1` sẽ có `mask_age_p95 = None`.
Không sai về ngữ nghĩa (`None` ≠ 0) nhưng là lỗ hổng của chính việc #8 ở cấu hình đơn luồng — đúng cấu
hình đã dùng để đo mIoU fixture và các số "1 luồng 8,8 FPS".

**Cách làm:** trong `_after_vos`, gọi `_note_mask_age(0.0, vos_ms=result.elapsed_ms, pre_ms=...,
queue_ms=None, post_ms=...)` (age = 0 vì frame vừa VOS chính là frame đang hiển thị), hoặc ghi rõ trong
docs/HUD là `vos_every=1` không đo tuổi.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `vos_every=1`, chạy 2 frame ⇒ `mask_age_total_ms` khác `None`, `age_n = 2` (test ghim)
- [ ] Bảng cấu hình / A/B chạy `--every 1` không còn `mask_age_p95 = None` (hoặc docs nói rõ là chưa đo)
