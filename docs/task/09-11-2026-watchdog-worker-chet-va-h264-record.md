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
`data/watchdog_2026-11-09_metrics.json` — `git_rev = cdcd1f5`, `git_dirty = false`
(đo lại SAU **cả hai vòng** review, để `git_rev` đúng là commit chứa code),
lệnh: `python scripts/measure_watchdog.py --lan 3`, clip `data/binh1.mp4`, `image_size 192`,
`vos_every 3`, laptop CPU (Iris Xe, torch CPU, SAM 2.1 tiny):

| Lần | nạp phiên | state sau kill | **báo `error`** | **đóng luồng MJPEG** | message |
|---|---|---|---|---|---|
| 1 | 4,2 s | `error` | **91,3 ms** | 92,6 ms | worker đã dừng (mã -9) — xem worker.log |
| 2 | 4,3 s | `error` | **111,2 ms** | 105,4 ms | worker đã dừng (mã -9) — xem worker.log |
| 3 | 4,2 s | `error` | **110,4 ms** | 96,9 ms | worker đã dừng (mã -9) — xem worker.log |

**Ngưỡng đăng ký trước: ĐẠT** — cả hai mốc plan ghi (mục nghiệm thu **≤ 5 s**, dòng ticket
**≤ 2 s**): chậm nhất 111,2 ms, 0/3 lần vượt; 3/3 lần luồng đóng (0/3 lần treo). Đây là phép đo
**ngưỡng**, không phải so A/B nên không cần ngưỡng nhiễu; độ tản 91–111 ms là độ trễ kiểm tra 0,2 s
cộng nhịp poll 0,02 s.

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
    (số đo lại ở trên không đổi: 96–114 ms). Thêm 3 test canh false-positive.
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

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Tự hạ cấp/cảnh báo khi drift xấu** (`p05 < 0,2` như `binh2`): hiện mới đo, chưa hành động.
- [ ] Đo drift cho **clip vật cản đi ngang che kín** (dự đoán LK trôi qua vật cản) — cần người quay.
- [ ] Nhãn GT trên video thật (`scripts/label_bbox.py`) + đo `mIoU`/IoU hộp trên clip thật.
- [ ] Sơ đồ khối + bảng phần cứng cho báo cáo.
- [ ] Muốn mask tươi hơn 0,2 s: đo **encoder nhẹ hơn / GPU** (nút thật, không phải `vos_every`).
- [ ] **Người dùng**: quay 2 clip (vật bị che một phần; vật ra khỏi khung rồi vào lại).
- [ ] (P3 review) `OpenCvFrameSource` cài `HealthReportingSource` — mode `raw` cũng phải báo lỗi khi
      webcam chết giữa phiên.
- [ ] (P3 review) `/api/live/stream` trả message theo `state` (409 hiện dùng chung một câu cho `error`
      và "chưa bật").
- [ ] (P3 review) Worker `_publish_status` **trước** `_stop_worker()` khi kết thúc phiên (hiện an toàn
      nhờ ngưỡng 15 s > join 5 s, nhưng đúng thứ tự thì rõ nghĩa hơn).

## 📚 Tài liệu tham khảo
- `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md` — thứ tự việc + tiêu chí ≤ 2 s (viết trước).
- `docs/task/08-11-2026-do-cai-gia-noi-suy-lk-va-nguong-nhieu.md` — ngưỡng nhiễu, `vos_every` không
  điều khiển độ tươi mask.
- `src/live_tracking.py:150-179` (schema `status.json`), `:342-348` (nhánh `waiting_selection` không
  ghi status) — căn cứ quyết định heartbeat.
- `src/worker/web_export.py` — chuyển mã H.264 đã có sẵn cho API job; nay dùng lại cho CLI.
