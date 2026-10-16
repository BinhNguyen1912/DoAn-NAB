# Ngày 16-10-2026 — Implement ticket 06: Visualizer HUD (mask + bbox + quỹ đạo + FPS + ghi video)

## 🎯 Mục tiêu
- Ticket 06: overlay trình bày hoàn chỉnh cho demo bảo vệ — mask alpha, ô bao, quỹ đạo (deque giới hạn), HUD FPS + độ trễ nhãn tiếng Việt (đúng font), ghi video mp4 bản overlay bật/tắt qua config/CLI. Đáp ứng yêu cầu 5 của thầy (vị trí, vùng phân đoạn, quỹ đạo).

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/06-...md` (claimed sau khi 05 resolve).
- Spec: quyết định module Visualizer — nhận frame + result → ảnh HUD; deque quỹ đạo tối đa N điểm; nhãn tiếng Việt; ghi mp4 bằng VideoWriter.
- Ràng buộc font: `cv2.putText` (Hershey ASCII) không render dấu tiếng Việt → vẽ text qua PIL + font TTF, fallback ASCII.
- Code sẵn có: `live_pipeline` (run_tracking/run_interactive), `TrackerEngine.TrackingResult`.

## 🔨 Công việc đã thực hiện
1. TDD chu kỳ 1 (RED → GREEN): `src/visualizer.py` — `Visualizer.update(frame, result)` trả ảnh HUD 5 lớp: mask alpha blend 0.35 → bbox đỏ → polyline quỹ đạo tím + chấm tâm hiện tại → HUD 2 dòng (`FPS: x.x`, `Độ trễ: … ms/frame`) → ghi vào recorder nếu mở. 15 test: assert từng lớp pixel, FPS hiệu dụng = 1000/mean(latency cửa sổ trượt 30).
2. Quỹ đạo: deque(maxlen=max_trajectory) tâm từ bbox; bbox (0,0,0,0) (mask rỗng) không thêm điểm rác; 60 điểm vào maxlen=50 → giữ đúng 50 điểm cuối (test không tràn). `reset()` xoá quỹ đạo + latency khi phím r.
3. Nhãn tiếng Việt: `find_vietnamese_font()` — thử CAMAI_FONT_PATH → DejaVuSans (Linux) → Segoe UI/Arial (Windows) → Arial Unicode (macOS); có font → PIL truetype render chữ có dấu; không → cv2.putText không dấu. Test tìm font (skip khi máy trống).
4. Ghi video: `open_recorder(path, fps, frame_size=None)` — mp4v; frame_size=None → mở trì hoãn ở update() đầu (display không biết trước kích thước); mở lỗi → False + cảnh báo; `close_recorder()` an toàn khi chưa mở. Test đọc lại mp4: đúng N frame, đúng (H,W,3).
5. Tích hợp: `run_tracking(..., visualizer=None)` và `run_interactive(..., visualizer=None)` — None giữ overlay tối thiểu ticket 04 (test cũ không đổi); track mode dùng `visualizer.update`, phím r gọi `visualizer.reset()`. CLI `run_live.py`: `--record FILE`, `--record-fps`, `--max-trajectory`; headless lấy fps nguồn từ peek (đọc TRƯỚC close), display mặc định 30.
6. Kiểm tra: **48/48 passed** (31 cũ + 17 mới, 1:42 — không regression). Smoke CLI thật trên fixture 5 frame + `--record`: mp4 đọc lại 5 frame (240,320,3), HUD có nội dung, mean=3332 ms, FPS hiệu dụng ≈0.30.

## 📤 Output / Kết quả
- Ticket 06: **3/3 tiêu chí ticked** (đường mp4 + quỹ đạo + HUD chứng minh tự động; hiển thị cửa sổ live chờ kiểm thủ công như 04/05).
- File thay đổi:
  - `src/visualizer.py` — Visualizer: HUD 5 lớp + deque quỹ đạo + PIL font Việt + recorder mp4 (mới)
  - `src/live_pipeline.py` — run_tracking/run_interactive nhận visualizer; r → visualizer.reset() (sửa)
  - `tools/run_live.py` — --record/--record-fps/--max-trajectory; _make_visualizer (sửa)
  - `tests/test_visualizer.py` — 15 test HUD/quỹ đạo/font/ghi video (mới)
  - `tests/test_interactive_loop.py` — +2 test tích hợp visualizer trong vòng lặp (sửa)

## 🐞 Vấn đề gặp phải & cách xử lý
- `peek.close()` trước khi đọc `source_fps` → RuntimeError khi bật --record headless. Sửa: đọc `peek_fps` trước khi close.
- Edit tool xoá nhầm 1 dòng test (chèn TestVisualizerIntegration) — phát hiện qua grep, khôi phục.
- Nền test là xám (40,40,40) ≠ 0 → assert `sum()>0` vô nghĩa; đổi sang so pixel với frame gốc/nền.
- Toạ độ tâm: bbox (100+5i, …) → tâm (110+5i) không phải (125+5i) — tính lại trước khi chạy test.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Kiểm thủ công --display/--record trên máy có GUI + camera.
- [ ] Ticket 07 MetricsLogger: CSV + summary (mean/p95) + độ ổn định (frame mask rỗng/điểm thấp).
- [ ] Ticket 08: config YAML (dồn --record/--max-trajectory vào file), README, hướng dẫn cài đặt.

## 📚 Tài liệu tham khảo
- `/implement`, `/tdd`; spec + ticket 06; ADR-0002 (số liệu trung thực); docs OpenCV polylines/VideoWriter; PIL ImageFont (Unicode rendering).