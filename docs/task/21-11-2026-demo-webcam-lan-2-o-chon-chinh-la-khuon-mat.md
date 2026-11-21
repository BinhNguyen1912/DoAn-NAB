# Ngày 21-11-2026 — Phiên demo webcam lần 2: "bám nhầm chỗ khác" = **ô chọn chính là KHUÔN MẶT**

## 🎯 Mục tiêu
Người dùng báo: *"sai tùm lum, khi đưa vật ra để test mất dấu, thì lại focus nhầm chỗ khác"*. Tìm nguyên
nhân bằng artifact + ảnh, không đoán.

## 📥 Input
- `data/demoip_1121-075227_{metrics.csv,_summary.json,_run_info.json,_web.mp4}` (`git_rev 1e2969b`), 102 frame.
- Người dùng chọn vật, rồi đưa vật ra khỏi khung để thử "mất dấu → tự tìm lại".

## 🔨 Công việc đã thực hiện
1. Đọc CSV 102 dòng: `state` = tracking 89 / reacquiring 11 / lost 2; **2 lần `reacquired`** (f61 score
   0,843 ncc 0,402; f94 score 0,805 ncc 0,485); 15 frame `lost`; 12 frame `ms=0` (không có suy luận mới).
2. Trích **18 frame** từ `_web.mp4` (715 frame @30 fps) và xem ảnh: f1, f3, f6, f10, f15, f20, f29, f31,
   f40, f51, f55, f61, f70, f76, f85, f89, f94, f102.
   ⇒ **Toàn bộ phiên, ô + mask nằm trên KHUÔN MẶT** (f1 đã vậy, f102 vẫn vậy).
3. Kiểm bằng số: chạy YuNet (`models/face/face_detection_yunet_2023mar.onnx`) trên frame đầu
   (28,9 ms/frame, CPU):
   - mặt = **(256, 208, 197, 228)** · ô đã chọn (CSV f0) = **(258, 241, 212, 201)** ⇒ **IoU = 0,768**
   - tâm ô (364, 341) vs tâm mặt (354, 322) ⇒ **cùng một vùng**.

## 📤 Output / Kết quả

### Kết luận (trả lời đúng câu "focus nhầm chỗ khác")
- **Hệ KHÔNG bám nhầm**: nó bám **đúng** thứ được chọn — mà thứ được chọn **là khuôn mặt** (IoU 0,768 với
  mặt YuNet tìm được). Đây là **lỗi chọn ô**, không phải lỗi re-ID/VOS.
- Hai lần "nhận lại" (f61, f94) cũng nhận lại **khuôn mặt** — nhất quán với đặc trưng đã học là mặt.
- Nối với phiên trước (`data/demoip_1120-224057`): ở đó vật được chọn có **tông màu da** và nằm cạnh mặt ⇒
  re-ID khớp mặt với cosine 0,974 / ncc 0,545. **Cùng một gốc**: vùng đặc trưng là da/mặt.

### Số của phiên (từ `_summary.json`)
| Đại lượng | Số | Ghi chú |
|---|---|---|
| `mean_latency_ms` / p95 | **359,8 / 429,6** (n=89) | vẫn `image_size 320` (không truyền `--image-size`) |
| `effective_fps` | **2,78** | mask mới ~2,8 lần/giây |
| `lost` / `reacquiring` / `reacquired` | 15 / 11 / **2** | mất dấu 3 cụm (f51–60, f74, f90–93) |
| CPU / RAM | 429 % (≈54 % máy) / 679 MB | GPU: không có |

### Đã thêm: cảnh báo lúc CHỌN Ô (`src/face_guard.py`, 10 test)
- `canh_bao_chon_o(frame, bbox)` chạy YuNet **một lần mỗi lần chọn** (28,9 ms, không nằm trong vòng lặp)
  và in cảnh báo ASCII nếu ô phủ khuôn mặt (IoU ≥ 0,35 — bắt cả ca ô bao cả người).
- Gắn vào **cả hai** đường chọn ô: `src/smooth_display.py` (đường `./run demoip --smooth`) và
  `src/live_pipeline.py`. **Fail-open**: thiếu model/thiếu opencv ⇒ im lặng, không làm chết phiên.
- **Chỉ cảnh báo, KHÔNG sửa ô** — bám mặt là hợp lệ nếu người dùng muốn bám mặt.
- Kiểm trên chính frame gây lỗi: in ra
  `[CANH BAO] o ban chon PHU KHUON MAT (IoU 0.78 voi mat (256, 208, 197, 228))…`.

## 🐞 Vấn đề gặp phải & cách xử lý
- Bài học lặp lại (lần 3 trong ngày): **phải xem ảnh**, không tin `score`/`reid_score`. Ở phiên này
  `Điểm tin cậy` 3,4–4,6 (rất "tự tin") trong khi đối tượng là khuôn mặt — hoàn toàn hợp lệ, chỉ là
  không phải thứ người dùng định chọn.
- `[WARN] nghi ngờ ĐỔI ĐỐI TƯỢNG` xuất hiện 2 lần (f60→f61, f75→f76) — cả hai là **báo oan** do ô nhỏ
  (31×67 px) nhảy theo tay/đầu; ngưỡng hiện so tâm với 1,5 × đường chéo ô. Đã ghi thành nợ, chưa nới
  (nới tay sẽ bỏ sót ca bám sang vật khác thật như f163 của `binh2`).

## 📌 Việc cần làm tiếp
- [ ] Chạy lại với **`--image-size 192`** (đo trên máy này: ~87–118 ms so với 360 ms ở 320) — đây là nút
      thắt lớn nhất của buổi demo.
- [ ] Chọn **vật có hoa văn/chữ**, không đặt trong ô cùng mặt; nếu cảnh báo `PHU KHUON MAT` hiện thì bấm
      `r` chọn lại — đó chính là mục đích của cảnh báo mới.
- [ ] Ticket #11 (hiệu chuẩn): `max_bad` nay 0,545 ⇒ NCC **không còn tách được**; cần ≥ 3 ca sai đa dạng.
- [ ] Ticket #42: nhận lại lặp ở mép khung; "ô ma" ở `gt_rong` 359.
- [ ] Web (`live_tracking`) chưa có cảnh báo này — mới có ở đường CLI.

## 📚 Tài liệu tham khảo
- `src/face_guard.py` (mới), `tests/test_face_guard.py` (10 test), `src/smooth_display.py`,
  `src/live_pipeline.py`
- Ảnh bằng chứng: `docs/media/reid/demoip_1121_o_chon_la_mat.jpg` (lưới 18 frame + số IoU)
- `data/demoip_1121-075227_{summary,run_info}.json`, `data/demoip_1121-075227_metrics.csv`
- `models/face/face_detection_yunet_2023mar.onnx` (YuNet, dùng chung với `src/reid.py`)
