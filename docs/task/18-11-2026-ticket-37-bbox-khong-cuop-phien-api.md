# 18-11-2026 — Ticket #37: `live_worker --bbox` không được cướp `bbox.json` của phiên API

## Mục tiêu

Đóng P3 mà review độc lập (vòng 3 của ticket #36) tạo ticket: `tools/live_worker.py` ghi
`<out-dir>/bbox.json` khi có `--bbox` **mà không kiểm** thư mục đó có phiên live khác đang dùng. Chạy CLI
vào đúng `--out-dir` của một phiên web đang `waiting_selection` ⇒ phiên web **bám ô của người chạy CLI**,
không một dòng cảnh báo.

## Input

- Ticket: `.scratch/camera-ai-realtime/issues/37-live-worker-bbox-ghi-de-bbox-json-cua-phien-api.md`
- Code liên quan: `tools/live_worker.py` (khối ghi `bbox.json`), `src/live_tracking.py` (`BBOX_NAME`),
  `src/api/adapters/worker_source.py` (`PID_NAME`, `_pid_alive`, `_OWNED_FILES`).

## Công việc đã thực hiện

1. **Một bản logic duy nhất cho "pid còn sống"**: chuyển `_pid_alive` từ
   `src/api/adapters/worker_source.py` sang `src/live_tracking.py` thành `pid_con_song(pid)` (zombie =
   đã chết, đúng kết luận ticket #34), và `_pid_alive = pid_con_song` ở adapter. Lý do: CLI **không**
   được import module API (nó kéo `fastapi`/port), mà logic này đã có hai chỗ suýt trùng.
2. `PID_NAME = "worker.pid"` khai ở `src/live_tracking.py` (adapter import lại — hết hằng trùng).
3. `phien_live_dang_giu(out_dir)` (trong `src/live_tracking.py`): đọc `<out-dir>/worker.pid`, trả pid nếu
   **khác pid của chính tiến trình** và **còn sống thật**, ngược lại `None`.
4. `tools/live_worker.py`: trước khi ghi `bbox.json` ⇒ nếu `phien_live_dang_giu(...)` khác `None` thì
   `parser.error` (mã 2) kèm gợi ý `--out-dir` riêng; **không** ghi file nào.
5. Test: `TestBboxKhongCuopPhienKhac` — (a) `worker.pid` trỏ tiến trình sống (`sleep 30`) ⇒ mã 2, stderr
   nêu lý do, **không** có `bbox.json`; (b) `worker.pid` trỏ tiến trình đã chết ⇒ **không** chặn oan.

## Output / Kết quả

- `./run lint` xanh · `./run test` **1388 passed**, 5 deselected.
- **Diễn tập ngược**: thay `chu = phien_live_dang_giu(args.out_dir)` bằng `chu = None` ⇒ test (a) **đỏ**;
  phục hồi ⇒ xanh.
- Không đổi hành vi đường API: adapter gọi đúng hàm cũ qua alias `_pid_alive`, 30 test liên quan
  (`worker_source`/`reap`/`pid`/`live_crash`) xanh.

## Vấn đề & cách xử lý

- **Không import module API từ CLI**: bản nháp đầu nghĩ tới `from src.api.adapters.worker_source import
  _pid_alive`, nhưng module đó import `src.api.domain`/`ports` (và gián tiếp `fastapi` ở đường app) ⇒
  CLI worker sẽ phải cõng cả API. Đổi sang đặt helper ở `src/live_tracking.py` (nơi đã có `BBOX_NAME`,
  `FRAME_NAME`… mà adapter vốn import).
- **Zombie**: dùng đúng kết luận ticket #34 (`/proc/<pid>/stat` trạng thái `Z` = đã chết) thay vì
  `os.kill(pid, 0)` (zombie vẫn "sống" theo `kill(0)`) — nếu không, `worker.pid` của phiên vừa chết sẽ
  chặn oan lần chạy sau.

## Next steps

- Chưa xử lý (ngoài phạm vi, không có bằng chứng cần): PID **tái chế** (pidfile cũ trỏ một tiến trình
  khác đang sống cùng pid) vẫn có thể chặn oan — ca hiếm, và repo đã có tiền lệ xử lý bằng cách đối
  chiếu `argv` (`_is_our_live_worker` trong `demo_preflight`); CLI chưa làm vì phải đọc `/proc/<pid>/cmdline`.
  Nếu gặp thật, thêm kiểm `cmdline` chứa `live_worker.py` + `--out-dir` bằng thư mục này.

## Tài liệu tham khảo

- `src/live_tracking.py` (`pid_con_song`, `phien_live_dang_giu`, `PID_NAME`)
- `src/api/adapters/worker_source.py:53` (`_OWNED_FILES`), `tools/live_worker.py` (khối `bbox_ghi`)
- `AGENTS.md` §6 (bẫy `0,0 ≠ số đo`; "chặn oan" nguy hiểm ngang "bỏ lọt")
