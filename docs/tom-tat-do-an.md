# Tóm tắt đồ án — đọc 5 phút là hiểu hết

> **Đây là file duy nhất cần đọc để hiểu mình đang làm gì.**
> Muốn số liệu chi tiết → `README.md` mục 7. Muốn giải thích dài → `docs/giai-thich-do-an.md`.
> Muốn biết phần nào tự viết → `docs/team-contribution.md`.

---

## 1. Một câu

Camera AI bám bắt **1 đối tượng** theo thời gian thực: người dùng **kéo chuột** chọn đối tượng →
hệ thống **phân đoạn (mask)** và **bám theo** qua từng frame → **giữ được khi bị che khuất** →
**mất dấu thì dừng chứ không bám sang người khác** → **tự bám lại đúng người khi họ quay lại** →
vẽ **quỹ đạo + FPS + độ trễ** lên màn hình và **ghi số liệu ra file**.

---

## 2. Một frame chạy qua những gì (đây là toàn bộ hệ thống)

```
1. src/video_source.py     read()          → lấy 1 frame từ webcam / camera IP / file
2. src/live_pipeline.py    vòng lặp         → quyết định frame này làm gì
3. src/reid.py             ReIdSession.step → đang bám? mất dấu? đang tìm lại?
4. src/tracker_engine.py   process(frame)   → SAM 2 trả MASK + bbox + điểm tin cậy + ms
5. src/visualizer.py       update(...)      → vẽ mask, ô bao, quỹ đạo, HUD 4 dòng
6. src/metrics_logger.py   log(record)      → ghi CSV/JSON (ms, score, tâm, lost, state)
```

Người dùng tác động ở bước 2 qua `src/prompt_selector.py` (kéo chuột chọn, phím `r` chọn lại).

---

## 3. Năm module — nhớ đúng 5 cái này là đủ

| Module | Nhiệm vụ | File |
|---|---|---|
| **VideoSource** | 1 interface cho 5 nguồn: webcam, **camera USB**, RTSP, MJPEG-HTTP (điện thoại), file, thư mục frame | `src/video_source.py` |
| **TrackerEngine** | Bọc SAM 2.1 thành **streaming từng frame**: `start(bbox)` → `process(frame)` → mask/bbox/score/ms | `src/tracker_engine.py` |
| **ReIdSession** | Máy trạng thái `tracking → lost → reacquiring`: **chống bám sang người khác** + **tự nhận lại đúng người** | `src/reid.py` |
| **PromptSelector + Visualizer** | Nhập liệu (chuột, phím `r`) và hiển thị (mask alpha, ô bao, quỹ đạo, HUD tiếng Việt, ghi mp4) | `src/prompt_selector.py`, `src/visualizer.py` |
| **MetricsLogger** | Hàm thuần: CSV từng frame + summary (mean/p95/FPS/tỉ lệ mất dấu) | `src/metrics_logger.py` |

Phụ trợ: `src/config.py` (YAML: checkpoint, nguồn, ngưỡng), `src/smooth_display.py` (hiển thị mượt 3 luồng),
`src/identity_guard.py` (cảnh báo ô bao nhảy xa), `src/synthetic_video.py` (sinh video test).

---

## 4. Của mình vs. có sẵn (câu này chắc chắn bị hỏi)

| Tự viết (đóng góp) | Dùng có sẵn (đã ghi trong ADR) |
|---|---|
| **Adapt SAM 2 từ offline → streaming per-frame** (SAM 2 gốc chỉ chạy hết video từ đĩa) | **SAM 2.1 tiny** (Meta) — backbone phân đoạn |
| Toàn bộ pipeline, chọn đối tượng, HUD, quỹ đạo, metrics, config | **SAMURAI** — Kalman filter + motion-aware memory bank (mình chỉ bọc, không viết lại) |
| Chế độ hiển thị mượt 3 luồng (capture / inference / display) | **YuNet + SFace** (OpenCV Zoo) — phát hiện mặt + embedding cho tái nhận diện |
| **Cơ chế đóng băng khi mất dấu + tái nhận diện** (ngưỡng, tập mẫu, cổng chất lượng) | OpenCV, PyTorch, NumPy… — hạ tầng |
| 216 test + CI + 3 ADR + bộ số đo CPU/GPU | |

Nguyên tắc (ADR-0001): **không huấn luyện lại model** — đóng góp nằm ở hệ thống + tối ưu + đánh giá.

---

## 4b. Model nào — của ai, license gì (hội đồng rất hay hỏi)

Hệ thống dùng **HAI bộ model khác nhau**, đừng nhầm khi bảo vệ:

| Bộ | Làm gì | Model | Nguồn · license | Số chính thức | Dùng ở đâu |
|---|---|---|---|---|---|
| **Lõi** | Phân đoạn (mask) + bám bắt + motion memory + temporal propagation | **SAM 2.1 tiny** + config **SAMURAI** | Meta (Apache-2.0) + yangchris11/samurai | — | `src/tracker_engine.py` |
| **Tái nhận diện** | Chỉ khi **mất dấu**: phát hiện mặt + embedding 128-D | **YuNet** + **SFace** | **OpenCV Zoo** (YuNet MIT · SFace Apache-2.0) | YuNet: WIDER Face AP **0,834 / 0,824 / 0,708**; SFace: **accuracy 0,9940** | `src/reid.py` (API `cv2.FaceDetectorYN_create`, `cv2.FaceRecognizerSF_create`) |
| **Hạ tầng** | Thu nhận camera, vẽ HUD, ghi mp4, 2 model trên | OpenCV | Apache-2.0 | — | khắp nơi |

- SFace = **MobileFaceNet** + SFace loss, input 112×112 **align bằng 5 landmark**; paper: *SFace: Sigmoid-Constrained Hypersphere Loss*.
- YuNet paper: *A tiny millisecond-level face detector*; **không phải YOLO**.
- Ngưỡng cosine **0,363** lấy từ chính demo OpenCV Zoo (`demo.cpp:87`).

> ⚠️ **Câu hỏi bẫy: “SFace chính xác 99,4% à?”**
> *“Đó là số của tác giả đo trên ảnh **align chất lượng cao**. Trên webcam thật của em, mặt nhỏ
> 42×62 px nên cosine **cùng một người** chỉ 0,20–0,72 (em đo, ghi trong ADR-0003). Vì vậy em
> không dựa vào 99,4% mà đo trực tiếp: lần chạy thật nhận lại **2/2** với cosine **0,650** và **0,772**.”*

---

## 5. Ba trụ của đề cương nằm ở đâu trong code

| Trụ | Nằm ở đâu |
|---|---|
| **Image Segmentation** (mask) | `tracker_engine.py` — SAM 2 mask decoder trả mask từng frame |
| **Motion Memory** | `tracker_engine.py` — Kalman + memory bank của SAMURAI (lưu vị trí/đặc trưng frame trước) |
| **Temporal Propagation** | `tracker_engine.py` — memory attention của SAM 2 lan truyền mask sang frame sau |

Lỗi người dùng thật đã gặp: chọn mặt **A**, A ra khỏi khung → báo mất dấu → **bám sang mặt B**.
Nguyên nhân: SAM 2 chỉ biết *hình dáng/màu sắc*, **không biết danh tính**.

---

## 6. Tái nhận diện — 3 pha, 3 dòng

Máy trạng thái **dùng chung cho 2 loại cue** (người → khuôn mặt, vật → đặc trưng ngoại hình):

```
tracking     : bám bình thường + lưu MẪU của đối tượng (mặt trong ô đang bám, ≥40px, score≥0.8
               — hoặc 89 số covariance+HSV của vùng mask nếu là VẬT)
     │ mask rỗng 2 frame liên tiếp
     ▼
lost         : NGỪNG lan truyền  →  bộ nhớ không thể nhảy sang B   ← đây là chỗ chặn "bám sang B"
               (mất dấu khi mask RỖNG **hoặc `object_score` ≤ 0** — SAM 2 hay "tưởng tượng" mask
               khi vật đã rời khung: đo thật mask 782 px nhưng score -4,98)
     │
     ▼
reacquiring  : cue MẶT : detect mặt (YuNet) + embedding (SFace) → cosine với TẬP mẫu, lấy MAX
               cue VẬT : cascade NCC (frame thu nhỏ 4×, top-K) → cosine 89 số với tập mẫu
     │ ≥ ngưỡng (mặt 0.363 / vật 0.6 — phải hiệu chỉnh) **VÀ** khớp cùng một chỗ 2 frame liên tiếp
     ▼
tracking     : engine.start(bbox)  →  bám lại ĐÚNG đối tượng, rồi **kiểm chứng 2 frame**
               (mask mới không giống vật → engine.reset() + về lost, không kẹt trên vùng nhầm)
```

Vì sao phải **tập mẫu + lấy max**: đo thật cùng 1 người, mặt nhỏ 42×62 px → cosine chỉ **0,199–0,723**
(so 1 mẫu duy nhất là trượt). Đo đầy đủ: `docs/adr/0003`.

**Vì sao cue vật thể không dùng model**: không tồn tại model "nhận ra cái remote này là cùng một cái"
cho vật bất kỳ (ReID học sẵn như OSNet chỉ học cho *người*) → phải tự mô tả bằng đặc trưng
(**covariance 5×5 + histogram HSV = 89 số**, tính ~2,9 ms) — đây cũng chính là phần "tự làm".

---

## 7. Số liệu chốt (nói được ngay, không cần nhớ nhiều)

| Cấu hình | ms/frame | FPS |
|---|---|---|
| CPU laptop, 1024 (mặc định) | 5 047 | **0,20** |
| CPU laptop, **256** + mượt (`./run fast`) | **155** | **6,5** |
| CPU laptop, 320 + mượt | 222 | 4,5 |
| CPU laptop, 384 + mượt | 329 | 3,0 |
| CPU laptop, 384 + `--reanchor-every 3` | 276 | 3,6 |
| CPU laptop, 512 | 672 | 1,5 |
| **Colab GPU T4**, 512 + tối ưu (bỏ 5 frame warmup) | **49,6** | **20,15** |
| *(cùng cấu hình, mean thô 60 frame — bị frame 0 warmup 2 954 ms kéo lên)* | *100,8* | *9,92* |

**Tái nhận diện VẬT THỂ (webcam thật, 213 frame, `--reid-cue object`):**

| Chỉ số | Trước (chỉ cue mặt) | Sau |
|---|---|---|
| frame mất dấu | 207/257 (**81%**) | 25/213 (**12%**) |
| số lần nhận lại | **0** | **6** (cos 0,671–0,955) |

- Chi phí thêm khi đang bám: **~3 ms/frame**; lúc tìm lại: **~24 ms/frame**
  (thay cho quét lưới 379 ô = 845 ms — nhanh **~35×**).
- Che khuất **50%**: IoU 0,97 → **0,53** → phục hồi **0,967** ngay khung đầu sau khi hết che.
- Che khuất **100%**: mất dấu 6/6 → hết che thì **0,984** ngay, mất dấu **0/12**.
- GPU T4 nhanh hơn CPU **13×** (cùng độ phân giải) → **~9×** (khi so cấu hình tối ưu hai bên:
  49,6 ms vs 445 ms). Số GPU mới nhất: `data/gpu_summary.json` (git `8d64d59`).
- Test: **251 pass** làn nhanh (255 tổng, 4 cần checkpoint), ruff sạch.

---

## 8. Giới hạn — nói trước, đừng để bị hỏi

1. **Không real-time trên laptop**: 1,5–6,5 FPS tuỳ `image_size` (không GPU rời). Muốn 15 FPS phải GPU.
   Lưu ý: `--smooth` làm **video** mượt ~30 FPS, còn overlay/mask cập nhật theo FPS suy luận.
2. **Không nhận lại được nếu không thấy mặt** (quay lưng, che kín, xa/mờ) — giới hạn phương pháp.
3. **Vật giống y hệt** / **vật đặc một màu (chai đen)**: mọi cue ngoại hình cho cosine ≈ 1,0
   (đo: hai vật đen khác nhau vẫn 1,000) → chỉ cue thời gian (Kalman/motion memory) giải được;
   cổng NCC bật mặc định **0,70** (đo có nhãn: sai 0,39–0,69 vs đúng 0,78–0,92) → thà không bám
   còn hơn bám nhầm; hệ thống ở trạng thái ĐANG TÌM nếu vật quay lại chỉ đạt ~0,6.
4. Ngưỡng tái nhận diện (mặt 0.363 / vật 0.6) **chưa hiệu chỉnh trên clip thật** — ticket 09 và 11 còn treo.
4. **Chưa đánh giá trên dataset chuẩn** (DAVIS/LaSOT) — mới có fixture tự sinh + số đo thực.
5. **Chưa có BE/FE web** — app desktop 1 process, HUD OpenCV.
6. Độ trễ **tăng dần** khi chạy lâu (3,4 s → 8,3 s) vì memory SAM 2 phình ra.

---

## 9. Chạy thử (2 lệnh)

```bash
./run demo5    # 5 frame, ~20 giây — an toàn khi họp
./run demo     # demo đầy đủ: mượt + tái nhận diện + ghi mp4/CSV/JSON
```

---

## 10. Bị hỏi thì mở file nào

| Thầy hỏi | Mở |
|---|---|
| "Giải thích hệ thống cho tôi" | file này (mục 2, 3, 5) |
| "Số liệu đâu?" | `README.md` mục 7 + `data/charts/*.png` |
| "Phần nào em tự làm?" | `docs/team-contribution.md` |
| "Sao chọn SAM 2/SAMURAI?" | `docs/adr/0001` ; "Sao không real-time?" → `docs/adr/0002` |
| "Tái nhận diện làm sao?" | `docs/adr/0003` |
| "Dùng model gì, của ai, license gì?" | **file này mục 4b** + `docs/adr/0003` |
| "Hôm qua làm gì?" | `docs/task/22-10-2026-tai-nhan-dien-khuon-mat-yunet-sface.md` |
