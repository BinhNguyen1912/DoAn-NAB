# Ngày 08-11-2026 — Quét source, commit tồn đọng, đo lại độ phân giải + kích thước model

## 🎯 Mục tiêu
- Trả lời: *"máy không GPU thì giảm tải thế nào mà vẫn xong đồ án? có nên đổi model xịn hơn SAMURAI không?"* — **bằng số đo**, không bằng suy đoán (AGENTS.md §6 "đo trước, hứa sau").
- Dọn cây làm việc: 19 file sửa + ~50 file số liệu chưa commit từ các phiên 02–05/11.

## 📥 Input
- Máy: MSI Modern 14 B11MOU — i7-1195G7 (4 nhân/8 luồng), 16 GB, **Iris Xe, không CUDA**.
- Checkpoint có sẵn: `samurai/sam2/checkpoints/sam2.1_hiera_{tiny,small,base_plus,large}.pt`.
- Video thật: `data/binh1.mp4`, bbox `104,308,209,287` (vật thể, 640×480).
- Nền tảng: `docs/research/03` (mục tiêu thực dụng **≥10 FPS**), `docs/research/05`, `data/*_summary.json`.

## 🔨 Công việc đã thực hiện
1. **Quét source**: 13 module `src/` (2.925 dòng) + 6 `tools/`; đồ thị import **không có chu trình**; 5 seam mở rộng (`video_source`, `tracker_engine`, `on_frame`, `smooth_display`, `sampler`).
2. **Xác minh trước khi commit**: `./run lint` → *All checks passed*; `./run test` → **362 passed, 5 deselected (43 s)**.
3. **Commit 3 lần** (5ba07e8 code+tests, e3f40ff docs, fc044f2 data) → cây sạch.
4. **Sweep kích thước model** @`image_size 256`, 8 frame, steady-state (bỏ frame 0):
   `data/sweep_{tiny,small,base_plus,large}_256_{metrics.csv,summary.json}`.
5. **Sweep độ phân giải** tiny @160/192/224/256 (+320 từ `data/fix1104b_summary.json`).
6. **Sweep chất lượng ↔ tốc độ trên video THẬT** (`binh1.mp4`, 60 frame, `--reid --reid-cue object`):
   `data/qs_{192,256,320}_{metrics.csv,summary.json}`.
7. **Đo chất lượng phân đoạn** bằng `scripts/experiment_lighting.py` @192 và @160
   (`data/lighting_iou_{160,192}_summary.json`).

## 📤 Output / Kết quả

### A. Kích thước model — "model xịn hơn" trên CPU = CHẬM hơn (cùng video, cùng 256)
| Model | ms/frame (ss) | FPS | so với tiny |
|---|---|---|---|
| **SAM 2.1 tiny** | **184** | **5,45** | 1,0× |
| SAM 2.1 small | 241 | 4,14 | 1,3× chậm |
| SAM 2.1 base+ | 585 | 1,71 | **3,2× chậm** |
| SAM 2.1 large | 754 | 1,33 | **4,1× chậm** |

### B. Độ phân giải (tiny, video `binh1.mp4`, 8 frame)
| image_size | ms/frame (ss) | FPS | IoU (fixture, gain 1.0) |
|---|---|---|---|
| 160 | 78 | 12,7 | 0,924 |
| **192** | **97** | **10,3** | 0,903 |
| 224 | 128 | 7,8 | — |
| 256 | 184 | 5,45 | — |
| 320 | ~234–245 | ~4,1 | **0,974** |

→ Chi phí ≈ `10 + 0,0027 × S²` ms (S = image_size). **192 là mốc cắt 10 FPS** — đúng ngưỡng "real-time thực dụng" đã đặt ở `docs/research/03` §6.4.

### C. Video THẬT 60 frame, bật re-ID vật thể (quan trọng nhất)
| image_size | ms/frame (ss) | FPS | p95 | mất dấu | score TB |
|---|---|---|---|---|---|
| **192** | **120** | **8,35** | 154 | **0/60** | **6,47** |
| 256 | 254 | 3,94 | 423 | 0/60 | 5,67 |
| 320 | 306 | 3,26 | 365 | 0/60 | 4,88 |

→ Trên clip thật, **192 không mất dấu frame nào**, score còn *cao hơn* 320 (6,47 vs 4,88), nhanh **2,5×**.
→ Chi phí re-ID khi đang bám: **+27 ms/frame** (97 → 124 ms @192) — chiếm 22 %, do `object_signature` chạy mỗi frame để thu mẫu.

### D file thay đổi
- `src/*`, `tools/*`, `tests/*`, `scripts/*`, `run` — commit `5ba07e8` (vật chạm mép, resource_usage, snapshot relay, HUD cache).
- `AGENTS.md`, `README.md`, `docs/*`, `.scratch/*` — commit `e3f40ff`.
- `data/*` (~50 file số liệu) — commit `fc044f2`.
- Mới: `data/sweep_*`, `data/qs_*`, `data/lighting_iou_160|192_*`.

## 🐞 Vấn đề gặp phải & cách xử lý
1. **Đổi checkpoint mà không đổi `model_cfg` → crash `size mismatch`** (tiny là 768 chiều, small là 384…). Không có cờ `--model-cfg` trong CLI.
   → Cách xử lý: tạo YAML tạm chỉ có `model_cfg: configs/samurai/sam2.1_hiera_<s|b+|l>.yaml` rồi truyền `--config`.
   → Đường dẫn này là **tương đối theo package hydra `sam2`**, KHÔNG phải đường dẫn filesystem (truyền `samurai/sam2/sam2/configs/...` → `MissingConfigException`).
2. **`image_size` 160 cho IoU cao hơn 192** (0,924 vs 0,903) — trái trực giác. Fixture chỉ có 1 ô vuông lớn, 12 frame ⇒ chênh 0,02 nằm trong nhiễu fixture. Kết luận an toàn: **320 (0,974) > ≤192 (~0,90–0,92)**; đừng đọc thứ tự giữa 160 và 192.
3. **`/tmp` dùng được nhưng `python` không có trên PATH** — phải gọi `.venv/bin/python` (torch 2.14.1+cpu) thay vì `python`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Thêm cờ **`--infer-max-fps`** (giới hạn nhịp suy luận, ví dụ 10): CPU hiện bị vắt 37–43 % máy liên tục → giảm nhiệt, hiển thị vẫn 30 FPS nhờ `smooth_display`.
- [ ] Giảm chi phí re-ID khi **đang bám**: thu mẫu `object_signature` mỗi N frame thay vì mỗi frame (đo được +27 ms/frame).
- [ ] Đặt mặc định demo: `./run fast` → `image_size 192`; số liệu chất lượng trong báo cáo giữ 320.
- [ ] Đo lại trên clip **vật nhỏ** (chai/bút) ở 192 — nghi vấn: vật < ~50 px trong frame 640×480 có thể mất mask.

## 📚 Tài liệu tham khảo
- `docs/research/03-kha-nang-real-time-tren-laptop-cpu-igpu.md` §6 (ngưỡng ≥10 FPS, EdgeTAM/EfficientTAM)
- `docs/research/05-ket-qua-benchmark-prototype-sam2-tiny.md` (encoder 1,6 s @1024; INT8 chỉ nhanh 19 %)
- `docs/task/05-11-2026-tang-toc-256-toi-uu-hud-va-nguon-snapshot.md` (trần 175 ms @256)
- Số đo mới: `data/sweep_*`, `data/qs_*`, `data/lighting_iou_160|192_summary.json`
