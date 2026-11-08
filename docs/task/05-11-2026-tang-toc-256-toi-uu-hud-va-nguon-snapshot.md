# Ngày 05-11-2026 — Tăng tốc pipeline: `image_size 256` (2,2×) + tối ưu HUD + nguồn snapshot

> Tiếp ngay sau log [05-11 webcam/usbipd](05-11-2026-webcam-usbipd-ket-o-driver-khong-phai-wsl.md)
> trong cùng buổi làm. Bối cảnh: người dùng demo bằng webcam qua relay, đo được **469 ms/frame
> (2,1 FPS)** và hỏi "vì sao yếu, có train lại model được không, có model nào hơn SAMURAI".
> Demo lại vào tuần sau ⇒ có ~5 ngày để cải thiện.

## 🎯 Mục tiêu
- Xác định **chi phí thật** của từng phần trên máy CPU-only, bằng số đo (không đoán).
- Kiểm chứng đề xuất "tích hợp ONNX Runtime INT8 cho encoder" trước khi đầu tư 1–2 ngày.
- Tăng FPS thực đo được, không đổi kiến trúc SAMURAI (giữ 3 trụ đề tài để bảo vệ).

## 📥 Input
- Máy: **MSI Modern 14, i7-1195G7 (4 nhân/8 luồng), Iris Xe iGPU, KHÔNG GPU rời**;
  `torch 2.14.1+cpu`, `cuda False`, `threads=4`; WSL thấy 8 lõi / 7 GB.
- Checkpoint đang dùng: `samurai/sam2/checkpoints/sam2.1_hiera_tiny.pt` + `configs/samurai/sam2.1_hiera_t.yaml`
  (đã là bản **tiny** — không còn bản nhỏ hơn).
- Số liệu người dùng dán: lần 320 → `469 ms/frame, 2,1 FPS, mất dấu 15%`; lần 256 → `223 ms, 5,45 FPS, mất dấu 20%`.

## 🔨 Công việc đã thực hiện

### 1. Đo lại từng tầng (số thật, cùng máy, cùng buổi)
| Phép đo | Kết quả |
|---|---|
| Encoder SAM 2.1 tiny, PyTorch CPU, `image_size 320` | **167 ms** (8 threads: 150 ms → chỉ +10%) |
| Encoder, `image_size 256` | **122 ms** |
| cProfile pipeline headless (video file, 256) | propagate 175 ms/frame, trong đó `forward_image` **124 ms** + memory/decoder **44 ms** + pipeline **~7 ms** |
| `HttpVideoSource.read()` (MJPEG 640×480) | 30,2 ms/frame (phần lớn là **chờ** relay phát 20 fps) |
| HTTP + `imdecode` từ `/snapshot.jpg` | **8,4 ms/frame** |
| `Visualizer.render()` đủ HUD | **16,5 ms** (trong đó 2,4 ms/dòng chữ) |

### 2. Kiểm chứng đề xuất ONNX INT8 — **bị bác bỏ bằng số đo**
| Backend, encoder, `image_size 320` | ms |
|---|---|
| PyTorch CPU | **166** |
| ONNX Runtime fp32 | 219 (0,76×) |
| ONNX Runtime INT8 | 196 (0,85×) |

ONNX chỉ thắng ở 1024 (1447 vs 2820 ms). Ngoài ra model INT8 có sẵn bị **fix cứng `[1,3,1024,1024]`**,
muốn dùng ở 320 phải export lại (mà kết quả vẫn chậm hơn). OpenVINO: chỉ thấy device `CPU`
(iGPU không được nhận), 2055 ms @1024. `onnxruntime` chỉ có `CPUExecutionProvider` (không DirectML).
⇒ Không đầu tư 1–2 ngày vào hướng này.

### 3. Hai thay đổi code (đều có test)
1. **`src/visualizer.py` — chữ HUD không còn chuyển cả khung sang PIL.**
   Cũ: mỗi dòng chữ `cvtColor` cả khung 640×480 → PIL → vẽ → `cvtColor` ngược = **2,4 ms/dòng**.
   Mới: `_glyph_bgr()` render glyph **một lần** cho mỗi (text, font, cỡ, màu) vào canvas nhỏ
   (`lru_cache` 256), rồi alpha-blend vào đúng **ROI** của chữ (có cắt biên khi HUD sát mép).
   Đo lại: `render()` đủ HUD + banner **16,5 → 2,3 ms** (7×).
   Vì sao quan trọng: chế độ `--smooth` vẽ ~30 FPS ⇒ riêng phần chữ trước đây đốt **~50% một lõi CPU**
   (đúng thủ phạm làm CPU 427% và inference bị chậm từ 175 → 223 ms).
2. **`src/video_source.py` — `HttpSnapshotSource`** (nguồn ảnh JPEG rời).
   `is_snapshot_url()` tự nhận URL `.jpg/.jpeg` hoặc chứa `/snapshot`; mở lỗi báo rõ đường dẫn;
   `read()` giữ **frame cuối** khi mạng chập chờn, chỉ kết thúc sau `max_misses` lần hỏng liên tiếp.
3. `scripts/cam_relay.sh` thêm `snapurl`; `./run demoip` dùng `/snapshot.jpg` thay `/video`.

## 📤 Output / Kết quả
| Cấu hình | ms/frame | FPS | Ghi chú |
|---|---|---|---|
| 320 + MJPEG + display (đầu ngày) | 469 | 2,1 | baseline của người dùng |
| **256 + MJPEG + display** (người dùng chạy) | **223** | **5,45** (đo từ CSV: 183 ms mọi frame) | **2,26×**, p95 1098 → 248 ms |
| 256, headless, video file | 175 | 5,72 | trần của pipeline (không display/relay) |
| 256, headless, relay MJPEG | 176 | 5,69 | |
| 256, headless, relay `/snapshot.jpg` | **171** | **5,85** | −5 ms nhờ ảnh rời |
| HUD render (sau tối ưu) | 16,5 → **2,3** | — | giải phóng ~0,5 lõi ở chế độ mượt |

- **Cổng kiểm tra:** `./run lint` → All checks passed · `./run test` → **351 passed, 5 deselected** (46,5 s)
  (+6 test mới: 4 cho `HttpSnapshotSource`, 2 cho tối ưu vẽ chữ — gồm test khoá cache glyph và test
  "chữ không lem ra toàn khung").
- **Kiểm chứng bằng mắt:** render 1 khung HUD ra PNG, xem lại — tiếng Việt có dấu ("Độ trễ") đúng,
  mask + ô bao + quỹ đạo + banner "DANG TIM LAI... (khop 0.61)" đều đúng vị trí.
- File thay đổi:
  - `src/visualizer.py` — `_glyph_bgr()` cache + blend theo ROI (thay PIL toàn khung)
  - `src/video_source.py` — `HttpSnapshotSource` + `is_snapshot_url()` + định tuyến trong factory
  - `scripts/cam_relay.sh` — thêm `snapurl`
  - `run` — `demoip` dùng snapshot URL
  - `tests/test_visualizer.py`, `tests/test_video_source.py` — 6 test mới
  - `README.md`, `docs/cheatsheet-lenh.md` — ghi chú nguồn snapshot

## 🐞 Vấn đề gặp phải & cách xử lý
- **Đo sai một lần (tự phát hiện):** bench `read()` MJPEG ra 30,2 ms ⇒ tưởng decode đắt. Nhưng trong
  pipeline chỉ chênh 5 ms ⇒ 30 ms kia phần lớn là **chờ** relay phát 20 fps (bench đọc nhanh hơn tốc độ
  sản xuất). Bài học: bench nguồn live phải **đo trong đúng nhịp tiêu thụ**, không đọc liên tục.
- **`--reanchor-every 3` là tư vấn sai:** pipeline tự tắt cờ này khi bật re-ID
  (`[re-ID] tắt --reanchor-every: ... ADR-0003`). Toàn bộ 2,2× là nhờ 320→256, không phải reanchor.
- **Chưa tăng được nhiều như kỳ vọng:** đã hứa "223 → ~170 ms"; thực tế phần lớn 223 ms là **model**
  (124 ms encoder + 44 ms memory/decoder = 168 ms). Trần thật của pipeline là **~170–175 ms** ⇒
  mọi tối ưu quanh đó chỉ còn ~20 ms. Muốn nhanh hơn nữa phải đổi model/phần cứng, không phải tối ưu code.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Chạy lại `./run demoip` để xác nhận con số mới (dự kiến 223 → ~195–205 ms ở chế độ mượt).
- [ ] Hiệu chỉnh ngưỡng re-ID trên clip thật: xem `data/demoip_1105-125828.mp4` tại frame
      56, 61, 66, 70, 162, 248, 338, 387 rồi `./run calibrate <csv> --good … --bad …`
      (8 lần nhận lại, cosine 0,609–0,965; 2 ca 0,609/0,616 sát ngưỡng 0,6 nên cần nhãn).
- [ ] Giảm "đóng băng" khi demo: `--lost-after-frames 4`; kỹ thuật demo: giữ vật ở **giữa khung**
      (24% frame có tâm vật cách mép < 60 px chính là nguồn của 20% mất dấu).
- [ ] (Tuỳ chọn) Thử `onnxruntime-directml` để dùng Iris Xe — đường iGPU duy nhất còn lại, chưa đo.

## 📚 Tài liệu tham khảo
- `docs/research/03-kha-nang-real-time-tren-laptop-cpu-igpu.md` — trần hiệu năng CPU/iGPU của máy này.
- `docs/research/05-ket-qua-benchmark-prototype-sam2-tiny.md` — "không VOS nào đạt ≥10 FPS trên CPU 4 nhân".
- `docs/task/16-10-2026-prototype-benchmark-sam2-tiny.md` + `tools/benchmark_sam2_realtime.py` — ONNX/OpenVINO.
- `docs/task/22-10-2026-colab-gpu-so-lieu-va-fix.md` — Colab T4 **49,6 ms/frame = 20,15 FPS** (nhanh ~9×).

---

## 🔍 Bổ sung 13:12 — người dùng chạy lại: "mất dấu 85%, ngu hơn" → tìm ra nguyên nhân khác

**Người dùng báo:** `./run demoip --image-size 256` → `326 frame | mean=297 ms | mất dấu 277/326 (85%) | score tb=0.50`,
"dơ lại vật thể nhưng vẫn không dính lại".

### Loại trừ (đo, không đoán)
| Nghi vấn | Cách kiểm | Kết quả |
|---|---|---|
| Nguồn `/snapshot.jpg` trả ảnh đứng yên (lỗi mới của tôi) | đọc 5 frame liên tiếp → so pixel; rồi đọc cách nhau 1,5 s | 5 lần liền nhau giống hệt (kéo nhanh hơn camera), **cách 1,5 s thì md5 khác nhau hoàn toàn** → relay vẫn phát mới |
| Cả video ghi lại bị "đứng hình" | trích 38 mẫu từ `demoip_1105-131222.mp4`, so vùng ảnh (bỏ HUD) | **0/38 mẫu đứng yên**, diff TB 16–47 → ảnh có chuyển động thật |
| Tốc độ | đọc CSV | chỉ **49 frame có suy luận** (296 ms/frame), 277 frame còn lại `ms=0` (đóng băng, không tốn CPU) → "mean 297" là trung bình trên frame có chạy, **không phải** nguyên nhân mất dấu |

### Nguyên nhân thật: **ô chọn chạm mép khung ⇒ không bao giờ lưu được mẫu đặc trưng**
- Trong cả 48 frame đang bám, bbox luôn có `y2 = 479` (khung cao 480) → mask chạm mép.
- `src/reid.py:_collect_reference()` có cổng `cham_mep` (đặt từ 04-11 để chống mask rác khi vật
  ra khỏi khung) → **return sớm, không nạp `_obj_refs`/template/EMA**.
- Hệ quả đo được trên CSV: `reid_score = -1.000` ở **toàn bộ 325 frame** (không có ứng viên nào),
  nên máy trạng thái kẹt `reacquiring` 277 frame mà không thể nhận lại — đúng cảm giác
  "dơ lại vật mà không dính lại".
- Đối chiếu lần 12:58 (vẫn nhận lại 8 lần): các ô nằm **trong** khung (`y2 ≈ 384`) → có mẫu.

### Đã sửa (cảnh báo sớm thay vì im lặng)
1. `src/reid.py` — hàm thuần `touches_frame_edge(bbox, w, h)` + hằng `HINT_CHAM_MEP`; `start()` in
   cảnh báo ngay khi ô chọn chạm mép: *"ô chọn CHẠM MÉP khung → không lưu được mẫu đặc trưng ⇒
   mất dấu sẽ KHÔNG tự nhận lại. Bấm r rồi kéo ô bao TRỌN vật, chừa mép khung."*
2. `src/visualizer.py` — HUD khi `reid_score < 0` ghi rõ
   `"(chua co ung vien — kiem tra vat chon co cham mep khung)"`.
3. `tests/test_reid.py` — 3 test: hàm nhận diện chạm mép (4 ca dương + 2 ca âm), `start()` cảnh báo
   khi engine trả ô chạm mép (và `object_ref_count == 0`), `start()` im lặng khi ô bao trọn.

**Cổng kiểm tra sau khi sửa:** `./run lint` → All checks passed · `./run test` → **354 passed, 5 deselected** (43,2 s).

### Bài học cho buổi demo
- Kéo ô **bao trọn vật, chừa mép khung**; nếu thấy dòng `[re-ID] CẢNH BÁO: ô chọn CHẠM MÉP khung`
  thì bấm **r** chọn lại — chạy tiếp chỉ mất thời gian.
- Không đổ lỗi cho tốc độ: 277/326 frame đóng băng có `ms=0` (không tốn tài nguyên); vấn đề là
  **identity không có mẫu**, không phải FPS.

---

## ✅ Bổ sung 14:00 — vật ở MÉP BIÊN vẫn phải học được (yêu cầu người dùng)

> Người dùng: *"nhưng tao còn phải test thêm case nó ở mép biên nữa chứ"* — đúng: cảnh báo thôi
> không đủ, đề cương yêu cầu chịu được vật **ra/vào khung**.

### Thay đổi (giữ nguyên bài học 04-11, không nới lỏng bừa)
Cũ: `_collect_reference()` **bỏ toàn bộ** mẫu khi mask chạm mép → chọn vật sát mép = mù vĩnh viễn.
Mới: **cắt đúng dải mép** rồi đánh giá phần CÒN THẤY:
1. `src/appearance.py` — `clip_mask_border(mask, w, h, margin=EDGE_MARGIN=4)`: xoá vòng 4 px sát
   khung (nơi SAM 2 vẽ mask rác), trả mask sạch + bbox trong khung (mask giữ toạ độ KHUNG vì
   `object_signature`/`signature_quality_ok` đều index theo frame).
2. `src/reid.py` — `_collect_reference()`: nếu mask chạm mép thì cắt dải mép, rồi **vẫn học** nếu
   - phần thấy qua cổng chất lượng cũ (`signature_quality_ok`: diện tích ≥ 600 px², fill ≥ 0,5, cạnh ≥ 8), **và**
   - diện tích phần thấy ≥ **`EDGE_MIN_AREA_FRAC = 0,35`** × diện tích kích thước THẬT (EMA).
   Mẫu học từ vật bị cắt **không** đưa vào EMA (kích thước bị cắt < thật, đưa vào sẽ hẹp vùng tìm).
3. Cảnh báo `HINT_CHAM_MEP` đổi điều kiện: chỉ in khi **không lưu được mẫu nào**
   (`_obj_refs` và `_obj_templates` đều rỗng) — không còn báo oan cho vật ở mép vẫn học được.

### Kiểm chứng
**Unit (chống hồi quy 04-11 vẫn xanh):** dải rác 71×10 px sát đáy (1,3% diện tích vật thật 220×204)
→ **vẫn bị chặn** (cả 2 cổng: diện tích < 600 px² và < 35% EMA); EMA không bị kéo theo.

**End-to-end (video tổng hợp, vật bị khung cắt mép phải → biến mất 25 frame → hiện lại trong khung):**
| | kết quả |
|---|---|
| Ô chọn ban đầu | `(590, 180, 640, 300)` = **chạm mép phải** (vật thật rộng 120 px) |
| Cảnh báo | **không in** (đã học được mẫu) |
| Mất dấu | f20–f45 (25 frame, vật bị che 100%) |
| **Nhận lại** | **f46: cosine 0,990 · NCC 0,751** (và f50–55: cosine 0,996) — **2 lần nhận lại** |
| Tốc độ | mean 107 ms, p95 193 ms, 9,35 FPS (video 70 frame, 480×640 @256) |

Lệnh tái lập: `python tools/run_live.py --source /tmp/edge_case.avi --bbox 590,180,50,120
--image-size 256 --reid --reid-cue object --max-frames 70 --metrics-csv /tmp/edge2.csv`
(video sinh bằng script tạm: nền nhiễu + vật cam có vân, f20–44 không vẽ vật).

**Cổng kiểm tra:** `./run lint` → All checks passed · `./run test` → **362 passed, 5 deselected** (44,4 s)
(+8 test mới: 3 cho `clip_mask_border`, 5 cho "vật ở mép vẫn học được" gồm cả ca chống hồi quy).

---

## 📘 Bổ sung 14:20 — ghi rule vào `AGENTS.md` (để phiên sau không làm lại từ đầu)

Thêm **mục 6 "Kinh nghiệm đã đo — đọc trước khi sửa"** (mục 7, 8 cũ dời xuống), gồm 7 rule
đã kiểm chứng bằng số trong ngày:

1. **Đo trước, hứa sao** — đề xuất tối ưu/đổi model phải kèm số đo trên máy này trước khi đưa
   phương án nhiều ngày (dẫn chứng: ONNX INT8 chậm hơn PyTorch ở 320; `--reanchor-every` bị tắt khi bật re-ID).
2. **Máy không có GPU rời** — trần ~175 ms/frame @256, model chiếm 168/175 ms.
3. **Demo CPU dùng `image_size 256`**.
4. **Đo nguồn live ở đúng nhịp tiêu thụ** (30 ms "decode" MJPEG = chờ relay, không phải decode).
5. **`Device busy (exported)` là cờ kẹt ở driver usbipd-win** ⇒ đi relay, đừng reset WSL/reboot lại.
6. **Re-ID: vật chạm mép vẫn phải học** (`clip_mask_border` + 35% EMA); `HINT_CHAM_MEP` chỉ in khi không lưu được mẫu.
7. **Báo cáo/handoff kèm số từ CSV** (mean, p95, mất dấu, reacquired).

Đồng thời mục 5 (quy trình) bước 1 trỏ sang mục 6 khi việc liên quan hiệu năng / webcam / re-ID.
Rule đặt dạng **positive** (nêu việc cần làm) + link tới log gốc để tra số, không chép lại số liệu
chi tiết vào AGENTS.md (tránh trôi tài liệu).
