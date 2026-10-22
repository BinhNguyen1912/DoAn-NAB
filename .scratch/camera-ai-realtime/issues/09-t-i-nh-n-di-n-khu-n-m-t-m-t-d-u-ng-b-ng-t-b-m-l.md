# 9: Tái nhận diện khuôn mặt: mất dấu → đóng băng → tự bám lại đúng người (buổi 9)

**What to build:** Đáp ứng buổi 6 ("duy trì định danh qua các khung hình") và buổi 9 ("xử lý mất dấu và tái nhận diện đối tượng") của đề cương. Theo ADR-0003.

Hành vi hiện tại có lỗi: chọn mặt A → A rời khung → báo MẤT DẤU → bộ nhớ SAM 2 bám sang mặt B. Cần: (1) mất dấu thì ĐÓNG BĂNG, không bám sang người khác; (2) A quay lại thì TỰ bám lại đúng A.

Cơ chế: máy trạng thái TRACKING → LOST (ngừng gọi engine.process) → REACQUIRING (YuNet detect + SFace embed + cosine với tập embedding tham chiếu của A, lấy max) → TRACKING. Model ONNX đã tải ở models/face/ (gitignored). Không thêm dependency Python.

Điểm thiết kế bắt buộc từ bằng chứng đo (xem ADR-0003): cùng 1 người, mặt 42×62px, cosine so 1 mốc chỉ 0,20–0,72 ⇒ phải lưu NHIỀU mẫu tham chiếu + lấy max cosine, và chỉ lưu mẫu khi detect score cao + mặt đủ lớn.

**Blocked by:** None (can start immediately)

**Status:** claimed

- [x] `src/reid.py`: hàm thuần tách được khỏi OpenCV để test — `embed_faces(frame)` (detect+align+feature) và `best_match(ref_embs, emb)` trả cosine lớn nhất; ngưỡng/cổng chất lượng là tham số
- [x] Máy trạng thái TRACKING→LOST→REACQUIRING trong `live_pipeline.py`: khi LOST KHÔNG gọi `engine.process()` nữa (test mock khẳng định không có lệnh process sau khi mất dấu)
- [x] Khớp ngưỡng → gọi `engine.start(frame, bbox_mặt)` và quay lại TRACKING (test mock)
- [x] Không khớp → vẫn LOST, ghi `reid_score` = cosine cao nhất frame đó (test mock)
- [x] `MetricsLogger` thêm cột `state` + `reid_score`; summary có số frame lost / số lần nhận lại (test)
- [x] `Visualizer` hiện trạng thái đang tìm lại + điểm khớp (smoke test, ảnh đúng kích thước)
- [x] `src/config.py` + `configs/default.yaml`: `reid_enabled`, `reid_detector_model`, `reid_recognizer_model`, `reid_threshold`, `lost_after_frames`, `reid_min_face_px`, `reid_min_detect_score`, `reid_ref_max` (test config)
- [ ] Đo trên video 2 người: tỉ lệ nhận lại đúng / nhận nhầm, ngưỡng đã chọn, ghi số vào docs/task
- [x] `ruff check .` + `pytest -m "not slow"` + full `pytest` đều xanh
