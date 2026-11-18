# 18-11-2026 — `democheck`/`CameraVideoSource` gợi ý ĐÚNG đường thoát khi webcam chết

## Mục tiêu

Chạy `./run democheck` (9 mục, không nạp model) trước buổi demo và sửa những gì nó báo. Hai mục đỏ khi
chạy trên máy này: `web/dist` cũ, và `nguồn video` = `0` (webcam). Mục thứ hai có **hai** vấn đề: máy
không có webcam dùng được (đã biết, AGENTS §6), và **câu gợi ý trong thông điệp lỗi chỉ sai đường**.

## Input

- `./run democheck` (mặc định lấy `source` từ `configs/default.yaml` = `0`).
- `AGENTS.md` §6: webcam WSL kẹt cờ `Device busy (exported)` ở **DRIVER usbipd-win**; đã thử index 1,
  `wsl --shutdown`, reboot, unbind/bind, restart service — không khỏi. Đường đã kiểm chạy được: relay
  HTTP (`./run relay`) hoặc file (`data/binh1.mp4`).

## Công việc đã thực hiện

1. **`web/dist` cũ** ⇒ `./run web` (build lại). `web/dist/` nằm trong `.gitignore` nên **không commit**
   — đây là bước chuẩn bị máy, không phải thay đổi mã. Sau khi build: mục `web/dist` **OK**.
2. **Sửa câu gợi ý sai đường** (2 chỗ, cùng một lỗi):
   - `src/video_source.py::_raise_open_error`: bỏ "thử index khác, ví dụ 1" (đã đo là **không** cứu
     được), thay bằng relay + file.
   - `scripts/demo_preflight.py::check_source_frames`: khi nguồn là webcam (`"0"`/`"1"`) mà đọc lỗi, nối
     thêm gợi ý relay/file; nguồn đã là file/URL thì **không** nối (tránh làm rối).
3. TDD: viết 3 test trước (`tests/test_demo_preflight.py`, `tests/test_video_source.py`), thấy đỏ, rồi sửa.

## Output / Kết quả

`./run democheck` (nguồn mặc định = webcam): 6 OK · 2 cảnh báo · **2 LỖI** — nhưng lỗi giờ **kèm đường
thoát**. `./run democheck --source data/binh1.mp4`: **7 OK · 2 cảnh báo · 0 LỖI** ("Preflight ĐẠT"), mục
`nguồn video` = 8 frame/233 ms, `frame có đổi` = khác biệt trung bình 18,51/255.

- `./run lint` xanh · `./run test` **1398 passed** (5 deselected).
- `./run democheck --source data/binh1.mp4`: **7 OK · 2 cảnh báo · 0 LỖI** (mục `clip demo` cũng OK:
  `binh1.mp4 720×1280 333 frame`). Nguồn mặc định (webcam) vẫn LỖI nhưng kèm đường thoát.
- **File thay đổi**: `src/video_source.py` (thêm `is_camera_source`, sửa `_raise_open_error`),
  `scripts/demo_preflight.py` (`check_source_frames`, `MANUAL_STEPS`), `tests/test_video_source.py`,
  `tests/test_demo_preflight.py`, log này.
- **Diễn tập ngược 5/5 đỏ→xanh** (mỗi lần phục hồi rồi chạy lại):
  `test_loi_mo_camera_goi_y_dung_duong_thoat` · `test_loi_webcam_thi_goi_y_DUNG_duong_thoat` (trả câu cũ)
  · `test_khong_lap_goi_y_khi_loi_da_co_relay` (bỏ điều kiện "chưa có relay") ·
  `test_ba_buoc_tay_khong_noi_nguon_0_la_relay` (trả `MANUAL_STEPS` cũ) ·
  `test_webcam_co_file_that_ten_0_thi_khong_goi_y` + `test_chuoi_khong_phai_so_thap_phan_thi_khong_goi_y`
  (dùng `isdigit()` thay `is_camera_source`).

## Vấn đề & cách xử lý

- **Không** đổi `source` mặc định trong `configs/default.yaml`: máy demo khác vẫn có webcam thật, và
  `democheck` phải kiểm đúng thứ sẽ dùng khi thi. Sửa **thông điệp**, không sửa hành vi kiểm.
- Mục `frame có đổi` báo "cần ≥ 2 frame để so" khi nguồn chết — đúng nhưng là *hệ quả*; giữ nguyên để
  không che mất nguyên nhân ở mục `nguồn video`.

## Next steps

- Trước buổi demo: `./run web` (nếu sửa `web/src`) → `./run relay` (nếu dùng webcam) → `./run api 8010`
  → `./run democheck --source <nguồn thật>` → `./run democheck --full --bbox x,y,w,h` (có nạp model).
- Chưa có webcam chạy được trên máy này để kiểm `--full` bằng camera thật; `--full` đã diễn tập trên
  file/relay ở các log trước.

## Tài liệu tham khảo

- `scripts/demo_preflight.py`, `src/video_source.py`, `tests/test_demo_preflight.py`,
  `tests/test_video_source.py`
- `docs/task/04-11-2026-cuu-webcam-relay-http.md`, `docs/task/05-11-2026-webcam-usbipd-ket-o-driver-khong-phai-wsl.md`

## Bổ sung sau review độc lập (4 P2 + 4 P3)

Reviewer xác nhận **hướng đúng** (relay/`/snapshot.jpg` + file là hai đường đã kiểm; "thử index khác" là
đường cụt trên máy này) và bắt 4 P2 — đều đã sửa:

- **P2-1 (lệch quy tắc)**: `_la_nguon_webcam` tự viết `str(source).strip().isdigit()` trong khi factory
  `open_video_source` dùng `isdecimal()` **và** ưu tiên file/thư mục THẬT trùng tên. Lệch ba chỗ: file
  tên `0` (quy ước 13-11), `"²"` (`isdigit()` True nhưng `int()` ném), `np.integer`. ⇒ Nay có **một bản**
  `src/video_source.is_camera_source()`, factory **và** preflight cùng gọi nó.
- **P2-2 (lặp gợi ý)**: `CameraVideoSource` đã in relay trong câu lỗi, preflight nối thêm lần nữa ⇒ một
  dòng bảng ~380 ký tự, `./run relay` xuất hiện **2 lần**. Nay chỉ nối khi câu lỗi **chưa** có "relay",
  và chỉ nối phần còn thiếu.
- **P2-3 (mâu thuẫn)**: `MANUAL_STEPS` bước 2 nói "Nguồn `0` (webcam thật qua relay)" — **sai**: `0` là
  webcam trong WSL (kẹt driver), relay là **URL HTTP**. Sửa thành URL lấy từ
  `bash scripts/cam_relay.sh snapurl`, và ghi rõ `0` là đường kẹt.
- **P2-4 (không dán được)**: `--source http://<IP-Windows>:8090/snapshot.jpg` — trong bash `<` là toán tử
  chuyển hướng ⇒ dán vào là sai. Nay câu lỗi **không** chứa URL dán được-dở: nó chỉ nói lấy URL ở đâu
  (`bash scripts/cam_relay.sh snapurl`) và dùng một clip có sẵn.
- **P3-1 (răng của test)**: trước đây bỏ URL `<snapshot>` khỏi gợi ý mà test vẫn xanh. Nay test ghim
  `cam_relay.sh snapurl` + `count("./run relay") == 1`, và có ca âm cho file tên `0`, `"²"`, URL.
- **P3-2 (`data/binh1.mp4` không có trong fresh clone)**: `.gitignore` có `data/*` (chỉ artifact được
  miễn) ⇒ đã bỏ hẳn tên file khỏi câu lỗi, đổi thành "một clip có sẵn (`--source <clip>.mp4`)".
- **P3-3 (câu chung bị mất)**: câu lỗi nay giữ bước **tổng quát** cho máy thường ("kiểm tra thiết bị,
  máy nhiều camera thì thử `--source 1`") **trước**, rồi mới tới phần đặc thù WSL — vì chuỗi này còn đi
  vào HTTP 400 `detail`/`status.json.message`/`worker.log` (ADR-0005: API còn chạy trên VPS).
- **P3-4**: log thêm mục review này + danh sách file + tên từng test của diễn tập ngược. Ghi chú: log cũ
  `docs/task/14-11-…` còn câu "kèm gợi ý index khác" — **không sửa** log lịch sử (AGENTS §2.3).

**Đã kiểm, không phải lỗi** (reviewer): `/snapshot.jpg` + cổng 8090 khớp `scripts/cam_relay.sh`; câu lỗi
**không** hứa relay biến `0` thành chạy được; không test nào khác phụ thuộc câu chữ cũ; `verdict()` không
đọc phần gợi ý nên không thể biến LỖI thành ĐẠT.
