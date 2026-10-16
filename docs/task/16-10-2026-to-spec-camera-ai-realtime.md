# Ngày 16-10-2026 — Viết spec Camera AI real-time (/to-spec)

## 🎯 Mục tiêu
- Chuyển toàn bộ bối cảnh (yêu cầu thầy + ADR-0001/0002 + benchmark + phỏng vấn) thành một spec triển khai có cấu trúc, đặt trong issue tracker cục bộ.

## 📥 Input
- Đề cương `docs/DoAnCameraAI.docx` (7 yêu cầu sản phẩm), ADR-0001/0002, `docs/research/03` (kiến trúc streaming), `docs/research/05` (0.2–0.7 FPS), `GLOSSARY.md`, quyết định phỏng vấn Round 1–2 (seams, UI, single object, ngôn ngữ).

## 🔨 Công việc đã thực hiện
1. Thống nhất với người dùng **2 seam kiểm tra**: `TrackerEngine` (trung tâm — fixture giả lập ô vuông di chuyển, đo IoU) và `VideoSource` (file-based test; RTSP/webcam test thủ công).
2. Viết spec theo template (Problem/Solution/User stories/Implementation/Testing/Out of scope).
3. Đăng spec vào tracker: `.scratch/camera-ai-realtime/spec.md` với nhãn `ready-for-agent` (dùng tracker op `create-spec`).
4. Sửa lỗi gõ trộn chữ Trung ("视频" → "video") trong User Story 1.

## 📤 Output / Kết quả
- `.scratch/camera-ai-realtime/spec.md` — spec đầy đủ: 5 module (VideoSource, TrackerEngine, PromptSelector+Visualizer, MetricsLogger, chế độ headless), 25 user stories, các quyết định triển khai (streaming per-frame theo SAMURAI issue #128, config YAML, single object, tiếng Việt comment/UI), quyết định test (fixture synthetic, pytest, test TrackerEngine slow), phạm vi loại bỏ (không tối ưu tốc độ theo ADR-0002).
- `.scratch/camera-ai-realtime/issues/` — thư mục trống chờ `/to-tickets`.

## 🐞 Vấn đề gặp phải & cách xử lý
- Lỗi gõ trộn chữ Trung trong story 1 → sửa bằng edit chính xác.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] `/to-tickets` — tách spec thành tickets tracer-bullet theo thứ tự phụ thuộc vào `.scratch/camera-ai-realtime/issues/`.
- [ ] `/implement` lần lượt từng ticket (blockers-first).

## 📚 Tài liệu tham khảo
- `/to-spec` (mattpocock-skills), `docs/agents/issue-tracker.md`.