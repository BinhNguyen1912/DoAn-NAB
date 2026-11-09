# Ngày 09-11-2026 — Watchdog phiên live + xuất bản H.264 cho `--record`

> Nối tiếp plan `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md` (việc **3** và **4** trong
> thứ tự đã chốt). Hai việc 1–2 của plan đã xong ở PR #9 (drift + tuổi mask + ngưỡng nhiễu).

## 🎯 Mục tiêu
1. **Watchdog**: worker chết/treo **giữa phiên** live phải lộ ra thành `error` có message + đóng luồng
   MJPEG — hết kiểu "hỏng mà trông như đang chạy". Tiêu chí đăng ký trước: `/api/live/status` trả
   `error` **≤ 2 s** sau `kill -9` worker.
2. **H.264 cho CLI `--record`**: video demo mở bằng Chrome/Edge phải phát được (recorder đang `mp4v`).

## 📥 Input
- Plan 08-11 (thứ tự việc + tiêu chí nghiệm thu có số), `AGENTS.md` §6 (đo trước, hứa sau).
- Mã hiện tại: `src/api/live.py`, `src/api/adapters/worker_source.py`, `src/api/ports.py`,
  `src/api/domain.py`, `tools/run_live.py`, `web/src/components/LivePanel.tsx`.
- Đồ nghề có sẵn: `src/worker/web_export.py` (`transcode_for_web`, libx264 + yuv420p + faststart).
- Bằng chứng lỗ hổng: sau `start()` **không chỗ nào** gọi `proc.poll()`; `live.py` chỉ set `ERROR`
  ở nhánh start thất bại; `frames()` im lặng `return` sau `idle_timeout`.

## 🔨 Công việc đã thực hiện

### 1. Watchdog (việc 3 của plan)
1. **Port mới** `HealthReportingSource` (`health() -> SourceHealth | None`, `None` = khoẻ) + dataclass
   `domain.SourceHealth(state, message)`. Tách riêng như `LiveTelemetrySource`: webcam/file không phải
   biết khái niệm "worker chết".
2. **Adapter** `WorkerFrameSource.health()` đọc 3 tín hiệu theo thứ tự tin cậy:
   1. `proc.poll()` — đã thoát thì phân biệt `stopped` (kết thúc bình thường: hết video,
      `stop_after_frames`) với lỗi, kèm **mã thoát** + đường dẫn `worker.log`;
   2. `status.json == error` — giữ nguyên message worker tự viết (model lỗi, nguồn đọc lỗi);
   3. **tuổi `frame.jpg` quá `max(15 s, 4 × vos_ms)`** — còn tiến trình mà frame đứng ⇒ treo
      (deadlock model). Ngưỡng phải rộng: nhịp ghi frame hợp lệ có thể ~4 s/frame (xem P1-1 ở mục
      Review); ca `kill -9` không dùng ngưỡng này mà bắt bằng `proc.poll()`.
3. **Service** kiểm mỗi **0,2 s** (không phải mỗi frame), lỗi đọc tín hiệu **không** tính là chết (chỉ
   log warning). Phát hiện chết ⇒ `error`/`stopped` + message, thread đọc thoát ⇒ `frames()` đóng luồng,
   và **đóng nguồn ngay** để worker treo không giữ webcam (nếu không, lần "Bật phát" sau sẽ không mở
   được camera).
4. **UI** (`LivePanel`): dòng trạng thái mang class `error` + `role="alert"` khi lỗi. Nút "Bật phát"
   vốn đã bật lại được khi `state != running` ⇒ chính là nút "chạy lại".
5. Script đo `scripts/measure_watchdog.py` (worker thật, `kill -9`, artifact JSON có `git_rev`).

### 2. H.264 cho `--record` (việc 4 của plan)
1. `_web_record_path`: `demo.mp4` → `demo_web.mp4` (không bao giờ ghi đè bản gốc).
2. `_export_web_record`: gọi lại `transcode_for_web` (ffmpeg qua `imageio-ffmpeg`), thiếu ffmpeg chỉ
   **cảnh báo**, không ném lỗi — bản ghi gốc đã xong.
3. `_finish_recording` thay `viz.close_recorder()` ở **cả hai** nhánh (`_run_display`, `_run_headless`)
   — thứ tự quan trọng: đóng recorder trước, chuyển mã sau.

### 3. Sửa kèm (phát hiện trong lúc chạy full suite)
- `_terminate_process` trả về **ngay sau** `killpg(SIGKILL)`; dưới tải, tiến trình còn sống thêm vài
  chục ms ⇒ test `test_reap_worker_cu_con_song` chập chờn. Nay chờ tới khi chết thật (`TERM_WAIT_S`,
  `KILL_WAIT_S`), có test riêng với tiến trình **bỏ qua SIGTERM**.

## 📤 Output / Kết quả

### Số đo thật (worker thật, `kill -9` giữa phiên, 3 lần)
`data/watchdog_2026-11-09_metrics.json` — `git_rev = 013e0a7`, `git_dirty_code = false`,
lệnh: `python scripts/measure_watchdog.py --mode worker --lan 3`, clip `data/binh1.mp4`,
`image_size 192`, `vos_every 3`, laptop CPU (Iris Xe, torch CPU, SAM 2.1 tiny):

| Lần | nạp phiên | state sau kill | **báo `error`** | **đóng luồng MJPEG** | message |
|---|---|---|---|---|---|
| 1 | 3,1 s | `error` | **115,9 ms** | 94,6 ms | worker đã dừng (mã -9) — xem worker.log |
| 2 | 2,9 s | `error` | **116,0 ms** | 110,0 ms | worker đã dừng (mã -9) — xem worker.log |
| 3 | 2,9 s | `error` | **116,5 ms** | 109,8 ms | worker đã dừng (mã -9) — xem worker.log |

> ⚠️ Bảng này **thay thế mọi bảng trước đó** trong file (mỗi lần đo lại là artifact bị ghi đè) ⇒
> **chỉ trích bảng này**, và bảng ở mục "Bổ sung 22:40" cho mode `raw`.

**Ngưỡng đăng ký trước: ĐẠT** — cả hai mốc plan ghi (mục nghiệm thu **≤ 5 s**, dòng ticket
**≤ 2 s**): chậm nhất 116,5 ms, 0/3 lần vượt; 3/3 lần luồng đóng (0/3 lần treo). Đây là phép đo
**ngưỡng**, không phải so A/B nên không cần ngưỡng nhiễu; độ tản 116–117 ms là độ trễ kiểm tra
0,2 s cộng nhịp poll 0,02 s (chạy lại trên `013e0a7` — xem "Bổ sung 23:30").

⚠️ **Con số này CHỈ đúng cho ca "tiến trình chết"** (bắt bằng `proc.poll()`). Ca khác — worker **còn
sống nhưng treo** (deadlock model) — phát hiện chậm hơn nhiều: **~15 s** (ngưỡng `max(15 s, 4 ×
vos_ms)`, trần 120 s). Cấm trích "watchdog phản ứng trong 0,1 s" cho ca treo.

### H.264 (CLI, chạy thật)
`python tools/run_live.py --source data/binh1.mp4 --bbox 104,308,209,287 --max-frames 40
--image-size 192 --record data/h264_check.mp4` → tự xuất `data/h264_check_web.mp4`.
`ffmpeg -i` trên hai file:

| File | Codec | Ghi chú |
|---|---|---|
| `data/h264_check.mp4` (gốc) | `mpeg4 (Simple Profile) (mp4v)` | Chrome/Edge **không** giải mã |
| `data/h264_check_web.mp4` (bản web) | `h264 (High) (avc1)`, `yuv420p` | phát được trên web |

### Kiểm tra tự động
- `./run lint` → **All checks passed**
- `./run test` (làn nhanh) → **xanh**, chạy **3 lần liên tiếp** để soi test chập chờn
- `./run testall` (full, có checkpoint SAM 2) → **654 passed** trong 211 s (đụng `visualizer`/CLI)
- `./run webtest` → 24 test xanh; `npm run build` → xong
- `./run e2e` (Chrome/Edge thật) → **PASS 23/23**, gồm `trình duyệt GIẢI MÃ được video kết quả (H.264)`
  và `luồng MJPEG hiện được frame trong trình duyệt`. **Phạm vi:** e2e phủ bản H.264 của **đường API
  job** (`out_web.mp4`); bản `_web.mp4` của **CLI** phủ bằng test thật `test_that_su_ra_h264…`
  (tag codec) + kiểm tay `ffmpeg -i` ở bảng trên.

### File thay đổi
- `src/api/domain.py` — `SourceHealth`
- `src/api/ports.py` — port `HealthReportingSource`
- `src/api/live.py` — kiểm sức sống mỗi 0,2 s, chuyển `error`/`stopped`, đóng luồng + đóng nguồn
- `src/api/adapters/worker_source.py` — `health()`, `_age_s`, `_wait_pid_gone`, sửa `_terminate_process`
- `tools/run_live.py` — `_web_record_path`, `_export_web_record`, `_finish_recording`
- `web/src/components/LivePanel.tsx` — dòng trạng thái kiểu `error` + `role="alert"`
- `tests/test_live_watchdog.py` — **mới**, 16 test (adapter + service + route + hợp đồng với worker)
- `tests/test_live_tracking.py` — test `_terminate_process` phải chờ tiến trình chết thật
- `tests/test_run_live_cli.py` — 4 test cho xuất bản H.264 (wiring, thiếu ffmpeg, không bật ghi, codec thật)
- `scripts/measure_watchdog.py` — **mới**, đo phản ứng API khi `kill -9` worker
- `data/watchdog_2026-11-09_metrics.json` — **mới**, artifact số đo
- `README.md` (mục codec), `AGENTS.md` §6 (quy tắc: heartbeat là `frame.jpg`, không phải `status.json`)

## 🔍 Review độc lập (AGENTS §9.1)
- **Ai:** agent `reviewer` (phiên riêng, chỉ đọc), phạm vi `git diff origin/main..HEAD`.
- **Kết quả vòng 1:** 0 **P0**, **2 P1**, 3 P2, 6 P3. Không có P0 ⇒ không chặn merge; cả 2 P1 đều
  sửa được trong < 30 phút nên sửa ngay trong PR này.
  - **P1-1 (nặng, đúng):** ngưỡng treo **2 s** giả định worker ghi ≥ 0,5 frame/s — sai với cấu hình
    hợp lệ: `image_size 1024` ≈ 4 s/frame, `vos_every=1` (tắt LK) ⇒ nhịp ghi = nhịp model, và
    `engine.start()` chạy **inline** trước frame đầu ⇒ watchdog sẽ **giết phiên khoẻ**. Sửa: ngưỡng
    `max(15 s, 4 × vos_ms)`; ca `kill -9` vẫn ≤ 2 s vì bắt bằng `proc.poll()`, không dùng ngưỡng này
    (số đo lại xem bảng ở mục "Bổ sung 22:40"; bộ số cũ trong file đã bị gỡ). Thêm 3 test canh
    false-positive.
  - **P1-2 (nặng, đúng):** `_finish_recording` (ffmpeg chạy **im lặng**, timeout 300 s) được gọi
    **trước** `_finish_metrics`; Ctrl+C lần hai lúc chờ ffmpeg (`KeyboardInterrupt ⊄ Exception`) ⇒
    **mất CSV/summary** — tái phạm bảo đảm "Ctrl+C không mất metrics" (18-10). Sửa: `_finish_outputs`
    (số liệu trước, video sau), bắt cả `KeyboardInterrupt`, in dòng báo trước khi gọi ffmpeg; có test
    `test_ctrl_c_trong_khi_chuyen_ma_van_giu_metrics`.
  - **P2 đã sửa:** (a) `stop()` phiên cũ xoá nhầm `worker.pid` của phiên mới (watchdog đóng nguồn
    trong luồng nền) ⇒ chỉ xoá nếu pidfile vẫn là của mình + test; (b) message đổ mọi thất bại chuyển
    mã thành "không có ffmpeg" ⇒ phân biệt bằng `find_ffmpeg()`, và chỉ chuyển mã khi `viz.recording`
    (tránh chuyển mã **file cũ** rồi báo "phát được trên Chrome" — thành công giả) + 2 test;
    (c) `_web_record_path` giữ đuôi nguồn (`demo.avi` → `demo_web.avi` = Chrome vẫn không phát) ⇒
    luôn `.mp4` + test.
  - **P3 đã sửa:** assert lỏng `"mã 1" in msg or "1" in msg` (luôn đúng); 3 test "không báo lỗi giả"
    chỉ `sleep(0,2–0,3)` rồi assert ⇒ nay đếm số lần `health()` được gọi (`_wait`); test thứ tự
    đóng-recorder nay đọc lại file bằng `cv2` để chứng minh moov đã ghi.
  - **P3 → Next steps (không sửa trong PR này):** (i) mode `raw` dùng `OpenCvFrameSource` **không** có
    `health()` ⇒ webcam chết giữa phiên raw vẫn báo `running` (cùng lớp lỗi, khác adapter — ticket
    riêng); (ii) `/api/live/stream` trả 409 với cùng một câu cho cả `error` và "chưa bật";
    (iii) worker nên `_publish_status` **trước** `_stop_worker()` khi kết thúc để cửa sổ "chưa kịp
    ghi `stopped`" không bị đọc thành treo (hiện đã an toàn vì ngưỡng 15 s > join 5 s).
- **Đã kiểm, không phải lỗi** (reviewer xác nhận): `_generation` chặn đúng thread cũ ghi đè phiên
  mới; không deadlock dù `_check_health` gọi `source.stop()` ngoài lock; `kill` hai lần vô hại;
  `waiting_selection` thật sự khoẻ (test dùng mtime `status.json` cũ 2 phút nên bản cài đặt dùng
  `ts` sẽ đỏ); port/domain không phá ADR-0005; artifact `git_rev`/`git_dirty` nhất quán; số trong
  docs khớp artifact.
- **Vòng 2 (review phần vừa sửa):** kết luận **merge được**, 0 P0/P1 mới, nhưng bắt **1 P2 do chính
  bản sửa sinh ra**: `_finish_outputs` gọi `_finish_metrics` trước mà **không có `try/finally`** ⇒ nếu
  ghi số liệu ném (đĩa đầy, `git` lỗi, Ctrl+C lần hai) thì recorder không được đóng và `demo_web.mp4`
  **không được tạo** — đúng thứ PR này muốn có. Đã sửa (`try/finally`), thêm 3 P3: pidfile chỉ xoá
  khi `_read_pid() == proc.pid` (file rỗng không bị coi là "không phải của mình"), chặn trần ngưỡng
  treo **120 s** (một mẫu `vos_ms` khó tin không được nới ngưỡng lên 4 phút), `Visualizer.recording`
  nay là "**đã ghi frame**" (đếm `_frames_written`) thay vì "writer đã mở". Ba test được siết lại:
  test "không có `health()`" chứng minh bằng **số frame thật** (không `sleep`), test pidfile dùng
  **tiến trình thật** thay pid bịa `111` (tránh gửi SIGTERM vào process group của người khác), test
  Ctrl+C kiểm **thứ tự** (CSV phải tồn tại ngay lúc chuyển mã).
- **Nợ lại có chủ:** 3 P3 ở trên đã ghi vào Next steps (không im lặng bỏ qua). Ngoài ra vòng 2 ghi
  nhận 2 điểm đã biết, chưa sửa: (a) `vos_ms` là **mẫu cuối** nên máy suy giảm > 4× đột ngột vẫn có
  thể false-positive (nếu cần chắc: đòi 2 lần vi phạm cách nhau ≥ 5 s); (b) API job chuyển mã **hai
  lần** (CLI xuất `out_web.mp4`, rồi `subprocess_runner` xoá và làm lại) — tốn gấp đôi thời gian hậu
  kỳ trên VPS 4 GB, có từ trước PR này.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Định giết phiên khoẻ oan**: bản nháp định thêm `ts` vào `status.json` rồi lấy đó làm heartbeat
  (đúng như plan ghi). Đọc lại `src/live_tracking.py:342-348` thì thấy lúc `waiting_selection` worker
  **chỉ ghi `frame.jpg`, không ghi `status.json`** ⇒ người dùng chờ 2 phút kéo chuột là `ts` cũ 2 phút
  và watchdog sẽ giết phiên hoàn toàn khoẻ. Chuyển sang **mtime của `frame.jpg`** (đúng thứ UI đang
  tiêu thụ) và ghi thẳng vào docstring + `AGENTS.md` §6 để lần sau không ai thêm `ts` nữa.
- **Test "route trả error" đầu tiên fail với `KeyError: 'message'`**: lỗi của test, không phải của code
  — `(body := ...)` trong `lambda` tạo biến **cục bộ của lambda**, biến ngoài vẫn `{}`. Sửa bằng hàm
  `_da_error()` có closure thật.
- **Test luồng MJPEG "DID NOT RAISE StopIteration"**: nguồn giả kịp ghi thêm vài frame trước khi chết
  nên luồng phát nốt rồi mới đóng. Sửa test cho đúng hành vi (điều cần kiểm là luồng **đóng**, không
  phải đóng ngay lập tức) thay vì bóp code cho vừa test.
- **`test_reap_worker_cu_con_song` chập chờn** khi chạy full suite (xanh khi chạy riêng): `killpg`
  xong `return` ngay. Đã sửa + thêm test hồi quy với tiến trình bỏ qua SIGTERM.
- **Test codec H.264**: `CAP_PROP_FOURCC` của OpenCV trả **int little-endian** (`0x34363268` ↔ `"h264"`);
  decode sai chiều ra `"462h"`. Đã kiểm chéo bằng `ffmpeg -i` (đúng là `h264 (High) (avc1)`).
- **`.venv` (python 3.14) không có `imageio-ffmpeg`** ⇒ 3 test mới lúc đầu không tìm được ffmpeg;
  chạy bằng env `samurai` (python 3.11) thì có, và test thật tự `skip` nếu máy thiếu ffmpeg.

## ➕ Bổ sung 21:30 — watchdog cho mode `raw` + 409 nêu lý do + thứ tự publish `stopped`

Làm 3 P3 mà vòng review 09-11 đã đẩy sang Next steps (không để nợ treo).

### Đã làm
1. **`OpenCvFrameSource` cài `HealthReportingSource`** (`src/api/adapters/opencv_source.py`): chế độ
   `raw` trước đây **không có watchdog** — rút webcam/relay chết thì `read_jpeg()` trả None mãi, API
   vẫn `running`, ảnh đứng. `health()` phân biệt 3 ca: (a) chưa start/đã stop theo lệnh ⇒ `None`;
   (b) file hết mà **không lặp** ⇒ `STOPPED`; (c) camera/luồng không trả frame > `STALE_S = 3 s`
   (hoặc mất `capture` vì mở lại file thất bại) ⇒ `ERROR`. `_rewind()` không còn gọi `stop()`
   (`stop()` đánh dấu "chủ động đóng" ⇒ health sẽ im lặng coi là khoẻ).
2. **`/api/live/stream`**: 409 kèm lý do của watchdog khi `state == error` (trước: câu chung "Chưa có
   phiên live nào đang chạy" cho cả hai ca).
3. **`LiveTrackingSession.run()`**: công bố `stopped` **trước** `_stop_worker()`; vẫn publish lần cuối
   sau join để nếu luồng VOS báo lỗi thì state thành `error`.
4. **`scripts/measure_watchdog.py`**: thêm `--mode raw` (tắt relay ảnh THẬT bằng
   `http.server` trên localhost) + ngưỡng đăng ký trước tách theo mode (worker 2 s, raw 5 s) +
   tách `git_dirty_code` (bỏ `data/`) để đo lại artifact không bị coi là "code bẩn".

### Số đo thật (2 mode, mỗi mode 3 lần)

> Số **cuối cùng** của cả hai mode nằm ở mục "Bổ sung 22:40" (`git_rev = 013e0a7`). Các bảng của
> lần đo cũ đã được gỡ để trong file chỉ còn MỘT bộ số — artifact bị ghi đè mỗi lần đo nên hai bộ số
> trong cùng file là bẫy trích dẫn.

| Mode | Nguồn bị giết | ngưỡng đăng ký trước | kết quả |
|---|---|---|---|
| `worker` (`proc.poll()`) | `kill -9` worker SAM 2 | ≤ 2 s | ✅ 3/3 (xem 22:40) |
| `raw` (không có frame) | tắt relay ảnh HTTP | ≤ 5 s | ✅ 3/3 (xem 22:40) |

- Artifact: `data/watchdog_2026-11-09_metrics.json` + `data/watchdog_raw_2026-11-09_metrics.json`.
- **Cấm trộn hai số**: mode `worker` bắt bằng `proc.poll()` nên ~0,1 s; mode `raw` chỉ biết qua
  "không có frame" nên phải chờ `STALE_S` 3 s (cộng ~0,7 s do nguồn snapshot giữ frame cuối
  `max_misses=20` lần trước khi trả None). Đừng trích "watchdog phản ứng 0,1 s" cho webcam.
- **Số `raw` chỉ đúng cho ca "connection refused" trên localhost.** Với `HttpSnapshotSource` thật:
  đồng hồ 3 s chỉ bắt đầu SAU `max_misses=20` lần hỏng liên tiếp; mạng "black-hole" (mỗi lần hỏng
  chờ hết timeout 5 s) ⇒ ảnh có thể đứng **hàng phút** trước khi báo lỗi. **Chưa đo trên
  webcam/RTSP thật** (máy này webcam WSL kẹt usbipd — xem AGENTS §6).
- **Giới hạn còn lại**: `health()` chạy cùng thread với `read()` ⇒ `read()` **treo vô hạn** thì
  không nhịp kiểm nào chạy (V4L2/RTSP không có read-timeout). Đã xử lý ca `read()` trả None hoặc
  ném lỗi; ca treo hẳn phải xử lý ở tầng đọc (đưa vào Next steps).

### Kiểm tra
- `./run lint` ✓ · `./run test` ✓ · `./run testall` **663 passed** · `./run webtest` 24 ✓ ·
  `./run e2e` **PASS**. **Phạm vi e2e**: phủ mode `raw` + nhánh 200 của `/api/live/stream`; nhánh
  **409** phủ bằng test (`TestLuongMjpegBaoDungLyDo`), không phải e2e.
- **Test có răng**: `test_status_da_la_stopped_trong_luc_dang_join_worker` và
  `test_read_jpeg_nem_loi_khong_lam_chet_thread_doc` đã được kiểm bằng cách checkout lại code cũ →
  **đỏ**, rồi phục hồi → xanh.

### Review độc lập (nhánh này)
- **Vòng 1:** 0 P0, **1 P1**, 3 P2, 5 P3. Đã sửa hết P1/P2 + 4 P3 trong cùng nhánh:
  - **P1**: `AGENTS.md` §6 vẫn trích số cũ (91–111 ms) trong khi PR này **ghi đè** artifact, và §6
    **chưa có** số của mode `raw` ⇒ nguy cơ trích "0,1 s" cho webcam. Đã sửa số + thêm bullet `raw`
    kèm cảnh báo cấm trộn hai mode và giới hạn `max_misses`.
  - **P2a**: `_looks_like_file` không nhận **thư mục ảnh** ⇒ chuỗi ảnh (`data/demo_input_frames`) bị
    coi là camera: không lặp lại được khi hết, và báo `ERROR "không trả frame"` cho phiên kết thúc
    bình thường. Sửa + 2 test với thư mục ảnh thật.
  - **P2b**: `git_dirty_code` chỉ được gán trong `try` ⇒ nhánh **git lỗi** ném `UnboundLocalError`
    **sau khi đo xong** (nuốt cả 3 lần đo). Tách `_git_provenance()`/`_is_dirty_outside_data()` +
    `tests/test_measure_watchdog.py` (gồm cả file code mới chưa track).
  - **P2c**: ghi rõ giới hạn `max_misses × timeout` ở trên (docs, không cần đổi logic).
  - **P3**: `read_jpeg()` ném lỗi làm **chết thread đọc** (state kẹt `running`) ⇒ `_read_safely()` +
    test; `run()` trả bản sao `_stats`; comment "watchdog đọc ra treo?" bớt claim (thực tế cửa sổ
    join 5 s < ngưỡng 15 s nên chưa từng xảy ra — giữ code vì đúng thứ tự); test 409 bỏ assertion
    tautology; câu "UI chỉ thấy câu chung" **sai** (UI đọc `status.message` qua `/api/live/status`,
    `<img>` không render JSON) — đã sửa lại: 409 hữu ích cho API client/e2e.

## ➕ Bổ sung 22:40 — review vòng 2 (2 P1 + 2 P2 + 4 P3) + đo lại cả hai mode

### Review độc lập vòng 2 (agent `reviewer`, chỉ đọc, phạm vi `git diff origin/main..HEAD`)
Kết luận: **chưa merge ngay — merge được sau khi sửa 2 P1** (0 P0). Bản sửa vòng 1 được xác nhận
**thật sự đóng lỗ hổng**, không phải làm test xanh (số `raw` 3,73–3,76 s **của lần đo lúc review**
tái lập được từ code: 20 miss ×
2 lần fetch @30 Hz ≈ 0,6–0,7 s + `STALE_S` 3 s). Reviewer cũng tự khai giới hạn: phiên review không
chạy được `git diff`, nên đối chiếu theo ngữ nghĩa code + `.git/logs/refs/heads/…`.

| Mức | Vấn đề | Xử lý trong nhánh này |
|---|---|---|
| **P1** | `STALE_S = 3 s` **nhỏ hơn** read-timeout 5 s của `HttpVideoSource`/`RtspVideoSource` ⇒ **một** lần `read()` chạm timeout đã làm `age` vượt ngưỡng ⇒ `_check_health` gọi `stop()` giết **phiên khoẻ**. Cùng cơ chế với frame đầu (V4L2 trả `False` vài giây khi thiết bị chưa sẵn sàng) | Kết luận cần `age > ngưỡng` **VÀ** `_misses >= MISS_MIN (3)`; thêm `WARMUP_S = 10 s` cho giai đoạn chưa có frame đầu. 4 test mới (một lần trượt không kết luận, đủ 3 lần ⇒ error, ân hạn warmup, đọc lại được thì xoá bộ đếm) |
| **P1** | Bảng số đầu log vẫn trích bản đo cũ (91,3/111,2/110,4 ms trên `cdcd1f5`) trong khi artifact đã bị ghi đè; trong file có **3 bộ số** cho cùng một artifact | Bảng đầu file + bảng ở mục 21:30 nay chỉ còn **một bộ số cuối** (mục này); số cũ ghi rõ "đã bị thay thế" |
| **P2** | Lần đo **không phát hiện được lỗi trong 15 s** bị ghi `vuot_nguong: false` ⇒ `so_lan_vuot_nguong = 0`, script thoát 0: hỏng nặng nhất lại được tính là "đạt" | Tách `_verdict()` → `that_bai`; artifact có `so_lan_khong_phat_hien`; in `[THAT BAI]`; `_exit_code()` trả 1 |
| **P2** | Nhánh git lỗi trả `("", None, None)` ⇒ artifact "trông hợp lệ" với `git_rev: ""`, `git_dirty_code: null`, exit 0 | `_git_provenance()` trả thêm `git_loi` (bắt cả `UnicodeDecodeError` — lỗi cũ bịt `OSError`/`CalledProcessError` là chưa đủ); artifact ghi `git_loi`, in `[CANH BAO]`, `_exit_code()` = 1 |
| **P3** | `_read_safely` log warning theo nhịp đọc (~30 Hz ≈ 1.800 dòng/phút) và **không đếm** ⇒ nguồn không có `health()` kẹt `running` mãi với 0 frame | Log lần 1 + mỗi 100 lần; lỗi liên tiếp quá `_READ_ERROR_GIVE_UP_S` (5 s) ⇒ `error` + message (2 test) |
| **P3** | Message raw "… xem log worker" — mode `raw` **không có** worker, mà UI hiện nguyên câu này | "… xem log API" |
| **P3** | Docstring port `HealthReportingSource` còn ghi "(hiện thực: WorkerFrameSource)" + "webcam/file **không** có khái niệm worker chết" | Cập nhật cả hai hiện thực + lý do mỗi adapter biết mình chết theo cách khác nhau |
| **P3** | Artifact `raw` có `frames_truoc_khi_giet: 0` (relay trả **cùng** bytes nên không tính là frame đổi) ⇒ dễ đọc thành "chưa từng có frame" | Thêm `ghi_chu_frames` giải thích trong từng lần chạy |

**Đã kiểm, không phải lỗi (reviewer xác nhận):** 3 ca của `health()` phân biệt đúng và đúng thứ tự
(`_exhausted` trước `_capture is None`); `_rewind()` không gọi `stop()` (nếu gọi thì `_closed` bật ⇒
watchdog im lặng); `_looks_like_file` với `"0"`/`rtsp://`/`http://…/snapshot.jpg`/`/dev/video0` đều
ra `False`; **không có race** giữa `health()` và `read_jpeg()` (cùng thread — `_check_health` chỉ
được gọi từ `_run`); `_check_health` gọi `source.stop()` ngoài lock là an toàn; test 409 hết
tautology; không có test `sleep`-rồi-assert ở phần mới; số trong `AGENTS.md` §6 khớp artifact.

**Nợ ghi nhận, chưa sửa (không chặn merge):** (a) chưa có test tự động ở **seam adapter↔service** cho
mode `raw` (hiện chỉ chứng minh bằng 3 lần đo tay); (b) `read()` treo vô hạn vẫn không cứu được (đã có
trong Next steps + AGENTS §6); (c) `stop()` từ thread request có thể `release()` `cv2.VideoCapture`
trong lúc thread đọc đang `read()` — race ở tầng C++, có từ trước PR này; (d) số `raw` chỉ đúng cho ca
connection-refused trên localhost.

### Số đo lại (sau khi sửa, cả hai mode) — `git_rev = 013e0a7`, `git_dirty_code = false`

| Mode | Nguồn bị giết | báo `error` (3 lần) | đóng luồng MJPEG | ngưỡng đăng ký trước | đạt? |
|---|---|---|---|---|---|
| `worker` (`proc.poll()`) | `kill -9` worker SAM 2 | **115,9 / 116,0 / 116,5 ms** | 95–110 ms | ≤ 2 s | ✅ 3/3 |
| `raw` (không có frame) | tắt relay ảnh HTTP | **3752 / 3763 / 3747 ms** | 3740–3753 ms | ≤ 5 s | ✅ 3/3 |

- Artifact: `data/watchdog_2026-11-09_metrics.json`, `data/watchdog_raw_2026-11-09_metrics.json` —
  cả hai có `git_rev = 013e0a7`, `git_dirty_code = false`, `git_loi = null`,
  `so_lan_khong_phat_hien = 0`. Số được đo lại **sau** bản sửa review vòng 3 (`013e0a7`).
- Mode `raw` nay là **3,75–3,76 s** (các lần đo cũ đã bị ghi đè — đừng trích số cũ); nguyên nhân
  chậm hơn ~0,7 s so với `STALE_S` hiển thị ngay trong message:
  `91–92 lần liên tiếp` không ra frame, tức là `MISS_MIN` không phải nút chặn ở ca relay (đồng hồ
  `STALE_S` mới là nút chặn). Đừng trích "3 s" — số đúng là **~3,76 s** gồm `max_misses` của nguồn.
- Mode `worker` tản 116–117 ms (3 lần) — cùng cơ chế (độ trễ kiểm tra 0,2 s + poll 0,02 s), chênh
  lệch nằm trong độ tản giữa các lần chạy; mọi lần đều ≪ ngưỡng 2 s.

### Kiểm tra
- `./run lint` ✓ · `./run test` **686 passed**, 5 deselected (~54 s)
- `./run testall` (full, có checkpoint SAM 2) → **691 passed** trong 175 s
- `./run e2e` (Chrome/Edge thật) → **PASS**, gồm "luồng MJPEG hiện được frame trong trình duyệt"
  (160×120, FPS live 29,7) và "dừng phát sạch (state=stopped)" — đúng phần API/live vừa sửa
- **Test có răng đã kiểm bằng cách làm hỏng code**: bỏ điều kiện `_misses >= MISS_MIN` ⇒
  `test_mot_lan_truot_chua_du_ket_luan_chet` + `test_truot_lien_tiep_du_so_lan_thi_error` **đỏ**, phục
  hồi ⇒ xanh.
- Bug thật gặp khi chạy đo: `**tuple` ⇒ `TypeError: 'tuple' object is not a mapping` (nuốt cả 3 lần
  đo trước khi ghi artifact) ⇒ tách `_verdict_dict()` + test.

## ➕ Bổ sung 23:30 — review vòng 3 (1 P1 + 1 P2 + 8 P3) + đo lại lần cuối

### Review độc lập vòng 3 (agent `reviewer`, chỉ đọc, phạm vi HEAD `e3826c6`)
Kết luận: **merge được sau khi sửa P1**. Vòng 3 xác nhận 4 bản sửa vòng 2 **đóng đúng lỗ hổng**
(không chỉ làm test xanh): nó tự kiểm lại "test có răng" bằng cách đọc assertion (thay vì tin log) và
tái lập cơ chế 3,7 s từ code (20 miss × 2 fetch ≈ 0,7 s + `STALE_S` 3 s). Nhưng chính bản sửa vòng 2
sinh ra **1 P1 mới**.

| Mức | Vấn đề | Xử lý |
|---|---|---|
| **P1** | `_read_errors`/`_read_error_since` chỉ khởi tạo ở `__init__`, `start()` không reset ⇒ **rò qua phiên**: phiên A give-up để lại bộ đếm > 0 + mốc cũ; phiên B trượt **một** lần thấy `stuck_s` = hàng chục giây ⇒ `error` + `_stop.set()` giết phiên khoẻ (message vô nghĩa "lỗi liên tiếp 620 s"), và lời hứa "log lần 1" cũng sai | Reset cả hai trong `start()` (cạnh `_frames = 0`). Test mới **tua đồng hồ 30 s** giữa hai phiên: bỏ fix ⇒ **đỏ**, có fix ⇒ xanh |
| **P2** | `git rev-parse` có `check=True` còn `git status --porcelain` **không** ⇒ `status` lỗi (index.lock/quyền) cho `stdout=""` ⇒ `git_dirty=False`, `git_loi=None`, exit 0: artifact "trông tái lập được" | Thêm `check=True` + test `CalledProcessError` cho lệnh status |
| **P3** | Hệ quả mới của `_misses >= MISS_MIN`: `capture.read()` **ném** (cv2.error) không tăng `_misses` ⇒ `health()` không bao giờ báo lỗi ca này (trước vòng 2 thì `age > STALE_S` vẫn bắt) | Đếm cả ca ném + test capture giả ném lỗi |
| **P3** | Give-up không đóng nguồn (giữ webcam tới lần `stop()` sau) trong khi `_check_health` đóng ngay | `source.stop()` **ngoài** `_lock` khi give-up + test `source.stopped` |
| **P3** | `_exit_code([], None, None) == 0` ⇒ `--lan 0` sinh artifact `n=0` (mọi số null) mà vẫn "đạt" | `if not runs: return 1` + test |
| **P3** | Thông báo `[THAT BAI] … trong 15 s` hardcode, nhưng mode `worker` chỉ chờ **10 s** | `WAIT_S = {worker: 10, raw: 15}` dùng cho cả vòng poll lẫn thông báo |
| **P3** | `--nguong-s` bị bỏ qua ở mode `worker` (`_one_run` hardcode 2 s) trong khi artifact khai ngưỡng theo `args.nguong_s` | Truyền `args.nguong_s` vào `_one_run` |
| **P3** | `imencode` hỏng mà `_last_frame_at` đã cập nhật ⇒ `health()` báo khoẻ trong khi 0 frame (có từ trước) | Chỉ tính "có frame" sau khi encode thành công + test |
| **P3** | `return 0` chết sau `return _exit_code(...)` | Xoá |
| **P3** | Log còn 3 chỗ trích bộ số đã bị ghi đè | Gỡ hết, chỉ còn MỘT bộ số khớp artifact |

**Đã kiểm, không phải lỗi (vòng 3 xác nhận):** P1 vòng 2 đóng thật; `_stop.set()` không phá vòng đời
(`start()` clear sau `_stop_locked()` + generation chặn thread cũ); không deadlock mới; `_verdict`/
`_verdict_dict`/`_exit_code` đủ 5 nhánh có test; `_git_provenance` không còn `UnboundLocalError`;
số trong docs/AGENTS khớp từng dòng JSON; `WorkerFrameSource.read_jpeg` nuốt `OSError` ⇒ đường give-up
5 s không chạm mode `track`.

**Nợ còn lại (không chặn merge):** chưa có test tự động ở seam adapter↔service cho mode `raw`;
`read()` treo vô hạn vẫn không cứu được; race `release()` `VideoCapture` trong lúc `read()` (tầng C++,
có từ trước); chưa đo trên webcam/RTSP thật.

### Số đo lại lần cuối — `git_rev = 013e0a7`, `git_dirty_code = false`, `git_loi = null`

| Mode | báo `error` (3 lần) | đóng luồng MJPEG | ngưỡng đăng ký trước | đạt? |
|---|---|---|---|---|
| `worker` (`proc.poll()`) | **115,9 / 116,0 / 116,5 ms** | 94,6–110,0 ms | ≤ 2 s | ✅ 3/3 |
| `raw` (không có frame) | **3751,9 / 3763,4 / 3747,2 ms** | 3740–3753 ms | ≤ 5 s | ✅ 3/3 |

- Hai lần đo liên tiếp trên code khác nhau lệch 94→116 ms (worker) và 3758→3752 ms (raw) — cùng
  cơ chế, độ tản **giữa các lần chạy**, không phải "cải thiện/thoái hoá"; cả hai đều cách ngưỡng rất
  xa nên không có gì để so sánh A/B ở đây.
- `so_lan_khong_phat_hien = 0` và `git_loi = null` ở cả hai artifact (đúng thứ vòng 3 bắt phải có).

### Kiểm tra
- `./run lint` ✓ · `./run test` **692 passed**, 5 deselected (~58 s)
- `./run testall` → **697 passed** · `./run e2e` → **PASS**
- **Test có răng (kiểm bằng cách làm hỏng code, không chỉ tin assertion):** bỏ 2 dòng reset bộ đếm ⇒
  `test_bo_dem_loi_doc_khong_ro_tu_phien_truoc` **đỏ** (message "lỗi liên tiếp 30 s"); bỏ đếm ở nhánh
  `read()` ném và trả lại thứ tự cũ của `imencode` ⇒ 2 test `TestCaptureNemLoi` **đỏ**.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Tự hạ cấp/cảnh báo khi drift xấu** (`p05 < 0,2` như `binh2`): hiện mới đo, chưa hành động.
- [ ] Đo drift cho **clip vật cản đi ngang che kín** (dự đoán LK trôi qua vật cản) — cần người quay.
- [ ] Nhãn GT trên video thật (`scripts/label_bbox.py`) + đo `mIoU`/IoU hộp trên clip thật.
- [ ] Sơ đồ khối + bảng phần cứng cho báo cáo.
- [ ] Muốn mask tươi hơn 0,2 s: đo **encoder nhẹ hơn / GPU** (nút thật, không phải `vos_every`).
- [ ] **Người dùng**: quay 2 clip (vật bị che một phần; vật ra khỏi khung rồi vào lại).
- [x] (P3 review) `OpenCvFrameSource` cài `HealthReportingSource` — mode `raw` cũng báo lỗi khi
      webcam chết giữa phiên (mục "Bổ sung 21:30").
- [x] (P3 review) `/api/live/stream` trả message theo `state`.
- [x] (P3 review) Worker `_publish_status` **trước** `_stop_worker()` khi kết thúc phiên.

## 📚 Tài liệu tham khảo
- `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md` — thứ tự việc + tiêu chí ≤ 2 s (viết trước).
- `docs/task/08-11-2026-do-cai-gia-noi-suy-lk-va-nguong-nhieu.md` — ngưỡng nhiễu, `vos_every` không
  điều khiển độ tươi mask.
- `src/live_tracking.py:150-179` (schema `status.json`), `:342-348` (nhánh `waiting_selection` không
  ghi status) — căn cứ quyết định heartbeat.
- `src/worker/web_export.py` — chuyển mã H.264 đã có sẵn cho API job; nay dùng lại cho CLI.
