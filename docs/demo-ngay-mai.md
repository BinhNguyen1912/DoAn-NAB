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

### Cảnh 3 — Mất dấu & bám lại (phần **tự làm**) — kịch bản mặc định 23-11

> ⚠️ Từ 23-11 `./run demoip` **mặc định TẮT re-ID** (`--no-reid`): đo bảng 2×2 cho thấy re-ID
> **không thắng ô nào** (binh1 0,4236 vs 0,7794; be2 0,5668–0,8577 vs 0,8754). Cơ chế đang chạy là
> **lan truyền liên tục của SAM 2** (memory của model), không phải so khớp "vân tay" ở trên.
> Đoạn dưới đây là **bản cũ** — giữ lại để đối chiếu, **đừng đọc** khi demo.

- **Đưa vật ra khỏi khung hẳn** 2–3 giây → HUD hiện `MẤT DẤU — bấm r chọn lại`, **không vẽ mask nào**
  (13/13 frame mất dấu có mask = 0 px — đo phiên `demoip_1123-144505`). Nói: *"Hệ không vẽ bừa khi
  không thấy vật; em đo trên phiên thật: 0 pixel mask ở mọi frame mất dấu."*
- Đưa vật vào lại **chỗ khác** → memory của SAM 2 tự bám lại **ngay frame đầu** (đo: 83 660 px ở
  frame đầu tiên vật xuất hiện lại).
- Nếu ô **nhảy vô lý** (bám sang tường/cửa cùng tông) → HUD hiện **ô NÉT ĐỨT vàng + nhãn `NGHI`** và
  banner `NGHI DOI TUONG — r: chon lai | c: van dung`. Nói: *"Hệ tự phát hiện nghi ngờ nên KHÔNG tô
  mask, chỉ vẽ ô nét đứt; em bấm `c` nếu vẫn đúng, `r` nếu phải chọn lại."* (Bấm `c` để cổng tự xoá.)
- **Chưa có** cơ chế tự nhận lại đáng tin: đo trên 2 clip GT, re-ID cho 0,4236/0,8577 so với 0,7794/0,8754
  của lan truyền liên tục ⇒ **đừng nói câu "tự nhận lại"**.

### (Bản cũ — chỉ để đối chiếu, không dùng khi demo)

> Nếu cảnh 3 **không bám lại**: nói luôn *"với vật này nó chưa đủ tin cậy nên vẫn ở trạng thái đang tìm — đây là hành vi em chọn có chủ đích, em đã đo và ghi trong tài liệu"* → rồi chuyển sang cảnh 4 (video dự phòng có cảnh bám lại thành công).

### ⚠️ Bằng chứng "tự nhận lại" — ĐÃ BỊ SỐ ĐO 23-11 PHỦ ĐỊNH, đừng nói câu cũ

> **ĐÍNH CHÍNH 23-11-2026.** Con số **"17/17"** trong bản cũ của mục này lấy từ
> `data/reid_2clip_calib.json` — đó là **hiệu chuẩn NGƯỠNG cosine/NCC trên 17 ca dương + 1 ca âm**,
> **KHÔNG** phải "hệ thống tự nhận lại đúng 17/17 lần trong một phiên". Đo lại bằng **mIoU mask vs GT**
> (thước đo duy nhất của "bám đúng") trên cùng một clip, cùng ô chọn, 3+3 lần chèn kẽ
> (`git_dirty_code=false`):
>
> | | mIoU | mask NGOÀI GT | frame vật đã cất |
> |---|---|---|---|
> | **có re-ID** | **0,4236** | **43,1 %** (tệ nhất 100 %) | **bịa** 33 199 / 37 574 / 6 385 / 34 696 / 52 056 px ở **5/5** frame |
> | **không re-ID** (lan truyền liên tục) | **0,7794** | 0,6 % | **0 px** ở **5/5** frame |
>
> Artifact: `data/miou_binh1_{reid,nofreeze}_lan{1,2,3}_2026-11-23_metrics.json`,
> `data/ab_binh1_*_lan1_masks/`, plan `docs/plan/23-11-2026-chon-co-che-tu-tim-lai.md`.
> Trên clip "vật rời khung rồi vào lại" (`docs/gt/vat_be_vaolai`, 6 frame GT tay): lan truyền
> **0,8754** vs re-ID **0,8577** (re-ID chậm ~8 frame và **nhận bừa 8 971 px** lúc vật vắng).
>
> **Câu ĐƯỢC nói** (kèm số): *"Trên clip có GT, để SAM 2 lan truyền liên tục cho mIoU 0,7794; bật
> re-ID thì còn 0,4236 và mask tràn ra ngoài vật 43 %. Em đã đo nên chọn lan truyền cho demo."*
> **Câu CẤM nói**: *"hệ thống tự nhận lại 17/17"*, *"tự tìm lại khi vật ra khỏi khung"*.
> Chạy demo bằng `./run demoip --no-reid` (cờ này thêm 23-11 để chạy đúng cơ chế đã đo là tốt hơn).

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
