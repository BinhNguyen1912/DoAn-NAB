# Ngày 13-11-2026 — Sửa lỗi live trên web: nguồn "0" (webcam) bị coi là file

## 🎯 Mục tiêu
- Sửa lỗi người dùng báo khi dùng web (panel "Phát trực tiếp"):
  `Lỗi: Không mở được nguồn 0: Không mở được video file: '0' (file không tồn tại hoặc codec không đọc được)`
  dù ô "Nguồn frame" đang là giá trị mặc định `0` = webcam.
- Khoá hồi quy bằng test đơn vị + 1 check E2E, và ghi lại bài học vào `AGENTS.md` mục 6.

## 📥 Input
- Yêu cầu người dùng (13-11-2026): ảnh chụp panel live của web + chuỗi lỗi ở trên.
- Code liên quan: `src/api/schemas.py` (hợp đồng HTTP `source: str`), `web/src/components/LivePanel.tsx`
  (mặc định `'0'`), `src/api/main.py:build_default_live()`, `src/api/adapters/opencv_source.py`
  (mode `raw`), `src/api/adapters/worker_source.py` + `tools/live_worker.py` (mode `track`),
  `src/video_source.py:open_video_source()` (seam chọn nguồn).
- Môi trường: WSL2, web qua `./run api` → `http://127.0.0.1:8000/`.

## 🔨 Công việc đã thực hiện
1. **Truy nguyên nhân** (đọc code, không đoán):
   - HTTP khai `source: str` với mô tả "0 = webcam" (`src/api/schemas.py:90-94`); frontend gửi đúng
     chuỗi (`web/src/components/LivePanel.tsx:29,164`).
   - `open_video_source()` chỉ coi **int** là webcam (`src/video_source.py`), mọi chuỗi khác rơi vào
     `FileVideoSource` ⇒ đúng thông báo "Không mở được video file: '0'".
   - Hai nhánh live đều dính: `raw` → `OpenCvFrameSource` gọi thẳng `open_video_source("0")`;
     `track` → `live_worker --source 0` → `src/live_tracking.py:379` cũng gọi `open_video_source("0")`.
   - CLI thì không dính vì đã tự đổi: `tools/run_live.py:670` và `tools/check_video_source.py:40`
     (`isdigit()` → `int`). Tức là hợp đồng bị lệch giữa CLI và HTTP.
2. **Sửa tại đúng một seam**: `open_video_source()` giờ đổi chuỗi **chỉ gồm chữ số** thành index webcam,
   **trừ khi** có file/thư mục thật trùng tên (`os.path.exists`) — giữ nguyên hành vi cho mọi kiểu nguồn
   khác (int, `rtsp://`, `http(s)://`, snapshot, thư mục ảnh, đường dẫn file). Cập nhật docstring module +
   factory để ghi rõ lý do.
3. **Test**: sửa 1 assertion cũ trong `tests/test_video_source.py` (trước đây khẳng định
   `open_video_source("1")` là `FileVideoSource` — chính là hành vi gây bug) và thêm class
   `TestChuoiSoTuWebLaWebcam` với 3 test (chuỗi số + khoảng trắng; file thật tên `0` vẫn là file; đường đi
   thật của web qua `OpenCvFrameSource("0")` với `cv2.VideoCapture` giả ⇒ index truyền xuống là `int` 0).
4. **E2E**: thêm bước 9c trong `scripts/e2e_web.js` — điền nguồn `0`, bấm "Bật phát", chấp nhận
   `running` (máy có webcam) hoặc lỗi chứa `camera index`; **cấm** lỗi `video file`.
5. **Ghi bài học** vào `AGENTS.md` mục 6 (bullet cuối, không sửa chỗ khác).

## 📤 Output / Kết quả
- Trước khi sửa (đo bằng `TestClient` + `create_app()`, POST `/api/live/start` `{"source":"0","mode":"raw"}`):
  `Lỗi: Không mở được nguồn 0: Không mở được video file: '0' (file không tồn tại hoặc codec không đọc được)`.
- Sau khi sửa, đúng cùng request: `HTTP 400 | Không mở được nguồn 0: Không mở được camera index 0
  (bận hoặc không tồn tại — thử index khác, ví dụ 1)` ⇒ thông báo đã trỏ đúng loại nguồn (camera).
- Bằng chứng đỏ→xanh: revert riêng `src/video_source.py` thì 2 test mới FAIL
  (`assert ['0'] == [0]` — index truyền xuống `cv2.VideoCapture` là **chuỗi**), khôi phục thì xanh.
- Kiểm chứng môi trường: `./run check 0` → `[LOI] Không mở được camera index 0 ...` kèm log OpenCV
  `V4L2:/dev/video0: can't open camera by index` (+ `device_list->nb_devices` = 0) ⇒ **máy WSL này hiện
  không có webcam nào** (usbipd kẹt, xem `AGENTS.md` §6). Vì vậy trên máy này, sau khi sửa, live webcam
  vẫn không chạy được — nhưng lỗi giờ nói đúng nguyên nhân. Đường demo thay thế: `./run relay` rồi nguồn
  `http://127.0.0.1:8080/snapshot.jpg`, hoặc đường dẫn video (backend tự lặp).
- Lệnh kiểm tra đã chạy:
  - `./run lint` → `All checks passed!`
  - `./run test` → `875 passed, 5 deselected in 90.13s`
  - `./run e2e` → `KẾT LUẬN: PASS`, gồm check mới:
    `✓ nguồn "0" là webcam index, không phải file tên "0" — Lỗi: Không mở được nguồn 0: Không mở được camera index 0 (...)`
- File thay đổi:
  - `src/video_source.py` — `open_video_source()`: chuỗi chỉ gồm chữ số → `CameraVideoSource`, trừ khi
    tên đó là file/thư mục thật; docstring nêu lý do + bug 13-11.
  - `tests/test_video_source.py` — sửa assertion cũ + class `TestChuoiSoTuWebLaWebcam` (3 test).
  - `scripts/e2e_web.js` — bước 9c (nguồn `0` phải là camera, không phải file).
  - `AGENTS.md` — 1 bullet mục 6 (hợp đồng `source` chuỗi vs int).
  - `docs/task/13-11-2026-live-webcam-nguon-0-tu-web.md` — log này.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Lỗi gốc**: hai đường vào seam nguồn (CLI đổi chuỗi→int, HTTP thì không) ⇒ chỉ web hỏng, CLI không
  hỏng, nên các test CLI cũ không bắt được. Xử lý: đặt phép đổi ở **seam** (`open_video_source`) để mọi
  caller hiện tại và sau này đều đúng.
- **Cạm bẫy "xanh giả" khi test**: nếu chỉ khẳng định `isinstance(open_video_source("0"), CameraVideoSource)`
  thì test vẫn xanh kể cả khi adapter truyền index dạng chuỗi xuống `cv2.VideoCapture` (OpenCV chấp nhận
  cả hai). Vì vậy test qua `OpenCvFrameSource` còn khẳng định `opened == [0]` (int) — chính là chỗ đã đỏ
  khi revert.
- **Bẫy môi trường**: sau khi sửa, máy này vẫn không mở được webcam (không có `/dev/video0`). Đã ghi rõ
  trong log để không ai đọc thành "sửa xong là webcam chạy".

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Đóng PR này, merge vào `main`.
- [ ] (Nếu cần demo webcam trên máy này) chạy `./run relay` + nguồn `http://127.0.0.1:8080/snapshot.jpg`;
      hoặc gỡ kẹt usbipd theo `docs/task/04-11-2026-cuu-webcam-relay-http.md`.
- [ ] Cân nhắc cảnh báo trên UI khi nguồn là `0` và máy không có camera (hiện chỉ báo ở banner lỗi).

## 📚 Tài liệu tham khảo
- `AGENTS.md` §6 (kinh nghiệm đã đo: webcam WSL/usbipd, relay) và §7b (quy trình git).
- `docs/task/_template.md` — khuôn log này.
- `docs/task/04-11-2026-cuu-webcam-relay-http.md`, `docs/task/05-11-2026-webcam-usbipd-ket-o-driver-khong-phai-wsl.md`.
