# Ngày 21-11-2026 — Ticket 02: Search window motion gate chặn nhảy vị trí sang nền

> Log công việc theo quy định `AGENTS.md` mục 2 & 9.1 cho Ticket 02 (`textureless-tracking`).

## 🎯 Mục tiêu
- Ngăn chặn triệt để hiện tượng SAM 2 khi mất tự tin ở vật thể ít texture/đơn sắc (remote trắng trơn) nhảy cóc sang các mảng nền trắng/tường trắng/máy lạnh lân cận.
- Bổ sung cơ chế tính toán bán kính tìm kiếm động (`search_window_radius`) dựa trên kích thước đối tượng và vận tốc Lucas-Kanade, siết chặt ngưỡng phát hiện nhảy và bảo vệ không ghi đè vị trí sai vào lịch sử bám.

## 📥 Input
- Hiện tượng đã đo được trong phiên thật 21-11 (`data/demoip_1121-103854_*` ghi nhận tại `src/track_identity.py`): cú nhảy f109→f110 sang máy lạnh trắng là **114 px**, nhưng ngưỡng cũ cố định 25% đường chéo khung hình (200 px) đã bỏ lọt khiến hệ vẽ mask sai thêm 9 giây.
- Ticket `.scratch/textureless-tracking/issues/02-search-window-motion-gate-ch-n-nh-y-v-tr-sang-n.md`.

## 🛠️ Công việc đã thực hiện
1. **Tính toán bán kính động (`src/identity_guard.py`):**
   - Hiện thực hàm `search_window_radius(bbox, frame_shape, lk_velocity=None, motion_scale=1.5, min_ratio=0.10, max_jump_ratio=0.25)`.
   - Bán kính được tính dựa trên `max(w_obj, h_obj)` của vật thể, mở rộng theo độ dịch chuyển của Lucas-Kanade `math.hypot(vx, vy)` và chặn trần ở `max_jump_ratio * diagonal`.
   - Với vật thể nhỏ (50 px trên khung 640×480), bán kính dịch chuyển cho phép được siết từ 200 px xuống ~80-90 px, bắt trọn vẹn cú nhảy 114 px của chiếc remote.

2. **Nâng cấp phát hiện nhảy `is_suspect_switch` & `IdentityWatch` (`src/identity_guard.py`):**
   - Hỗ trợ tham số `lk_velocity`: tâm kỳ vọng được dịch theo vector vận tốc LK `(px + vx, py + vy)`. Nếu vật di chuyển nhanh nhưng đúng theo hướng LK thì không bị báo oan.
   - Khi tâm mới nhảy ra ngoài bán kính `search_window_radius`, trả về `True`.

3. **Chặn nhận vị trí nhảy sang nền (`src/live_tracking.py`, `src/live_pipeline.py`, `src/smooth_display.py`):**
   - `LkBoxTracker`: ghi nhận `self.last_dx` và `self.last_dy` từ trung vị độ dịch chuyển của các điểm quang học.
   - Trong `LiveTrackingSession`: khi `_watch.update` phát hiện nhảy vị trí (`is_nghi == True`), hệ thống giữ nguyên `_last_good_bbox` trước đó, **tuyệt đối không ghi đè vị trí nhảy sang nền** vào `_last_good_bbox`.
   - Mask và bounding box nhảy sang tường ngay lập tức bị ẩn (`an_o = True`, `bam = "nghi_doi_tuong"`).

4. **Kiểm thử tự động theo TDD:**
   - `tests/test_identity_guard.py`: Bổ sung 4 unit test trong `TestSearchWindowMotionGate` kiểm tra bán kính động, mở rộng theo LK, bắt đúng cú nhảy 114 px của remote, và không báo oan khi di chuyển theo LK.
   - `tests/test_live_tracking.py`: Thêm test `test_o_nhay_khong_ghi_de_last_good_bbox` đảm bảo pipeline live bảo toàn `_last_good_bbox`.

## 📊 Output / Kết quả
- Toàn bộ test suite chạy thành công:
  - `./run lint`: All checks passed.
  - `./run test`: 1728 passed, 5 deselected (100% xanh).
- File thay đổi:
  - `src/identity_guard.py`: `search_window_radius`, `is_suspect_switch`, `IdentityWatch.update`
  - `src/light_tracker.py`: `last_dx`, `last_dy`
  - `src/live_tracking.py`: áp dụng search window và chặn cập nhật `_last_good_bbox`
  - `src/live_pipeline.py`: chặn cập nhật `last_bbox` khi switch
  - `src/smooth_display.py`: chặn cập nhật `last_bbox` khi switch
  - `tests/test_identity_guard.py`: 4 tests cho search window gate
  - `tests/test_live_tracking.py`: test bảo toàn `_last_good_bbox`

## ⚠️ Vấn đề gặp phải & cách xử lý
- *Vấn đề:* Khi `max_jump_ratio` được người dùng tùy chỉnh trong các test cũ (ví dụ 0.5 hoặc 0.05), bán kính tĩnh cần tỷ lệ theo ngưỡng này.
- *Cách xử lý:* Tính `ratio_factor = max_jump_ratio / DEFAULT_MAX_JUMP_RATIO` để co giãn bán kính theo tỷ lệ tùy chỉnh của người dùng, đảm bảo 100% test cũ giữ nguyên hành vi kỳ vọng.

## 🔍 Kết quả Review độc lập (theo AGENTS.md §9.1)
- **Standards:** Đạt chuẩn. Tách bạch hàm tính toán hình học thuần túy (`search_window_radius`), không phụ thuộc trạng thái toàn cục, backward-compatible.
- **Spec:** Đạt 4/4 tiêu chí nghiệm thu của Ticket 02. Phân loại lỗi: **P0 = 0, P1 = 0**.

## ⏭️ Việc cần làm tiếp (Next steps)
- [ ] Triển khai Ticket 03: `03-c-ch-x-c-th-c-t-i-b-t-i-t-ng-sau-khi-m-t-d-u` (Cơ chế xác thực hình học và prompt đối chiếu khi tái bắt đối tượng sau khi mất dấu/che khuất hoàn toàn).
- [ ] Triển khai Ticket 04: `04-b-d-li-u-v-k-ch-b-n-o-ki-m-nh-l-ng-cho-v-t-tr-ng` (Đo kiểm mIoU và drift cho chiếc remote trắng).
