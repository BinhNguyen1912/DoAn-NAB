# Kết quả prototype benchmark SAM 2.1 tiny trên máy sinh viên (16-10-2026)

> Trả lời câu hỏi ADR-0001 yêu cầu: "SAM 2.1 tiny có đạt ≥ 10 FPS (real-time) trên laptop
> không GPU NVIDIA không?" — **đã đo thật**, không lý thuyết.
> Script: `tools/benchmark_sam2_realtime.py` (env conda `samurai` — Python 3.11, torch 2.14.1+cpu).
> Máy: MSI Modern 14 B11MOU — i7-1195G7 (4 nhân/8 luồng), 16GB, Intel Iris Xe (không CUDA).

---

## 1. Số liệu đo được

### Pipeline video thật (PyTorch CPU, 15 frame demo con chó)
| Thành phần | Thời gian |
|---|---|
| init_state (load ảnh, KHÔNG encode) | 2.3s / 15 frame |
| propagate trung bình | **~5,225 ms/frame** (chậm dần 2.5s → 6.5s — dấu hiệu thermal throttling CPU) |
| **Tổng streaming/frame** | **~5.4s → ≈ 0.2 FPS** |

### Image Encoder riêng (chiếm phần lớn chi phí mỗi frame), độ phân giải 1024×1024
| Backend | ms/frame | FPS |
|---|---|---|
| PyTorch CPU, 4 threads | 1,771 | 0.6 |
| PyTorch CPU, 8 threads | 1,625 | 0.6 |
| ONNX Runtime CPU fp32, 4 threads | 1,705 | 0.6 |
| ONNX Runtime CPU **INT8** (dynamic quantize) | 1,376 | 0.7 |
| OpenVINO CPU (fp32) | 1,613 | 0.6 |
| OpenVINO **GPU (Iris Xe)** | — | **không khả dụng trong WSL** (chỉ thấy device `CPU`) |

Models đã export (dùng lại được): `models/bench/sam2.1_tiny_encoder_fp32.onnx`,
`models/bench/sam2.1_tiny_encoder_int8.onnx`, `models/bench/sam2.1_tiny_encoder_ir.xml`.

## 2. Phát hiện quan trọng (vượt giả định ban đầu)
1. **`init_state` KHÔNG encode trước** — encode diễn ra mỗi frame trong propagate →
   chi phí streaming/frame = encoder + memory attention + decoder (~5.2s).
2. **Encoder ~1.6–1.8s/frame trên CPU, mọi backend gần như như nhau** — nén INT8 chỉ nhanh ~19%.
   CPU 4 nhân của máy là nút cổ chai cứng, không vượt được bằng runtime nào.
3. **OpenVINO không thấy GPU trong WSL** — để dùng Iris Xe phải chạy Python trên Windows
   (bản thân đó cũng chỉ giải quyết được 1 phần, ước tính lạc quan ~2–3 FPS).
4. Số benchmark browser (2.19s trên chip Intel iGPU **16 nhân**) khớp thang đo này.

## 3. Kết luận kĩ thuật
**SAM 2.1 tiny trên laptop này ≈ 0.2–0.7 FPS — không thể đạt real-time (≥10 FPS) với mọi
tối ưu runtime (ONNX/INT8/OpenVINO).** Khoảng cách ~14–50×. Vượt khả năng của quantize/resolution/skip-frame.

Đối chiếu phương án dự phòng: XMem ≈ 33 FPS trên GTX 1080Ti (GPU rời) → ước tính trên CPU
máy này ~0.5–1.5 FPS — vẫn không đạt. Hiểu đúng: không có VOS có temporal propagation nào
chạy real-time ≥10 FPS trên CPU 4 nhân ultrabook — lý do EdgeTAM/EfficientTAM mới ra đời
(chúng đạt 10–16 FPS trên iPhone nhờ NPU/GPU của điện thoại).

## 4. Trạng thái ADR-0001
Rủi ro mà ADR-0001 đã cảnh báo **hiện thực hóa**. Bộ ràng buộc hiện tại
(**SAM 2 backbone + chỉ laptop này + real-time + webcam live**) **vô nghiệm** theo số liệu đo
— cần người dùng + GVHD chọn nhượng bộ một ràng buộc. (Quyết định mới sẽ ghi ADR-0002.)

## 5. Các đường đi khả thi cho cuộc trao đổi với GVHD
| Đường | Sự đánh đổi | Kết quả real-time |
|---|---|---|
| **C. Mượn/dùng máy có GPU NVIDIA** (lab/PC bàn, ≥6GB VRAM) | đổi phần cứng | ✅ SAM 2 tiny ~15–25 FPS — **đáp ứng đủ ràng buộc** |
| **B. Giữ máy này, trình bày kiến trúc real-time + số đo CPU trung thực** | rời "real-time" khỏi demo | ⚠️ 0.2 FPS live (demo như slideshow) |
| **A. Xử lý video đã quay trên GPU (Colab), demo live trên máy chỉ chạy UI** | rời "live inference cục bộ" | video-GPU đạt; live-UI không đạt |
| **D. Đổi backbone sang model on-device (EdgeTAM/EfficientTAM)** | (Q7 trước đó: bị GVHD chê "dùng sẵn") | ⚠️ chưa đo; iPhone 10–16 FPS, laptop CPU → cần đo |

## 6. Việc cho người dùng
1. Mang **mục 3 + 5** (số liệu đo) đi trao đổi với GVHD — hỏi **bộ ràng buộc nào được phép nhượng bộ**.
2. Nếu được dùng GPU NVIDIA → tiếp tục SAM 2/SAMURAI đúng ADR-0001, demo trên máy đó.
3. Nếu phải giữ máy này → chọn A/B/D; khi đó ADR-0002 sẽ ghi lại quyết định mới.