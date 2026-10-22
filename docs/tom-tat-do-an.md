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

```
tracking     : bám bình thường + lưu mẫu khuôn mặt CỦA A (mặt trong ô đang bám, ≥40px, score≥0.8)
     │ mask rỗng 2 frame liên tiếp
     ▼
lost         : NGỪNG lan truyền  →  bộ nhớ không thể nhảy sang B   ← đây là chỗ chặn "bám sang B"
     │
     ▼
reacquiring  : mỗi frame detect mặt (YuNet) + embedding (SFace) → cosine với TẬP mẫu của A, lấy MAX
     │ ≥ ngưỡng 0.363
     ▼
tracking     : engine.start(bbox mặt)  →  bám lại ĐÚNG A
```

Vì sao phải **tập mẫu + lấy max**: đo thật cùng 1 người, mặt nhỏ 42×62 px → cosine chỉ **0,199–0,723**
(so 1 mẫu duy nhất là trượt). Đo đầy đủ: `docs/adr/0003`.

---

## 7. Số liệu chốt (nói được ngay, không cần nhớ nhiều)

| Cấu hình | ms/frame | FPS |
|---|---|---|
| CPU laptop, 1024 (mặc định) | 5 047 | **0,20** |
| CPU laptop, 384 + mượt | 445 | **2,25** |
| CPU laptop, 384 + tái nhận diện | 292 | **3,40** |
| **Colab GPU T4**, 512 + tối ưu | **65** | **15,28** |

- Che khuất **50%**: IoU 0,97 → **0,53** → phục hồi **0,967** ngay khung đầu sau khi hết che.
- Che khuất **100%**: mất dấu 6/6 → hết che thì **0,984** ngay, mất dấu **0/12**.
- GPU T4 nhanh hơn CPU **13×** (cùng độ phân giải) → **78×** (khi cả hai đã tối ưu).
- Test: **216 pass**, ruff sạch.

---

## 8. Giới hạn — nói trước, đừng để bị hỏi

1. **Không real-time trên laptop**: 0,2–3,4 FPS (không GPU rời). Muốn 15 FPS phải GPU.
2. **Không nhận lại được nếu không thấy mặt** (quay lưng, che kín, xa/mờ) — giới hạn phương pháp.
3. Ngưỡng tái nhận diện **chưa hiệu chỉnh trên clip 2 người thật** (cần quay).
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
| "Hôm qua làm gì?" | `docs/task/22-10-2026-tai-nhan-dien-khuon-mat-yunet-sface.md` |
