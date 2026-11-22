# Ngày 21-11-2026 — Ticket 01: Prompt negative và positive points khi chọn đối tượng

> Log công việc theo quy định `AGENTS.md` mục 2 & 9.1 cho Ticket 01 (`textureless-tracking`).

## 🎯 Mục tiêu
- Khắc phục hiện tượng phân đoạn vật thể đơn sắc / ít vân bề mặt (textureless) như remote màu trắng trơn trên nền sáng bị tràn mask (bleeding) dính vào tường/áo trắng ngay từ frame đầu tiên.
- Triển khai trọn vẹn vertical slice (Ticket 01): từ lõi `TrackerEngine` (SAM 2 predictor), bộ đọc/ghi `PromptSelection`, API endpoint `/api/live/select` & `/api/live/start`, bộ chọn giao diện `PromptSelector`, đến kiểu dữ liệu frontend TypeScript.

## 📥 Input
- Yêu cầu người dùng: remote trắng trơn nhận diện không tốt, dễ bắt nhầm vào nền sáng; máy tính không có GPU rời.
- Đặc tả kỹ thuật: `.scratch/textureless-tracking/spec.md` và ticket `.scratch/textureless-tracking/issues/01-prompt-negative-v-positive-points-khi-ch-n-i-t-n.md`.
- Tài liệu liên quan: SAM 2 `SAM2VideoPredictor.add_new_points_or_box(points, labels, box)`.

## 🛠️ Công việc đã thực hiện
1. **Lõi TrackerEngine (`src/tracker_engine.py`):**
   - Mở rộng hàm `start(frame, bbox, points=None, labels=None)`.
   - Kiểm tra ràng buộc đầu vào chặt chẽ: `points` và `labels` phải đi cùng nhau, số lượng khớp nhau, label thuộc {0, 1} (1=positive, 0=negative), tọa độ không vượt khung hình.
   - Truyền trực tiếp vào `self._predictor.add_new_points_or_box(self._state, frame_idx=0, obj_id=0, box=..., points=..., labels=...)`.
   - Bổ sung guard an toàn `if hasattr(gen, "close"): gen.close()` trong `_propagate_one`.

2. **Cấu trúc lưu trữ và đọc ô chọn (`src/live_tracking.py`):**
   - Định nghĩa dataclass `PromptSelection(bbox, points, labels)`.
   - Bổ sung `read_selection(path)` đọc file `bbox.json` có hỗ trợ `points` và `labels`.
   - Giữ nguyên hàm `read_bbox(path)` trả về `(x, y, w, h)` để đảm bảo tương thích ngược 100% với các hàm gọi cũ.
   - Trong vòng lặp chính của session live: chỉ truyền `points` và `labels` xuống `engine.start()` khi có dữ liệu điểm, tránh làm vỡ các mock/fake engine chỉ nhận 2 tham số.

3. **Adapter tiến trình nền (`src/api/adapters/worker_source.py`):**
   - `WorkerFrameSource`: nhận thêm `points` và `labels` tùy chọn.
   - Thêm phương thức `select(bbox, points=None, labels=None)` ghi nguyên tử ra `bbox.json`.
   - `_write_bbox` hỗ trợ serialize `points` và `labels`.

4. **Service & Routes API (`src/api/live.py`, `src/api/routes.py`, `src/api/schemas.py`, `src/api/main.py`):**
   - Định nghĩa schema `PointPrompt(x, y, label)` và `SelectLiveRequest(bbox, points)`.
   - Bổ sung `points` vào `SelectRequest` và `LiveStartRequest`.
   - Thêm phương thức `LiveStreamService.select(bbox, points=None, labels=None)`.
   - Bổ sung endpoint `POST /api/live/select` cho phép chọn hoặc chọn lại đối tượng kèm điểm prompt khi phiên live đang chạy.

5. **Bộ chọn OpenCV (`src/prompt_selector.py`):**
   - Mở rộng máy trạng thái ở trạng thái `DONE`: click chuột trái thêm điểm positive (xanh lá), click chuột phải thêm điểm negative (đỏ), click chuột giữa reset.
   - Bổ sung `take_selection()` trả về `(bbox, points, labels)`.
   - Vẽ trực quan các điểm đã chọn lên khung hình: vòng tròn xanh cho positive, vòng tròn đỏ cho negative kèm viền trắng nổi bật.

6. **Frontend DTO (`web/src/api.ts`):**
   - Khai báo interface `PointPrompt` và cập nhật `LiveStartOptions.points`.
   - Thêm hàm `selectLive(bbox, points)` gửi request lên `POST /api/live/select`.

7. **Kiểm thử tự động theo TDD:**
   - `tests/test_tracker_engine.py`: Thêm bộ test `TestStartPointsAndLabels` kiểm tra chuyển tiếp tham số xuống predictor, bắt lỗi validation khi dữ liệu không hợp lệ, và fixture phân tách vật trắng trên nền sáng chặn tràn mask.
   - `tests/test_live_tracking.py`: Thêm test `test_read_selection_co_points_va_labels` và `test_live_session_truyen_points_sang_engine_khi_co`.
   - `tests/test_api_live.py`: Thêm bộ test `TestLiveSelectPoints` kiểm tra `WorkerFrameSource.select` và `POST /api/live/select`.
   - `tests/test_api_routes.py`: Cập nhật whitelist kiểm tra hợp đồng OpenAPI.
   - `tests/test_prompt_selector.py`: Thêm bộ test `TestPromptSelectorPoints` kiểm tra thao tác chuột và màu sắc điểm vẽ.

## 📊 Output / Kết quả
- Toàn bộ test suite chạy thành công:
  - `./run lint`: All checks passed.
  - `./run test`: 1723 passed, 5 deselected (100% xanh).
  - `./run webtest`: 80 passed (100% xanh).
  - `cd web && npm run build`: build thành công không lỗi typecheck.
- File thay đổi:
  - `src/tracker_engine.py`: start nhận `points`, `labels` và validation
  - `src/live_tracking.py`: `PromptSelection`, `read_selection`, tương thích ngược
  - `src/api/adapters/worker_source.py`: `WorkerFrameSource.select` và `_write_bbox`
  - `src/api/live.py`: `LiveStreamService.select` và `start` points
  - `src/api/main.py`: `make_source` chuyển tiếp points
  - `src/api/routes.py`: route `POST /api/live/select`
  - `src/api/schemas.py`: `PointPrompt`, `SelectLiveRequest`
  - `src/prompt_selector.py`: click chọn điểm positive/negative và vẽ HUD
  - `web/src/api.ts`: types và helper `selectLive`
  - `tests/test_tracker_engine.py`: unit tests + fixture test
  - `tests/test_live_tracking.py`: tests đọc selection và truyền points
  - `tests/test_api_live.py`: tests endpoint live select
  - `tests/test_api_routes.py`: cập nhật contract OpenAPI
  - `tests/test_prompt_selector.py`: tests tương tác điểm prompt

## ⚠️ Vấn đề gặp phải & cách xử lý
1. **Lỗi `FakeEngine.start()` trong 40 test cũ của `test_live_tracking.py`:**
   - *Nguyên nhân:* Các lớp test double `FakeEngine` cũ chỉ khai báo `start(self, frame, bbox)` mà không nhận `**kwargs` hoặc `points=None`.
   - *Cách xử lý:* Trong `LiveTrackingSession`, chỉ truyền `points` và `labels` khi người dùng thật sự cung cấp điểm (`if selection.points is not None and selection.labels is not None:`), giữ nguyên lệnh gọi 2 tham số khi không có điểm.
2. **Lỗi `AttributeError: 'list_iterator' object has no attribute 'close'`:**
   - *Nguyên nhân:* `_propagate_one` gọi `gen.close()` trong khi các mock test trả về generic iterator `iter(...)`.
   - *Cách xử lý:* Thêm guard `if hasattr(gen, "close"): gen.close()`.
3. **OpenAPI Schema Contract:**
   - *Nguyên nhân:* Test `test_schema_sinh_ra_co_du_endpoint` ghim danh sách endpoint bắt buộc để tránh endpoint rác.
   - *Cách xử lý:* Cập nhật khai báo `/api/live/select` trong whitelist `bat_buoc`.

## 🔍 Kết quả Review độc lập (theo AGENTS.md §9.1)
- **Standards:** Đạt. Code tuân thủ quy ước type hint Python 3.10+, không có Fowler code smells, tương thích ngược với mọi caller cũ.
- **Spec:** Đạt 4/4 tiêu chí nghiệm thu của Ticket 01 trong `.scratch/textureless-tracking/issues/01-prompt-negative-v-positive-points-khi-ch-n-i-t-n.md`.
- **Phân loại lỗi:**
  - P0 (chặn merge): 0
  - P1 (sửa sớm): 0
  - P2 (nên sửa): 0
  - P3 (góp ý): 0

## ⏭️ Việc cần làm tiếp (Next steps)
- [ ] Triển khai Ticket 02: `02-search-window-motion-gate-ch-n-nh-y-v-tr-sang-n` (Search Window Motion Gate chặn nhảy vị trí sang nền tường sáng khi mất tự tin).
- [ ] Triển khai Ticket 03: `03-c-ch-x-c-th-c-t-i-b-t-i-t-ng-sau-khi-m-t-d-u` (Cơ chế tái bắt đối tượng hình học và prompt đối chiếu).
- [ ] Triển khai Ticket 04: `04-b-d-li-u-v-k-ch-b-n-o-ki-m-nh-l-ng-cho-v-t-tr-ng` (Benchmark mIoU và drift cho vật trắng trơn).

## 📚 Tài liệu tham khảo
- Segment Anything 2 (SAM 2): `sam2.sam2_video_predictor.SAM2VideoPredictor.add_new_points_or_box`.
