# Nghiên cứu khả năng real-time trên laptop CPU/Intel iGPU (không NVIDIA)

> Phục vụ quyết định kiến trúc: đề tài yêu cầu **webcam live + real-time**, máy sinh viên là **MSI Modern 14 B11MOU** (i7-1195G7, 16GB RAM, **Intel Iris Xe — không CUDA**).
> Ngày: 16-10-2026.

---

## 1. Phần cứng máy sinh viên (quét thực tế)

| Thành phần | Giá trị |
|---|---|
| CPU | Intel Core i7-1195G7 (4 nhân / 8 luồng, 2.9GHz) — ultrabook |
| RAM | ~16 GB |
| GPU | Intel Iris Xe Graphics (tích hợp), **không NVIDIA, không CUDA** |

→ Không chạy được PyTorch CUDA. Chỉ CPU hoặc Intel iGPU (qua OpenVINO).

---

## 2. Số liệu benchmark SAM 2.1 trên chip Intel mobile + iGPU (gần nhất)

Nguồn: AnnotateIt local benchmark (`annotateit.ai/docs/sam2-benchmark/`), máy **Intel Core Ultra 9 386H** (mobile, iGPU, không GPU rời, 32GB) — **mạnh hơn** máy sinh viên (16 nhân vs 4 nhân).

Encoder mỗi frame (phần nặng nhất, chạy mỗi frame trong video tracking), độ phân giá 1024×1024:

| Model | Backend | Encoder/frame | ~FPS (chỉ encoder) |
|---|---|---|---|
| SAM 2.1 Tiny | iGPU (WebGPU) | 2.19 s | ~0.5 |
| SAM 2.1 Tiny | CPU multi-thread | 2.82 s | ~0.35 |
| SAM 2.1 Small | CPU multi-thread | 2.29 s | ~0.44 |
| MobileSAM | iGPU | 624 ms | ~1.6 |
| SAM 2.1 Large | iGPU | 28.10 s | ~0.04 |

Lưu ý: số trên là **browser WASM/WebGPU (ORT-web)** — chậm hơn native. Native OpenVINO trên Intel iGPU sẽ nhanh hơn, nhưng bậc lớn chứ không vượt bậc. Kết luận: **full SAM 2 video tracking trên máy này KHÔNG đạt real-time** (kỳ vọng native tối ưu ~2–8 FPS).

> MobileSAM nhanh nhưng là **SAM 1 (ảnh tĩnh), không temporal propagation** → mất 1 trụ đề tài.

---

## 3. Streaming webcam có làm được không?

Nguồn: SAMURAI issue #128 (`github.com/yangchris11/samurai/issues/128`).
- SAM 2/SAMURAI **CÓ THỂ** chạy trên stream (webcam `video_path=0`, hoặc `rtsp://<ip>` cho camera IP/điện thoại).
- Cách: thêm `async_loading_frames=True` vào `init_state`, sửa code để nhận video stream (mặc định chỉ đọc JPG).
- Kiến trúc SAM 2 cho phép không "nhìn tới tương lai" (chỉ cần frame quá khứ trong memory bank) → phù hợp streaming 1 chiều.
- Batching không ảnh hưởng nhiều (≤25–30%).

→ **Yêu cầu "webcam live + mở rộng cam điện thoại (IP/RTSP)" khả thi về mặt kiến trúc.**

---

## 4. Đường tới real-time: dùng biến thể "on-device" của SAM 2

Đề tài cho phép "tham khảo SAM 2, SAMURAI **hoặc XMem**". Các biến thể hiệu năng của chính SAM 2 (giữ đủ 3 trụ: segmentation + memory + temporal propagation):

### 4.1 EfficientTAM (Meta, ICCV 2025)
- Nguồn: `yformer.github.io/efficient-track-anything/`, repo `yformer/EfficientTAM`, paper arXiv:2411.18933.
- Encoder = vanilla lightweight ViT + efficient memory cross-attention → giảm complexity cả encoder lẫn memory.
- Hiệu năng: **~1.6× nhanh hơn SAM 2 (HieraB+) trên A100**, **~2.4× giảm parameter**.
- **Mobile: ~10 FPS video object segmentation trên iPhone 15 Pro Max**.
- Có video predictor (temporal + memory) ✓. ONNX export chưa official (issue #3) nhưng có model ONNX cộng đồng `egordm/efficienttam-ti-512` (HuggingFace).

### 4.2 EdgeTAM (Meta Reality Labs, on-device)
- Nguồn: `github.com/facebookresearch/EdgeTAM`, README.
- Biến thể on-device của SAM 2, **22× nhanh hơn SAM 2**, **16 FPS trên iPhone 15 Pro Max (không quantize)**.
- Cùng codebase SAM 2 → API video predictor giống SAM 2 → **logic motion-memory (Kalman) của SAMURAI có thể port sang** (cùng họ code).
- Có CoreML export (iOS/macOS). Gradio demo sẵn.

### 4.3 XMem (ECCV 2022) — phương án dự phòng
- Nguồn: `github.com/hkchengrex/XMem`, paper arXiv:2207.07115.
- VOS nhẹ, kiến trúc memory kiểu Atkinson-Shiffrin, **ít nặng hơn SAM 2**. Có GUI demo tương tác.
- Tốc độ paper báo ~30ms/frame trên GPU 1080Ti (480p); CPU sẽ chậm hơn nhiều nhưng có khả năng nhẹ hơn SAM 2.

---

## 5. Tăng tốc thêm trên Intel iGPU

Nguồn: blog "Intel iGPU で SAM2" (`note.com/todamah/n/n2a2894126d9b`), OpenVINO docs.
- Chuyển SAM 2 → **OpenVINO IR**, chạy trên **Intel Iris Xe iGPU** (native, tối ưu cho Intel).
- Image Encoder có thể **quantize INT8** (CPU có lợi; **iGPU không hỗ trợ INT8** → iGPU dùng FP16).
- OpenVINO notebook sẵn: `notebooks/segment-anything-2-image-with-output.html`.
- Cùng kỹ thuật áp dụng được cho EdgeTAM/EfficientTAM (cùng kiến trúc SAM 2).

Nguồn phụ trợ: `microsoft/onnxruntime` có tool export SAM2 ONNX (CPU); `wp133716/samurai-onnxruntime` (ONNX port SAMURAI, hỗ trợ CPU/INT8); `umitkacar/sam2-edge-cpp` (real-time edge, ONNX C++, 40× nhanh hơn).

---

## 6. Kết luận & khuyến nghị

1. **Full SAM 2 / SAMURAI trên laptop này KHÔNG real-time** (chứng minh bằng số liệu mục 2).
2. **Đường khả thi nhất tới "webcam live + real-time"**: đổi backbone sang **EdgeTAM** (hoặc EfficientTAM) — cùng họ SAM 2, giữ 3 trụ đề tài, thiết kế on-device, 22× nhanh hơn; **port logic Kalman + memory-bank selection của SAMURAI sang** để giữ "Motion Memory" cho luận văn; **tăng tốc bằng ONNX Runtime / OpenVINO trên Intel Iris Xe** (+ INT8 encoder cho CPU, FP16 cho iGPU); **stream qua `async_loading_frames`** theo issue #128.
3. **Bất định lớn nhất cần đo sớm**: FPS thực tế của EdgeTAM trên Iris Xe/CPU máy này chưa có số chính thức (16 FPS là trên iPhone). → cần **prototype benchmark** trước khi cam kết kiến trúc.
4. **Định nghĩa "real-time" thực dụng cho đồ án**: ngưỡng chấp nhận **≥ 10 FPS live** (mục tiêu 15–24). Nếu prototype đạt → tốt; nếu không → giảm resolution (512), skip-frame, hoặc xét XMem.

## 7. Nguồn tham khảo
- AnnotateIt benchmark: https://annotateit.ai/docs/sam2-benchmark/
- SAMURAI issue #128 (streaming): https://github.com/yangchris11/samurai/issues/128
- EfficientTAM: https://yformer.github.io/efficient-track-anything/ , https://github.com/yformer/EfficientTAM , arXiv:2411.18933
- EdgeTAM: https://github.com/facebookresearch/EdgeTAM
- XMem: https://github.com/hkchengrex/XMem , arXiv:2207.07115
- OpenVINO + SAM2 trên Intel iGPU: https://note.com/todamah/n/n2a2894126d9b , https://docs.openvino.ai/2024/notebooks/segment-anything-2-image-with-output.html
- ONNX Runtime SAM2 export: https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/python/tools/transformers/models/sam2/README.md
- samurai-onnxruntime: https://github.com/wp133716/samurai-onnxruntime
- Tối ưu SAMURAI (ONNX/TensorRT): https://egordmitriev.dev/blog/2026-05-16-optimizing-samurai-part-1