# Ngày 16-10-2026 — Implement ticket 07: MetricsLogger (CSV + summary + độ ổn định)

## 🎯 Mục tiêu
- Ticket 07: module hàm thuần nhận bản ghi mỗi frame → CSV từng dòng + summary (mean/p95 latency, FPS hiệu dụng, tỷ lệ mất dấu) — phục vụ mục "Đánh giá hiệu năng" (yêu cầu 6 của thầy, story 13–16, 23).

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/07-...md` (claimed sau khi resolve 01/02/04/05/06).
- Spec: "MetricsLogger — log(record), summary() → CSV + JSON; thuần chức năng"; story 16 độ ổn định (mask rỗng/điểm thấp); story 23 toạ độ tâm trong CSV.
- Code sẵn có: `TrackingResult`, 2 vòng lặp trong `live_pipeline`.

## 🔨 Công việc đã thực hiện
1. TDD (RED → GREEN): `src/metrics_logger.py` — `FrameRecord` (frame_idx, latency_ms, score, center, lost=None) + `is_lost()` (ưu tiên cờ explicit; thiếu thì suy: tâm None hoặc score ≤ LOST_SCORE_THRESHOLD=0.0 — đúng ngữ nghĩa object_score_logits của SAM 2) + `MetricsLogger` (log/write_csv/summary/write_summary_json).
2. CSV cột `frame_idx,latency_ms,score,center_x,center_y,lost` — tâm trống khi mất dấu (không vẽ điểm rác vào biểu đồ quỹ đạo); score format `%.6g` (0.9 → "0.9", logit thô 21.6925 → "21.6925").
3. Summary: total_frames, mean/p95 latency (nội suy tuyến tính), effective_fps=1000/mean, mean_score, lost_count/lost_ratio; summary rỗng trả 0 an toàn; JSON dump UTF-8.
4. Tích hợp: `run_tracking(..., metrics=None)` và `run_interactive(..., metrics=None)` — `_record_from(TrackingResult)` tự sinh record (mất dấu = mask rỗng — cờ explicit, đúng hiện tượng thật). CLI: `--metrics-csv`, `--metrics-summary` + in dòng tổng hợp `[metrics] … mất dấu n/N (x%) | score tb=…`.
5. Kiểm tra: **62/62 passed** (~1:43 — gồm 14 test mới MetricsLogger). Smoke CLI thật trên fixture 5 frame: CSV đủ 5 dòng, tâm (79,80)→(95,87) bám đúng quỹ đạo ô vuông (80+4i, 80+2i lệch lerp 1px do MJPG), lost=0/5; summary JSON mean=3441 ms, p95=4123 ms, FPS≈0.29.

## 📤 Output / Kết quả
- Ticket 07: **4/4 tiêu chí ticked** (CSV đúng cột, lost_ratio, tâm vẽ quỹ đạo được, test nhanh không model).
- File thay đổi:
  - `src/metrics_logger.py` — FrameRecord + is_lost + MetricsLogger (mới)
  - `src/live_pipeline.py` — metrics=None vào 2 vòng lặp + _record_from (sửa)
  - `tools/run_live.py` — --metrics-csv/--metrics-summary + _make_metrics/_finish_metrics (sửa)
  - `tests/test_metrics_logger.py` — 14 test thuần + 2 test tích hợp FakeEngine (mới)
  - Cùng phiên: resolve ticket 01/02/04 (đã xong từ trước) để mở khoá tracker; ticket 06 visualizer (log riêng).

## 🐞 Vấn đề gặp phải & cách xử lý
- Format score `:.3f` cho "0.900" != test kỳ vọng "0.9" (vi phạm RED của chính mình) → dùng `%.6g`: vừa gọn vừa giữ độ chính xác logit.
- Test `is_lost` để score 0.05 với ngưỡng 0.0 — sai logic (0.05 > 0 không mất dấu) → đổi thành score âm; thêm test explicit `lost=False` chứng minh ưu tiên.
- Đếm `on_result` trong test tích hợp interactive bị lệch (đếm cả start) → sửa biên ≥4.
- Smoke thật cho thấy score là logit thô (7–21), không phải xác suất 0–1 — ghi chú trung thực: ngưỡng 0 vẫn hợp lệ theo SAM 2, báo cáo cần ghi rõ thang đo.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Ticket 08: config YAML (dồn cờ CLI vào file) + README + hướng dẫn cài đặt tái tạo.
- [ ] Kiểm thủ công --display/--record trên máy có GUI + camera (các ticket 04–06).
- [ ] Sau 08: vẽ biểu đồ quỹ đạo/latency từ CSV MetricsLogger phục vụ báo cáo.

## 📚 Tài liệu tham khảo
- `/implement`, `/tdd`; spec + ticket 07; ADR-0002; python `csv`/`json`, `np.percentile` (nội suy tuyến tính mặc định).