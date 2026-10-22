# Ngày 22-10-2026 — Tái nhận diện khuôn mặt: mất dấu → đóng băng → tự bám lại đúng người (buổi 9)

> Ticket 09 · ADR-0003 · Đáp ứng buổi 6 ("duy trì định danh đối tượng qua các khung hình") và
> buổi 9 ("xử lý trường hợp mất dấu và tái nhận diện đối tượng") của đề cương.

## 🎯 Mục tiêu
- Sửa đúng lỗi demo 2 người: chọn mặt A → A rời khung → hệ thống báo MẤT DẤU rồi **bám sang mặt B**.
- Yêu cầu mới: (1) mất dấu thì **ĐÓNG BĂNG**, không bám sang người khác; (2) A quay lại thì **tự bám lại đúng A**.

## 📥 Input
- Phản hồi người dùng sau buổi test thật (A = sinh viên, B = bạn): "chọn mặt A, A rời cam thì báo mất dấu, rồi nó tự focus vào mặt B".
- Bảng 14 buổi của đề cương (buổi 6 + buổi 9 yêu cầu tái nhận diện).
- `.scratch/camera-ai-realtime/spec.md` cũ xếp tái nhận diện **ngoài phạm vi** → mâu thuẫn đề cương.
- `docs/research/01` dòng 137 và `docs/research/02` dòng 242 (repo tự ghi cần cơ chế tái nhận diện).

## 🔨 Công việc đã thực hiện

1. **Đối chiếu 14 buổi với repo** → xác định gap duy nhất là buổi 9 (mất dấu + tái nhận diện);
   `src/identity_guard.py` chỉ **cảnh báo** (ngưỡng 25% đường chéo khung), không dừng, không nhận lại.
2. **Chọn tín hiệu nhận dạng**: kiểm tra `opencv-python` 5.0.0 trên máy → có
   `cv2.FaceDetectorYN_create` (YuNet) + `cv2.FaceRecognizerSF_create` (SFace) + `alignCrop` + `feature`
   ⇒ **không thêm dependency Python**, chỉ 2 file ONNX.
3. **Tải model** vào `models/face/` (gitignored): `face_detection_yunet_2023mar.onnx` (232 KB),
   `face_recognition_sface_2021dec.onnx` (38,7 MB) từ OpenCV Zoo.
4. **Đo để chọn thiết kế** (bằng chứng ở ADR-0003):
   - Cùng 1 người, 8 frame liên tiếp, cosine so frame 0: **1,000 · 0,561 · 0,723 · 0,638 · 0,538 · 0,199 · 0,428 · 0,283**
     ⇒ mặt nhỏ 42×62 px + di chuyển làm cosine tụt dưới ngưỡng tài liệu 0,363 ⇒ **bắt buộc** lưu
     **nhiều mẫu tham chiếu + lấy max cosine** + cổng chất lượng.
   - Nhiễu ngẫu nhiên vs nhiễu: cosine **0,83** ⇒ embedding vùng không phải mặt là vô nghĩa ⇒ phải có cổng.
5. **Sửa spec** (`.scratch/camera-ai-realtime/spec.md`): thêm user story 26–27, thêm Implementation
   Decision về máy trạng thái + ngưỡng + metrics; chuyển "tái nhận diện" từ *Out of Scope* sang
   *In Scope*, chỉ để ngoài phạm vi trường hợp **không có tín hiệu khuôn mặt**.
6. **Viết ADR-0003** (`docs/adr/0003-tai-nhan-dien-khuon-mat-yunet-sface.md`): quyết định, lý do,
   bằng chứng đo, 4 phương án đã xét (tự viết histogram / YuNet+SFace / insightface / chỉ đóng băng),
   hậu quả & rủi ro.
7. **Tạo + claim ticket 09** trong `.scratch/camera-ai-realtime/issues/`.
8. **TDD — viết test trước, rồi implement**:
   - `tests/test_reid.py` (16 test): `cosine`, `best_match`, `face_quality_ok`, `pick_face_near`,
     máy trạng thái với engine/embedder giả (freeze, reacquire, không khớp, reset).
   - `src/reid.py`: hàm thuần + `FaceEmbedder` (bọc YuNet+SFace) + `ReIdSession`
     (`tracking → lost → reacquiring → tracking`), `LostResult` duck-type `TrackingResult`.
   - `tests/test_metrics_logger.py`: +3 test cho cột `state`/`reid_score`/`reacquired` và
     summary `reacquiring_frames`/`reacquired_count`; cập nhật 2 test cũ theo schema mới.
   - `src/metrics_logger.py`: mở rộng `FrameRecord` + `CSV_HEADER` + summary.
   - `tests/test_visualizer.py`: +2 smoke test; `src/visualizer.py`: hiện `DANG TIM LAI A... (khop 0.xx)`.
   - `tests/test_config.py`: +4 test; `src/config.py`: thêm 8 key `reid_*`/`lost_after_frames` + validate kiểu.
   - `tests/test_live_pipeline.py`: +1 test **tích hợp** khẳng định sau khi mất dấu **không còn lệnh
     `engine.process`** (đóng băng thật ở mức pipeline) và metrics có cột trạng thái.
   - `src/live_pipeline.py`: `run_tracking`/`run_interactive` nhận `reid_session`; `_record_from`/
     `_annotate` truyền state; phím `r` reset cả session.
   - `tools/run_live.py`: `--reid`, `--reid-threshold`, `--lost-after-frames`, `--reid-min-face-px`,
     `--reid-ref-max`; tự **tắt `--reanchor-every`** khi bật re-ID (re-anchor chọn lại ô cũ sẽ phá
     trạng thái mất dấu); cảnh báo `--smooth` chưa hỗ trợ re-ID.
   - `configs/default.yaml`: `reid_enabled: true` + các tham số kèm giải thích.
9. **Cập nhật tài liệu**: `docs/giai-thich-do-an.md` mục 14 (thêm 14.3 cơ chế mới + viết lại câu trả
   lời hội đồng), `docs/team-contribution.md` (thêm dòng 13 + YuNet/SFace vào mục "không tự viết"),
   `README.md` (bước 6 tải model khuôn mặt + mục hướng dẫn tái nhận diện).

## 📤 Output / Kết quả
- **Kiểm thử**: `ruff check .` → All checks passed; `pytest -m "not slow"` → **210 passed**;
  full `pytest` → **215 passed in 133,43 s** (4 FutureWarning là upstream torch trong sam2).
- **Kiểm chứng model thật** trên frame 720p có người: YuNet detect bbox 42×62 px, score 0,82;
  SFace → embedding (128,); `best_match` cùng người = 0,538.
- **Kiểm chứng end-to-end qua pipeline thật** (SAM 2 + YuNet/SFace, chuỗi frame
  `mặt → màn đen → màn đen → mặt`, `--image-size 384`):

  | frame | state | lost | reid_score | reacquired |
  |---|---|---|---|---|
  | 0 | tracking | 0 | – | 0 |
  | 1 | tracking | 1 | -1 | 0 |
  | 2 | **lost** | 1 | -1 | 0 |
  | 3 | **tracking** | 0 | **0,560** | **1** |

  ⇒ đóng băng đúng (frame 2 không lan truyền) và **nhận lại đúng người** khi A quay lại.
  Tốc độ khi bật re-ID: mean **292 ms/frame** ≈ **3,4 FPS** (CPU, image_size 384).
- Sửa thêm: sau khi nhận lại, `engine.start` reset `frame_idx` → session gán lại `frame_idx`
  liên tục để CSV/biểu đồ đơn điệu tăng (trước đó CSV có `0` hai lần).
- Thêm lệnh tắt **`./run reid`** — **SAU ĐÓ ĐÃ GỘP LẠI** (xem mục dưới), không còn lệnh `reid` riêng.

## Cập nhật: GỘP về 1 LỆNH (theo phản hồi "sao nhiều lệnh thế")
- **Ghép re-ID vào chế độ hiển thị MƯỢT**: `InferenceWorker` trong `src/smooth_display.py` giờ nhận
  `reid_session` và dùng máy trạng thái thay vì gọi `engine.start/process` trực tiếp; thêm
  `worker.reid_status()` để vòng hiển thị lấy `state/reid_score/reacquired` → HUD + metrics.
  `run_smooth_display(..., reid_session=...)` + `tools/run_live.py` truyền thẳng session vào
  (bỏ thông báo "--smooth chưa hỗ trợ re-ID").
- **`./run demo` = MỘT lệnh làm hết**: `scripts/demo_webcam.sh` thêm `--reid` → mượt + tái nhận diện
  + ghi mp4/CSV/JSON. `view`/`video`/`fast` cũng thêm `--reid`; `fast` bỏ `--reanchor-every`
  (vì re-anchor tự tắt khi bật re-ID). Bỏ hẳn lệnh `./run reid` và cảnh báo `--smooth`
  trong `docs/cheatsheet-lenh.md` + `README.md`.
- Test thêm: `tests/test_smooth_display.py::TestWorkerVoiReId` (worker dùng session + báo trạng thái).
- **Kiểm chứng nhánh mượt + re-ID bằng model thật**: `run_smooth_display` với
  `PromptSelector` + `TrackerEngine.build_default(image_size=384)` + `FaceEmbedder` chạy 4 lần
  suy luận, không lỗi, mode chuyển `select → track`, state cuối `tracking`.
- Gates cuối: `ruff check .` → passed; full `pytest` → **216 passed in 120,25 s**.
- Hành vi mới: bật `--reid` (mặc định đã bật trong YAML) → mất dấu 2 frame liên tiếp là **đóng băng**;
  HUD hiện "DANG TIM LAI A... (khop 0.xx)"; CSV có `state`, `reid_score`, `reacquired`.
- File thay đổi:
  - `src/reid.py` — MỚI: hàm thuần + `FaceEmbedder` + `ReIdSession`
  - `src/live_pipeline.py` — nhận `reid_session`, ghi/ hiển thị trạng thái
  - `src/metrics_logger.py` — cột `state`/`reid_score`/`reacquired` + summary
  - `src/visualizer.py` — hiện trạng thái đang tìm lại
  - `src/config.py`, `configs/default.yaml` — 8 key cấu hình re-ID
  - `tools/run_live.py` — CLI `--reid*`, tự tắt re-anchor
  - `tests/test_reid.py` — MỚI (16 test); `tests/test_metrics_logger.py`, `tests/test_visualizer.py`,
    `tests/test_config.py`, `tests/test_live_pipeline.py` — test bổ sung
  - `docs/adr/0003-*.md` — MỚI; `docs/giai-thich-do-an.md`, `docs/team-contribution.md`, `README.md`
  - `.scratch/camera-ai-realtime/spec.md`, `issues/09-*.md`

## 🐞 Vấn đề gặp phải & cách xử lý
- **Ngưỡng tài liệu 0,363 không dùng được máy móc**: đo thật cùng 1 người có frame chỉ 0,199 →
  nếu chỉ lưu 1 embedding mốc thì re-ID trượt. Xử lý: lưu `reid_ref_max` mẫu + lấy max cosine;
   và ghi rõ ngưỡng phải hiệu chỉnh trên video thật.
- **Mặt nhỏ bị cổng chất lượng loại**: với frame benchmark, mặt 42×62 px và nhiều frame có score
  < 0,8 nên `FaceEmbedder.detect` trả rỗng (đúng thiết kế) → demo phải đứng gần camera (mặt ≥ 40 px).
- **Test tự viết sai kích thước mask** (40×40 trên frame 240×320) → sửa test dùng mask cùng kích thước.
- **2 test CSV cũ assert đúng nội dung dòng** → cập nhật theo 3 cột mới (schema đổi có chủ đích theo ticket).
- **OpenCV 5 in cảnh báo** `Targets are not supported by the new graph engine` khi tạo model — vô hại.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Đo trên video 2 người thật** (còn lại 1/9 criteria của ticket 09): tỉ lệ nhận lại đúng /
      nhận nhầm theo từng ngưỡng, chọn ngưỡng cuối, ghi số vào log + báo cáo. Cần footage A-B thật.
- [ ] Cân nhắc hiệu chỉnh `--reid-threshold` theo camera demo thật (mặc định đang 0,363).
- [ ] (Tuỳ chọn) hỗ trợ re-ID trong chế độ `--smooth` (hiện đã cảnh báo là chưa hỗ trợ).
- [ ] (Tuỳ chọn) nếu ngưỡng không đủ tốt: xét nâng lên insightface/ArcFace (phương án C của ADR-0003).

## 📚 Tài liệu tham khảo
- `docs/adr/0003-tai-nhan-dien-khuon-mat-yunet-sface.md`
- OpenCV Zoo: YuNet (`face_detection_yunet_2023mar`) + SFace (`face_recognition_sface_2021dec`)
- SFace paper: *Sigmoid-Constrained Hypersphere Loss for Robust Face Recognition*
- `docs/giai-thich-do-an.md` mục 14; `docs/research/01` (dòng 137), `docs/research/02` (dòng 242)
