# Hệ thống Camera AI bám bắt đối tượng real-time (SAMURAI streaming)

## Problem Statement

Sinh viên đang thực hiện đề tài "Hệ thống Camera AI bám bắt đối tượng theo thời gian thực" nhưng mới chỉ có:
- repo SAMURAI chạy được **offline** (load cả video từ đĩa) và các tài liệu phân tích/benchmark,
- số liệu đo cho biết SAM 2.1 tiny trên laptop CPU chỉ đạt ~0.2–0.7 FPS (ADR-0002 đã chốt: demo live CPU, báo cáo trung thực).

Còn thiếu toàn bộ **hệ thống sản phẩm**: chưa thu nhận video trực tiếp từ camera, người dùng chưa thể chọn đối tượng cần bám, chưa hiển thị mask/quỹ đạo real-time, chưa có module đo FPS/độ trễ/chất lượng phân đoạn/độ ổn định — tức 7 yêu cầu sản phẩm cuối kỳ trong đề cương mới đáp ứng được 1 phần.

## Solution

Xây các thành phần còn thiếu quanh lõi SAMURAI có sẵn:
1. **VideoSource** — một interface thống nhất cho 3 nguồn: webcam laptop (USB index), camera ngoài/điện thoại qua RTSP, và video file (dùng cho demo lặp lại được + test).
2. **TrackerEngine** — bọc SAM 2 video predictor (config SAMURAI) thành chế độ **streaming từng frame** (theo hướng `async_loading_frames` — nghiên cứu `docs/research/03`), nhận bbox prompt từ người dùng, trả mask + bbox + điểm tin cậy mỗi frame.
3. **PromptSelector + Visualizer (HUD)** — cửa sổ OpenCV: kéo chuột vẽ ô chọn đối tượng ở frame đầu; overlay mask, ô bao, **quỹ đạo** (đường tâm qua thời gian), text FPS/latency.
4. **MetricsLogger** — ghi mỗi frame: thời gian xử lý (ms), FPS trượt, điểm tin cậy mask, vị trí tâm; xuất CSV + thống kê tổng hợp cho báo cáo.
5. **Chế độ headless** (không UI) — chạy trên một video file, xuất video kết quả: dùng được trên Colab GPU để làm video minh họa 15–25 FPS cho báo cáo (ADR-0002).

Demo live trên CPU với số FPS trung thực; mọi việc nặng offline (nén model, đánh giá) bỏ ra ngoài phạm vi này (đã có benchmark `tools/benchmark_sam2_realtime.py`).

## User Stories

1. Là người trình bày đồ án, tôi muốn hệ thống nhận **video trực tiếp** từ **webcam laptop** qua một lệnh chạy đơn giản, để demo trực tiếp trước hội đồng.
2. Là người trình bày, tôi muốn dùng được **camera USB rời** thay webcam tích hợp (chọn camera theo số thứ tự), để demo với cam tốt hơn.
3. Là người trình bày, tôi muốn nhận video từ **điện thoại/cam IP qua RTSP**, để đáp ứng yêu cầu "Camera USB/IP" của đề cương và quay cảnh từ xa.
4. Là người trình bày, tôi muốn chạy trên một **video file** cho trước, để demo lặp lại được khi phòng thi không có camera hoặc wifi.
5. Là người trình bày, tôi muốn **kéo chuột vẽ ô** quanh đối tượng ở frame đầu tiên để chọn đối tượng cần bám, để thao tác trực quan đúng yêu cầu "lựa chọn đối tượng".
6. Là người trình bày, tôi muốn thấy **mặt nạ phân đoạn (mask)** phủ đúng hình dáng đối tượng theo từng frame, để chứng minh phần Segmentation Mask (yêu cầu 3 của thầy).
7. Là người trình bày, tôi muốn thấy **ô bao (bbox)** quanh đối tượng theo từng frame, để thấy rõ vị trí đối tượng.
8. Là người trình bày, tôi muốn thấy **quỹ đạo di chuyển** (đường nối tâm đối tượng qua thời gian) vẽ trên khung hình, để đáp ứng yêu cầu "quỹ đạo theo thời gian thực" (yêu cầu 5).
9. Là người trình bày, tôi muốn HUD hiển thị **FPS và độ trễ ms/frame** cập nhật liên tục, để minh bạch hiệu năng khi demo (phù hợp ADR-0002: báo cáo trung thực).
10. Là người trình bày, tôi muốn hệ thống **tiếp tục bám khi đối tượng bị che khuất một phần hoặc biến dạng** (nhờ Motion Memory + Temporal Propagation của SAMURAI), để đúng yêu cầu 4 của đề cương.
11. Là người trình bày, tôi muốn ghi **video demo** ra file khi chạy live, để ném vào slide báo cáo và trình chiếu dự phòng nếu camera hỏng.
12. Là người trình bày, tôi muốn nhấn một phím để **chọn lại đối tượng khác** mà không cần tắt chương trình, để demo nhiều đối tượng liên tiếp trong 1 phiên.
13. Là người đánh giá, tôi muốn mỗi frame được **ghi lại độ trễ xử lý, FPS, điểm tin cậy mask**, để có số liệu trung thực cho mục "Đánh giá hiệu năng" (yêu cầu 6).
14. Là người đánh giá, tôi muốn các chỉ số được xuất ra **file CSV + bảng thống kê tổng hợp** (trung bình/p95), để vẽ biểu đồ cho báo cáo.
15. Là người đánh giá, tôi muốn một **bộ test tự động** với ảnh giả lập (ô vuông di chuyển, quỹ đạo biết trước) đo được **IoU** mask so với đáp án đúng, để đo "chất lượng phân đoạn" định lượng (yêu cầu 6).
16. Là người đánh giá, tôi muốn có chỉ số **độ ổn định bám bắt** (phát hiện frame mask rỗng/điểm tin cậy thấp), để đáp ứng đủ 4 đại lượng đánh giá trong yêu cầu 6.
17. Là người phát triển, tôi muốn **TrackerEngine** là một module sâu với interface nhỏ (feed frame → nhận mask/bbox/điểm), để không đụng vào UI khi đổi checkpoint/tham số.
18. Là người phát triển, tôi muốn **tham số hóa qua file cấu hình** (đường dẫn checkpoint, model config, độ phân giải, nguồn video mặc định), để đổi model/máy mà không sửa code.
19. Là người phát triển, tôi muốn có **chế độ headless** (không cửa sổ UI) chạy trên video file và xuất video kết quả, để chạy được trên Colab GPU làm video minh họa tốc độ thật của GPU (ADR-0002).
20. Là người phát triển, tôi muốn có **hướng dẫn cài đặt tái tạo được từ commit mới** (cách clone SAMURAI, cài env conda, tải checkpoint), để Colab hoặc máy khác chạy theo được.
21. Là người đánh giá, tôi muốn chạy **bộ test trên chính laptop CPU** trong ít phút, để kiểm chứng mọi thay đổi mà không cần GPU (đủ theo ADR-0002).
22. Là người trình bày, tôi muốn **README** hướng dẫn chạy + giải thích ngắn kiến trúc bằng tiếng Việt, để thầy/collab người khác tự chạy được.
23. Là người phát triển, tôi muốn mỗi frame ghi lại được **tọa độ tâm đối tượng** (trong CSV), để vẽ biểu đồ quỹ đạo cho báo cáo.
24. Là người trình bày, tôi muốn các **nhãn hiển thị trên HUD bằng tiếng Việt**, để hội đồng và người xem hiểu ngay.
25. Là người phát triển, tôi muốn module đo (`MetricsLogger`) là **hàm thuần** nhận bản ghi, để test độc lập không cần chạy model.

## Implementation Decisions

- **Backbone: SAM 2.1 tiny với config SAMURAI** (ADR-0001) — checkpoint `sam2.1_hiera_tiny`, CPU PyTorch. Không dùng EdgeTAM/EfficientTAM (GVHD muốn đóng góp tự xây). Không cam kết ≥10 FPS on-device (ADR-0002).
- **Streaming adaptation**: adapt `init_state`/`propagate_in_video` của SAM 2 theo hướng nghiên cứu (SAMURAI issue #128 — `async_loading_frames`): predictor giữ inference_state, mỗi frame mới đến từ VideoSource được nạp và propagate một bước. Đây là quyết định kỹ thuật trung tâm của TrackerEngine.
- **Module & interface** (5 module, seam như đã thống nhất với người dùng):
  - `VideoSource` — interface trả frame kế tiếp + thuộc tính (FPS nguồn, kích thước); 3 adapter: webcam index, RTSP URL, file path.
  - `TrackerEngine` — `select(bbox)`, `process(frame) → (mask, bbox, score)`; đóng gói Kalman + memory-bank selection có sẵn của SAMURAI (không viết lại).
  - `PromptSelector` — mouse callback OpenCV: vẽ ô lúc kéo chuột, xác nhận ô vào TrackerEngine.
  - `Visualizer` — nhận frame + (mask, bbox, score, lịch sử tâm) → ảnh HUD; giữ deque quỹ đạo tối đa N điểm.
  - `MetricsLogger` — `log(record)`, `summary() → CSV + JSON`; thuần chức năng.
- **Cấu hình**: file YAML trong thư mục `configs/` (checkpoint path, model cfg, nguồn mặc định, số điểm quỹ đạo tối đa, bật/tắt ghi video).
- **Chú thích/docstring tiếng Việt, identifier tiếng Anh** (Q6, Round 1).
- **Single object** (ADR-0001): một TrackerEngine = một đối tượng; chọn đối tượng mới = khởi tạo lại engine.
- **Điểm tin cậy**: dùng `best_iou_score`/object score SAM 2 xuất sẵn làm proxy chất lượng mask khi live (không có ground truth ngoài synthetic fixture) — đủ cho chỉ số độ ổn định + báo cáo trung thực.
- **Khởi tạo lại đối tượng**: phím r — dừng track hiện tại, quay về chế độ chọn ô trên frame hiện tại.
- **Ghi video**: ghi trực tiếp các frame đã overlay ra mp4 bằng OpenCV VideoWriter khi bật trong config.
- **Cài đặt SAMURAI không vendor trong Git** (đã loại trong `.gitignore`): README ghi lệnh clone + `pip install -e .` + script tải checkpoint; conda env `samurai` dùng cho máy hiện tại.

## Testing Decisions

- **Chỉ test hành vi bên ngoài**, không test chi tiết nội bộ (không đụng vào hàm riêng của SAM 2 predictor).
- **Hai seam đã thống nhất với người dùng**:
  1. `VideoSource`: test bằng video file — assert đúng số frame, kích thước, dtype. Adapter RTSP/webcam là lớp mỏng, test thủ công (không unit test — phụ thuộc thiết bị).
  2. `TrackerEngine`: test bằng **fixture giả lập sinh bằng code** (ô vuông màu đặc di chuyển trên nền màu, quỹ đạo tuyến tính biết trước — không commit dữ liệu nặng):
     - frame 0: chọn ô bao đúng vị trí → mask không rỗng, IoU với hình vuông cao.
     - các frame mẫu sau: bbox trả về IoU so với vị trí thật của ô vuông > ngưỡng quy định (ví dụ 0.5) → chứng minh Temporal Propagation bám theo quỹ đạo.
     - frame bị che (chen một cản giả lập): mask có thể rỗng/điểm thấp — assert hệ thống trả điểm tin cậy thấp thay vì crash.
  - `MetricsLogger`: cho N bản ghi giả → assert CSV đúng cột, `summary()` tính đúng trung bình/p95.
  - `Visualizer`/`PromptSelector`: smoke test (chạy không crash, ảnh đầu ra đúng kích thước).
- **Prior art**: chưa có test nào trong repo (bộ test đầu tiên) — pytest, đặt trong thư mục `tests/` chuẩn; fixture generator là một module nhỏ dùng chung.
- Test chạy được trên CPU máy hiện tại; test TrackerEngine được đánh dấu "slow" (mỗi lần build model ~20–60s) để tách khỏi test nhanh.

## Out of Scope

- Đạt ≥ 10 FPS on-device / mọi tối ưu tốc độ: skip-frame, decoupled tracker, đa luồng, decord, TensorRT (ADR-0002 đã bỏ ngưỡng; làm lại sau nếu báo cáo cần).
- Multi-object tracking hơn 1 đối tượng cùng lúc.
- Đổi backbone sang EdgeTAM/EfficientTAM/XMem (ADR-0001 loại; nếu sau này đổi sẽ là ADR mới).
- Tái nhận diện đối tượng sau khi mất dấu lâu (một phần xử lý tự nhiên của SAMURAI memory, nhưng không xây cơ chế riêng).
- Giao diện web/Gradio; chỉ dùng cửa sổ OpenCV.
- Colab notebook + các job offline (nén INT8, đánh giá dataset LaSOT...) — tách phase sau; phần này chỉ đảm bảo chế độ headless chạy được.
- Training/fine-tuning mô hình.
- Chế độ live-qua-Colab (stream frame lên mây) — tùy chọn sau này.

## Further Notes

- Số liệu nền đã có: full pipeline CPU ≈ 5.4s/frame ≈ 0.2 FPS (`docs/research/05`) — demo live là slideshow có chủ đích; video GPU minh họa trên Colab.
- Đối chiếu yêu cầu thầy (7 mục) nằm ở `docs/research/04` — mỗi ticket sau này nên nêu được yêu cầu nào nó phục vụ.
- Thuật ngữ dùng nhất quán theo `GLOSSARY.md` (Segmentation Mask, Motion Memory, Temporal Propagation, Motion-Aware Memory, Real-time theo ADR-0002, Backbone).
- ADR liên quan: `0001` (backbone SAM 2/SAMURAI + tự tối ưu), `0002` (giữ laptop CPU, Colab offline).
- Sau khi spec được tách tickets (`/to-tickets`), tickets sẽ nằm `.scratch/camera-ai-realtime/issues/` theo cấu hình `docs/agents/issue-tracker.md`.
