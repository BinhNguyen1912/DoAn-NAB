# Ngày 08-11-2026 — Đo cái giá của nội suy LK (drift_iou, tuổi mask) + ngưỡng nhiễu

## 🎯 Mục tiêu
- Trả lời câu hỏi nền mà **toàn bộ kiến trúc hybrid đứng trên nhưng chưa từng được đo**: *bỏ 2/3 lần
  suy luận (VOS) thì ô bao trôi bao nhiêu so với lần VOS kế tiếp?* `stability` hiện có chỉ đo **nhấp
  nháy**, không đo **đúng**.
- Công bố **ngưỡng nhiễu** để phép so A/B sau này không bị đọc thành "cải thiện" khi thực ra là dao
  động giữa hai lần chạy (SAM 2 không tất định).
- **Ngưỡng đăng ký TRƯỚC khi chạy** (`docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md`):
  binh1 @ `vos_every=3` phải có `drift_iou_p05 ≥ 0,70`, `drift_iou ≥ 0,85`, `mask_age_p95 ≤ 150 ms`;
  không đạt ⇒ hạ `vos_every` về 2.

## 📥 Input
- Plan 3 cố vấn; cố vấn A: *"repo đang đo sai thứ quan trọng nhất"*.
- 3 clip có sẵn: `data/binh1.mp4`, `data/binh1_simloss.mp4`, `data/binh2.mp4`.

## 🔨 Công việc đã thực hiện
1. **`src/live_tracking.py`**
   - `drift_iou` / `drift_iou_p05`: IoU giữa ô bao **đã phát ở đúng frame mà VOS đã thấy** và ô bao
     VOS sửa lại. Ánh xạ `seq → frame_idx` lúc submit; nếu kết quả về trước khi frame đó được phát
     thì hẹn `_pending_drift` và so lúc phát (quá hạn ⇒ bỏ mẫu, không lấy frame khác).
   - `_bbox_iou` dùng toạ độ **bao gồm** (+1) đúng quy ước `tracker_engine._mask_to_bbox`, trả `None`
     khi hộp suy biến (bên gọi bỏ mẫu, không quy thành 0 điểm).
   - `mask_age_ms` (từ lúc kết quả model sẵn sàng) + **`mask_age_total_ms`** (cộng `vos_ms` = tuổi dữ
     liệu ảnh người xem thực thấy) + `mask_age_p95` tính trên con số **total**.
   - `drift_n` / `age_n`: `0` ⇒ **chưa đo**; giá trị là `None` chứ không phải `0,0`.
   - Đường inline (`vos_every=1`) **không** đo drift (lúc đó không có nội suy; trước đây nó đổ "độ ổn
     định bbox của VOS" vào cùng field, khiến "tắt LK" trông tốt hơn 0,03 một cách vô nghĩa).
2. **`scripts/repeatability.py`** (mới): `spread()`, `la_khac_biet()`, `danh_gia()` — hàm thuần, có
   test; `n < 2` ⇒ không kết luận được gì.
3. **Artifact** `data/drift_2026-11-08_metrics.json`: **10 lần chạy**, `git_rev` = commit **chứa code
   sinh ra số** (kiểm bằng `git show ee9f256:src/live_tracking.py | grep -c drift_iou` = 13),
   `git_dirty: false`, lệnh cụ thể từng lần, ngưỡng đăng ký trước, ngưỡng nhiễu, `mask_drops`,
   `lost_streak`.

## 📤 Output / Kết quả
`image_size=192`, 900 frame/cấu hình, laptop CPU, mỗi cấu hình **3 lần**:

| Lần chạy | FPS phát | mask/giây | **drift (p05)** | n | **tuổi ảnh p95** | mask rỗng |
|---|---|---|---|---|---|---|
| binh1 · vos3 · lần 1 | 29,9 | 8,6 | **0,887 (0,720)** | 200 | **210 ms** | 0 |
| binh1 · vos3 · lần 2 | 29,9 | 8,7 | 0,889 (0,663) | 200 | 210 ms | 0 |
| binh1 · vos3 · lần 3 | 29,8 | 8,7 | 0,885 (0,663) | 200 | 207 ms | 0 |
| binh1 · vos2 · 3 lần | 29,8–29,9 | 7,5–7,8 | 0,873–0,879 (0,671–0,673) | 200 | 238–251 ms | 0 |
| binh1 · vos6 | 29,8 | 5,0 | 0,891 (0,721) | 140 | 309 ms | 0 |
| binh1 · vos1 (tắt LK) | **9,5** | 9,5 | **None** (không nội suy) | 0 | — | 0 |
| binh1_simloss · vos3 | 30,0 | 7,5 | 0,873 (0,644) | 200 | 236 ms | 16 |
| **binh2 · vos3** | 29,9 | 7,4 | **0,528 (0,000)** | 198 | 238 ms | **26** |

### Kết luận trung thực (quan trọng nhất của ngày)
- **Ngưỡng đăng ký trước KHÔNG ĐẠT.** Lần chạy đầu báo "ĐẠT" là **sản phẩm của metric lỏng**: khi đó
  drift so ô bao "đang phát" với kết quả của frame đã submit ~`vos_ms` trước (lệch ~3 frame), và tuổi
  mask **bỏ** thời gian suy luận. Review độc lập bắt đúng hai chỗ này (P2-5, P2-7). Đo lại đúng định
  nghĩa: p05 = 0,720 / 0,663 / 0,663 (2/3 lần dưới 0,70) và tuổi ảnh p95 = 210/210/207 ms (> 150 ms).
- **Theo luật đã đăng ký, hạ `vos_every` về 2 và đo lại — vô ích:** p05 0,671–0,673; tuổi ảnh p95
  238–251 ms; `mask_fps` 7,5–7,8 (**không** tăng so với 8,6–8,7 ở vos3). Nguyên nhân: VOS chỉ chạy
  ~7,5–8,7 lần/giây (`vos_ms` ≈ 130 ms) ⇒ **`vos_every` không phải nút điều khiển độ tươi của mask**,
  nút thật là độ trễ model. **Giữ mặc định `vos_every = 3`.**
- Điều này phải vào báo cáo: **HUD 30 FPS nhưng mask/ô bao lấy từ model cũ ~0,2 giây**; cấm viết
  "mask 30 FPS". Muốn mask tươi hơn phải nhanh hơn model (GPU/encoder nhẹ hơn) — không phải tinh
  chỉnh `vos_every`.
- **Ngưỡng nhiễu** (3 lần cùng cấu hình binh1/vos3): `drift_iou` ±0,004; `drift_iou_p05` ±0,057
  (gấp 14 lần mean — phân vị rất run); `vos_fps` ±1,2 %; `measured_fps` ±0,3 %; `mask_age_p95` ±3 ms;
  `mask_age_total_ms` tức thời ±87 ms (đừng dùng số tức thời để so).
- **binh2 hỏng thật**: drift 0,528 / p05 0,000 với 26 lần VOS trả mask rỗng, nhưng `mask_drops` và
  `lost_streak` = **0** ⇒ **LK không mất dấu**, lỗi nằm ở VOS/mẫu khởi tạo trên clip đó. Sửa lại câu
  chữ cũ ("LK mất dấu") cho đúng dữ liệu.
- File thay đổi: `src/live_tracking.py`, `scripts/repeatability.py` (mới),
  `tests/test_repeatability.py` (mới), `tests/test_live_tracking.py`, `README.md`, `AGENTS.md`,
  `data/drift_2026-11-08_metrics.json`.

## 🐞 Vấn đề gặp phải & cách xử lý
- Bench đầu trả **0 frame** ở cả 7 cấu hình: script truyền thiếu tham số ⇒ `bbox.json` rỗng ⇒ worker
  đứng ở `waiting_selection` (đúng thiết kế). Bài học: đọc `state` trong `status.json` trước khi tin số.
- **Deadlock tự gây ra** khi sửa P2-8: `_record_drift` lấy `_stats_lock` trong khi
  `_update_stats_locked` **đang giữ** lock ⇒ pytest treo tới timeout 600 s. Nay tách
  `_apply_drift_locked()`. Đây là lý do phải chạy test với `--timeout`.
- Đo drift theo frame cần ánh xạ `seq → frame_idx`; nếu kết quả về **trước** khi frame đó được phát
  (engine rất nhanh) thì phải hẹn `_pending_drift`, nếu không `drift_n` = 0 một cách im lặng.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Tự hạ cấp / cảnh báo khi drift xấu**: `p05 < 0,2` (như binh2) ⇒ báo đỏ trên UI hoặc tự
      `vos_every=1`. Hiện mới đo, chưa hành động.
- [ ] Đo drift cho **clip che khuất đi ngang** (kịch bản khó nhất) — dự đoán LK sẽ trôi qua vật cản.
- [ ] Muốn mask tươi hơn 0,2 s: đo **encoder nhẹ hơn / GPU** (đây là nút thật, không phải `vos_every`).
- [ ] Video demo H.264 (recorder đang `mp4v`, Chrome không phát được).

## 📚 Tài liệu tham khảo
- `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md` (ngưỡng đăng ký trước, viết trước khi chạy).
- `data/drift_2026-11-08_metrics.json` (10 lần chạy, ngưỡng nhiễu, phát hiện), `scripts/repeatability.py`.
- AGENTS §6 (4 quy tắc: stability/drift không phải độ chính xác; A/B phải nêu ngưỡng nhiễu;
  `vos_every` không điều khiển độ tươi mask; "0,0" phải đọc kèm `*_n`).
