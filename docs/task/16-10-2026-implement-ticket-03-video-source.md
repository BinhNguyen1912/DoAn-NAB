# Ngày 16-10-2026 — Implement ticket 03: VideoSource (/tdd)

## 🎯 Mục tiêu
- Hoàn thành ticket 03: interface nguồn video thống nhất (webcam / RTSP / file) — seam thứ hai của hệ thống.

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/03-...md` (claimed), fixture từ ticket 01 (dùng để tạo video tạm cho test), quy ước code AGENTS.md.

## 🔨 Công việc đã thực hiện (TDD đỏ→xanh, 3 nhịp)
1. Chu kỳ 1: test FileVideoSource đọc đúng số frame/kích thước/dtype từ video tạm ghi từ fixture (helper `write_video` trong `tests/conftest.py`) → hiện thực `src/video_source.py`.
2. Chu kỳ 2–3: test factory định tuyến kiểu nguồn (int→webcam, rtsp://→RTSP, path→file, lazy-open), test báo lỗi rõ ràng: file không tồn tại → `FileNotFoundError`; RTSP timeout/không kết nối → `ConnectionError`; read trước open → `RuntimeError`.
3. Viết `tools/check_video_source.py` — script chọn nguồn bằng 1 tham số (tiêu chí 4); thêm bootstrap sys.path đầu script.
4. Smoke test thủ công 3 đường: file thật → đọc OK (0.2 ms/frame); file sai → lỗi rõ; RTSP không kết nối → lỗi rõ sau timeout, không treo.
5. Code-review 2 trục: tìm thấy smell **Duplicated Code** (3 adapter lặp body bọc cv2.VideoCapture) → refactor rút lớp cơ sở `_CaptureSource`, mỗi adapter chỉ khai `_create_capture()` + `_raise_open_error()`. Chạy lại test vẫn 10/10 (chứng minh test bám hành vi).

## 📤 Output / Kết quả
- **10/10 tests green** toàn suite (5 fixture + 5 video source).
- Ticket 03: 3/4 tiêu chí ticked (tiêu chí 2 — webcam — chờ xác nhận thủ công: chạy `python tools/check_video_source.py --source 0` trên máy có camera).
- File thay đổi:
  - `src/video_source.py` — interface + 3 adapter + factory (mới)
  - `tests/test_video_source.py` — 5 test (mới)
  - `tests/conftest.py` — helper write_video (mới)
  - `tools/check_video_source.py` — script kiểm tra nguồn (mới)

## 🐞 Vấn đề gặp phải & cách xử lý
- Script trong `tools/` không thấy package `src` khi chạy trực tiếp → thêm bootstrap sys.path đầu script.
- Lần đầu viết nhầm: edit vào file chưa có → chuyển sang `write`.
- WSL không có camera → tiêu chí webcam để hở, có script kiểm chứng sẵn. ⚠️ **Rủi ro ghi nhận**: hệ thống chạy trong WSL conda; để demo webcam live cần camera nhìn thấy được trong WSL (usbipd-win) HOẶC cài Python Windows — quyết định ở ticket 04/08.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Implement ticket 02 (TrackerEngine streaming) — frontier quan trọng nhất.
- [ ] User xác nhận webcam thủ công (sau khi có đường chạy camera trong WSL).

## 📚 Tài liệu tham khảo
- `/implement`, `/tdd`; spec + ticket 03; OpenCV VideoCapture CAP_PROP_OPEN/READ_TIMEOUT.