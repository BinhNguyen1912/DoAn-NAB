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

## Bổ sung sau review độc lập (P2 ×2 + P3 ×4)

Reviewer (phiên chỉ-đọc, không thấy nhánh nên kiểm tĩnh trên `main` + mô tả) bắt đúng **2 P2**:

**P2-1 — guard chỉ cứu đường `--bbox`.** Chạy CLI **không** `--bbox` vào thư mục của phiên web vẫn: ghi
`status.json` `loading` đè phiên kia, ghi `frame.jpg` xen vào (API phát ảnh trộn), và **đọc luôn**
`bbox.json` của phiên đó rồi bám đúng ô ấy. ⇒ Nay guard **VÔ ĐIỀU KIỆN**, đặt **trước** `mkdir` /
`_write_loading` để không đụng một byte nào của phiên đang chạy. Test mới: chạy **không** `--bbox` ⇒ mã
2 và `status.json` **nguyên byte**.

**P2-2 — PID tái chế ⇒ chặn vĩnh viễn + câu báo sai sự thật.** pidfile cũ trỏ một tiến trình khác đang
sống (không phải worker) thì `pid_con_song` vẫn nói "có phiên đang giữ"; lối thoát duy nhất là tự xoá
pidfile. Repo đã có tiền lệ `_is_our_live_worker` (đối chiếu **argv**), dùng ở `demo_preflight` + 3 test.
⇒ Nay `phien_live_dang_giu` chỉ trả pid khi `is_live_worker_for(read_cmdline(pid), out_dir)`; thông điệp
in kèm pid + đường dẫn pidfile + cách xử lý (`xoá worker.pid` nếu là pid tái chế). Test: tiến trình
`sleep 30` sống thật nhưng **không** phải worker ⇒ **không** chặn oan.

**P3 đã sửa:**
- **`src/proc_pid.py` (module mới)**: `pid_con_song`, `read_pid`, `read_cmdline`, `is_live_worker_for` —
  một bản duy nhất; `src/api/adapters/worker_source.py` import lại và **giữ tên cũ** (`_read_pid`,
  `_read_cmdline`, `_is_our_live_worker`, `_pid_alive`) vì `tests/test_live_tracking.py` +
  `scripts/demo_preflight.py` import trực tiếp.
- **Chỉ Linux**: ghi rõ trong docstring module — trên macOS/Windows `/proc` không có ⇒ các hàm này
  **fail-open** (không chặn); **cấm** dùng `os.kill(pid, 0)` (trên Windows tín hiệu 0 = `TerminateProcess`
  ⇒ giết tiến trình đang kiểm, đã ghi ở `scripts/demo_preflight.py`).
- **3 lỗ "răng" của test cũ** đã bịt: (i) assert `exc.value.code == 2` (không chỉ `SystemExit`);
  (ii) pre-tạo `status.json` + assert **nguyên byte** (nếu guard bị dời xuống sau `_write_loading` thì
  test đỏ); (iii) tiến trình giả có **argv đúng** (`… live_worker.py --out-dir <dir>`) thay vì pid bịa.
- **Docstring `Output`** của `src/live_tracking.py` nêu `bbox.json` + `worker.pid` do **phía API** ghi,
  module chỉ đọc — để người sau không "dọn" nhầm.
- **Ticket #37 lệch phạm vi (đúng hướng, đã ghi)**: ticket đề nghị kiểm `status.json ∈
  {running,loading,waiting_selection}`, bản này kiểm **pid + argv** — tốt hơn, vì `waiting_selection`
  không ghi `status.json` đều (AGENTS §6) và `status.json` cũ/hỏng sẽ gây chặn oan.

**Diễn tập ngược 3/3 đỏ→xanh**: (a) bỏ đối chiếu argv ⇒ `test_pid_tai_che_khong_chan_oan` đỏ;
(b) `pid_con_song` luôn `True` ⇒ `test_pid_alive_tinh_zombie_la_da_chet` đỏ; (c) dời guard xuống **sau**
`_write_loading` ⇒ `test_tu_choi_ca_khi_KHONG_co_bbox` đỏ (đúng lỗ P2-1).

**Trạng thái**: `./run lint` xanh · `./run test` **1390 passed** (5 deselected) · 5 file test liên quan
(`test_live_worker_cli`, `test_live_tracking`, `test_live_watchdog`, `test_api_live`,
`test_demo_preflight`) xanh.
