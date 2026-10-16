# Camera AI Real-time Object Tracking

Ngữ cảnh của đồ án: hệ thống camera AI bám bắt đối tượng theo thời gian thực, xây dựng trên SAM 2 / SAMURAI, chạy live trên laptop (CPU/Intel iGPU, không GPU NVIDIA).

## Ngôn ngữ

**Image Segmentation**:
Phân đoạn ảnh — gán nhãn từng pixel thuộc đối tượng để tạo mặt nạ (mask) bao phủ đối tượng. Trụ cột 1 của đề tài.
_Avoid_: object detection, bounding-box-only

**Motion Memory**:
Bộ nhớ chuyển động — cơ chế lưu lịch sử vị trí/đặc trưng đối tượng để hỗ trợ bám bắt khi che khuất/biến dạng. Trong SAMURAI = Kalman Filter (state 8 chiều, constant velocity) + memory-bank selection (lọc frame vào memory theo 3 ngưỡng iou/obj/kf).
_Avoid_: tracking history (quá chung), plain memory

**Temporal Propagation**:
Lan truyền theo thời gian — đưa mask/thông tin đối tượng từ frame quá khứ sang frame hiện tại qua memory attention của SAM 2. Trụ cột 3, khác với "tracking" thuần (chỉ bbox).
_Avoid_: tracking, frame-by-frame detection

**Motion-Aware Memory**:
Đóng góp riêng của SAMURAI: chọn mask theo weighted score (0.25·kf_iou + 0.75·sam_iou) + state machine stable/unstable + lọc memory bank. Đây là phần đồ án sẽ **tự port/tối ưu** trên backbone SAM 2.
_Avoid_: motion memory (dùng khi chỉ nói chung chung cả 2 cơ chế)

**Real-time (ngưỡng đồ án)**:
Hiển thị và xử lý mỗi frame kịp thời với người xem. Phần cứng CPU laptop không đạt (đo ~0.2 FPS) → theo ADR-0002 (GVHD chọn): demo live chạy CPU với **số đo trung thực**, chứng minh real-time-capable bằng kiến trúc + số FPS GPU tham chiếu từ Colab. Mục tiêu thiết kế vẫn là ≥ 10 FPS trên GPU.
_Avoid_: "real-time" không định lượng, offline-then-playback

**Backbone**:
Model VOS nền mà hệ thống dựa vào — trong đồ án này là **SAM 2.1 / SAMURAI** (không phải EdgeTAM/EfficientTAM). Phần tối ưu hóa backbone để đạt real-time là đóng góp sáng tạo.
_Avoid_: model (quá chung)