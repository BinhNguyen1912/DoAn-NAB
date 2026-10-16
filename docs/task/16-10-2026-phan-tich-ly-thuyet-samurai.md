# Ngày 16-10-2026 — Phân tích lý thuyết SAM 2 & SAMURAI

## 🎯 Mục tiêu
- Giải thích lý thuyết nền tảng (SAM → SAM 2 → Kalman Filter → SAMURAI) để nắm bản chất trước khi triển khai, đồng thời chuẩn bị sẵn tài liệu cho chương "Cơ sở lý thuyết" của báo cáo.

## 📥 Input
- Yêu cầu từ người dùng: phân tích lý thuyết các cơ chế của SAMURAI (segmentation, motion memory, temporal propagation).
- Kết quả phân tích code repo SAMURAI (xem log `16-10-2026-phan-tich-repo-samurai.md`).

## 🔨 Công việc đã thực hiện
1. Hệ thống hóa lý thuyết thành tài liệu `docs/research/02-co-so-ly-thuyet-sam2-samurai.md`, gồm:
   - Đặt bài toán semi-supervised VOS, so sánh Detection / Tracking / VOS, 5 thách thức chính (che khuất, biến dạng, distractors, ánh sáng, drift).
   - Kiến trúc SAM (ảnh tĩnh) và giới hạn không có khái niệm thời gian.
   - Kiến trúc SAM 2: Hiera encoder, Memory Attention, Memory Encoder, Memory Bank, object pointer/score — và giải thích Temporal Propagation = vòng lặp "dự đoán mask → encode vào memory → condition frame sau".
   - Lý thuyết Kalman Filter: predict/update equations, state 8 chiều `(x,y,a,h,vx,vy,va,vh)`, constant velocity model, vai trò motion prior.
   - 2 đóng góp của SAMURAI: motion-aware mask selection (weighted score 0.25·kf + 0.75·sam) kèm state machine stable/unstable (ngưỡng 15 frame, IoU 0.3), và motion-aware memory bank selection (3 ngưỡng iou/obj/kf).
   - Pseudocode toàn bộ vòng lặp tracking.
   - Ánh xạ 3 trụ cột đề tài ↔ hiện thực trong hệ thống.
   - Các đại lượng đánh giá (IoU, FPS, latency, AUC...).

## 📤 Output / Kết quả
- Nắm được bản chất lý thuyết: SAMURAI không train thêm gì, "trí tuệ" nằm ở chiến lược **chọn mask bằng motion prior (KF)** và **lọc memory bank theo độ tin cậy**.
- File thay đổi:
  - `docs/research/02-co-so-ly-thuyet-sam2-samurai.md` — tài liệu lý thuyết cho báo cáo (mới)
  - `docs/task/16-10-2026-phan-tich-ly-thuyet-samurai.md` — log hôm nay (mới)

## 🐞 Vấn đề gặp phải & cách xử lý
- Không có vấn đề kỹ thuật; nội dung được tổng hợp từ code đã đọc + paper.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Lập kế hoạch triển khai chi tiết theo phase (chờ người dùng xác nhận phần cứng GPU/CPU và môi trường Windows/WSL).
- [ ] Clone repo SAMURAI, cài môi trường, chạy demo offline trước.

## 📚 Tài liệu tham khảo
- arXiv:2411.11922 (SAMURAI), arXiv:2408.00714 (SAM 2), ICCV 2023 (SAM)
- DeepSORT (ICIP 2017) — nguồn gốc Kalman Filter cho tracking
