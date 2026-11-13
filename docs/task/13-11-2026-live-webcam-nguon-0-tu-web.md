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
   `TestChuoiSoTuWebLaWebcam` với **5 test**: chuỗi số (+ khoảng trắng) → `CameraVideoSource`; file thật
   tên `0` → `FileVideoSource`; thư mục thật tên `0` → `FramesVideoSource`; chuỗi `"²"` không làm nổ
   (`isdecimal()`); đường đi thật của web qua `OpenCvFrameSource("0")` với `cv2.VideoCapture` giả ⇒
   index truyền xuống là `int` 0.
4. **E2E**: thêm bước 9c trong `scripts/e2e_web.js` — điền nguồn `0`, bấm "Bật phát", chấp nhận
   `running` (máy có webcam) hoặc lỗi chứa `camera index`; **cấm** lỗi `video file`. Banner lỗi được
   scope vào card live (trang còn banner của khối job).
5. **Ghi bài học** vào `AGENTS.md` mục 6 (bullet cuối, không sửa chỗ khác).

## 📤 Output / Kết quả
- Trước khi sửa (đo bằng `TestClient` + `create_app()`, POST `/api/live/start` `{"source":"0","mode":"raw"}`):
  `Lỗi: Không mở được nguồn 0: Không mở được video file: '0' (file không tồn tại hoặc codec không đọc được)`.
- Sau khi sửa, đúng cùng request: `HTTP 400 | Không mở được nguồn 0: Không mở được camera index 0
  (bận hoặc không tồn tại — thử index khác, ví dụ 1)` ⇒ thông báo đã trỏ đúng loại nguồn (camera).
- Bằng chứng đỏ→xanh: revert riêng `src/video_source.py` ⇒ 2 test mới FAIL (`assert ['0'] == [0]` — index
  truyền xuống `cv2.VideoCapture` là **chuỗi**); đổi riêng `isdecimal()` → `isdigit()` ⇒
  `ValueError: invalid literal for int() with base 10: '²'` ở `test_chuoi_khong_phai_so_thap_phan_khong_lam_no`.
  Khôi phục thì cả 25 test của file xanh.
- Kiểm chứng môi trường: `./run check 0` → `[LOI] Không mở được camera index 0 ...` kèm log OpenCV
  `V4L2:/dev/video0: can't open camera by index` (+ `device_list->nb_devices` = 0) ⇒ **máy WSL này hiện
  không có webcam nào** (usbipd kẹt, xem `AGENTS.md` §6). Vì vậy trên máy này, sau khi sửa, live webcam
  vẫn không chạy được — nhưng lỗi giờ nói đúng nguyên nhân. Đường demo thay thế: `./run relay` rồi nguồn
  `http://127.0.0.1:8080/snapshot.jpg`, hoặc đường dẫn video (backend tự lặp).
- Lệnh kiểm tra đã chạy:
  - `./run lint` → `All checks passed!`
  - `./run test` → `877 passed, 5 deselected in 93.54s`
  - `./run e2e` → `KẾT LUẬN: PASS`, gồm check mới:
    `✓ nguồn "0" là webcam index, không phải file tên "0" — Lỗi: Không mở được nguồn 0: Không mở được camera index 0 (...)`
    (Chỉ tập nhánh **âm** — máy này không có webcam; nhánh dương "webcam thật chạy từ web" chưa được kiểm
    end-to-end ở đâu cả.)
- File thay đổi:
  - `src/video_source.py` — `open_video_source()`: chuỗi chỉ gồm chữ số → `CameraVideoSource`, trừ khi
    tên đó là file/thư mục thật; docstring nêu lý do + bug 13-11.
  - `tests/test_video_source.py` — sửa assertion cũ + class `TestChuoiSoTuWebLaWebcam` (5 test).
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
- **`isdigit()` ≠ `isdecimal()`**: `"²".isdigit()` là `True` nhưng `int("²")` ném `ValueError` ⇒ bản đầu
  dùng `isdigit()` làm một nguồn vào hợp lệ nổ `ValueError`; đã đổi sang `isdecimal()` + test khoá lại.

## 🔍 Kết quả review độc lập (§9.1)
- **Ai review**: agent `reviewer` (tool `task`), **không** phải phiên đã code; chỉ đọc, không sửa.
  Phạm vi: `src/video_source.py`, `tests/test_video_source.py`, `scripts/e2e_web.js`, `AGENTS.md` §6, log này.
- **Kết luận**: **0 P0, 0 P1** — "thay đổi nhỏ, đúng seam, test bắt hồi quy thật, không phá hợp đồng nguồn nào".
  Review cũng xác nhận độc lập các điểm: nhánh int/RTSP/HTTP/snapshot/thư mục ảnh/đường dẫn file **không
  đổi**; watchdog `raw` không kích hoạt nhầm `STOPPED "nguồn đã hết"` cho webcam (`_exhausted` chỉ set
  khi `_is_file`); `LiveStreamService.start` bọc `except Exception` ⇒ lỗi mới là **HTTP 400**, không 500;
  test không flaky (không webcam/mạng/thời gian thật, `cv2.VideoCapture` bị monkeypatch).
- **Đã sửa ngay trong PR (P2/P3)**:
  - P2-1 — log lệch code sau lần sửa cuối (ghi 3 test / 875 passed trong khi code có 4 test + `isdecimal()`):
    đã chạy lại toàn bộ kiểm tra và cập nhật đúng số ở trên (5 test, `877 passed`, e2e PASS lần 2).
  - P3-1 — check E2E đọc `document.querySelector('p.error')` toàn trang (banner khối job đứng trước
    panel live) ⇒ scope vào card "Phát trực tiếp".
  - P3-2 — comment trong test nói sai cơ chế đỏ (không phải `FileNotFoundError` mà là `opened == ['0']`).
  - P3-3 — thiếu test "thư mục thật tên `0`" ⇒ đã thêm (`FramesVideoSource`).
  - P3-4 — ghi rõ tên số được hiểu theo CWD (muốn trỏ file tên `0` thì ghi `./0`) trong `AGENTS.md`.
  - P3-7 — bỏ chữ "đo" cho ca lỗi người dùng báo (đổi thành "người dùng báo 13-11, tái hiện bằng `TestClient`").
- **Còn nợ (đã lên Next steps, chưa sửa trong PR)**: P2-2 (`_rewind` áp ngữ nghĩa file cho webcam ở mode
  `track` — hành vi có sẵn, không phải hồi quy của bug này), P3-5 (3 chỗ CLI còn `isdigit()` thừa/lệch
  luật), P3-6 (index phi lý → `OverflowError` thô).
- **Giới hạn bằng chứng** (ghi để không ai đọc quá mức): phiên review không chạy được pytest/ruff/e2e;
  nhánh **dương** của webcam (mở được thật từ web) chưa được kiểm end-to-end ở đâu — máy này không có
  `/dev/video0`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Đóng PR này, merge vào `main`.
- [ ] (Nếu cần demo webcam trên máy này) chạy `./run relay` + nguồn `http://127.0.0.1:8080/snapshot.jpg`;
      hoặc gỡ kẹt usbipd theo `docs/task/04-11-2026-cuu-webcam-relay-http.md`.
- [ ] **P2-2 (review 13-11): `_rewind` của mode `track` áp ngữ nghĩa "file lặp lại" lên webcam** —
      `read()` trả None **một lần** (USB chập) là đóng + mở lại camera, và nếu mở lại lỗi thì phiên
      `break` → `stopped` (UI báo "đã dừng") trong khi mode `raw` báo `ERROR "camera/luồng không trả
      frame"` cho đúng sự cố đó. Chỉ `_rewind` khi nguồn là file (mirror `_looks_like_file`) + đặt
      `error` khi nguồn không phải file mà `read()` trả None. Chưa làm trong PR này (không phải hồi quy
      của bug `"0"`, nhưng trước fix thì `"0"` không vào được nhánh này).
- [ ] **P3-5**: 3 chỗ CLI còn tự đổi chuỗi→int (`tools/run_live.py:670`, `tools/check_video_source.py:40`,
      `scripts/record_raw.py:41`) — nay **thừa** và lệch luật với factory (`isdigit` vs `isdecimal`).
- [ ] **P3-6**: index/chuỗi số phi lý (vd `"999…9"`) → `cv2` ném `OverflowError`: mode `raw` = HTTP 400
      với message Python thô, mode `track` = worker thoát mã 1. Nên kẹp index hoặc bọc thành lỗi miền rõ.
- [ ] Cân nhắc cảnh báo trên UI khi nguồn là `0` và máy không có camera (hiện chỉ báo ở banner lỗi).

## 📚 Tài liệu tham khảo
- `AGENTS.md` §6 (kinh nghiệm đã đo: webcam WSL/usbipd, relay) và §7b (quy trình git).
- `docs/task/_template.md` — khuôn log này.
- `docs/task/04-11-2026-cuu-webcam-relay-http.md`, `docs/task/05-11-2026-webcam-usbipd-ket-o-driver-khong-phai-wsl.md`.
