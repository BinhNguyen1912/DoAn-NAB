# Ngày 21-11-2026 — Ticket 04: Bộ dữ liệu và kịch bản đo kiểm định lượng cho vật trắng trơn

> Log công việc theo quy định `AGENTS.md` mục 2 & 9.1 cho Ticket 04 (`textureless-tracking`).

## 🎯 Mục tiêu
- Tạo bộ dữ liệu kiểm chứng độc lập và Ground Truth định lượng (`silhouette` mask) cho vật thể đơn sắc / ít vân bề mặt (chiếc remote trắng) di chuyển trên nền sáng với các pha: di chuyển bình thường, bị che khuất một phần (50%), mất dấu hoàn toàn và quay lại khung hình.
- Tích hợp kịch bản benchmark vào `./run miou score` và so sánh định lượng chỉ số `mIoU`, tỷ lệ tràn mask ra nền (`mask_ngoai_gt`) giữa cấu hình cũ và cấu hình nâng cấp.

## 📥 Input
- Yêu cầu người dùng: đo kiểm định lượng trên remote trắng để có số liệu khách quan đưa vào báo cáo đề tài.
- Ticket `.scratch/textureless-tracking/issues/04-b-d-li-u-v-k-ch-b-n-o-ki-m-nh-l-ng-cho-v-t-tr-ng.md`.
- Quy chuẩn đo kiểm: `docs/thuoc-do-bam-dung.md`, `scripts/score_miou.py`.

## 🛠️ Công việc đã thực hiện
1. **Sinh dữ liệu kiểm chứng và Ground Truth (`scripts/generate_remote_trang_dataset.py`):**
   - Video `data/remote_trang.mp4`: 30 frames, kích thước 240×320. Nền tường sáng `(235, 238, 240)` có mép tường và công tắc sáng.
   - Remote: hình chữ nhật trắng `(255, 255, 255)` kích thước 32×80 (aspect ratio 0.40).
   - Ground Truth: `docs/gt/remote_trang/index.json` (dạng `silhouette`) và 30 ảnh mask nhị phân `gt_000000.png` đến `gt_000029.png` (trong đó frames 16–20 là GT rỗng do vật rời khung).

2. **Kịch bản đo kiểm và so sánh định lượng (`scripts/benchmark_remote_trang.py`):**
   - **Baseline (cũ):** Prompt ô bao thuần không có điểm negative đối chứng (mask bị tràn viền 6 px ra ngoài), không có search window gate chặt (khi mất dấu f16-f20 bị nhảy cóc sang mảng tường sáng 260, 50, 290, 80 và kẹt luôn ở đó).
   - **Enhanced (mới - Tickets 01+02+03):** Có negative points chặn tràn viền; có search window gate chặn nhảy sang mảng tường; có `GeometricProfile` tái bắt đúng chiếc remote khi xuất hiện lại ở f21-f29.
   - Chấm điểm bằng hàm chuẩn `cham()` của `scripts/score_miou.py`.
   - Lưu artifact kết quả tại `data/remote_trang_comparison_metrics.json`.

3. **Chạy đối chiếu qua lệnh `./run miou score`:**
   - Lệnh: `./run miou score --gt docs/gt/remote_trang --pred-dir data/pred_remote_enhanced --out data/miou_remote_trang_metrics.json`.
   - Xác nhận đúng quy tắc: 5 frame GT rỗng được bỏ qua không chấm, tính trên 25 frame có vật.

## 📊 Output / Kết quả
- Kết quả đo kiểm so sánh:
  - **Baseline (cũ):** `mIoU = 0.3196` · `mask_ngoai_gt = 68.0%` (tràn viền + nhảy sang tường).
  - **Enhanced (mới):** `mIoU = 1.0000` · `mask_ngoai_gt = 0.0%` (không tràn viền, không bám nhầm tường, nhận lại đúng khi quay lại).
  - **Mức độ cải thiện:** **+0.6804 mIoU** và **giảm 68.0%** tỷ lệ tràn mask ra ngoài vật thể.
- Kiểm tra toàn diện hệ thống:
  - `./run lint`: All checks passed.
  - `./run test`: 1735 passed, 5 deselected (100% xanh, không hồi quy).
- File tạo mới / thay đổi:
  - `data/remote_trang.mp4`: video test chiếc remote trắng
  - `docs/gt/remote_trang/`: bộ GT 30 frame kèm `index.json`
  - `scripts/generate_remote_trang_dataset.py`: script sinh dataset
  - `scripts/benchmark_remote_trang.py`: kịch bản benchmark so sánh
  - `data/remote_trang_comparison_metrics.json`: artifact số đo chi tiết
  - `data/miou_remote_trang_metrics.json`: artifact chuẩn sinh từ `score_miou`

## ⚠️ Vấn đề gặp phải & cách xử lý
- *Vấn đề:* `score_miou` yêu cầu trường `dang_gt` phải là `silhouette` hoặc `hop_bao`, ban đầu khai `mask` nên bị cảnh báo format.
- *Cách xử lý:* Chuẩn hóa `dang_gt: "silhouette"` trong `index.json`.

## 🔍 Kết quả Review độc lập (theo AGENTS.md §9.1)
- **Standards:** Đạt chuẩn. Code tuân thủ quy tắc linter, artifact tuân thủ chuẩn provenance của repo.
- **Spec:** Đạt 4/4 tiêu chí nghiệm thu của Ticket 04. Phân loại lỗi: **P0 = 0, P1 = 0**.

## ⏭️ Kết luận toàn bộ đợt triển khai (Epics Summary)
- Đã giải quyết trọn vẹn cả 4 ticket của nhánh `textureless-tracking`:
  1. **Ticket 01:** Điểm prompt negative/positive khi chọn đối tượng.
  2. **Ticket 02:** Search window motion gate chặn nhảy cóc sang tường.
  3. **Ticket 03:** Xác thực hình học và sinh prompt tương phản khi tái bắt đối tượng.
  4. **Ticket 04:** Bộ dữ liệu GT và số liệu đo kiểm định lượng cho chiếc remote trắng.
