# 17-11-2026 — Ticket #34: `test_reap_khong_cho_zombie_5_giay` thôi đo thời gian tường

## Mục tiêu

Bỏ ngưỡng thời gian tuyệt đối (`elapsed < 3 s`) — trên máy bị chiếm CPU một lần reap **hợp lệ** vẫn có
thể vượt 3 s ⇒ test đỏ oan. Thứ cần khẳng định là **hành vi**: tiến trình đã được reap.

## Input

- `src/api/adapters/worker_source.py`: `TERM_WAIT_S = 2.0`, `KILL_WAIT_S = 1.0` ⇒ trường hợp xấu nhất
  hợp lệ ≈ 3 s (worker bỏ qua SIGTERM); lỗi cũ (chờ zombie) luôn ~5 s.
- Nợ từng nằm trong Answer của ticket #22, đã tách thành ticket #34.

## Công việc đã thực hiện

- `tests/test_live_tracking.py::TestVeSinhWorkerCu::test_reap_khong_cho_zombie_5_giay` (bản sau review):
  - spy `worker_source._wait_pid_gone`: lần chờ **ĐẦU** phải là `TERM_WAIT_S` và phải trả `True` ⇒
    `len(goi) == 1` (**không leo thang SIGKILL** — đây mới là dấu hiệu "zombie tính là sống");
  - `elapsed < TERM_WAIT_S` (2,0 s; đo thật **0,22 s** ⇒ biên ~9×);
  - `proc.poll() is not None` giữ lại nhưng nói đúng: **"đã bị giết"** (chính `poll()` là thứ reap nên
    nó không chứng minh reaper đã *chờ* tới khi chết).
- Test mới `test_pid_alive_tinh_zombie_la_da_chet`: spawn `true`, chờ `/proc/<pid>/stat` = `Z`, assert
  `_pid_alive(pid) is False`.

**Vì sao không dùng trần `TERM_WAIT_S + KILL_WAIT_S + 1 = 4,0 s`** (bản đầu) và **không** dùng
`max(5, 2×CPU)` (gợi ý trong ticket): cả hai đều là "ngân sách", không phải hành vi. Hồi quy "zombie
tính là sống" chỉ tốn đúng **2 + 1 = 3,0 s** ⇒ **lọt** trần 4,0 s (review vòng 1 bắt đúng, P1); còn
`max(5, …)` thì 5 s của lỗi cũ cũng lọt.

## Output / Kết quả

- Chạy riêng **5/5 lần xanh**; thời gian reap đo được **0,22 s** (máy này, 8 lõi) — lệnh:
  `python -m pytest tests/test_live_tracking.py -k "reap_khong or pid_alive"`.
- **Diễn tập ngược** (chứng minh test có răng): tạm cho `_pid_alive` chỉ kiểm `/proc` tồn tại (đúng lỗi
  cũ) ⇒ **2/2 test ĐỎ**; phục hồi ⇒ **2/2 xanh**.
- `./run lint` xanh · `./run test` **1354 passed**, 5 deselected.
- **File thay đổi**: `tests/test_live_tracking.py` (2 test), `.scratch/camera-ai-realtime/issues/34-*.md`,
  `docs/task/17-11-2026-ticket-34-test-reap-assert-poll.md`. **Không** đổi code sản phẩm.

## Vấn đề & cách xử lý

- `nproc` = 8 nhưng ngưỡng **không** dùng số CPU: trần suy từ hằng thời gian của chính reaper là quan
  hệ nhân quả (chậm hơn trần ⇒ reaper đã phải chờ hết `TERM_WAIT_S`/`KILL_WAIT_S`), còn số CPU chỉ là
  proxy. Ghi lại để lần sau không "sửa" ngược về `2 × CPU`.

## Review độc lập (§9.1)

Vòng 1 (agent `reviewer`, chỉ đọc): **1 P1** — trần 4,0 s không phân biệt được hồi quy "zombie tính là
sống" (chỉ 3,0 s) trong khi docstring/log khẳng định ngược. **Đã sửa** bằng cách bám hành vi (spy
`_wait_pid_gone` + `elapsed < TERM_WAIT_S`) và thêm test `_pid_alive`. P2/P3 khác: tripwire tự tham
chiếu hằng sản phẩm (đã bỏ), lời "đã reap" (đã sửa), log thiếu danh sách file + ngày (đã bổ sung),
ticket có 2 dòng Status và title nói "ngưỡng theo số CPU" (đã sửa title + checklist).

## Next steps

- Hai nợ còn lại của audit: ticket **#35** (`stability` nhận 2 mẫu cho frame `start()`), **#36** (tên file
  mask khi chọn ô giữa phiên).

## Tài liệu tham khảo

- Ticket #34 · ticket #22 (nơi phát sinh nợ) · `src/api/adapters/worker_source.py`
  (`_terminate_process`, `TERM_WAIT_S`, `KILL_WAIT_S`) · AGENTS §6 ("đo trước, hứa sau"; test không được
  đỏ oan vì thời gian tường).
