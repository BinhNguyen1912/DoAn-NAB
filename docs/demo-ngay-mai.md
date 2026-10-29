# Kịch bản demo cho buổi thầy xem (chuẩn bị tối 29-10-2026)

> Mục tiêu: **không thể trượt**. Demo đúng 3 cảnh đã đo được, có video dự phòng, có số liệu để nói.
> Đừng thêm tính năng mới sáng mai.

---

## 1. Chuẩn bị trước (làm tối nay, 15 phút)

| # | Việc | Lệnh / cách làm |
|---|---|---|
| 1 | **Chọn vật demo có MÀU hoặc NHÃN** (chai trà xanh/Coca, hộp sữa, remote có nút màu) | Đo thật: vật có màu/nhãn tách tốt (cosine khác màu 0,33–0,38); **ly trắng / bóng đèn / vật đen trơn là ca tệ nhất** (0,77–1,00) |
| 2 | **Ghi video dự phòng** đúng kịch bản (phòng webcam hỏng trước mặt thầy) | `./run fast --reid-cue object` → diễn 3 cảnh dưới → `q`. Lưu file `data/fast_*.mp4` (tự ghi, có HUD) |
| 3 | Kiểm môi trường | `./run env` (GUI phải `DISPLAY=:0`), `./run test` (xanh) |
| 4 | Kê camera cố định, đủ sáng, **đừng quay dọc** | 720p ngang, vật chiếm ≥ 60 px cạnh |
| 5 | Mở sẵn 2 cửa sổ: 1) `./run fast --reid-cue object` chuẩn bị chạy; 2) video dự phòng | |

---

## 2. Ba cảnh diễn (mỗi cảnh ~15 giây, nói 1 câu trước khi diễn)

### Cảnh 1 — Bám + phân đoạn (trụ cột 1 + 3)
- Kéo ô **sát vật** → bám. Nói: *"Đây là SAM 2.1 tiny + config SAMURAI, chạy CPU, ~5–6 FPS ở `image_size 256`."*
- Di chuyển vật chậm. HUD hiện mask + ô + quỹ đạo + FPS + độ trễ.

### Cảnh 2 — Che khuất một phần (Motion Memory — trụ cột 2)
- Lấy tay che **một nửa** vật rồi bỏ ra. Nói: *"Mask vẫn giữ nhờ memory bank + Kalman của SAMURAI; đo trên fixture: IoU 0,97 → 0,53 khi che 50% → hồi 0,967 ngay khung sau khi hết che."*

### Cảnh 3 — Mất dấu & tìm lại (phần **tự làm**)
- **Đưa vật ra khỏi khung hẳn** 2–3 giây → HUD hiện `MẤT DẤU / ĐANG TÌM LẠI`.
- Đưa vật vào lại **chỗ khác**.
- Nói: *"Hệ thống đóng băng thay vì bám sang vật khác. Khi vật trở lại, nó so khớp 'dấu vân tay' 89 số (covariance + histogram màu) với tập mẫu và bám lại khi đủ tin cậy. Em đặt ngưỡng 0,70 vì đo trên video thật: ca đúng 0,78–0,92, ca sai 0,39–0,69 — thà không bám còn hơn bám nhầm."*

> Nếu cảnh 3 **không bám lại**: nói luôn *"với vật này nó chưa đủ tin cậy nên vẫn ở trạng thái đang tìm — đây là hành vi em chọn có chủ đích, em đã đo và ghi trong tài liệu"* → rồi chuyển sang cảnh 4 (video dự phòng có cảnh bám lại thành công).

### ⭐ Bằng chứng nó CHẠY ĐƯỢC (dùng để trấn an khi thầy hỏi)

Lần chạy thật `data/fast_1029-212632.mp4` (576 frame, webcam, `--reid-cue object`):

| Chỉ số | Kết quả |
|---|---|
| frame mất dấu | 107/576 (**19%**), chia 31 đoạn |
| **số lần tự nhận lại** | **17 / 17** (không lần nào phải bấm `r`) |
| cosine khi nhận lại | **13 lần ≥ 0,90** · 3 lần 0,80–0,89 · 1 lần 0,77 |
| FPS | 5,5 (183 ms/frame) |
| ca khó nhất đã kiểm chứng | nhận lại sau khi tâm **nhảy 407 px** (tay di chuyển nhanh) → **bám đúng vật** (người dùng xác nhận ảnh `data/reid_review3/3_f328_nhay407px.png`) |

→ Câu nói khi demo: *"Trong lần đo này, mất dấu 19% số frame, nhưng hệ thống tự nhận lại 17/17 lần,
13 lần cosine trên 0,90. Không có lần nào phải chọn lại bằng tay."*

### Cảnh 4 (dự phòng) — Chiếu video đã ghi
- Mở `data/fast_*.mp4` (có HUD) hoặc `data/out_binh1_simloss.mp4` (**mất dấu f60, bám lại f80 với điểm 0,918**).

---

## 3. Bảng số nói được ngay (không cần nhớ nhiều)

| Cấu hình | ms/frame | FPS |
|---|---|---|
| CPU, `image_size 1024` (mặc định) | 5 047 | 0,20 |
| CPU, **256** (`./run fast`) | 155 | **6,5** |
| CPU, 320 | 222 | 4,5 |
| CPU, 384 | 329 | 3,0 |
| **Colab T4**, 512 + tối ưu | **49,6** | **20,2** |

- Tìm lại khi mất dấu: cascade NCC + top-K → **~24 ms** (thay vì quét lưới 379 ô = 845 ms).
- Bộ nhớ mẫu: **8 vector × 356 B** trong RAM (không ghi đĩa).
- Test: **261 test** làn nhanh + `ruff` sạch.
- Trần "mượt" trên máy này: webcam qua WSL đọc **66,9 ms/frame ≈ 14 FPS**.

---

## 4. Năm câu thầy dễ hỏi — trả lời 1 câu mỗi ý

| Câu hỏi | Trả lời ngắn |
|---|---|
| "Sao dùng model có sẵn? Em làm gì?" | Backbone SAM 2/SAMURAI là **công cụ**; phần của em: **tầng tái nhận diện** (89 số đặc trưng + cascade tìm lại + state machine + hiệu chuẩn ngưỡng từ 3 video thật của em) và **bộ đo** (CSV/metrics/ablation). |
| "Mất dấu thì sao?" | Đóng băng (không gọi `engine.process`) → không bám sang vật khác. Có 3 điều kiện phát hiện mất dấu: mask rỗng, `object_score ≤ 0`, và 2 frame liên tiếp — vì SAM 2 hay "tưởng tượng" mask khi vật đã đi (đo: mask 782 px nhưng score −4,98). |
| "Nhận lại thế nào?" | Cascade: NCC trên frame thu nhỏ → top-K → so 89 số với tập mẫu → nếu đủ ngưỡng thì `engine.start(bbox)` bám lại; sau đó **kiểm chứng 2 frame**, sai thì bỏ và về trạng thái tìm. |
| "Sao không dùng model ReID có sẵn?" | ReID học sẵn (OSNet/torchreid) **học cho người**, mang sang vật lệch miền; license BoxMOT là AGPL. Em đo trên CPU: MobileNetV3 3,8 ms vs mạng nhỏ tự train 0,72 ms. |
| "Hạn chế?" | Vật **đen trơn / hai vật giống y hệt / cùng tông màu với nền** thì ngoại hình không tách được (đo: cosine 0,77–1,00) — chỉ cue thời gian giải; ngưỡng chưa hiệu chỉnh trên clip vật thật; chưa đánh giá trên dataset chuẩn (DAVIS/LaSOT). |

---

## 5. Nếu có sự cố giữa buổi

| Sự cố | Xử lý (nói 1 câu, đừng loay hoay) |
|---|---|
| Cửa sổ không hiện | `pkill -f run_live.py` rồi chạy lại; kiểm `./run env` |
| Camera bận / mất kết nối | Chuyển **video dự phòng** (đã ghi sẵn) |
| Máy chậm bất thường | Đóng hết app khác; dùng `IMG_SIZE=256` (`./run fast`) |
| Bám nhầm vật | Bấm **`r`** chọn lại, giữ bình tĩnh: *"hệ thống có cảnh báo nghi ngờ đổi đối tượng"* |

---

## 6. Việc **KHÔNG** làm trước buổi demo

- Không train lại model, không đổi backbone, không merge tính năng mới.
- Không hứa "bám lại 100%": nói theo số đo (0,78–0,92 cho ca đúng ở video đã đo).
