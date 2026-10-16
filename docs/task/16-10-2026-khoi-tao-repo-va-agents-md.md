# Ngày 16-10-2026 — Khởi tạo repo và thiết lập AGENTS.md

## 🎯 Mục tiêu
- Đọc và nghiên cứu đề cương đề tài (`docs/DoAnCameraAI.docx`).
- Thiết lập `AGENTS.md` — quy ước làm việc bắt buộc cho mọi phiên code sau này (đặc biệt là quy tắc ghi log công việc theo ngày phục vụ viết báo cáo).

## 📥 Input
- File đề cương đề tài: `docs/DoAnCameraAI.docx` (đề tài: Hệ thống Camera AI bám bắt đối tượng thời gian thực — Image Segmentation + Motion Memory + Temporal Propagation; tham khảo SAM 2 / SAMURAI / XMem).
- Yêu cầu từ người dùng: tạo `AGENTS.md`, quy định sau mỗi ngày code phải ghi log (input/output) vào `docs/task/`, tên file theo định dạng `DD-MM-YYYY-ten-cong-viec.md`.

## 🔨 Công việc đã thực hiện
1. Trích xuất và đọc toàn bộ nội dung `DoAnCameraAI.docx` (giải nén docx → parse `word/document.xml` bằng Python).
2. Phân tích yêu cầu đề tài: mục tiêu, lịch trình 14 buổi, yêu cầu sản phẩm cuối kỳ, định hướng kỹ thuật.
3. Tạo `AGENTS.md` tại thư mục gốc repo, bao gồm:
   - Tổng quan dự án và yêu cầu sản phẩm cuối kỳ.
   - **Quy tắc bắt buộc ghi log ngày** vào `docs/task/` kèm template chuẩn (Mục tiêu / Input / Công việc / Output / Vấn đề / Next steps / Tài liệu tham khảo).
   - Cấu trúc thư mục repo dự kiến (`src/`, `scripts/`, `configs/`, `models/`, `data/`...).
   - Quy ước code Python và quy trình làm việc mỗi phiên.
4. Tạo thư mục `docs/task/` và file log đầu tiên (file này).

## 📤 Output / Kết quả
- Nắm rõ phạm vi đề tài, sẵn sàng nhận repo tham khảo để lập kế hoạch triển khai.
- File thay đổi:
  - `AGENTS.md` — quy ước làm việc cho agent (mới)
  - `docs/task/16-10-2026-khoi-tao-repo-va-agents-md.md` — log ngày hôm nay (mới)

## 🐞 Vấn đề gặp phải & cách xử lý
- File `.docx` không đọc trực tiếp được → xử lý bằng cách giải nén zip và parse XML thủ công bằng Python (môi trường chưa có `pandoc`/`python-docx`).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Nhận repo tham khảo từ người dùng (SAM 2 / SAMURAI / XMem hoặc repo baseline).
- [ ] Phân tích kiến trúc repo đó và lập kế hoạch triển khai chi tiết theo từng phase (tương ứng lịch trình 14 buổi).

## 📚 Tài liệu tham khảo
- `docs/DoAnCameraAI.docx` — đề cương đề tài.
- https://github.com/facebookresearch/sam2
- https://github.com/yangchris11/samurai
- https://github.com/hkchengrex/XMem
