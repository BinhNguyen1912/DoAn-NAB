# Ngày 21-11-2026 — Ticket 03: Cơ chế xác thực tái bắt đối tượng sau khi mất dấu

> Log công việc theo quy định `AGENTS.md` mục 2 & 9.1 cho Ticket 03 (`textureless-tracking`).

## 🎯 Mục tiêu
- Khắc phục triệt để nhược điểm của việc chỉ dựa vào đặc trưng màu sắc / cosine appearance khi tái nhận diện (Re-ID) vật thể đơn sắc / ít vân bề mặt (như remote trắng trơn) sau khi bị che khuất hoặc rời khung hình.
- Bổ sung cơ chế lưu vết hình học (`GeometricProfile`), kiểm tra tính tương thích hình học (diện tích và tỷ lệ `w/h`) của ứng viên, và tự động sinh điểm prompt tương phản (positive ở tâm + negative ở viền ngoài) khi khởi động lại tracker.

## 📥 Input
- Kết luận từ các phiên đo trước (`AGENTS.md` mục 6): đặc trưng cosine màu sắc không thể phân biệt được vật thể trắng với mảng tường/cửa/công tắc cùng tông (mask-cos vùng sai 0.75-0.98 nằm trọn trong phân bố ca đúng 0.90).
- Ticket `.scratch/textureless-tracking/issues/03-c-ch-x-c-th-c-t-i-b-t-i-t-ng-sau-khi-m-t-d-u.md`.

## 🛠️ Công việc đã thực hiện
1. **Module bảo vệ hình học (`src/geometry_guard.py`):**
   - Định nghĩa lớp `GeometricProfile`: lưu lịch sử `(w, h, area, aspect_ratio)` qua các frame tracking ổn định (bộ đệm rolling maxlen=30, cần tối thiểu 3 mẫu).
   - Hàm `is_compatible(cand_bbox, area_tol=0.60, aspect_tol=0.45)`: loại bỏ ngay các ứng viên sai lệch diện tích (>60%) hoặc sai lệch tỷ lệ `w/h` (>45%).
   - Hàm `generate_contrast_points(bbox, frame_shape, margin=None)`: tự động sinh điểm positive ở tâm đối tượng và 4 điểm negative ở sát rìa ngoài 4 cạnh (có clip trong khung hình).

2. **Tích hợp vào ReIdSession (`src/reid.py`):**
   - Khởi tạo `self.geo_profile = GeometricProfile()`.
   - Trong `_collect_reference`: tự động cập nhật bounding box vào `geo_profile` mỗi khi quan sát thấy đối tượng ổn định.
   - Trong `_best_object_candidate`: tích hợp cổng kiểm tra hình học `if not self.geo_profile.is_compatible((x1, y1, x2, y2)): continue` trước khi tính điểm ưu tiên (prior/choice).
   - Trong `_reacquire`: tự động sinh điểm tương phản qua `generate_contrast_points` và truyền `points`/`labels` vào `self.engine.start(frame, bbox, points=pts, labels=lbls)` khi khởi động lại engine, giúp SAM 2 bám khít đối tượng mà không tràn mask ra nền.
   - Trong `reset()`: đặt lại trạng thái `geo_profile.reset()`.

3. **Kiểm thử tự động theo TDD:**
   - `tests/test_geometry_guard.py`: 5 unit tests kiểm tra `GeometricProfile` (chưa đủ mẫu fail-open, tính toán trung bình, chấp nhận ứng viên cùng hình dạng, loại bỏ mảng tường ngang/vuông) và `generate_contrast_points` (sinh điểm tâm + điểm viền).
   - `tests/test_reid.py`: 2 tests trong `TestReIdGeometricVerification` kiểm tra loại bỏ ứng viên sai tỉ lệ trong Re-ID session và chuyển tiếp điểm tương phản khi reacquire.

## 📊 Output / Kết quả
- Toàn bộ test suite chạy thành công:
  - `./run lint`: All checks passed.
  - `./run test`: 1735 passed, 5 deselected (100% xanh).
- File thay đổi:
  - `src/geometry_guard.py`: module mới chứa `GeometricProfile` và `generate_contrast_points`
  - `src/reid.py`: tích hợp `geo_profile` và sinh prompt tương phản khi reacquire
  - `tests/test_geometry_guard.py`: 5 tests cho module geometry guard
  - `tests/test_reid.py`: 2 tests tích hợp xác thực hình học

## ⚠️ Vấn đề gặp phải & cách xử lý
- *Vấn đề:* `ReIdSession(engine, embedder, ...)` yêu cầu tham số positional `embedder`.
- *Cách xử lý:* Truyền `embedder=None` trong fixture test khi chỉ kiểm thử cue `object`.

## 🔍 Kết quả Review độc lập (theo AGENTS.md §9.1)
- **Standards:** Đạt chuẩn. Module `geometry_guard.py` hoàn toàn độc lập, là hàm thuần hình học không phụ thuộc trạng thái toàn cục, backward-compatible.
- **Spec:** Đạt 4/4 tiêu chí nghiệm thu của Ticket 03. Phân loại lỗi: **P0 = 0, P1 = 0**.

## ⏭️ Việc cần làm tiếp (Next steps)
- [ ] Triển khai Ticket 04: `04-b-d-li-u-v-k-ch-b-n-o-ki-m-nh-l-ng-cho-v-t-tr-ng` (Đo kiểm mIoU và drift cho chiếc remote trắng).
