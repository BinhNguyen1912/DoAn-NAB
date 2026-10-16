# Ngày 16-10-2026 — Tách spec thành 8 tickets (/to-tickets)

## 🎯 Mục tiêu
- Tách spec `.scratch/camera-ai-realtime/spec.md` thành các ticket tracer-bullet dọc, khai báo blocking edges, sẵn sàng cho `/implement`.

## 📥 Input
- Spec `camera-ai-realtime` (vừa tạo), ADR-0001/0002, yêu cầu thầy (docx), cấu hình tracker local (`docs/agents/issue-tracker.md`).

## 🔨 Công việc đã thực hiện
1. Dự thảo 8 lát cắt dọc (đề xuất người dùng duyệt — user OK):
   - 01 Fixture giả lập + pytest (prefactor, không blocker)
   - 02 TrackerEngine streaming — nhân kỹ thuật (block 01)
   - 03 VideoSource webcam/RTSP/file (không blocker — song song 01–02)
   - 04 Pipeline live end-to-end (block 02+03) — lát "sống" đầu tiên
   - 05 PromptSelector kéo chuột + phím r (block 04)
   - 06 Visualizer HUD + quỹ đạo + ghi video (block 05)
   - 07 MetricsLogger CSV/summary/độ ổn định (block 01 — song song mảng UI)
   - 08 Headless + config YAML + README (block 04+07) — đóng gói
2. Đăng 8 ticket qua tracker op `create-ticket` vào `.scratch/camera-ai-realtime/issues/` (Status: ready-for-agent, blocking edges đúng).

## 📤 Output / Kết quả
- 8 file ticket: `01`–`08` (mỗi ticket: What to build / Blocked by / Status / acceptance criteria).
- Frontier hiện tại: **01 và 03** có thể bắt đầu ngay (không blocker).
- Log này (mới).

## 🐞 Vấn đề gặp phải & cách xử lý
- Filename sinh từ title tiếng Việt bị bỏ dấu (`01-fixture-gi-l-p-...`) — chỉ ảnh hưởng thẩm mỹ, nội dung file giữ nguyên tiếng Việt.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] `/implement` ticket 01 (blockers-first), rồi lần lượt theo frontier.
- [ ] `/code-review` đóng gói theo nhịp từng ticket.

## 📚 Tài liệu tham khảo
- `/to-tickets` (mattpocock-skills), spec `camera-ai-realtime`.