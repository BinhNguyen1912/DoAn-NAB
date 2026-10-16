# Ngày 16-10-2026 — Phân tích repo SAMURAI

## 🎯 Mục tiêu
- Nghiên cứu repo tham khảo chính của đề tài: https://github.com/yangchris11/samurai
- Phân tích kiến trúc, cơ chế kỹ thuật và xác định khoảng trống cần tự triển khai cho đề tài Camera AI real-time.

## 📥 Input
- Link repo SAMURAI do người dùng cung cấp.
- Yêu cầu đề tài trong `docs/DoAnCameraAI.docx` (Segmentation + Motion Memory + Temporal Propagation, real-time camera).

## 🔨 Công việc đã thực hiện
1. Đọc README repo (qua web fetch): mô tả, cách cài đặt, cách chạy demo, FAQs.
2. Duyệt toàn bộ cây thư mục repo qua GitHub API → xác định các file cốt lõi.
3. Tải và đọc code các file quan trọng:
   - `scripts/demo.py` (122 dòng): pipeline demo với bbox prompt từ file txt.
   - `scripts/main_inference.py`: pipeline benchmark VOT (LaSOT...).
   - `sam2/sam2/utils/kalman_filter.py` (324 dòng): Kalman Filter 8-dim state `(x,y,a,h + vận tốc)`, constant velocity model.
   - `sam2/sam2/modeling/sam2_base.py` (1061 dòng): logic `samurai_mode` — motion-aware mask selection (weighted score = 0.25·kf_iou + 0.75·sam_iou) và motion-aware memory bank selection (lọc frame vào memory theo 3 ngưỡng iou/obj/kf score).
   - `sam2/sam2/sam2_video_predictor.py` (1176 dòng): predictor lưu `best_iou_score`, `kf_score` vào inference state.
   - Config `sam2.1_hiera_b+.yaml`: hyperparameters SAMURAI (`stable_frames_threshold=15`, `stable_ious_threshold=0.3`, `kf_score_weight=0.25`, `memory_bank_*_threshold`, `num_maskmem=7`).
4. Đối chiếu với yêu cầu đề tài → lập bảng "có sẵn vs phải tự xây dựng".
5. Viết tài liệu phân tích chi tiết: `docs/research/01-phan-tich-repo-samurai.md`.

## 📤 Output / Kết quả
- Hiểu rõ kiến trúc SAMURAI: **SAM 2.1 (zero-shot) + Kalman Filter + memory bank selection**; không cần train.
- Xác định được **khoảng trống chính so với đề tài**: SAMURAI chỉ chạy offline (load cả video), chưa hỗ trợ streaming/webcam (FAQ #2 trong repo) → đây chính là phần đóng góp ta phải xây: pipeline camera real-time, UI chọn đối tượng, vẽ quỹ đạo, đo FPS/độ trễ.
- Đề xuất sơ bộ kiến trúc hệ thống (sơ đồ khối trong file phân tích).
- File thay đổi:
  - `docs/research/01-phan-tich-repo-samurai.md` — tài liệu phân tích repo (mới)
  - `docs/task/16-10-2026-phan-tich-repo-samurai.md` — log ngày hôm nay (mới)

## 🐞 Vấn đề gặp phải & cách xử lý
- Trang GitHub tree view bị chặn fetch (HTTP 404 anti-bot) → chuyển sang dùng **GitHub API** (`api.github.com/repos/.../git/trees`) và **raw.githubusercontent.com** để lấy cấu trúc và nội dung file.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Hỏi người dùng về phần cứng (GPU available? VRAM?) để chọn checkpoint (tiny/small/base_plus).
- [ ] Lập kế hoạch triển khai chi tiết theo từng phase (tương ứng lịch trình 14 buổi): clone/setup repo → chạy demo offline → xây streaming pipeline → UI → metrics.
- [ ] (Dự kiến phase sau) Nghiên cứu cách adapt `init_state`/`propagate_in_video` cho streaming (tham khảo facebookresearch/sam2 issue #90, #388).

## 📚 Tài liệu tham khảo
- https://github.com/yangchris11/samurai
- https://arxiv.org/abs/2411.11922 (paper SAMURAI)
- https://github.com/facebookresearch/sam2 (SAM 2 gốc)
