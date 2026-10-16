# Ngày 16-10-2026 — Implement ticket 01: fixture giả lập + pytest (/tdd)

## 🎯 Mục tiêu
- Hoàn thành ticket 01 của spec `camera-ai-realtime`: bộ sinh ảnh giả lập làm nền test cho TrackerEngine, setup pytest.

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/01-...md` (claimed), TDD loop tại seam `generate_tracking_sequence` (đã thống nhất với người dùng), GLOSSARY + ADR-0001/0002.

## 🔨 Công việc đã thực hiện (TDD đỏ→xanh, 4 chu kỳ)
1. Cài pytest 9.1.1 vào env `samurai`; claim ticket 01.
2. Chu kỳ 1: test shape/dtype chuỗi frame → hiện thực `src/synthetic_video.py` (module thuần numpy, không model).
3. Chu kỳ 2: test quỹ đạo bằng **literal tính tay** (bbox frame 3 = (32,26,72,66)) + so khớp pixel tâm ô = màu ô, pixel nền = màu nền.
4. Chu kỳ 3: test che khuất — ô biến mất khỏi frame (pixel = nền) nhưng đáp án bbox vẫn tiếp tục quỹ đạo + cờ `occluded` đúng.
5. Chu kỳ 4 (RED thật): quỹ đạo tràn frame → `ValueError` báo lỗi rõ; thêm validate sớm trong generator.
6. Code-review 2 trục (không có sub-agent trong môi trường này → làm trực tiếp): tìm thấy 2 lỗi nhỏ (typo "velocidad" trong docstring, unused import `field`) → sửa.
7. Tick 4/4 tiêu chí ticket 01 qua tracker; tạo `requirements.txt`, `conftest.py`.

## 📤 Output / Kết quả
- **5/5 tests green** (4.5s, CPU không model — tiêu chí 4 của ticket).
- Commit `f11233e` trên main.
- File thay đổi:
  - `src/synthetic_video.py` — generator fixture (mới)
  - `tests/test_synthetic_video.py` — 5 test (mới)
  - `conftest.py`, `requirements.txt` — hạ tầng (mới)
  - Ticket 01: 4/4 criteria ticked.

## 🐞 Vấn đề gặp phải & cách xử lý
- chu kỳ 1 viết implementation phủ sẵn quỹ đạo/che khuất (hơi wider-than-minimal) → các chu kỳ sau thành test khoá hành vi; chu kỳ 4 là RED thật duy nhất.
- Review tìm 2 finding nhỏ — đã sửa trước khi commit.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Implement ticket 03 (VideoSource) — frontier còn lại, chạy song song được.
- [ ] Sau đó ticket 02 (TrackerEngine) — nhân kỹ thuật.

## 📚 Tài liệu tham khảo
- `/implement`, `/tdd`, `/code-review` (mattpocock-skills); spec `camera-ai-realtime`.