# ADR-0003: Tái nhận diện đối tượng bằng khuôn mặt (YuNet + SFace) + đóng băng khi mất dấu

## Bối cảnh

- Đề cương đồ án yêu cầu rõ:
  - **Buổi 6** — "…duy trì **định danh đối tượng** qua các khung hình."
  - **Buổi 9** — "Kết hợp Image Segmentation, Motion Memory và Temporal Propagation; **xử lý trường hợp mất dấu và tái nhận diện đối tượng**."
- Hiện trạng trước ADR này: `src/identity_guard.py` chỉ **cảnh báo** khi tâm ô bao nhảy > 25% đường chéo khung. Hệ thống **không dừng** và **không nhận lại** người cũ.
- Hệ quả đã quan sát khi demo 2 người: chọn mặt A → A rời khung → báo MẤT DẤU → bộ nhớ SAM 2 **bám sang mặt B** (giải thích + hướng xử lý: `docs/giai-thich-do-an.md` mục 14).
- Spec cũ (`.scratch/camera-ai-realtime/spec.md`) xếp "tái nhận diện" **ngoài phạm vi** ⇒ **mâu thuẫn với đề cương**. ADR này sửa lại phạm vi đó.
- SAM 2/SAMURAI chỉ lan truyền mask theo *hình dáng/màu sắc* của vùng đã chọn; **không có khái niệm danh tính** ⇒ không thể tự biết "đây là A hay B". Muốn "quay lại thì bám lại đúng tôi" **bắt buộc** phải có tín hiệu nhận dạng.

## Quyết định

1. **Tín hiệu nhận dạng = khuôn mặt**, dùng **model có sẵn của OpenCV** (không thêm dependency Python):
   - phát hiện mặt: `cv2.FaceDetectorYN_create` + `face_detection_yunet_2023mar.onnx` (232 KB);
   - trích đặc trưng: `cv2.FaceRecognizerSF_create` + `face_recognition_sface_2021dec.onnx` (38,7 MB) → embedding 128-D, so bằng `FR_COSINE`.
   - 2 file đặt trong `models/face/` (**`models/` đã gitignored**); đường dẫn khai báo trong `configs/default.yaml`.
2. **Máy trạng thái 3 pha** thay cho hành vi "bám mãi":
   - `TRACKING` → mask rỗng ≥ `LOST_AFTER_FRAMES` → `LOST`;
   - `LOST` = **đóng băng**: **ngừng gọi `engine.process()`** ⇒ bộ nhớ SAM 2 không có cơ hội nhảy sang người khác (đây chính là cơ chế "không bám sang B");
   - `REACQUIRING` = mỗi frame detect + embed + so cosine với **tập embedding tham chiếu của A**; khớp ≥ ngưỡng → `engine.start(frame, bbox_mặt)` → về `TRACKING`.
3. **Tập tham chiếu nhiều mẫu + lấy max**: trong lúc `TRACKING`, khi phát hiện mặt **đủ lớn + đủ tin cậy** thì lưu embedding vào deque (`REID_REF_MAX`); khi so khớp lấy **cosine lớn nhất trên toàn tập** (xem bằng chứng đo bên dưới — so với 1 mẫu duy nhất sẽ trượt).
4. **Ngưỡng là tham số phải hiệu chỉnh**, không giả định: khởi điểm 0,363 (khuyến nghị tài liệu OpenCV cho `FR_COSINE`), nhưng phải đo trên video demo và ghi số vào báo cáo.

## Lý do

- **Không thêm dependency**: đã kiểm chứng `opencv-python` (5.0.0 trên máy này) có `FaceDetectorYN_create` / `FaceRecognizerSF_create` / `alignCrop` / `feature` / `match`.
- **Cùng triết lý ADR-0001**: dùng model có sẵn, đóng góp của đồ án nằm ở hệ thống + ngưỡng + đánh giá, **không huấn luyện lại**. Điều này đã được ghi ở `docs/team-contribution.md` và trả lời được hội đồng.
- **Có cơ sở học thuật để trích dẫn**: SFace (Sigmoid-Constrained Hypersphere Loss, benchmark LFW) — trả lời được câu "sao biết đúng người?" tốt hơn nhiều so với "em tự so histogram màu".
- **Nhẹ, chạy CPU**: detect + embed chỉ chạy ở pha `REACQUIRING` (khi đã mất dấu) nên **không ảnh hưởng FPS lúc đang bám**.

## Bằng chứng đo (máy hiện tại, 22-10-2026)

| Kiểm chứng | Kết quả |
|---|---|
| Load 2 model | OK; `feature(112×112)` → shape `(1, 128)`, `float32`; `alignCrop` có |
| Frame 720p có người thật | YuNet detect 1 mặt, bbox **42×62 px**, score **0,82** |
| Cùng 1 người, 8 frame liên tiếp, cosine so frame 0 | **1,000 · 0,561 · 0,723 · 0,638 · 0,538 · 0,199 · 0,428 · 0,283** |
| Nhiễu ngẫu nhiên vs nhiễu khác | cosine **0,83** (⇒ embedding của vùng **không phải mặt** là vô nghĩa) |
| **Pipeline thật** (SAM 2 + YuNet/SFace, chuỗi frame: mặt → màn đen → màn đen → mặt) | `tracking` → `tracking`(lost=1) → **`lost`** → **`tracking` + `reid_score=0,560` + `reacquired=1`** — tức đã đóng băng đúng và nhận lại đúng người |
| Tốc độ khi bật re-ID (CPU, image_size 384) | mean **292 ms/frame** ≈ **3,4 FPS** (chỉ detect+embed ở pha tìm lại, không ảnh hưởng lúc đang bám) |

**Diễn giải (quan trọng cho thiết kế):**

- Cùng một người mà cosine tụt xuống **0,199** — **thấp hơn ngưỡng tài liệu 0,363** — vì mặt nhỏ (42×62 px) và đang di chuyển/nghiêng. Nếu chỉ lưu **1** embedding mốc thì re-ID sẽ **trượt**.
  ⇒ **bắt buộc** lưu nhiều mẫu tham chiếu + lấy **max cosine**, và chỉ lưu mẫu khi `score` cao + mặt đủ lớn.
- Cosine 0,83 giữa hai vùng **không phải mặt** cho thấy phải có **cổng chất lượng** (score ≥ `REID_MIN_DETECT_SCORE`, diện tích ≥ `REID_MIN_FACE_PX`), không được embed bừa.

## Các lựa chọn đã xét

| Phương án | Đánh giá |
|---|---|
| **A. Tự viết (histogram/mẫu màu/ NCC)** | Không cần model, nhưng **không phân biệt được A và B khi mặc giống nhau**, và không có cơ sở học thuật để bảo vệ. **Loại.** |
| **B. YuNet + SFace (OpenCV)** | **Chọn.** Đúng nghĩa re-ID khuôn mặt, không thêm dep, nhẹ CPU, có paper. |
| **C. insightface / ArcFace** | Chính xác hơn nhưng thêm `insightface` + `onnxruntime` + model nặng, chậm hơn. **Để dự phòng** nếu B không đạt trên video thật. |
| **D. Chỉ đóng băng khi mất dấu (không re-ID)** | Rẻ và chặn được "bám sang B", nhưng **không đáp ứng buổi 9**. Giữ làm mức tối thiểu (vẫn cần), không đủ một mình. |

## Hậu quả & rủi ro

- **Không nhận lại được** khi: quay lưng, che kín mặt, quá xa/mờ, ánh sáng ngược → không detect được mặt. Hệ thống ở `LOST` và hiện "đang tìm lại" — **trung thực, không đoán bừa** (đúng tinh thần ADR-0002).
- **False positive**: người khác rất giống A (cùng giới/tuổi/kính) có thể vượt ngưỡng. Giảm bằng ngưỡng cao hơn + đòi khớp liên tiếp N frame.
- **Ngưỡng phụ thuộc thiết bị**: camera/ánh sáng/khoảng cách khác nhau → phải đo lại trên video demo, ghi số liệu vào `docs/task/` và báo cáo.
- **Cảnh báo log của OpenCV 5**: `Targets are not supported by the new graph engine` khi tạo model — **vô hại**; có thể tắt nếu cần demo sạch.
- **Phạm vi**: chỉ 1 đối tượng mục tiêu; **multi-person re-ID vẫn ngoài phạm vi**; không xử lý khi không có tín hiệu khuôn mặt.
- **Không đổi** ADR-0001 (backbone vẫn SAM 2.1 tiny + config SAMURAI) và ADR-0002 (demo CPU trung thực).
