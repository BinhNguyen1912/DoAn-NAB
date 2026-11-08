# Đo encoder RepViT (EdgeTAM) trên CPU này — trần realtime thật là bao nhiêu?

> Ngày: 08-11-2026. Máy: i7-1195G7 (4 nhân/8 luồng), 16 GB, **không CUDA**.
> Đây là phép đo **quyết định** cho câu hỏi "làm sao đạt realtime thật": profile cho thấy image
> encoder chiếm **70–77 %** chi phí mỗi frame (`scripts/profile_stages.py`), nên muốn nhanh gấp
> nhiều lần thì **chỉ có thay encoder**. Câu hỏi: encoder của EdgeTAM (RepViT-M1.1) nhanh hơn
> Hiera-T bao nhiêu trên chính CPU này?

## 1. Kết luận

1. **RepViT-M1.1 nhanh hơn Hiera-T từ 2,2× đến 3,2×** (đo thật, cùng CPU, cùng 4 luồng):
   34,7 vs 75,2 ms @160; 35,6 vs 90,0 @192; 50,9 vs 164,2 @256.
2. Ước lượng pipeline đầy đủ nếu thay encoder (giữ nguyên memory attention + decoder + Kalman
   của SAMURAI): **14–19 FPS @192, 17–22 FPS @160** (thêm nén memory kiểu EdgeTAM).
3. **30 FPS mask-mỗi-frame vẫn KHÔNG đạt được** kể cả khi thay encoder — thiếu ~1,4–2×. Trần thực tế
   của máy này là **~20 FPS** cho lớp AI.
4. Nhưng 15–22 FPS là đủ để **hiển thị 25–30 FPS thật** bằng kiến trúc hybrid (VOS + tracker nhẹ),
   vì lúc đó lớp nặng chỉ cần ~15–20 FPS là "kịp" cho mắt người.

## 2. Số đo encoder (cùng input vuông, fp32, CPU)

| image_size | Hiera-T (SAM 2.1 tiny, đang dùng) | **RepViT-M1.1 (EdgeTAM)** | Tỉ lệ |
|---|---|---|---|
| 160 | 75,2 ms | **34,7 ms** (min 25,5) | **2,17×** |
| 192 | 90,0 ms | **35,6 ms** (min 33,6) | **2,53×** |
| 256 | 164,2 ms | **50,9 ms** (min 48,2) | **3,22×** |

Nguồn: `scripts/profile_stages.py` (Hiera, trong pipeline thật) vs `/tmp/time_repvit.py`
(RepViT trunk `repvit_m1.dist_in1k` + `FpnNeck` d_model 256 lấy từ `sam2/edgetam.yaml` của
facebookresearch/EdgeTAM — **trọng số ngẫu nhiên**: thời gian chạy không.phụ thuộc trọng số).
Đo với `torch.set_num_threads(4)`; thử 8 luồng cho kết quả **tệ hơn** (nhiễu, p95 232–332 ms)
⇒ giữ 4 luồng.

## 3. Suy ra pipeline đầy đủ (phép tính)

Cấu trúc chi phí đo được @192 (tổng 127,7 ms): encoder 90,0 + memory_attention 22,6 +
mask_decoder 9,4 + memory_encoder 8,0 + prompt 1,3.

| Kịch bản | @160 | @192 | @256 |
|---|---|---|---|
| Hiện tại (Hiera-T) | 104,9 ms → **9,5 FPS** | 127,7 → **7,8** | 212,7 → **4,7** |
| Thay encoder RepViT | 104,9−75,2+34,7 = **64,4 → 15,5 FPS** | 127,7−90+35,6 = **73,3 → 13,6** | 212,7−164,2+50,9 = **99,4 → 10,1** |
| ⊕ giảm `num_maskmem` 7→3 (memory attn ×3/7) | ≈ 56 → **17,9 FPS** | ≈ 61 → **16,4** | ≈ 85 → 11,8 |
| ⊕ nén memory kiểu EdgeTAM (Perceiver 2D) | ≈ 45 → **22,2 FPS** | ≈ 55 → **18,2** | ≈ 78 → 12,8 |

**Đọc bảng này:** dù cộng dồn mọi đòn, trần vẫn ~18–22 FPS. Con số 30 FPS chỉ còn cách nếu
đồng thời giảm cả decoder (9,4 ms) và bỏ hẳn bước `memory_encoder` (8 ms) — và như thế là
**sửa kiến trúc SAM 2**, không còn là "đổi encoder" nữa.

## 4. Vì sao EdgeTAM 16 FPS trên iPhone không áp dụng được nguyên con

EdgeTAM (CVPR 2025, arXiv:2501.07256, Tab. 2) — cùng độ phân giải huấn luyện 1024²:

| Model | A100 | iPhone 15 Pro Max |
|---|---|---|
| EdgeTAM | 150,9 FPS | **15,7 FPS** |
| SAM 2-B+ | 64,8 | **0,7** |
| SAM 2.1-B+ | 64,1 | 0,7 |

- iPhone **có NPU/GPU** cho conv; laptop này **không có**. Tỉ lệ 22× của họ đo trên iPhone.
- Paper ghi rõ: trên A100, EdgeTAM dùng **dưới 50 % SM** và bị **nghẽn CPU/IO** ⇒ con số GPU không
  nói gì về CPU.
- **Cảnh báo quan trọng:** issue #24 của repo EdgeTAM
  (https://github.com/facebookresearch/EdgeTAM/issues/24) chỉ ra rằng **bước encode ảnh nằm NGOÀI
  vòng đo FPS**, và nếu tính cả encode thì FPS giảm ~15×. Issue không có phản hồi của maintainer.
  ⇒ Khi trích "16 FPS" vào báo cáo **phải ghi rõ** đây là số của họ trên iPhone và có tranh cãi về
  phạm vi đo. Trên máy này encoder = 70–77 % thời gian frame, nên con số đó **không dùng được**.
- Tab. 3(a) của paper: bỏ nén memory thì 2,5 FPS, có Perceiver 2D thì 15,7 FPS trên iPhone ⇒ phần
  lớn lợi ích của EdgeTAM nằm ở **memory**, không phải encoder. Trên CPU này memory chỉ chiếm 18 %
  ⇒ hưởng lợi ít hơn iPhone.

## 5. Bảng quyết định (đã tính bằng số đo trên)

| Phương án | FPS lớp AI | FPS hiển thị | Công sức | Rủi ro |
|---|---|---|---|---|
| Giữ Hiera-T @192 | 8,9 | 30 (smooth_display) | 0 | không |
| Hiera-T @160 | 12,7 | 30 | 0 | IoU −5 % |
| Dùng lại encoder K=2 | 13,3 | 30 | 1 ngày | IoU −13 % ❌ |
| **Thay encoder RepViT @192** | **13,6–18,2** | 30 | 1–2 tuần | trung bình (port sang codebase SAM 2) |
| **RepViT + nén memory @160** | **~22** | 30 | 2–3 tuần | cao (sửa lõi SAM 2) |
| Hybrid: VOS bất kỳ + tracker nhẹ 30 FPS | 8,9–22 | **30 thật** | 3–5 ngày | thấp |
| GPU (Colab T4, đã đo) | 9,9 @512 | 30 | 0 code | cần mạng, không live |

## 6. Việc nên làm tiếp

- [ ] **Đo full pipeline EdgeTAM thật** (tải checkpoint `facebook/EdgeTAM`, dựng
      `build_sam2_video_predictor` với `sam2/edgetam.yaml`) trên `data/binh1.mp4` để thay số ước
      lượng bằng số đo — dự kiến 2–4 giờ, đây là bước chốt quyết định có đáng đổi không.
- [ ] Đo chất lượng: J&F/SA-V của EdgeTAM thấp hơn SAM 2.1-B+ (72,3 vs 76,8 SA-V val) ⇒ cần đo lại
      IoU trên fixture của repo trước khi cam kết.
- [ ] Nếu không đủ thời gian: chọn **hybrid** (đã có `smooth_display`, chỉ cần thêm tracker nhẹ).

## 7. Nguồn

- EdgeTAM: https://github.com/facebookresearch/EdgeTAM · arXiv:2501.07256 · CVPR 2025
- Tranh cãi phạm vi đo FPS: https://github.com/facebookresearch/EdgeTAM/issues/24
- EfficientTAM (so sánh, cho báo cáo): https://arxiv.org/html/2411.18933 (SAM 2 43,8 FPS;
  EfficientTAM-Ti/2 109,4 FPS; phone 261,4 ms @1024 — **trên A100/iPhone, không phải CPU**)
- Số đo trên máy này: `scripts/profile_stages.py`, `scripts/exp_encoder_reuse.py`,
  `/tmp/time_repvit.py` (tái tạo: clone EdgeTAM, dùng `sam2/edgetam.yaml`)
- `docs/research/10-tang-toc-runtime-iris-xe-va-knob-sam2.md` (đọc mã nguồn: cache encoder chỉ 1
  frame, torch.compile bị chặn cho HieraT, selection memory của SAMURAI là knob chất lượng)
