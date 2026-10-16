# Ngày 16-10-2026 — Implement ticket 05: PromptSelector (kéo chuột chọn object + phím r)

## 🎯 Mục tiêu
- Ticket 05: tương tác chọn đối tượng trên cửa sổ OpenCV — kéo chuột vẽ ô chọn, thả chuột → track khởi động; phím `r` dừng track và chọn lại trên frame hiện tại; ESC/q thoát sạch.

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/05-...md` (claimed sau khi 04 xong 3/3).
- Spec `.scratch/camera-ai-realtime/spec.md` (quyết định: PromptSelector là mouse callback; phím r; single-object ADR-0001; test PromptSelector = smoke/headless).
- Code sẵn có: `src/live_pipeline.py` (run_tracking + draw_overlay_minimal), `src/tracker_engine.py` (start/process/reset), `tools/run_live.py`.

## 🔨 Công việc đã thực hiện
1. TDD chu kỳ 1 (RED → GREEN): `src/prompt_selector.py` — `PromptSelector` là máy trạng thái thuần (idle → dragging → done): `on_mouse()` nhận sự kiện chuột OpenCV (LBUTTONDOWN/MOUSEMOVE/LBUTTONUP/RBUTTONDOWN), clip vô frame, chuẩn hoá bbox (kéo ngược vẫn đúng x1<x2), ô < 5px bị huỷ về idle; `take_bbox()` trả bbox và reset để chọn tiếp; `draw()` vẽ khung rubber-band xanh lá (đang kéo) / cam (đã xác nhận); `bind(frame)` cập nhật kích thước + reset. 12 unit test chạy headless bằng sự kiện chuột tổng hợp.
2. TDD chu kỳ 2 (RED → GREEN): thêm `run_interactive()` vào `src/live_pipeline.py` — vòng lặp tương tác SELECT (chờ bbox từ selector) → TRACK (`engine.process` từng frame) → `r`: `engine.reset()` + `selector.bind(frame hiện tại)` → SELECT lại; q/ESC thoát. Tiêm phụ thuộc để test headless không cần GUI:
   - `display(img, mode) -> key` (thay imshow+waitKey; test trả phím kịch bản).
   - `preselect_bbox` (từ --bbox: arm selector sau khi bind → track ngay không cần kéo).
   - `on_result(result)` (log ms/bbox từng frame — giữ tiêu chí độ trễ trung thực của ticket 04).
3. Test vòng lặp bằng `FakeEngine` (ghi lại start/process/reset, trả TrackingResult thật) + display trả phím script: chọn → track hết video; `r` → reset + chọn bbox mới track tiếp; `q`/ESC thoát sạch ở đúng chỗ; on_result gọi đủ N lần với frame_idx tăng dần.
4. Nối CLI `tools/run_live.py`: tách `_run_display()` (cửa sổ + `cv2.setMouseCallback` + run_interactive) và `_run_headless()` (run_tracking như cũ); `--display` không có bbox → hướng dẫn kéo chuột; có bbox → track ngay (vẫn bấm r được); headless giữ nguyên hành vi ticket 04.
5. Kiểm tra: full suite **31/31 passed** (trước đó 14/14 — không_regression; 1:44). Smoke CLI headless trên video fixture 5 frame với bbox thật: `mean=3270 ms, p95=3961 ms, FPS hiệu dụng ≈ 0.31` (khớp ticket 04). Đường `--display` chạy được trên máy có GUI (WSL không màn hình — kiểm thủ công).

## 📤 Output / Kết quả
- Ticket 05: **3/3 tiêu chí ticked** (máy trạng thái + vòng lặp được chứng minh tự động bằng test; phần kéo chuột thật trên cửa sổ chờ kiểm thủ công trên máy có GUI/camera — như tiếng tiếng ticket 04).
- File thay đổi:
  - `src/prompt_selector.py` — PromptSelector: máy trạng thái kéo-thả + draw khung (mới)
  - `src/live_pipeline.py` — thêm run_interactive + InteractiveSummary, QUIT_KEYS/RESET_KEY (sửa)
  - `tools/run_live.py` — --display dùng run_interactive; tách _run_display/_run_headless (sửa)
  - `tests/test_prompt_selector.py` — 12 test máy trạng thái + draw (mới)
  - `tests/test_interactive_loop.py` — 5 test vòng lặp với FakeEngine (mới)

## 🐞 Vấn đề gặp phải & cách xử lý
- Test treo ~30 phút (timeout): phím `r` trong test match điều kiện lặp lại vô hạn (đếm `process` không đổi sau reset) → vòng r/reset/start. Sửa: bấm r dựa trên số lần `start` + cờ `pressed_r`, và mọi script phím bảo đảm có đường thoát.
- `selector.bind(frame)` trong run_interactive reset bbox đã pre-arm trong test → đổi cách test: arm ngay trong display callback lần select đầu (giống hành vi người dùng kéo chuột sau khi window lên).
- `count(("start",))` = 0 vì entry là tuple 2 phần tử `("start", bbox)` → viết `_count_by_name()`.
- WSL không GUI/camera → đường --display để kiểm thủ công; toàn bộ logic kiểm tự động được.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Kiểm thủ công --display trên máy có màn hình + webcam: kéo chuột, r, q/ESC.
- [ ] Ticket 06 Visualizer HUD đầy đủ (mask + ô bao + quỹ đạo + FPS/latency + ghi video).
- [ ] Ticket 07 MetricsLogger (CSV + summary); Ticket 08 cấu hình YAML + README.

## 📚 Tài liệu tham khảo
- `/implement`, `/tdd`; spec + ticket 05; ADR-0001 (single object), ADR-0002 (số liệu trung thực).
- Docs OpenCV mouse callback: `cv2.setMouseCallback`, `cv2.EVENT_LBUTTONDOWN/MOUSEMOVE/LBUTTONUP`.