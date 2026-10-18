# CODING_STANDARDS.md — chuẩn code của repo DoAn-NAB

File này đọc khi **review** (code-review trục Standards) và khi thêm module mới. Kiểm tra
cơ học (import thừa, biến thừa, trùng import, cú pháp) do `ruff` + `pytest` lo — không
nhắc lại ở đây. Dưới đây chỉ là những gì máy không tự phán được.

## Ngôn ngữ & đặt tên

- Python 3.10+. Biến/hàm `snake_case`, class `PascalCase`, hằng số `UPPER_SNAKE`.
- Module quan trọng PHẢI có docstring đầu file 4 mục: **Chức năng / Input / Output / Lưu ý**.

## Ngôn ngữ comment & chuỗi hiển thị

- Comment + docstring + `print()` console: **tiếng Việt CÓ DẤU đầy đủ** (thống nhất 1 kiểu
  trong file). Đây là quy tắc khẳng định — "tiếng Việt không dấu" KHÔNG được coi là tiếng Việt.
- **Ngoại lệ duy nhất:** chuỗi đưa vào `cv2.putText` phải là ASCII (font Hershey không có
  glyph dấu tiếng Việt). Khi cần chữ có dấu trên khung hình → dùng `Visualizer` (PIL + TTF).
  Mỗi chỗ dùng ASCII trên khung hình phải có comment nêu lý do.

## UI phải test được không cần màn hình

- Mọi tương tác/hiển thị phải **tiêm qua callback** (`display(img, mode)`, `on_frame(...)`,
  `on_result(...)`) để logic chạy headless được. Cửa sổ OpenCV chỉ là một cách cắm callback.
- Trong test **tuyệt đối không gọi GUI thật**: `cv2.namedWindow` khi không có display
  **SIGABRT cả process** (không phải exception bắt được). Giả lập bề mặt cv2 bằng
  `monkeypatch` (`namedWindow`, `imshow`, `waitKey`, `setMouseCallback`, `destroyAllWindows`)
  — xem mẫu `tests/test_run_live_cli.py::TestDisplayPath`.
- Kiểm GUI thật (kéo chuột, camera) là việc thủ công trên máy Windows — ghi rõ trong log.

## Test

- Mọi vòng lặp trong test PHẢI có đường thoát hữu hạn (kịch bản phím/step có `q`/StopIteration).
  `pytest.ini` có `--timeout=120` để test treo chết thay vì treo cả phiên.
- Số liệu kỳ vọng viết **literal tính tay** (nguồn độc lập), không tính lại bằng chính code đang test.
- Dùng fixture chung trong `tests/conftest.py` (`write_video`, `samurai_engine`) thay vì
  copy-paste; engine giả dùng `FakeEngine` (duck-type `start/process/reset`) cho test nhanh.
- Test cần model/checkpoint đánh dấu `@pytest.mark.slow` — làn nhanh `-m "not slow"` không chạy.

## Dữ liệu & artefact

- Không commit model weights, video/mp4, frame export — `.gitignore` đã chặn; chỉ giữ `.txt` nhỏ.
- Video/fixture trong test sinh bằng code (`src/synthetic_video.py`) hoặc `tmp_path`, không commit.
