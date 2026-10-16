# Cơ sở lý thuyết: SAM 2 & SAMURAI cho bám bắt đối tượng thời gian thực

> Tài liệu này giải thích lý thuyết nền tảng của hệ thống — dùng cho chương "Cơ sở lý thuyết" của báo cáo đồ án.

---

## 1. Đặt bài toán

### 1.1. Video Object Segmentation (VOS) bán giám sát (semi-supervised VOS)

- **Input:** Chuỗi khung hình video `I₁, I₂, ..., I_T` + annotation ở frame đầu (mask / bounding box / điểm click) của đối tượng cần theo dõi.
- **Output:** Mặt nạ phân đoạn (segmentation mask) `M₁, M₂, ..., M_T` của đối tượng ở **mọi frame**.
- "Bán giám sát" = máy chỉ được cho biết đối tượng ở frame đầu, phải tự lan truyền (propagate) sang các frame sau.

### 1.2. Khác biệt giữa các bài toán liên quan

| Bài toán | Output | Đặc điểm |
|---|---|---|
| Object Detection | Bbox từng frame (độc lập) | Không liên kết qua thời gian |
| Object Tracking (VOT/SOT) | Bbox theo thời gian, 1 định danh | Không có mask |
| **VOS** | **Mask theo thời gian, giữ định danh** | Khó nhất, chính xác nhất |

### 1.3. Thách thức của VOS

1. **Che khuất (occlusion):** đối tượng bị che một phần/toàn phần → mất thông tin ngoại quan.
2. **Biến dạng (deformation):** người/vật phi cứng thay đổi hình dạng liên tục.
3. **Nhiễu nền & vật tương tự (distractors):** nhiều đối tượng giống nhau → dễ đổi mục tiêu (identity switch).
4. **Thay đổi tỉ lệ, ánh sáng, motion blur.**
5. **Trôi lỗi (error drift):** dự đoán sai ở frame t bị dùng làm "kinh nghiệm" cho frame t+1 → sai tích lũy.

---

## 2. Nền tảng: SAM (Segment Anything Model)

SAM (Meta, 2023) là mô hình **phân đoạn theo prompt** cho **ảnh tĩnh**, gồm 3 khối:

```
Ảnh ──▶ Image Encoder (ViT) ──▶ Image embedding ─┐
                                                  ├──▶ Mask Decoder ──▶ N mask candidates + IoU dự đoán
Prompt (click/box/mask) ──▶ Prompt Encoder ──────┘    (two-way transformer)
```

- **Image Encoder:** Vision Transformer nặng, chạy 1 lần/ảnh.
- **Prompt Encoder:** mã hóa điểm/box/mask thành vector.
- **Mask Decoder:** transformer 2 chiều (prompt ↔ image tokens), xuất **nhiều mask candidate** (thường 3) để xử lý sự mơ hồ của prompt (click vào áo → mask áo hay mask cả người?), kèm **IoU dự đoán** cho từng mask.
- **Giới hạn:** xử lý từng ảnh độc lập, **không có khái niệm thời gian** → không dùng trực tiếp được cho video.

---

## 3. SAM 2: Mở rộng SAM cho video (nền tảng của SAMURAI)

SAM 2 (Meta, 2024) thêm **bộ nhớ (memory)** để biến SAM thành mô hình VOS. Đây chính là hiện thực của **Temporal Propagation** trong đề tài.

### 3.1. Kiến trúc tổng thể

```
                 ┌──────────────────────── MEMORY BANK ────────────────────────┐
                 │  maskmem features + obj pointers của các frame trước        │
                 └──────────────────────────────▲────────────────┬─────────────┘
                                                │ add            │ cross-attend
Frame t ─▶ Image Encoder (Hiera) ─▶ Memory Attention ─▶ Mask Decoder ─▶ Mask t + IoU + obj score + obj ptr
                                              ▲                          │
                              Prompt (frame đầu)         Memory Encoder ◀┘
```

**Các thành phần:**

1. **Image Encoder (Hiera):** vision transformer phân cấp, cho đặc trưng đa tỉ lệ (FPN: stride 4/8/16/32). Chạy 1 lần mỗi frame.
2. **Memory Attention:** chồng các lớp transformer: self-attention trên đặc trưng frame hiện tại + **cross-attention sang memory bank** → đặc trưng frame hiện tại được "điều kiện hóa" bởi quá khứ. *Đây chính là cơ chế lan truyền theo thời gian (temporal propagation).*
3. **Mask Decoder:** giống SAM, nhận đặc trưng đã condition + prompt tokens → nhiều mask candidate + **IoU dự đoán** + **object score** (đối tượng có hiện diện trong frame không) + **object pointer** (token đại diện định danh đối tượng).
4. **Memory Encoder:** fuse mask dự đoán với đặc trưng ảnh → **memory features** → đẩy vào memory bank (để các frame sau dùng).
5. **Memory Bank:** SAM 2 gốc giữ: (a) các conditioning frames (frame có prompt) + (b) **N=6 frame gần nhất** (FIFO), kèm mã hóa vị trí thời gian `t_pos`.

### 3.2. Temporal Propagation hoạt động thế nào?

> "Lan truyền theo thời gian" trong SAM 2 = vòng lặp: **dự đoán mask frame t → mã hóa thành memory → memory điều kiện hóa dự đoán frame t+1**.

Nhờ đó mask + định danh đối tượng (qua object pointer) được lan truyền qua các frame mà không cần prompt lại. Frame đầu chỉ cần 1 bbox/click.

### 3.3. ⚠️ Điểm yếu của SAM 2 thuần (lý do SAMURAI ra đời)

1. **Chọn mask chỉ dựa vào IoU dự đoán** (`argmax IoU`) — hoàn toàn dựa vào *ngoại quan*, **không dùng thông tin chuyển động**. Khi bị che khuất/distractor xuất hiện, IoU dự đoán không đáng tin → chọn nhầm mask.
2. **Memory bank FIFO mù quáng** — frame nào cũng vào memory, kể cả frame bị che khuất/mask sai → **ô nhiễm bộ nhớ → lỗi tích lũy (drift)**.

---

## 4. Kalman Filter — mô hình chuyển động (Motion Memory phần 1)

### 4.1. Ý tưởng

Kalman Filter (1960) là bộ ước lượng trạng thái tối ưu cho **hệ động lực tuyến tính với nhiễu Gaussian**. Nó duy trì:
- **State mean** `x̂`: ước lượng trạng thái hiện tại.
- **Covariance** `P`: độ bất định của ước lượng.

Lặp 2 bước: **Predict** (dự đoán theo mô hình chuyển động) → **Update** (hiệu chỉnh bằng quan sát thực tế).

### 4.2. Toán học

**Predict:**
```
x̂⁻ = F · x̂            (dự đoán trạng thái)
P⁻  = F · P · Fᵀ + Q    (dự đoán bất định, Q = nhiễu quá trình)
```

**Update:**
```
K  = P⁻ · Hᵀ · (H · P⁻ · Hᵀ + R)⁻¹     (Kalman gain, R = nhiễu quan sát)
x̂  = x̂⁻ + K · (z − H · x̂⁻)           (hiệu chỉnh theo measurement z)
P  = (I − K · H) · P⁻
```

- `K` lớn → tin measurement; `K` nhỏ → tin mô hình chuyển động. Tự động cân bằng theo độ bất định.

### 4.3. State space trong SAMURAI

State 8 chiều (kiểu DeepSORT):
```
x = (x, y, a, h, vx, vy, va, vh)
```
- `(x, y)`: tâm bbox; `a`: aspect ratio (w/h); `h`: chiều cao bbox.
- `(vx, vy, va, vh)`: vận tốc tương ứng.
- **Mô hình constant velocity:** `F = [I₄  dt·I₄; 0  I₄]` — giả định đối tượng chuyển động đều trong ngắn hạn.
- Measurement `z = (x, y, a, h)` trích từ mask dự đoán (bbox bao quanh mask, convert xyxy→xyah).

### 4.4. Vai trò trong hệ thống

KF cung cấp **motion prior**: "theo quán tính chuyển động, đối tượng đáng lẽ ở đâu frame này?" — tín hiệu **độc lập với ngoại quan**, cực kỳ giá trị khi ngoại quan bị nhiễu (che khuất). KF **không cần train** → phù hợp hệ zero-shot.

---

## 5. SAMURAI: Motion-Aware Memory (đóng góp chính)

SAMURAI = **SAM 2 đóng băng (zero-shot)** + 2 cơ chế dùng chuyển động. Cờ `samurai_mode: true` trong config.

### 5.1. Motion-aware Mask Selection

**Bài toán:** mask decoder xuất nhiều mask candidate `{maskᵢ}` kèm IoU dự đoán `{iouᵢ}`. Chọn cái nào?

- **SAM 2:** `argmaxᵢ iouᵢ` (chỉ nhìn ngoại quan).
- **SAMURAI:** kết hợp motion prior từ KF:

```
1. KF.predict() → bbox dự đoán B_kf
2. Với mỗi candidate i:  kf_iouᵢ = IoU(B_kf, bbox(maskᵢ))
3. scoreᵢ = w · kf_iouᵢ + (1 − w) · iouᵢ ,   w = 0.25 (kf_score_weight)
4. Chọn argmaxᵢ scoreᵢ
```

→ Khi che khuất, `iouᵢ` (ngoại quan) mất tin cậy nhưng `kf_iouᵢ` (chuyển động) vẫn đúng → kéo lựa chọn về đúng quỹ đạo.

### 5.2. State machine độ ổn định (khi nào tin KF?)

KF cần "khởi động" — dự đoán chỉ đáng tin sau khi quan sát ổn định một thời gian. SAMURAI quản lý bằng bộ đếm `stable_frames`:

```
stable_frames = 0:
    chọn mask theo argmax IoU; KF.initiate(bbox); stable_frames = 1

0 < stable_frames < 15  (stable_frames_threshold):
    KF.predict(); chọn mask theo argmax IoU
    nếu iou_best > 0.3 (stable_ious_threshold): KF.update(bbox); stable_frames += 1
    ngược lại: stable_frames = 0            ← tracking mất ổn định, reset

stable_frames ≥ 15  (ĐÃ ỔN ĐỊNH):
    dùng weighted score (mục 5.1) để chọn mask
    nếu iou_best < 0.3: stable_frames = 0   ← mất dấu, không tin KF nữa
    ngược lại: KF.update(bbox đã chọn)
```

**Bản chất:** đây là máy trạng thái 2 trạng thái `UNSTABLE ↔ STABLE` — chỉ dùng motion prior khi nó đáng tin, và chỉ update KF bằng measurement "sạch" (tránh làm bẩn bộ lọc).

### 5.3. Motion-aware Memory Bank Selection (Motion Memory phần 2)

**Bài toán:** frame nào xứng đáng vào memory bank để "dạy" các frame sau?

- **SAM 2:** N frame gần nhất (FIFO) — kể cả frame che khuất/mask sai.
- **SAMURAI:** frame `i` chỉ vào bank nếu vượt **cả 3 ngưỡng**:

```
best_iou_scoreᵢ      > 0.5   (memory_bank_iou_threshold)     ← phân đoán tự tin
object_score_logitsᵢ > 0.0   (memory_bank_obj_score_threshold) ← đối tượng thực sự hiện diện
kf_scoreᵢ            > 0.0   (memory_bank_kf_score_threshold)  ← khớp chuyển động
```

- Luôn giữ frame `t−1` (liên tục ngắn hạn), tối đa `num_maskmem = 7` frames.

**Ý nghĩa:** memory bank chỉ chứa các **quan sát đáng tin** → memory attention không bị nhiễu → giảm drift, bám bắt bền hơn khi che khuất kéo dài. Đây chính là "bộ nhớ chuyển động có chọn lọc".

### 5.4. Vì sao gọi là zero-shot?

- Weight SAM 2.1 dùng nguyên bản, **không fine-tune**.
- KF là ước lượng cổ điển, không học.
- Toàn bộ "trí tuệ" mới nằm ở **chiến lược chọn mask & chọn memory** lúc inference.

---

## 6. Pseudocode toàn hệ thống (1 vòng lặp tracking)

```python
state = init_state(video)
add_box_prompt(state, frame=0, bbox)     # người dùng chọn đối tượng
kf = KalmanFilter(); stable = 0

for each frame t:
    feats = image_encoder(frame_t)
    memory = select_memory(bank, thresholds)     # 5.3 — lọc theo iou/obj/kf
    feats_cond = memory_attention(feats, memory)
    masks, ious, obj_score, obj_ptr = mask_decoder(feats_cond)

    if stable < 15:                            # 5.2 — chưa ổn định
        best = argmax(ious)
    else:                                      # đã ổn định
        kf_pred = kf.predict()
        kf_ious = IoU(kf_pred, bbox(masks))
        best = argmax(0.25*kf_ious + 0.75*ious)   # 5.1

    mask_t = masks[best]
    if ious[best] > 0.3:  kf.update(bbox(mask_t)); stable += 1
    else:                 stable = 0

    bank[t] = memory_encoder(mask_t, feats)     # sẽ bị lọc ở bước select_memory
    yield mask_t
```

---

## 7. Ánh xạ vào 3 trụ cột của đề tài

| Trụ cột đề tài | Hiện thực trong hệ | Bản chất lý thuyết |
|---|---|---|
| **Image Segmentation** | SAM 2 mask decoder | Promptable segmentation + IoU prediction |
| **Motion Memory** | Kalman Filter + memory bank được lọc | Ước lượng trạng thái (Bayes lọc tuyến tính) + chọn lọc quan sát tin cậy |
| **Temporal Propagation** | Memory attention + memory encoder | Lan truyền mask/định danh qua attention có điều kiện thời gian |

---

## 8. Các đại lượng đánh giá (phục vụ chương thực nghiệm)

- **IoU (Jaccard):** `|A ∩ B| / |A ∪ B|` — chất lượng phân đoạn.
- **FPS (frames/sec):** tốc độ xử lý; **Latency:** độ trễ mỗi frame (ms).
- **AUC / Precision (VOT benchmark):** theo chuẩn LaSOT/GOT-10k.
- **Độ ổn định bám bắt:** tỉ lệ frame giữ được đối tượng (không mất dấu), khả năng tái nhận diện sau che khuất.
- **Mức dùng CPU/GPU (VRAM):** giới hạn triển khai thực tế.

## 9. Tài liệu tham khảo

- SAM: Kirillov et al., "Segment Anything", ICCV 2023.
- SAM 2: Ravi et al., "SAM 2: Segment Anything in Images and Videos", arXiv:2408.00714.
- SAMURAI: Yang et al., "SAMURAI: Adapting SAM for Zero-Shot Visual Tracking with Motion-Aware Memory", arXiv:2411.11922.
- Kalman, R. E. (1960), "A New Approach to Linear Filtering and Prediction Problems".
- DeepSORT (nguồn gốc KF cho tracking): Wojke et al., ICIP 2017.
