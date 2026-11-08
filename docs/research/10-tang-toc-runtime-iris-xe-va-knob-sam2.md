# Đòn tăng tốc runtime SAM 2.1/SAMURAI trên Iris Xe (không CUDA) — xếp hạng theo số đo

> Máy chuẩn: MSI Modern 14 B11MOU — i7-1195G7 (Tiger Lake, 4 nhân/8 luồng), 16 GB, Iris Xe 96EU, WSL2.
> Ngày: 08-11-2026.
> Quy ước: số in đậm = **đo trên chính máy này** (có file repo chứng); số thường kèm URL = nguồn ngoài;
> "ƯỚC LƯỢNG" = suy luận có nêu giả định; "N/A" = không có số công bố kiểm chứng được.
> Hạn chế: phần số đo ngoài cho OpenVINO-GPU/DirectML **chưa truy xuất được trong phiên** (xem mục 6).

## 1. Kết luận

**Đòn duy nhất ĐÃ kiểm chứng ≥2× trên máy này là giảm `image_size`** (320→192 = 2,4×; 256→192 = 1,9×;
video thật @192 còn 0/60 mất dấu — `docs/task/08-11-2026-...` §B/C). Hai đòn còn lại có khả năng ≥2×
nhưng **chưa** kiểm chứng:

1. **Giảm nhịp suy luận** (propagate mỗi 2 frame / `--infer-max-fps`) — 2× FPS cảm nhận, công sức ~1 giờ.
2. **OpenVINO GPU plugin chạy native Windows** (iGPU Iris Xe FP16) — đòn duy nhất có thể ≥2× trên
   *chính encoder*; ƯỚC LƯỢNG 2–4× (giả định mục 3.1); công sức 1–2 ngày.
3. Mọi đòn runtime CPU khác (ONNX INT8, OpenVINO CPU, IPEX/bf16, torch.compile) đều **<1,3× hoặc bị
   chặn upstream** — xem bảng §2.

Knob SAM2/SAMURAI (num_maskmem, obj ptrs, multimask) chỉ cắt được phần memory/decoder ~44 ms trong
tổng 175 ms @256 ⇒ trần lý thuyết ~10–20 %, **không phải đòn ≥2×**.

## 2. Bảng đòn tăng tốc

| # | Đòn | Lợi (×) | Công sức | Kiểm chứng trên máy này? | Nguồn |
|---|---|---|---|---|---|
| 1 | `image_size` 256→192 (hoặc 320→192) | **1,9× (2,4×)** — 184→97 ms (đo) | 0 (cờ có sẵn) | ✅ ĐÃ ĐO, video thật 0/60 mất dấu | `docs/task/08-11-2026-...` §B/C |
| 2 | Giảm nhịp suy luận (propagate mỗi N frame, giữ hiển thị mượt) | 2× cảm nhận (bỏ 1/2 lần propagate) | ~1 giờ | ✅ Đo được <1 ngày (headless, video file) | `docs/task/08-11-2026-...`; `src/live_pipeline.py` |
| 3 | OpenVINO GPU plugin (Iris Xe, **native Windows**, FP16) | ƯỚC LƯỢNG 2–4× encoder (giả định: Hiera map tốt lên GPU plugin, LPDDR4x không cổ chai) | 1–2 ngày | ❌ Chưa — WSL không thấy iGPU | `docs/research/05` §1; notebook OpenVINO |
| 4 | `num_maskmem` 7→3 + `max_obj_ptrs_in_encoder` 16→8 | ƯỚC LƯỢNG 1,05–1,15× pipeline (memory/decoder = 44/175 ms @256) | ~2 giờ (hydra override) | ✅ Đo được <1 ngày | `samurai/sam2/sam2/modeling/sam2_base.py:636-690` |
| 5 | IPEX / INT8 VNNI / bf16 / channels_last | ≤1,2–1,3× (ƯỚC LƯỢNG; căn cứ: ONNX INT8 chỉ +19 % @1024 và CHẬM HƠN @320) | 0,5–1 ngày | ✅ Đo được, kỳ vọng thấp | `docs/research/05` §1; `docs/task/05-11-2026-...` §2 |
| 6 | ONNX Runtime + DirectML EP (Windows) | N/A | 0,5–1 ngày | ❌ Chưa | N/A |
| 7 | torch.compile encoder | **BỊ CHẶN upstream** — config chính thức: "HieraT does not currently support compilation" | — | — | `configs/samurai/sam2.1_hiera_t.yaml` (`compile_image_encoder: False`) |
| 8 | Đổi backbone EdgeTAM/EfficientTAM | Ngoài phạm vi "đòn runtime" | nhiều ngày | ❌ | `docs/research/03` §4 |

## 3. Chi tiết

### 3.1 OpenVINO GPU plugin trên Iris Xe native Windows
- **Đã đo (máy này, WSL):** OpenVINO chỉ thấy device `CPU` — 1.613 ms @1024 (`docs/research/05` §1);
  2.055 ms @1024 ở lần đo 05-11 (`docs/task/05-11-2026-...` §2). Muốn dùng iGPU phải chạy Python
  **native Windows**.
- **Số ngoài gần nhất:** AnnotateIt benchmark (Core Ultra 9 386H, browser WASM/WebGPU, @1024):
  encoder tiny 2,19 s trên iGPU-WebGPU vs 2,82 s CPU multithread ⇒ **iGPU chỉ ~1,3×** — nhưng là
  browser runtime, không phải OpenVINO native, và chip khác (16 nhân).
  URL: https://annotateit.ai/docs/sam2-benchmark/
- **Số SAM2-encoder trên Iris Xe qua OpenVINO native Windows: N/A.**
- Giới hạn: iGPU dùng **FP16** (nguồn blog Intel-iGPU+SAM2: https://note.com/todamah/n/n2a2894126d9b).
  Notebook chính thức: https://docs.openvino.ai/2024/notebooks/segment-anything-2-image-with-output.html

### 3.2 ONNX Runtime + DirectML
- Trên máy này `onnxruntime` chỉ có `CPUExecutionProvider`; `onnxruntime-directml` chưa đo.
- Số SAM2 + DirectML: **N/A**.
- Tool export chính thức: https://github.com/microsoft/onnxruntime/blob/main/onnxruntime/python/tools/transformers/models/sam2/README.md

### 3.3 torch.compile / IPEX / bf16 trên Tiger Lake
- **AMX:** Tiger Lake **không có AMX** (AMX từ Sapphire Rapids); Tiger Lake có AVX-512 + VNNI ⇒ mọi
  đường "AMX bf16" của IPEX không áp dụng.
- **torch.compile:** bị chặn chính thức cho HieraT (xem bảng #7, nguồn config trong repo).
- **INT8:** ONNX Runtime INT8 chỉ nhanh 19 % @1024 (1.771→1.376 ms) và **chậm hơn PyTorch ở 320**
  (196 vs 166 ms) ⇒ IPEX cùng bậc.
- bf16/channels_last: không có số đo cho Hiera/SAM2 trên Tiger Lake — N/A.

## 4. Knob SAM2/SAMURAI (đọc từ mã nguồn vendored — nguồn sơ cấp)

**Encoder có chạy lại mỗi frame không? — CÓ, và không cache được.**
`sam2_video_predictor.py:879-892`: `cached_features` chỉ giữ **đúng 1 frame gần nhất** (comment
upstream: *"Cache the most recent frame's feature … we can use an LRU cache for more frames in the
future"*). Streaming 1 chiều ⇒ frame mới = cache miss = encode lại. Cache chỉ giúp khi nhiều object
chia sẻ 1 frame (expand batch).
→ **"Cache embedding để tái dùng" là đường cụt** — khớp với đo thực nghiệm: dùng lại feature cũ cho
K-1 frame cho 13,3 FPS nhưng IoU 0,966→0,840 (`scripts/exp_encoder_reuse.py`).

**`num_maskmem` (mặc định 7 = 1 cond + 6 non-cond):** `sam2_base.py:32` + config dòng 87. Chi phí
memory cross-attention **tỉ lệ thuận** số frame memory ⇒ 7→3 cắt ~2,3× phần cross-attn; nhưng
memory+decoder chỉ 44 ms trong 175 ms @256 ⇒ tiết kiệm tuyệt đối nhỏ.

**`max_cond_frames_in_attn = -1`** (không giới hạn, `sam2_base.py:43`) — streaming chỉ có 1–2 cond
frame nên cap không đổi gì trên máy này.

**Selection memory bank của SAMURAI là knob CHẤT LƯỢNG, không phải tốc độ.**
`sam2_base.py:660-689` (nhánh `samurai_mode`): frame trước vào memory khi `iou > 0,5` **và**
`obj > 0,0` **và** `kf > 0,0`; luôn giữ frame `t−1`; quét tối đa `max_obj_ptrs_in_encoder − 1 = 15`.
Selection đổi *frame nào* attend, không đổi *bao nhiêu* frame (trần vẫn `num_maskmem`).

**`multimask_output_for_tracking: true`** — decoder sinh 3 mask/frame thay vì 1; tắt tiết kiệm vài ms
nhưng mất lựa chọn mask tốt nhất.

**`memory_temporal_stride_for_eval`** (`sam2_base.py:63-64`) — r>1 làm thưa memory, tương đương
giảm `num_maskmem`.

## 5. Top 3 nên thử trong 1 ngày (đều headless, không cần webcam)

1. **`--infer-max-fps` / propagate mỗi 2 frame** (~1 giờ): 2× FPS suy luận cảm nhận, HUD vẫn mượt nhờ
   `smooth_display`.
2. **Sweep knob memory** `++model.num_maskmem={3,4,7}` × `++model.max_obj_ptrs_in_encoder={8,16}`
   (hydra override, không sửa code), đo @192 và @256, kiểm mất dấu trên `data/binh1.mp4`.
3. **Python Windows native + OpenVINO GPU**: export IR encoder @256, đo `GPU` vs `CPU` plugin cùng
   script. Phép thử duy nhất có thể chạm ≥2× trên encoder — nếu <1,5× thì đóng hướng iGPU bằng dữ kiện.

## 6. Nguồn

**Mã nguồn vendored (sơ cấp):** `samurai/sam2/sam2/sam2_video_predictor.py:879-892`;
`samurai/sam2/sam2/modeling/sam2_base.py:32,43,63-71,636-690`;
`samurai/sam2/sam2/configs/samurai/sam2.1_hiera_t.yaml`; `src/live_pipeline.py`; `src/tracker_engine.py`.

**Số đo trong repo:** `docs/research/05` §1; `docs/task/05-11-2026-...`;
`docs/task/08-11-2026-do-lai-do-phan-giai-va-kich-thuoc-model.md`;
`docs/task/22-10-2026-colab-gpu-so-lieu-va-fix.md` (T4 49,6 ms = 20,15 FPS).

**Ngoài (URL ghi tại `docs/research/03` §7):** annotateit.ai/docs/sam2-benchmark/;
note.com/todamah/n/n2a2894126d9b; docs.openvino.ai (notebook SAM2); github.com/microsoft/onnxruntime
(sam2 export); github.com/wp133716/samurai-onnxruntime; egordmitriev.dev (optimizing-samurai).

**Hạn chế:** phiên research này không có web tool ⇒ các mục #3, #6 phần số ngoài là N/A; mục đánh dấu
「kiến thức phần cứng」 cần trích ark.intel.com trước khi đưa vào báo cáo chính thức.
