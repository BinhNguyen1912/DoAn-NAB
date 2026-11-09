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
   3. **tuổi `frame.jpg` > 2 s** — còn tiến trình mà frame đứng ⇒ treo (deadlock model).
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
`data/watchdog_2026-11-09_metrics.json` — `git_rev = ab46ef8`, `git_dirty = false`,
lệnh: `python scripts/measure_watchdog.py --lan 3`, clip `data/binh1.mp4`, `image_size 192`,
`vos_every 3`, laptop CPU (Iris Xe, torch CPU, SAM 2.1 tiny):

| Lần | nạp phiên | state sau kill | **báo `error`** | **đóng luồng MJPEG** | message |
|---|---|---|---|---|---|
| 1 | 5,2 s | `error` | **98,2 ms** | 96,9 ms | worker đã dừng (mã -9) — xem worker.log |
| 2 | 5,0 s | `error` | **117,7 ms** | 105,7 ms | worker đã dừng (mã -9) — xem worker.log |
| 3 | 5,2 s | `error` | **117,1 ms** | 100,1 ms | worker đã dừng (mã -9) — xem worker.log |

**Ngưỡng đăng ký trước ≤ 2 000 ms: ĐẠT** (chậm nhất 117,7 ms, 0/3 lần vượt), 3/3 lần luồng đóng
(0/3 lần treo). Đây là phép đo **ngưỡng**, không phải so A/B nên không cần ngưỡng nhiễu; độ tản
98–118 ms là độ trễ kiểm tra 0,2 s + nhịp poll 0,02 s.

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
- `./run test` (làn nhanh) → **xanh**, chạy **2 lần liên tiếp** để soi test chập chờn
- `./run webtest` → 24 test xanh; `npm run build` → xong
- `./run e2e` (Chrome/Edge thật) → **PASS 23/23**, gồm `trình duyệt GIẢI MÃ được video kết quả (H.264)`
  và `luồng MJPEG hiện được frame trong trình duyệt`

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

## 📚 Tài liệu tham khảo
- `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md` — thứ tự việc + tiêu chí ≤ 2 s (viết trước).
- `docs/task/08-11-2026-do-cai-gia-noi-suy-lk-va-nguong-nhieu.md` — ngưỡng nhiễu, `vos_every` không
  điều khiển độ tươi mask.
- `src/live_tracking.py:150-179` (schema `status.json`), `:342-348` (nhánh `waiting_selection` không
  ghi status) — căn cứ quyết định heartbeat.
- `src/worker/web_export.py` — chuyển mã H.264 đã có sẵn cho API job; nay dùng lại cho CLI.
