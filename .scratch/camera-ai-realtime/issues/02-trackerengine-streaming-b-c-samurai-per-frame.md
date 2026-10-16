# 2: TrackerEngine streaming (bọc SAMURAI per-frame)

**What to build:** Bọc SAM 2 video predictor (config SAMURAI tiny, CPU) thành module interface nhỏ: select(bbox) ở frame đầu, feed từng frame mới → nhận (mask, bbox, score, thời gian ms). Thực hiện adapt streaming per-frame theo hướng nghiên cứu docs/research/03 (SAMURAI issue #128 — async_loading_frames): giữ inference_state, mỗi frame mới được nạp và propagate một bước. Kèm script demo đọc frames từ thư mục, in kết quả từng frame. Giữ nguyên Kalman + memory-bank selection của SAMURAI (không viết lại).

**Blocked by:** 01

**Status:** resolved

- [x] Trên fixture giả lập: chọn bbox frame 0 → mỗi frame sau trả mask không rỗng, bbox IoU với vị trí thật ≥ 0.5 ở các frame mẫu
- [x] Frame bị che: trả mask rỗng/điểm tin cậy thấp mà không crash
- [x] Test TrackerEngine đánh dấu slow (build model) tách khỏi test nhanh, chạy được trên CPU laptop
- [x] Kết quả process có kèm thời gian xử lý (ms) để metrics dùng được

## Answer

Hoàn thành: TrackerEngine streaming per-frame (init frame 0 + nạp frame mới vào _StreamingImages + propagate 1 bước), mask/bbox/score/ms; test slow với fixture — IoU ≥ 0.5, che khuất không crash. Log docs/task/16-10-2026-implement-ticket-02-tracker-engine.md.
