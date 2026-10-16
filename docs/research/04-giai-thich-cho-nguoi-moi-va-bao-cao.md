# Giải thích cho người mới + tài liệu viết báo cáo

> Tài liệu này giải thích **bằng tiếng Việt đơn giản** mọi khái niệm kỹ thuật trong đồ án,
> đối chiếu **đúng yêu cầu của thầy**, và cho biết **chúng ta sẽ làm gì**.
> Dùng để: (1) bạn tự hiểu, (2) chép vào báo cáo với thầy.
> Ngày: 16-10-2026.

---

## 1. Bài toán bằng tiếng đời thường

Bạn có một cái webcam. Bạn **click/chọn 1 đối tượng** trên khung hình đầu (ví dụ: con chó, quả bóng, người).
Hệ thống sẽ **tự bám theo đối tượng đó qua từng khung hình video**, vẽ ra:
- **một cái "mặt nạ" bám sát hình dáng đối tượng** (không phải ô vuông, mà theo đúng rìa),
- **vị trí** của nó,
- **quỹ đạo** (đường đi) qua thời gian,
- và làm việc này **theo thời gian thực** (ngay khi camera quay, không phải quay xong mới xử lý).

Đặc biệt: khi đối tượng **bị che một phần, biến dạng, hoặc mất dấu rồi xuất hiện lại** → hệ thống vẫn phải bám được (đây là phần khó, và là lý do cần "bộ nhớ chuyển động").

---

## 2. Đối chiếu yêu cầu của thầy (trong `docs/DoAnCameraAI.docx`) — chúng ta làm gì

| # | Yêu cầu của thầy | Chúng ta làm gì | Đạt? |
|---|---|---|---|
| 1 | Thu nhận & xử lý video trực tiếp (Camera USB/IP) | Webcam laptop + hỗ trợ cam rời/cam điện thoại qua RTSP | ✅ |
| 2 | Cho phép người dùng lựa chọn đối tượng | Cửa sổ OpenCV, dùng chuột kéo vẽ ô bao quanh đối tượng ở frame đầu | ✅ |
| 3 | Phân đoạn & theo dõi theo Segmentation Mask | Dùng SAM 2 để tạo mặt nạ pixel-theo-pixel, theo dõi qua các frame | ✅ |
| 4 | Tích hợp Motion Memory + Temporal Propagation | Dùng SAMURAI (Kalman Filter + memory bank) — chính là 2 cơ chế này | ✅ |
| 5 | Hiển thị vị trí, vùng phân đoạn, quỹ đạo real-time | Vẽ mask + ô bao + đường quỹ đạo trên cửa sổ, cập nhật mỗi frame | ✅ |
| 6 | Đánh giá FPS, độ trễ, chất lượng phân đoạn, độ ổn định | Module đo FPS, latency ms/frame, IoU (độ khớp mask), vẽ biểu đồ | ✅ |
| 7 | Hoàn thiện mã nguồn, báo cáo, demo | Code + báo cáo + demo live | ✅ |

→ **Tất cả yêu cầu của thầy đều được đáp ứng.** Đóng góp sáng tạo của bạn = **tự tối ưu SAM 2/SAMURAI để chạy real-time trên laptop không có GPU NVIDIA** (phần này thầy sẽ đánh giá cao vì không dùng model sẵn).

---

## 3. Các khái niệm kỹ thuật — giải thích đơn giản

### 3.1 SAM 2 (Segment Anything Model 2)
- **Là gì**: Một mô hình AI của Meta (công ty Facebook) có khả năng "phân đoạn mọi thứ". Cho nó 1 ảnh + 1 điểm/ô chỉ định → nó vẽ ra **mặt nạ (mask) bám đúng rìa đối tượng**.
- **Phiên bản dùng**: SAM 2.1, bản nhỏ nhất `tiny` (nhanh nhất, nhẹ nhất) vì máy bạn yếu.
- **Vì sao dùng**: Đây là mô hình nền. Đề tài thầy cho phép tham khảo SAM 2/SAMURAI/XMem.

### 3.2 SAMURAI
- **Là gì**: Một bản "nâng cấp" của SAM 2 cho bài toán bám bắt đối tượng (của tác giả Yang Chris, 2024). Nó **không train thêm**, chỉ thêm 2 cơ chế thông minh:
  1. **Kalman Filter** để đoán đối tượng đi đâu.
  2. **Memory bank selection** để chọn frame "tốt" lưu vào bộ nhớ.
- **Vì sao dùng**: Đúng 2 trụ "Motion Memory" + "Temporal Propagation" mà thầy yêu cầu. Repo đã chạy được offline trên máy bạn.

### 3.3 Segmentation Mask (mặt nạ phân đoạn)
- **Là gì**: Ảnh nhị phân đen/trắng cùng kích thước video, pixel trắng = thuộc đối tượng, pixel đen = nền. Khác với "ô vuông bbox" chỉ khoanh vùng.
- **Vì sao dùng**: Yêu cầu 3 của thầy.

### 3.4 Motion Memory (bộ nhớ chuyển động)
- **Là gì**: Hệ thống nhớ lại đối tượng đã ở đâu, di chuyển thế nào, để khi bị che/mất dấu vẫn đoán được vị trí. Trong SAMURAI = **Kalman Filter + memory bank**.
- **Kalman Filter**: một công thức toán học dự đoán vị trí tiếp theo dựa trên vận tốc quá khứ (giống đoán quả bóng đang bay sẽ tới đâu).
- **Memory bank**: bộ nhớ các frame quá khứ, SAM 2 dùng để "nhìn lại" khi xử lý frame mới.

### 3.5 Temporal Propagation (lan truyền theo thời gian)
- **Là gì**: Đưa thông tin mask từ frame cũ sang frame mới (không phát hiện lại từ đầu mỗi frame). SAM 2 có sẵn cơ chế này qua "memory attention".
- **Khác biệt quan trọng**: đây là "theo dõi + phân đoạn", không phải "phát hiện lại mỗi frame" (đó chỉ là detection).

### 3.6 Real-time / FPS
- **FPS** = Frames Per Second = số khung hình xử lý được mỗi giây. Phim mượt ~24–30 FPS.
- **Real-time** (theo đồ án ta chốt): **≥ 10 FPS** hiển thị trực tiếp (mục tiêu 15–24). Tức là xử lý kịp khi camera quay, không phải quay xong mới chạy.
- **Latency** = độ trễ, tính bằng mili-giây/frame (ms/frame). FPS càng cao, latency càng thấp.

### 3.7 GPU / CUDA / Intel Iris Xe / OpenVINO — phần dễ nhầm nhất
- **GPU** = card đồ họa, tính toán song song nhanh hơn CPU. Mô hình AI chạy nhanh hơn nhiều trên GPU.
- **CUDA** = hệ thống của **NVIDIA** để chạy tính toán trên GPU NVIDIA. SAM 2 mặc định cần CUDA.
- **Máy bạn**: có GPU tích hợp **Intel Iris Xe** (không phải NVIDIA) → **không có CUDA**.
- **OpenVINO** = bộ công cụ của **Intel** để chạy AI trên chip Intel (kể cả GPU Intel Iris Xe). **Không cần CUDA.** → Đây là đường mình dùng để tận dụng GPU Intel của máy bạn.
- **Vì sao quan trọng**: không có NVIDIA không phải hết cách. Mình chuyển SAM 2 sang dạng OpenVINO để chạy trên Intel Iris Xe. Chậm hơn NVIDIA, nhưng vẫn chạy được — và tự làm được việc này chính là đóng góp của bạn.

### 3.8 ONNX / INT8 quantization (nén model)
- **ONNX** = định dạng model chung (như file .mp4 cho video). Chuyển SAM 2 sang ONNX để chạy bằng các công cụ tối ưu hơn PyTorch.
- **INT8 quantization** = "nén" model từ số thực (32-bit) sang số nguyên (8-bit) → model nhẹ hơn, chạy nhanh hơn ~2–4×, chất lượng giảm không đáng kể. Áp dụng cho phần encoder (phần nặng nhất).

### 3.9 Prototype benchmark (bước sắp làm)
- **Là gì**: Một chương trình nhỏ dùng thử, **chỉ để đo** SAM 2.1 tiny chạy trên máy bạn đạt bao nhiêu FPS, bằng 3 cách:
  1. PyTorch CPU (baseline, chậm nhất).
  2. ONNX Runtime CPU (+ INT8).
  3. OpenVINO trên Intel Iris Xe (GPU Intel).
- **Mục đích**: biết có đạt ≥ 10 FPS không trước khi xây cả hệ thống. Nếu đạt → tiến. Nếu không → bật thêm các tối ưu (giảm resolution, skip-frame...).
- **Không lãng phí**: code đo này dùng lại được cho module đánh giá (yêu cầu 6 của thầy).

### 3.10 Decoupled tracking / skip-frame (cách giảm tải máy, giữ real-time)
- **Ý tưởng**: không cần chạy SAM 2 nặng ở **mọi** frame. Chạy nó **cứ 3–5 frame một lần** để "neo lại" mask đúng; các frame giữa dùng một bộ theo dõi nhẹ (Kalman + khớp mẫu) để dời mask mượt.
- **Lợi ích**: máy nhẹ hơn nhiều, hiển thị vẫn mượt real-time. Đây vừa là cách giảm tải, vừa là đóng góp kỹ thuật cho báo cáo.

---

## 4. Chúng ta sẽ làm gì — theo từng bước (bằng lời đơn giản)

1. **Đo thử (prototype)**: xem SAM 2 tiny trên máy bạn chạy được bao nhiêu FPS, bằng mấy cách. → biết có hy vọng real-time không.
2. **Tùy kết quả đo**, bật các tối ưu đến khi đạt ≥ 10 FPS: OpenVINO trên Intel Iris Xe, nén INT8, giảm phân giải, skip-frame.
3. **Xây pipeline live**: webcam → chọn đối tượng bằng chuột → SAM 2/SAMURAI bám theo → vẽ mask + ô + quỹ đạo.
4. **Module đánh giá**: đo FPS, latency, độ khớp mask (IoU), độ ổn định.
5. **Báo cáo + demo live**.

---

## 5. Bạn cần biết gì để báo cáo thầy (tóm tắt)
- Đề tài dùng **SAM 2 + SAMURAI** (thầy cho phép).
- 3 trụ cột: **Phân đoạn ảnh (SAM 2)** + **Bộ nhớ chuyển động (Kalman + memory bank của SAMURAI)** + **Lan truyền thời gian (memory attention của SAM 2)**.
- Đóng góp riêng: **tự tối ưu để chạy real-time trên laptop Intel không có GPU NVIDIA**, bằng OpenVINO/ONNX/INT8/skip-frame.
- Demo: **webcam live**, chọn đối tượng bằng chuột, hiển thị mask + quỹ đạo real-time.
- Đánh giá: FPS, độ trễ, IoU, độ ổn định.

> Mọi thuật ngữ trong mục 3 có thể chép vào phần "Cơ sở lý thuyết" của báo cáo.