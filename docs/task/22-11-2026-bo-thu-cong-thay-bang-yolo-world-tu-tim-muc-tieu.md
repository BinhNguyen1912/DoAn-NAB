# Ngày 22-11-2026 — Bỏ phương pháp thủ công, thay bằng TỰ TÌM MỤC TIÊU theo MÔ TẢ VĂN BẢN (YOLO-World)

> Log theo `AGENTS.md` mục 2 & 9. **Đây là đổi kiến trúc (thêm model) ⇒ có đo trước khi hứa** (§6
> "Đo trước, hứa sau"), và **có phần CHƯA đo được** — ghi rõ ở mục "Hạn chế".

## 🎯 Mục tiêu
- Bỏ đường **thủ công** (người dùng click chấm điểm âm/dương trên web) vì mục tiêu cuối là **thiết bị
  camera không có màn hình/chuột**.
- Thay bằng **cue ngữ nghĩa**: YOLO-World tìm vật theo mô tả văn bản (`"remote control"`) ⇒ tự chọn ô
  lúc bắt đầu **và** tự nhận lại khi vật quay vào khung, không cần ai chạm tay.

## 📥 Input
- Yêu cầu người dùng: *"phải tự train / tự động chứ, sau này còn đưa lên thiết bị camera"*.
- Hiện trạng đã đo 21-11: `mask-cos` **không** tách được vùng sai cùng tông (0,752–0,989 nằm trong dải
  ca đúng) ⇒ mọi cổng dựa vào *màu/đặc trưng* đều mù với vật trắng trên tường trắng.

## 🔬 ĐO TRƯỚC KHI CODE (CPU Iris Xe, không GPU rời, torch 2.14.1+cpu)

| Việc đo | Kết quả |
|---|---|
| `yolov8s-worldv2.pt` (25 MB) — tốc độ `imgsz=320` | **38–52 ms/lần** (19–26 FPS) |
| cùng model `imgsz=640` | 160–242 ms/lần (4–6 FPS) |
| Detect trên `data/remote_trang.mp4` (hình chữ nhật trắng tổng hợp) | **0 box** ở cả 320 và 640 ⇒ **clip tổng hợp KHÔNG nghiệm thu được hướng này** |
| Detect trên `data/binh1.mp4` với lớp `remote control` | 0,38 box/frame, `conf` **0,29–0,30** = dương tính giả ⇒ ngưỡng mặc định phải **≥ 0,30** |
| Chạy THẬT `./run autodemo "bottle" --source data/binh1.mp4` (model thật, **không có bbox.json**) | `[auto] YOLO-World thấy 'bottle' conf=0.79 box=(298,285,437,737) · 207 ms` → phiên tự bám: **25–40 frame**, `display 29,1–29,3 FPS`, `bam=tracking`, `image_size_hieu_luc=192` |

Artifact: `data/auto_detect_2026-11-22_metrics.json` (có `git_rev`, `lenh`, `do_luc`).

## 🛠️ Công việc đã thực hiện
1. **`src/open_vocab_detector.py` (mới)** — bọc YOLO-World:
   - `available` chỉ kiểm **file weights**; `load()` mới import `ultralytics` (import nặng).
   - **Fail-open tuyệt đối**: thiếu weights / thiếu thư viện / `predict` ném ⇒ `detect()` trả `[]` +
     `last_error`, `calls` **không** tăng (để không ai đọc `0` thành "đã chạy mà không thấy gì").
   - `last_ms` + `calls` để artifact nói được "đã đo hay chưa". Ngưỡng mặc định **0,30** (đo được
     dương tính giả ở 0,29–0,30 ⇒ 0,25 là quá thấp).
2. **`src/live_tracking.py`** — `LiveTrackConfig.auto_detect / auto_detect_every / auto_detect_conf`;
   `_auto_selection()` chạy detector **tối đa 1 lần mỗi N frame đang CHỜ** (throttle vì 38–52 ms/lần),
   loại ô < 16 px (cùng ngưỡng `PromptSelector.MIN_BOX`), trả `PromptSelection` ⇒ **phiên tự bám khi
   KHÔNG có `bbox.json`** (đường thiết bị).
3. **`src/reid.py`** — **cue 0**: tìm lại theo mô tả văn bản, đặt **TRƯỚC** `if not self.enabled`
   (cue này không dùng mẫu đặc trưng ⇒ phải chạy được cả khi `--reid` tắt). Vẫn qua `_confirm`
   (2 frame cùng chỗ) + **cổng hình học** `geo_profile.is_compatible` ⇒ detector một mình không đủ tin.
   Đếm `detector_hits` / `detector_rejects` để biết cổng hình học có ăn hay không.
4. **`tools/live_worker.py`** — `--auto-detect "<mô tả>"`, `--auto-detect-every`, `--auto-detect-conf`;
   validate: `every ≥ 1`, `conf ∈ (0,1]`, và **chặn `--auto-detect` + `--bbox` cùng lúc** (hai đường
   cùng chỉ định mục tiêu thì không rõ cái nào thắng).
5. **`./run autodemo "remote control" [--source …]`** — một lệnh, không cần chọn ô.
6. **BỎ ĐƯỜNG THỦ CÔNG trên web**: revert `SelectionCanvas`/`LivePanel`/`selection.ts` về bản trước
   (không còn click chấm điểm xanh/đỏ). Backend vẫn giữ `points/labels` vì `_reacquire` dùng
   `generate_contrast_points` **tự động** — đó là thuật toán, không phải thao tác tay.
7. **`requirements.txt`** — `ultralytics>=8.3` ở nhóm **TUỲ CHỌN** kèm lệnh tải weights (25 MB,
   `*.pt` bị `.gitignore` chặn).

## 📤 Output / Kết quả
- `./run lint` → All checks passed.
- `./run test` → **1749 passed, 5 deselected** (thêm 11 test: 6 detector + 5 auto-chọn/cue 0).
- `./run webtest` → 81 passed; `npm run build` sạch.
- File: `src/open_vocab_detector.py` (mới), `tests/test_open_vocab_detector.py` (mới),
  `src/live_tracking.py`, `src/reid.py`, `tools/live_worker.py`, `run`, `requirements.txt`,
  `data/auto_detect_2026-11-22_metrics.json`.

## ⚠️ Hạn chế — PHẢI đọc trước khi hứa với hội đồng
1. **CHƯA đo trên vật thật "remote trắng trơn"**: repo không có footage. Trên clip tổng hợp detector
   trả **0 box** (hình chữ nhật trơn không phải "cái điều khiển" về ngữ nghĩa) ⇒ **cấm** trích
   `remote_trang.mp4` làm bằng chứng cho hướng này. Cần **quay 1 clip thật** trước khi kết luận.
2. Detector chỉ biết **lớp có trong YOLO-World**; vật lạ (bút bi, kính) có thể **không có lớp** phù hợp
   ⇒ đường VOS tương tác (kéo ô) vẫn phải tồn tại, chỉ là không còn là đường *bắt buộc*.
3. Phụ thuộc **tuỳ chọn**: `ultralytics` + 25 MB weights + CLIP text encoder (lần đầu tự cài
   `clip`, `ftfy`, `regex`) ⇒ trên thiết bị nhúng phải export ONNX/TensorRT riêng (chưa làm).
4. **Chưa train lại model nào.** Quyết định: **không** fine-tune SAM 2 (51k video, sẽ hỏng tính tổng
   quát) — thêm *một* model detector nhẹ là cách đúng để đưa lên thiết bị.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Quay clip thật: remote trắng trên tường trắng (có đoạn rời khung rồi quay lại) → chấm lại bằng
      `./run autodemo "remote control"` + `./run miou` để có số **thật**.
- [ ] Đo A/B: `--auto-detect` BẬT/TẮT trên cùng clip, 3 lần, theo `./run ab` (nêu ngưỡng nhiễu).
- [ ] Export ONNX/OpenVINO cho thiết bị nhúng (`openvino` đã có sẵn trong env) — chỉ khi hướng này
      qua được bước đo bằng clip thật.

## 📚 Tài liệu tham khảo
- YOLO-World (CVPR 2024): open-vocabulary detection bằng text prompt.
- `docs/task/21-11-2026-ticket-01..04-*.md` (đường thủ công trước đó, nay chỉ còn phần TỰ ĐỘNG).
