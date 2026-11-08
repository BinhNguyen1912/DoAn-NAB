# VOS nào đạt 25–30 FPS thật trên CPU/iGPU (không CUDA)?

> Câu hỏi: có mô hình VOS nào giữ đủ 3 trụ đề cương (Segmentation mask + Motion Memory +
> Temporal Propagation) và đạt **≥ 25 FPS thật** trên CPU 4 nhân x86 / Intel Iris Xe không?
> Máy mục tiêu: MSI Modern 14 B11MOU — i7-1195G7 (4C/8T), 16 GB, Iris Xe, **không CUDA**.
> Ngày: 08-11-2026.
> ⚠️ Phần lớn số liệu lấy từ nguồn đã truy xuất trong repo (`docs/research/03,05,07a`) hoặc đánh
> dấu **[cần kiểm chứng]** (từ tri thức paper, chưa fetch lại). **Mục 7 là bổ sung của parent:
> số đo THẬT trên máy này, đã đóng câu hỏi của mục 3.1.**

## 1. Kết luận

- **Không tìm được** số đo công bố nào cho thấy một model VOS đủ 3 trụ đạt ≥ 25 FPS **CPU-only trên
  x86 hoặc Intel iGPU**. Mọi con số "nhanh" trong văn liệu (SAM 2 ~44 FPS, XMem ~33 FPS,
  Cutie ~40 FPS) đều đo trên **GPU rời** (A100/1080Ti) — không áp dụng cho máy này.
- **EdgeTAM là ứng viên duy nhất có cửa** trên máy này: 16 FPS trên iPhone 15 Pro Max (ANE), 22×
  nhanh hơn SAM 2 trên cùng thiết bị, giữ đủ memory bank + temporal propagation (cùng codebase
  SAM 2). **Chưa ai công bố số CPU x86** — nhưng xem **mục 7**: parent đã đo encoder RepViT trên
  chính máy này, và trần suy ra là **13,6–18,2 FPS**, không phải 25–30.
- Stack hiện tại (SAM 2.1 tiny/SAMURAI) chạm trần **12,7 FPS @image_size 160** (78 ms); @256 chỉ
  5,45 FPS → thiếu 2–2,4× so với 30 FPS, và không runtime nào (ONNX/INT8/OpenVINO) bù nổi ở 1024
  (0,2–0,7 FPS — `docs/research/05`).

## 2. Bảng so sánh

FPS "N/A" = không tìm thấy số đo có nguồn. Memory/Temporal: ✓ = có đủ theo kiến trúc paper.

| Model | FPS công bố | Thiết bị đo | Độ phân giải | Memory | Temporal | Nguồn |
|---|---|---|---|---|---|---|
| **SAM 2.1 tiny (hiện tại)** | **5,45 / 10,3 / 12,7** (đo thật) | **i7-1195G7, máy này** | image_size 256/192/160 | ✓ | ✓ | `docs/task/08-11-2026-...` |
| SAM 2 (Hiera-B+) | ~44 | A100 | 1024² | ✓ | ✓ | arXiv:2408.00714 (SAM 2 paper §7, xác nhận qua issue #159 của repo sam2) |
| SAMURAI | ≈ tốc độ SAM 2.1 tiny; máy này 5,45 @256 | A100-class / CPU máy này | 256–1024 | ✓ (Kalman) | ✓ | arXiv:2411.11922 + đo local |
| **EdgeTAM** | **15,7 (không quantize)**; A100 150,9 | iPhone 15 Pro Max (ANE) / A100 | 1024² (huấn luyện) | ✓ | ✓ | arXiv:2501.07256 Tab. 2 · github.com/facebookresearch/EdgeTAM |
| EfficientTAM-Ti/2 | A100 **109,4**; phone 261,4 ms | A100 / iPhone 2023 | 1024² | ✓ | ✓ | arXiv:2411.18933 Tab. 1 |
| XMem | ~33 (≈30 ms/frame) | GTX 1080Ti | 480p | ✓ | ✓ | arXiv:2207.07115 |
| Cutie | ~40 **[cần kiểm chứng]** | GPU | 480p | ✓ | ✓ | **arXiv:2310.12982** (không phải 2311.17117) |
| DEVA | N/A (framework; phụ thuộc segmentor) | GPU | tùy segmentor | ✓ | ✓ | arXiv:2309.03903 |
| MobileSAM / MobileSAMv2 | 624 ms/frame (chỉ encoder, browser WASM) | Core Ultra 9 386H iGPU | 1024² | ✗ | ✗ | annotateit.ai benchmark |
| EfficientViT-SAM | nhanh hơn SAM 17–69× (TensorRT) **[cần kiểm chứng]** | A100 | 1024² | ✗ | ✗ | arXiv:2402.05008 |
| RepViT-SAM | ~10× nhanh hơn MobileSAM **[cần kiểm chứng]** | A100 / iPhone 12 | 1024² | ✗ | ✗ | arXiv:2312.05760 |

Ba model cuối **chỉ segment ảnh tĩnh** → thiếu 2 trụ; chỉ dùng làm **encoder thay thế** nếu tự xây
phần temporal.

## 3. Phân tích từng ứng viên

### 3.1 EdgeTAM — ứng viên duy nhất (xem thêm mục 7 để có số đo thật)
16 FPS trên iPhone 15 Pro Max là **NPU điện thoại (ANE qua CoreML)**, không phải CPU x86. Có video
predictor đầy đủ (cùng codebase SAM 2 ⇒ port được Kalman/memory-selection của SAMURAI). CoreML có
sẵn; ONNX chưa có export chính thức.
**Cảnh báo bắt buộc khi trích:** issue #24 của repo EdgeTAM chỉ ra rằng **bước encode ảnh nằm NGOÀI
vòng đo FPS** của họ (tính cả vào thì FPS giảm ~15×); maintainer không phản hồi.

### 3.2 EfficientTAM
Encoder vanilla ViT nhẹ + memory cross-attention hiệu quả; **~1,6× nhanh hơn SAM 2 Hiera-B+ trên
A100**; **>10 FPS trên iPhone 15**. Có video predictor. ONNX chưa official (issue #3); có bản cộng
đồng `egordm/efficienttam-ti-512`.

### 3.3 XMem / XMem++
~30 ms/frame trên **GTX 1080Ti @480p**. Ước tính CPU máy này ~0,5–1,5 FPS (`docs/research/05` §3)
→ loại.

### 3.4 Cutie — arXiv:2310.12982
Object-level memory + temporal propagation, đủ 3 trụ. ~40 FPS **trên GPU**; không có số CPU → loại.

### 3.5 DEVA — arXiv:2309.03903
Framework "tách đôi": segmentor ảnh chạy định kỳ + module lan truyền. Tốc độ phụ thuộc segmentor
(Grounded-SAM rất nặng) → không phải ứng viên CPU, nhưng **ý tưởng kiến trúc thì đúng** (xem
`docs/research/09`).

### 3.6 MobileSAMv2 / EfficientViT-SAM / RepViT-SAM
SAM ảnh tĩnh: không memory bank, không temporal → thiếu 2 trụ.

### 3.7 SAM 2 / SAMURAI (baseline)
Trên máy này: **5,45 FPS @256, trần 12,7 FPS @160** — cách 25 FPS tối thiểu ~2×.

## 4. Có số đo CPU-only công bố nào không?

**Không tìm được.** Bằng chứng CPU-only duy nhất có nguồn lại ngược chiều kỳ vọng: AnnotateIt
(chip Intel Core Ultra 9 386H **16 nhân**, browser WASM): encoder SAM 2.1 tiny = 2,82 s/frame CPU
multi-thread @1024 (~0,35 FPS) — `docs/research/03` §2. Tức trên phần cứng Intel mạnh hơn máy này
~4×, VOS họ SAM 2 vẫn dưới 1 FPS ở độ phân giải đầy đủ.

## 5. Kết luận cho mục tiêu 25–30 FPS trên máy này

1. **Theo bằng chứng đã truy xuất: không có model nào được chứng minh đạt 25–30 FPS CPU-only/iGPU**
   với đủ 3 trụ. Đây là kết luận hợp lệ để viết trung thực vào báo cáo.
2. **EdgeTAM là ứng viên duy nhất đáng đo** — và **đã được đo một phần ở mục 7**.
3. Nếu vẫn < 25 FPS: chỉ còn nhượng bộ — giữ ngưỡng thực dụng ≥10–12,7 FPS (đã đo), skip-frame,
   hoặc kiến trúc **hybrid** (`docs/research/09`) để hiển thị 30 FPS thật.

## 6. Nguồn

- EdgeTAM: https://github.com/facebookresearch/EdgeTAM · https://arxiv.org/abs/2501.07256 ·
  tranh cãi phạm vi đo FPS: https://github.com/facebookresearch/EdgeTAM/issues/24
- EfficientTAM: https://arxiv.org/abs/2411.18933 · https://github.com/yformer/EfficientTAM
- SAM 2: https://arxiv.org/abs/2408.00714 · https://github.com/facebookresearch/sam2/issues/159
- SAMURAI: https://arxiv.org/abs/2411.11922 · https://github.com/yangchris11/samurai
- XMem: https://arxiv.org/abs/2207.07115 · XMem++: https://arxiv.org/abs/2401.06269
- Cutie: https://arxiv.org/abs/2310.12982 · DEVA: https://arxiv.org/abs/2309.03903
- MobileSAMv2: https://arxiv.org/abs/2312.09579 · EfficientViT-SAM: https://arxiv.org/abs/2402.05008
  · RepViT-SAM: https://arxiv.org/abs/2312.05760
- Benchmark Intel iGPU (browser): https://annotateit.ai/docs/sam2-benchmark/
- Đo local: `docs/task/08-11-2026-do-lai-do-phan-giai-va-kich-thuoc-model.md`,
  `docs/research/05`, `docs/research/03`

## 7. Bổ sung của parent — ĐO THẬT encoder EdgeTAM trên máy này (đóng câu hỏi §3.1)

Câu "chưa ai đo trên CPU x86" ở §3.1 **đã được trả lời trong cùng phiên**: clone
`facebookresearch/EdgeTAM`, dùng đúng `sam2/edgetam.yaml` (trunk `repvit_m1.dist_in1k` + `FpnNeck`
d_model 256), đo trên i7-1195G7 với `torch.set_num_threads(4)`. Thời gian chạy **không phụ thuộc
trọng số** nên trọng số ngẫu nhiên là đủ cho phép đo này.

| image_size | Hiera-T (SAM 2.1 tiny) | **RepViT-M1.1 (EdgeTAM)** | Tỉ lệ |
|---|---|---|---|
| 160 | 75,2 ms | **34,7 ms** (min 25,5) | 2,17× |
| 192 | 90,0 ms | **35,6 ms** (min 33,6) | 2,53× |
| 256 | 164,2 ms | **50,9 ms** (min 48,2) | 3,22× |

Suy ra pipeline đầy đủ khi thay encoder (giữ memory attention + decoder + Kalman):

| Kịch bản | @160 | @192 | @256 |
|---|---|---|---|
| Hiện tại | 104,9 ms → 9,5 FPS | 127,7 → 7,8 | 212,7 → 4,7 |
| Thay encoder RepViT | 64,4 → **15,5** | 73,3 → **13,6** | 99,4 → 10,1 |
| ⊕ giảm `num_maskmem` 7→3 | 56 → 17,9 | 61 → 16,4 | 85 → 11,8 |
| ⊕ nén memory kiểu EdgeTAM | 45 → **22,2** | 55 → **18,2** | 78 → 12,8 |

**Kết luận cập nhật:** EdgeTAM-class trên CPU này đạt **13,6–18,2 FPS @192** (tối đa ~22 FPS @160
nếu port cả nén memory) — **không đạt 25–30 FPS**, khớp với kết luận §1 nhưng giờ **có số đo thay
vì phỏng đoán**. Còn thiếu để chốt tuyệt đối: dựng full video predictor EdgeTAM (cần tải
checkpoint) và đo trên `data/binh1.mp4` — dự kiến 2–4 giờ.

Chi tiết + cách tái tạo: `docs/research/11-do-encoder-repvit-tren-cpu-va-tran-realtime.md`.
