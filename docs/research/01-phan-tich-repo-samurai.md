# Phân tích repo SAMURAI (tham khảo chính)

> Repo: https://github.com/yangchris11/samurai
> Paper: *SAMURAI: Adapting Segment Anything Model for Zero-Shot Visual Tracking with Motion-Aware Memory* (arXiv: 2411.11922)
> License: Apache 2.0 | Nền tảng: SAM 2.1 của Meta (không cần train thêm — zero-shot)

---

## 1. SAMURAI là gì?

- **Zero-shot Visual Object Tracking (VOT)**: theo dõi 1 đối tượng trong video, prompt là **bounding box ở frame đầu tiên** — không cần train/fine-tune, dùng trực tiếp weight **SAM 2.1**.
- Cải tiến so với SAM 2 gốc: thêm **Motion-Aware Memory** gồm 2 cơ chế:
  1. **Kalman Filter (KF)** mô hình hóa chuyển động đối tượng → chọn mask đầu ra tốt hơn khi có nhiều mask candidate.
  2. **Motion-aware memory bank selection** → chỉ đưa các frame "chất lượng tốt" vào memory bank, tránh nhiễu khi đối tượng bị che khuất/mất dấu.

→ **Rất khớp với đề tài**: Segmentation (SAM 2) + Motion Memory (Kalman Filter + memory bank) + Temporal Propagation (memory attention của SAM 2).

---

## 2. Cấu trúc repo (các phần quan trọng)

```
samurai/
├── sam2/                          # Bản fork của SAM 2 (Meta) đã chỉnh sửa
│   ├── checkpoints/               # download_ckpts.sh tải weight SAM 2.1
│   ├── sam2/
│   │   ├── configs/samurai/       # Config: sam2.1_hiera_{t,s,b+,l}.yaml
│   │   ├── modeling/sam2_base.py  # ⭐ CHỈNH SỬA CHÍNH: motion-aware logic
│   │   ├── sam2_video_predictor.py# ⭐ Predictor video, lưu kf_score vào state
│   │   └── utils/kalman_filter.py # ⭐ Kalman Filter (8-dim state, DeepSORT-style)
│   └── demo/                      # Web demo gốc của SAM 2 (React + Flask)
├── scripts/
│   ├── demo.py                    # ⭐ Demo tracking trên video tùy ý (bbox prompt)
│   ├── main_inference.py          # Chạy benchmark VOT (LaSOT, GOT-10k...)
│   └── main_inference_chunk.py    # Multi-GPU inference
├── lib/                           # Bộ evaluation VOT toolkit
└── data/                          # Dataset benchmark (LaSOT...)
```

⭐ = file quan trọng nhất cần nghiên cứu.

---

## 3. Cơ chế kỹ thuật cốt lõi

### 3.1. Pipeline tổng thể (theo `scripts/demo.py`)

```
Video/frames → init_state() → add_new_points_or_box(frame 0, bbox prompt)
→ propagate_in_video() generator → từng frame: mask + bbox → visualize
```

- Prompt bbox: file txt định dạng `x,y,w,h` → convert sang `x1,y1,x2,y2` cho SAM 2.
- Output mỗi frame: `mask` (segmentation mask) → suy ra bbox bao quanh.

### 3.2. Kalman Filter (`sam2/sam2/utils/kalman_filter.py`)

- State 8 chiều: `(x, y, a, h, vx, vy, va, vh)` — tâm bbox, aspect ratio, chiều cao + vận tốc tương ứng.
- Mô hình **constant velocity**; API: `initiate()`, `predict()`, `update()`, `compute_iou()`, `xyxy_to_xyah()`, `xyah_to_xyxy()`.
- Không cần train (KF truyền thống, lấy ý tưởng từ DeepSORT).

### 3.3. Motion-aware mask selection (`sam2_base.py`, `_forward_sam_heads`, khi `samurai_mode: true`)

SAM decoder xuất **nhiều mask candidate** kèm IoU dự đoán. SAMURAI chọn mask theo 2 giai đoạn:

| Giai đoạn | Điều kiện | Cách chọn |
|---|---|---|
| **Khởi tạo / chưa ổn định** (`stable_frames < 15`) | | Chọn mask IoU cao nhất; KF `initiate`/`predict`+`update`; nếu IoU < `0.3` → reset `stable_frames = 0` |
| **Ổn định** (`stable_frames >= 15`) | | KF `predict` ra bbox dự đoán → tính `kf_ious` (IoU giữa bbox dự đoán và bbox từng mask candidate) → **weighted score = 0.25·kf_iou + 0.75·sam_iou** → chọn mask có weighted score cao nhất |

→ Khi đối tượng bị che khuất, SAM thuần dễ chọn nhầm mask; KF giúp "kéo" về đúng quỹ đạo chuyển động.

### 3.4. Motion-aware memory bank selection (`sam2_base.py`, `_prepare_memory_conditioned_features`)

SAM 2 gốc: luôn lấy N frame gần nhất làm memory.
SAMURAI: frame chỉ vào memory bank nếu **vượt cả 3 ngưỡng**:

```python
best_iou_score      > 0.5   # memory_bank_iou_threshold
object_score_logits > 0.0   # memory_bank_obj_score_threshold
kf_score            > 0.0   # memory_bank_kf_score_threshold
# + luôn giữ frame liền trước (frame_idx - 1); tối đa num_maskmem = 7 frames
```

→ Đây chính là **"Motion Memory"** mà đề tài yêu cầu: lưu lịch sử chuyển động + lọc nhiễu khỏi bộ nhớ.

### 3.5. Hyperparameters (config `sam2.1_hiera_b+.yaml`)

```yaml
samurai_mode: true
stable_frames_threshold: 15      # số frame ổn định trước khi tin KF
stable_ious_threshold: 0.3       # IoU tối thiểu coi là "ổn định"
min_obj_score_logits: -1
kf_score_weight: 0.25            # trọng số motion trong weighted score
memory_bank_iou_threshold: 0.5
memory_bank_obj_score_threshold: 0.0
memory_bank_kf_score_threshold: 0.0
num_maskmem: 7                   # số frame memory tối đa
```

---

## 4. Yêu cầu môi trường & cài đặt

```bash
# Yêu cầu: python>=3.10, torch>=2.3.1, torchvision>=0.18.1, GPU CUDA
cd sam2 && pip install -e . && pip install -e ".[notebooks]"
pip install matplotlib==3.7 tikzplotlib jpeg4py opencv-python lmdb pandas scipy loguru
cd checkpoints && ./download_ckpts.sh   # tải sam2.1_hiera_{tiny,small,base_plus,large}.pt
```

Checkpoints (chọn theo tốc độ/độ chính xác):
| Model | Config | Ghi chú |
|---|---|---|
| `sam2.1_hiera_tiny.pt` | `sam2.1_hiera_t.yaml` | Nhanh nhất → phù hợp real-time |
| `sam2.1_hiera_small.pt` | `sam2.1_hiera_s.yaml` | Cân bằng |
| `sam2.1_hiera_base_plus.pt` | `sam2.1_hiera_b+.yaml` | Mặc định của demo |
| `sam2.1_hiera_large.pt` | `sam2.1_hiera_l.yaml` | Chính xác nhất, chậm |

Chạy demo:
```bash
python scripts/demo.py --video_path video.mp4 --txt_path bbox_frame0.txt \
    --model_path sam2/checkpoints/sam2.1_hiera_base_plus.pt
```

Hiệu năng tham khảo (từ comment trong code): model 768×768 đạt ~**27 FPS** với 1 object (GPU), giảm còn ~24 nếu `offload_state_to_cpu`.

---

## 5. ⚠️ Khoảng trống so với yêu cầu đề tài (việc ta phải làm)

| Yêu cầu đề tài | SAMURAI có sẵn? | Phải tự xây dựng |
|---|---|---|
| Segmentation mask theo thời gian | ✅ SAM 2 mask decoder | — |
| Motion Memory | ✅ KF + memory bank selection | — |
| Temporal Propagation | ✅ Memory attention của SAM 2 | — |
| Che khuất / mất dấu | ✅ (nhờ KF + lọc memory) | Cần thêm cơ chế **tái nhận diện** rõ ràng |
| **Video real-time từ Camera USB/IP** | ❌ FAQ #2: *"Not yet support streaming/webcam"* | ⭐ **Pipeline streaming**: đọc frame từ `cv2.VideoCapture`, xử lý từng frame (không load cả video) |
| **Người dùng chọn đối tượng tương tác** | ❌ Prompt lấy từ file txt | ⭐ **UI chọn bbox/click** trên frame đầu (chuột OpenCV) hoặc tự detect + chọn |
| **Hiển thị quỹ đạo di chuyển real-time** | ❌ Demo chỉ ghi video output | ⭐ Vẽ trajectory (lưu tâm bbox các frame) + hiển thị trực tiếp |
| **Đo FPS, độ trễ, CPU/GPU** | ❌ | ⭐ Module benchmark/metrics |
| Tối ưu real-time | Một phần (tiny/small ckpt, fp16) | ⭐ Giảm resolution, TensorRT/ONNX (nếu kịp), threading capture |

**Thách thức kỹ thuật chính:** `init_state()` của SAM 2 load toàn bộ frames của video → không phù hợp stream vô hạn. Hướng xử lý:
1. Xây wrapper streaming: duy trì `inference_state`, nạp frame dần (tham khảo issue facebookresearch/sam2#90, #388).
2. Chạy `propagate_in_video` theo từng bước frame mới đến (generator step).
3. Giới hạn bộ nhớ: chỉ giữ features cần thiết, offload CPU.

---

## 6. Định hướng kiến trúc hệ thống của đề tài (dựa trên SAMURAI)

```
┌─────────────┐   ┌──────────────────┐   ┌─────────────────────────┐
│ Camera USB/ │──▶│ Preprocessing     │──▶│ SAMURAI Tracker         │
│ IP (OpenCV) │   │ (resize, RGB...)  │   │ ├─ SAM 2.1 (seg+prop)   │
└─────────────┘   └──────────────────┘   │ ├─ Kalman Filter (motion)│
                                         │ └─ Memory bank selection │
┌─────────────┐   ┌──────────────────┐   └───────────┬─────────────┘
│ UI hiển thị │◀──│ Visualization    │◀──────────────┘
│ + chọn obj  │   │ mask/bbox/quỹ đạo│         │
│ + FPS meter │   │ + metrics logger │◀── Metrics (FPS, latency)
└─────────────┘   └──────────────────┘
```

## 7. Tài liệu tham khảo

- Repo: https://github.com/yangchris11/samurai
- Paper: https://arxiv.org/abs/2411.11922
- SAM 2 gốc: https://github.com/facebookresearch/sam2 (paper arXiv:2408.00714)
- Discussion streaming/webcam: facebookresearch/sam2 issue #90, #388
- Checkpoints: https://github.com/facebookresearch/sam2?tab=readme-ov-file#model-description
