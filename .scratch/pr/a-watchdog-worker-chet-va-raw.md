## Watchdog: phiên live "sống" mà thực ra đã chết (mode `track` và mode `raw`)

### Vấn đề

API đọc `status.json` để biết phiên live còn khoẻ. Worker chết ⇒ không ai ghi `status.json` ⇒ file **cũ** vẫn nằm đó ⇒ API báo `running` **mãi mãi**, luồng MJPEG vẫn mở, UI vẫn hiện ảnh cuối cùng. Người dùng thấy "đang chạy" trong khi máy không chạy gì (đo được: `kill -9` worker, API báo `running` vô hạn).

### Thay đổi

**1. Watchdog mode `track` đọc `frame.jpg`, không đọc `status.json`** (`src/api/live.py`)
- `proc.poll()` bắt ca worker chết (`kill -9`): `error` sau **110–111 ms**, message nêu **mã thoát**; luồng MJPEG đóng sau **100–108 ms**.
- Ngưỡng "frame đứng" = `max(15 s, 4 × vos_ms)`, trần **120 s** — **không** hạ về 2 s: nhịp ghi frame hợp lệ có thể ~4 s/frame (`image_size 1024`, `vos_every=1`) và `engine.start()` chạy inline ⇒ ngưỡng 2 s giết phiên khoẻ (review độc lập bắt đúng). Ca **sống mà treo** mất **~15 s** — **không** trích "0,1 s" cho ca này.
- Ở `waiting_selection` worker **không** ghi `status.json` ⇒ không dùng nó làm heartbeat (nếu không, phiên khoẻ bị giết khi người dùng đang chờ chọn ô).

**2. Watchdog mode `raw` (webcam/relay)** — không có `proc.poll()` để hỏi, chỉ biết qua "không có frame": `OpenCvFrameSource` chờ **3 s** (`STALE_S`); đo trên relay localhost: **3,73–3,76 s** để `error`, luồng MJPEG đóng cùng lúc (`data/watchdog_raw_2026-11-09_metrics.json`, 3 lần).
Giới hạn ghi rõ trong log: **chưa đo trên webcam/RTSP thật**; với `HttpSnapshotSource` (relay) nguồn giữ frame cuối `max_misses = 20` lần rồi mới trả `None` ⇒ đồng hồ 3 s chỉ bắt đầu **sau** đó; mạng "black-hole" có thể làm ảnh đứng hàng phút. `read()` **treo vô hạn** thì watchdog **không cứu được** (`health()` chạy cùng thread với `read()`).

**3. `409` nêu đúng lý do** thay vì "đã có phiên"; publish `stopped` **trước** khi join worker.

**4. Provenance của artifact đo** — `scripts/measure_watchdog.py` ghi `git_rev`/`git_dirty`/`lenh`/`do_luc` và **`git_dirty_code`** = bẩn **bỏ qua `data/`** (đo lại lần hai thì chính file artifact bị sửa ⇒ `git_dirty` luôn `true` vô nghĩa; tái lập được ⇔ `git_dirty_code == false`).

### Kiểm tra

- `./run lint` ✓ · `./run test` → **696 passed** · `./run testall` → **701 passed** · `./run e2e` → **PASS**
- Artifact: `data/watchdog_2026-11-09_metrics.json` (mode `track`, `git_dirty_code = false`), `data/watchdog_raw_2026-11-09_metrics.json` (mode `raw`, 3 lần)
- AGENTS §6 cập nhật: ngưỡng "frame đứng", hai con số **không trộn** giữa hai mode, ca `kill -9` ≠ ca treo, ca `read()` treo không cứu được.

### Review độc lập (§9.1) — 4 vòng

| Vòng | Phát hiện chính | Xử lý |
|---|---|---|
| 1 | P1: ngưỡng 2 s giết phiên khoẻ; P2/P3 raw health, message | `max(15 s, 4×vos_ms)`, trần 120 s |
| 2 | P1: `git_dirty` luôn true; bảng số chép tay; P2/P3 409, comment | `git_dirty_code`; số chép từ artifact |
| 3 | P1: `_verdict` trả tuple nên không trải được vào dict (**TypeError thật khi chạy đo**) | Tách `_verdict_dict` + test |
| 4 | P3 ×5 + 2 note; P3-6 tách thành **ticket 16** | Sửa 5; ticket 16 = `state=error` khi mở lại phiên |

Kết luận vòng 4: **merge được**, P0 = 0.

### Cái PR này KHÔNG nói

- Không nói "raw phát hiện trong 3 s" cho **mọi** kiểu mất mạng.
- Không nói watchdog cứu được ca `read()` treo vô hạn.
