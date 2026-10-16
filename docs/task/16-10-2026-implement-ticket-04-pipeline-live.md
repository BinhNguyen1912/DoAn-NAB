# Ngày 16-10-2026 — Implement ticket 04: Pipeline live end-to-end (/tdd)

## 🎯 Mục tiêu
- Lát dọc "hệ thống sống" đầu tiên: một lệnh nối VideoSource → TrackerEngine → overlay, in số liệu trung thực.

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/04-...md` (claimed — 02, 03 đã xong), engine từ ticket 02, adapter nguồn từ ticket 03.

## 🔨 Công việc đã thực hiện
1. TDD chu kỳ 1 (RED → GREEN): `run_tracking()` — vòng lặp chạy qua video fixture (6 frame): đúng số frame, đúng thứ tự, overlay thay đổi pixel so với frame gốc, summary đủ nghĩa (mean/p95/FPS hiệu dụng). Thiết kế: hiển thị tiêm qua callback `on_frame(img, res)` (trả False = dừng) → test headless, window chỉ là 1 cách cắm.
2. `src/live_pipeline.py`: `run_tracking` + `draw_overlay_minimal` (mask mờ addWeighted + ô bao + nhãn `f<i> ms`) + `SessionSummary` (mean/p95/FPS hiệu dụng — tính từ latency trung bình, ghi chú trung thực ADR-0002).
3. CLI `tools/run_live.py`: `--source {số|rtsp://|file}` + `--bbox`/`--bbox-file` (mặc định ô trung tâm; quy ước `data/<tên>_bbox_frame0.txt` tự tìm) + `--display` (q/ESC thoát) / headless; Ctrl+C thoát sạch (finally + KeyboardInterrupt).
4. Smoke test CLI headless trên video fixture 5 frame: bbox bám đúng quỹ đạo (60,60→76,68 = 60+4i, 60+2i), mean=3192 ms, FPS hiệu dụng ≈ 0.31.
5. Full suite: **14/14 green** (1:45). Review 2 trục: 1 finding nhỏ (code chết `_display_frame` trùng logic) đã dọn khi viết lại; 1 judgement call ("peek" nguồn 2 lần để suy bbox mặc định) — chấp nhận.

## 📤 Output / Kết quả
- Ticket 04: **3/3 tiêu chí ticked** (đường file chứng minh tự động; webcam/display chờ thủ công trên máy có màn hình/camera).
- File thay đổi:
  - `src/live_pipeline.py` — vòng lặp + overlay + summary (mới)
  - `tests/test_live_pipeline.py` — 1 test slow (mới)
  - `tools/run_live.py` — CLI 1 lệnh chạy pipeline (mới)

## 🐞 Vấn đề gặp phải & cách xử lý
- WSL không GUI/camera → đường `--display`/webcam để tick thủ công; headless test được đầy đủ.
- Mở nguồn 2 lần (peek frame đầu) để định bbox mặc định — judgement call, giữ đơn giản.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Ticket 05 PromptSelector (kéo chuột + phím r) — mở khoá sau 04.
- [ ] 06 HUD đầy đủ + quỹ đạo + ghi video; 07 MetricsLogger; 08 Headless+README.

## 📚 Tài liệu tham khảo
- `/implement`, `/tdd`; spec + ticket 04; ADR-0002.