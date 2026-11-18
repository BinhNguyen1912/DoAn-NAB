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

- `./run lint` xanh · `./run test` **1393 passed** (5 deselected).
- **Diễn tập ngược**: trả 2 thông điệp về bản cũ ⇒ **2/2 test đỏ**; phục hồi ⇒ xanh.

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
