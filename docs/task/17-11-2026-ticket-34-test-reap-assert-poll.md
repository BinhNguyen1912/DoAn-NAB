# 17-11-2026 — Ticket #34: `test_reap_khong_cho_zombie_5_giay` thôi đo thời gian tường

## Mục tiêu

Bỏ ngưỡng thời gian tuyệt đối (`elapsed < 3 s`) — trên máy bị chiếm CPU một lần reap **hợp lệ** vẫn có
thể vượt 3 s ⇒ test đỏ oan. Thứ cần khẳng định là **hành vi**: tiến trình đã được reap.

## Input

- `src/api/adapters/worker_source.py`: `TERM_WAIT_S = 2.0`, `KILL_WAIT_S = 1.0` ⇒ trường hợp xấu nhất
  hợp lệ ≈ 3 s (worker bỏ qua SIGTERM); lỗi cũ (chờ zombie) luôn ~5 s.
- Nợ từng nằm trong Answer của ticket #22, đã tách thành ticket #34.

## Công việc đã thực hiện

- `tests/test_live_tracking.py::TestVeSinhWorkerCu::test_reap_khong_cho_zombie_5_giay`:
  - assert **`proc.poll() is not None`** (đã reap) — khẳng định hành vi, không phải số đo;
  - trần thời gian đổi thành **`TERM_WAIT_S + KILL_WAIT_S + 1.0`** (4,0 s), lấy theo **chính hằng của
    code reaper** thay vì số 3 gõ tay ⇒ khi ai đổi `TERM_WAIT_S` thì trần tự đi theo;
  - message in **thời gian thật** + trần + gợi ý "~5 s = chờ zombie";
  - thêm `assert tran < 5.0` **trong test** để trần không bị nới tới mức lỗi cũ (chờ đúng 5 s) lọt.

Vì sao **không** chọn `max(5, 2×số CPU)` (gợi ý trong ticket): 5 s chính là thời gian của lỗi cũ ⇒ biên
đó làm test **mất răng**. Trần 4,0 s vẫn rộng gấp ~18 lần thời gian reap thật (0,22 s) nên máy chậm
không đỏ oan.

## Output / Kết quả

- Chạy riêng **5/5 lần xanh**; thời gian reap đo được **0,22 s** (máy này, 8 lõi).
- `./run lint` xanh · `./run test` **1353 passed**, 5 deselected.
- Không đổi code sản phẩm (chỉ test + log).

## Vấn đề & cách xử lý

- `nproc` = 8 nhưng ngưỡng **không** dùng số CPU: trần suy từ hằng thời gian của chính reaper là quan
  hệ nhân quả (chậm hơn trần ⇒ reaper đã phải chờ hết `TERM_WAIT_S`/`KILL_WAIT_S`), còn số CPU chỉ là
  proxy. Ghi lại để lần sau không "sửa" ngược về `2 × CPU`.

## Next steps

- Hai nợ còn lại của audit: ticket **#35** (`stability` nhận 2 mẫu cho frame `start()`), **#36** (tên file
  mask khi chọn ô giữa phiên).

## Tài liệu tham khảo

- Ticket #34 · ticket #22 (nơi phát sinh nợ) · `src/api/adapters/worker_source.py`
  (`_terminate_process`, `TERM_WAIT_S`, `KILL_WAIT_S`) · AGENTS §6 ("đo trước, hứa sau"; test không được
  đỏ oan vì thời gian tường).
