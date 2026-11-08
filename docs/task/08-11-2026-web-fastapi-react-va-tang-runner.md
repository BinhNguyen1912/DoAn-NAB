# Ngày 08-11-2026 — Dựng backend FastAPI + frontend React + tầng runner (Phase 0–3 gộp)

## 🎯 Mục tiêu
- Biến pipeline SAM 2 đang chạy bằng CLI thành **hệ thống web**: upload video → chọn đối tượng
  bằng chuột → xem mask/quỹ đạo + tải số liệu.
- Giữ **tách tầng**: API không import torch/SAM 2 (chạy được trên VPS 4 GB), xử lý nặng ở tiến trình con.
- Làm **không cần GPU, không cần database** (filesystem là store) để kịp mốc 3 ngày.
- Có **progress bar thật** (không phải spinner giả): pipeline ghi `progress.json`, API đọc để tính %.

## 📥 Input
- Yêu cầu người dùng: "làm liên tục, được quyền chia sub-agent, parent review rồi merge".
- Lộ trình đã chốt: Phase 0 (contract) → 1 (API + worker stub) → 2 (pipeline thật) → 3 (React).
- Môi trường đã kiểm chứng: **WSL2 Ubuntu 26.04.1**, repo ở `/mnt/d/DOAN-NAB` (filesystem **9p**,
  272 MB/s so với 1,9 GB/s của ext4), conda env `samurai` = **Python 3.11.17 + torch 2.14.1+cpu**,
  `python` trần **không tồn tại**, node v22.23.3/npm 10.9.9 có sẵn.
- Cài thêm vào env: `fastapi 0.162.2`, `uvicorn 0.54.0`, `pydantic 2.14.3`, `httpx 0.28.1`,
  `python-multipart 0.0.33`.

## 🔨 Công việc đã thực hiện

### 1. Thêm tiến trình thật cho pipeline — `tools/run_live.py`
- Flag mới `--progress-json PATH`: ghi `{"frames","total","updated_at"}` **atomic** (file tạm +
  `os.replace`) mỗi 5 frame và một lần lúc kết thúc. Không truyền flag → **hành vi cũ y nguyên**.
- `_progress_callback()` bọc `on_frame` của `run_tracking`, **luôn trả `True`** (trả `False` sẽ làm
  vòng lặp tracking dừng — bẫy dễ chết người).
- `_total_frames_hint()`: chỉ tin `CAP_PROP_FRAME_COUNT` khi nguồn là **file thật**; webcam/RTSP
  trả số rác nên phải lọc, nếu không thanh tiến trình nhảy loạn.

### 2. Tầng runner — `src/worker/runner.py` (mới)
`build_command` / `start` / `read_progress` / `load_summary` / `load_metrics` / `is_running` /
`artifact_path`. Dựng `bash -lc 'source ~/miniconda3/.../conda.sh && conda activate samurai && cd <repo>
&& python tools/run_live.py …'` (bắt buộc, vì `python` trần không có trong WSL), `shlex.quote` toàn bộ
đường dẫn, `on_exit` gọi trong **thread riêng** nên FastAPI không bị block. Module **không import
cv2/torch/sam2**.

### 3. Backend — `src/api/{schemas,jobs,main}.py` (mới)
- `schemas.py`: Pydantic = **nguồn sự thật của contract** (`BBox`, `TrackParams`, `JobStatus`,
  `JobCreateResponse`, `SelectRequest`, `JobListItem`), sinh `/openapi.json` cho frontend.
- `jobs.py`: store filesystem. `job_id = %Y%m%d-%H%M%S-<6hex>` + **regex validate trước mọi thao tác đĩa**
  (chống path traversal). Upload ghi theo **chunk 1 MB**, chặn 500 MB. `refresh_state()` tính % từ
  `progress.json`; có `summary.json` → `done 100`; tiến trình chết mà không có kết quả → `error`.
- `main.py`: `/health`, `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{id}`,
  `/preview?index=N`, `POST /select`, `/artifacts/{name}` (whitelist cứng), `DELETE /api/jobs/{id}`;
  CORS cho `localhost:5173`; **mount `web/dist` ở `/`** khi đã build (một lệnh là có demo).

### 4. Frontend — `web/` (mới): React 18 + Vite 5 + TypeScript strict, CSS thuần
- `SelectionCanvas.tsx`: canvas có kích thước nội tại = **kích thước gốc của video**, CSS chỉ thu nhỏ;
  toạ độ chuột nhân `canvas.width / rect.width` → ô chọn không lệch khi ảnh bị scale.
- `App.tsx`: 3 bước (upload → chọn bbox → kết quả), poll 1 s/lần và **clear interval khi unmount**,
  hiện bảng mean/p95/FPS/mất dấu/reacquired + tải CSV/JSON.
- `vite.config.ts`: proxy `/api`,`/health` → `127.0.0.1:8000` (né CORS hoàn toàn) và
  `server.watch.usePolling = true` (HMR không thấy file đổi trên filesystem 9p).

### 5. Hạ tầng repo
- `run`: thêm `api [cổng]`, `web`, `webdev` + mục **WEB** trong bảng `./run help`.
- `requirements.txt`: thêm `fastapi`, `uvicorn[standard]`, `python-multipart`, `httpx`.
- `AGENTS.md` §3: thêm `src/api/`, `src/worker/`, `web/` vào cây thư mục.
- `README.md`: mục **2b. Web app** (luồng xử lý + 2 chế độ chạy).
- `.gitignore`: thêm `web/node_modules/`, `web/dist/`, `web/.vite/`.

### 6. Test mới (45 test)
- `tests/test_worker_runner.py`: dựng lệnh (có ca `reid=True, cue=object` vì mặc định repo là `face`,
  ca đường dẫn có dấu cách), đọc progress hỏng/thiếu khoá, đổi kiểu CSV, whitelist artifact,
  `_write_progress` atomic, callback ghi mỗi 5 frame.
- `tests/test_api.py`: health, upload hợp lệ/sai đuôi/sai cue, danh sách job, preview JPEG
  (kiểm magic `\xff\xd8`), select (202 / 422 bbox rỗng / 400 vượt khung / 409 khi đã done),
  artifacts + chặn tên ngoài whitelist, `refresh_state` (50 % → running, có summary → done,
  tiến trình chết → error), DELETE 204/404. Toàn bộ dùng `DOAN_JOBS_ROOT` trỏ `tmp_path`,
  **không ghi vào `data/jobs` thật**, không cần checkpoint.

## 📤 Output / Kết quả

**Kiểm chứng tự động:**
- `./run lint` → `All checks passed!`
- `./run test` → **407 passed, 5 deselected** (34,83 s) — trước phiên này là 362 → **+45 test**.
- `npm run build` → `dist/index.html` 0,41 kB, CSS 2,20 kB, JS **149,68 kB (gzip 48,89 kB)**, build 693 ms.

**Kiểm chứng end-to-end với pipeline THẬT** (uvicorn cổng 8011, video test 20 frame 160×120,
`image_size=192`, `max_frames=5`):

```text
health  : {'status': 'ok', 'version': '0.1.0'}
upload  : 201 {"job_id":"20261108-113746-9c5673","state":"uploaded"}
preview : 200 jpeg=True bytes=1347
select  : 202 {"job_id":"…","state":"queued"}
poll    : state=running progress=0%   → state=done progress=100%
artifacts: ['metrics.csv', 'out.mp4', 'summary.json', 'worker.log']
số liệu : frames=5 mean=101,3 ms p95=168,4 ms fps=9,87   ← khớp số đo cũ (~97 ms @192)
tải out.mp4: 200 14.145 bytes | metrics.csv: 200 222 bytes
KẾT LUẬN: PASS
```

**File thay đổi:**
- `tools/run_live.py` — thêm `--progress-json` + `_write_progress` / `_total_frames_hint` / `_progress_callback`
- `src/worker/__init__.py`, `src/worker/runner.py` — tầng runner (mới)
- `src/api/__init__.py`, `src/api/schemas.py`, `src/api/jobs.py`, `src/api/main.py` — backend (mới)
- `web/` — `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `.gitignore`,
  `src/main.tsx`, `src/App.tsx`, `src/SelectionCanvas.tsx`, `src/api.ts`, `src/styles.css` (mới)
- `tests/test_worker_runner.py`, `tests/test_api.py` — 45 test (mới)
- `run`, `requirements.txt`, `AGENTS.md`, `README.md`, `.gitignore` — cập nhật

## 🐞 Vấn đề gặp phải & cách xử lý
- **Sub-agent không khởi động được** (đúng như người dùng cho phép chia việc): `general` báo
  *"Declared subagent skill(s) not found: development-lifecycle, test-driven-development"*;
  `claude-code` báo *"herdr … blocked during startup"*. Chỉ `explore` (read-only) chạy được.
  → **Tự làm toàn bộ**, giữ nguyên contract đã chốt trong handoff để sau này vẫn chia được.
- **Race condition trạng thái:** bản đầu `start_job()` gọi `runner.start()` rồi mới ghi `running`;
  nếu pipeline xong rất nhanh, callback `on_exit(0)` ghi `done` **trước** và bị dòng `running` ghi đè
  ngược → job treo ở "đang chạy". Sửa: ghi `running` **trước** khi start.
- **`is_running(CompletedProcess)`** ném `AttributeError` (không có `.poll`) → dùng `getattr` an toàn,
  thêm test cho đối tượng không có `poll`.
- **`npm install` xoá symlink `node_modules`** ("Removing non-directory …") → mẹo đưa `node_modules`
  sang ext4 không dùng được. Đo thực tế: cài 67 gói **16 s** trên 9p → chấp nhận, đã sửa `./run web`
  bỏ phần symlink và ghi chú lại.
- **Server nền chết giữa các lần gọi bash** (tiến trình con bị dọn khi shell kết thúc) → lần smoke
  test đầu trả `http=000`. Sửa: dựng video + script + server + test **trong cùng một lần gọi**.
- **`write` tool ghi `/tmp/...`** vào đường dẫn Windows chứ không phải `/tmp` của WSL → script test
  tạo bằng heredoc trong bash thay vì tool `write`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Chạy thử bằng trình duyệt thật** (`./run web && ./run api` → mở `http://127.0.0.1:8000/`):
      kéo chuột chọn vật trên video webcam thật, xem mask có bám đúng và ô chọn có lệch không.
      Đây là việc **thủ công** duy nhất chưa kiểm được trong phiên này (môi trường không có GUI).
- [ ] **Phase 4** (live streaming): kiến trúc hybrid VOS ~10 FPS + LK 30 FPS (`docs/research/09`),
      đẩy frame qua WebSocket; đo độ trễ đầu-cuối **gồm cả mạng**.
- [ ] **Phase 5** (GPU worker): Dockerfile + hàm Modal (`gpu="L4"`), chỉ đổi base URL trong
      `src/worker/runner.py` — contract API không đổi.
- [ ] `worker.log` hiện chưa có endpoint xem trực tiếp trên UI (đã tải được qua `/artifacts`),
      nên thêm khung log khi job `error` để người dùng tự thấy lỗi.
- [ ] Dọn `data/jobs/` định kỳ (chưa có TTL) — hiện chỉ xoá tay bằng `DELETE /api/jobs/{id}`.

## 📚 Tài liệu tham khảo
- `CODING_STANDARDS.md` — docstring 4 mục, chữ Việt có dấu, UI phải test headless, quy tắc test.
- `AGENTS.md` §4, §5, §6 — quy ước code, lệnh kiểm chứng, số đo đã có (trần ~18–22 FPS).
- `docs/research/08-real-time-25fps-tren-cpu-igpu.md`, `docs/research/09-kien-truc-hybrid-vos-cham-tracker-nhe-30fps.md`
  — cơ sở cho Phase 4 (hybrid) và con số FPS dùng trong báo cáo.
- FastAPI: https://fastapi.tiangolo.com/ (StaticFiles, `UploadFile`, `TestClient`)
- Vite: https://vitejs.dev/config/ (`server.proxy`, `server.watch.usePolling`)

---

## 🔁 Bổ sung (cùng ngày) — Refactor kiến trúc theo ports & adapters

**Vì sao:** bản đầu gom lưu trữ + nghiệp vụ + HTTP + OpenCV + subprocess vào 2 file
(`src/api/jobs.py`, `src/api/main.py`), có biến toàn cục `_PROCS` và một race thật (pipeline xong
nhanh → `done` bị dòng `running` ghi đè). Yêu cầu: code phải có cấu trúc, theo SOLID, dễ mở rộng.

**Đã làm** (quyết định ghi ở `docs/adr/0005-kien-truc-web-ports-va-adapters.md`):

```text
src/api/  domain.py · ports.py · service.py · schemas.py · routes.py · config.py · main.py
          adapters/{fs_store, subprocess_runner, cv2_probe}.py
src/worker/  command.py · artifacts.py · process.py · __init__.py (facade)   ← bỏ runner.py
web/src/  api.ts · hooks/useJobPolling.ts · components/{UploadForm,SelectionCanvas,ResultPanel,SummaryTable}.tsx · App.tsx
```

- `domain.py`: `JobState/Job/JobStatus/JobView`, lỗi miền, quy tắc thuần (progress, can_select, bbox).
- `ports.py`: 3 Protocol nhỏ (`JobStore`, `PipelineRunner`, `VideoProbe`) — service không biết hạ tầng.
- `service.py`: `JobService` = toàn bộ use case; ghi `RUNNING` **trước** `start()` (sửa race).
- `adapters/`: `cv2_probe.py` là **nơi duy nhất** tầng API import cv2; bảng tiến trình là thuộc tính
  instance của `SubprocessPipelineRunner`, không còn biến global.
- `main.py`: `create_app()` = composition root duy nhất; lỗi miền ánh xạ HTTP ở một chỗ.
- Frontend: `App` không fetch, không đặt interval; polling nằm trong hook tự clear khi unmount.

**Kiểm chứng:**

| Mục | Trước refactor | Sau refactor |
|---|---|---|
| `./run test` | 407 passed | **476 passed, 5 deselected (39,95 s)** |
| `./run lint` | pass | **All checks passed!** |
| `npm run build` | 149,68 kB (48,89 kB gzip) | **150,05 kB (49,07 kB gzip)** |
| E2E, pipeline thật @192, 5 frame | mean 101,3 ms · p95 168,4 ms · 9,87 FPS | **mean 96,0 ms · p95 158,0 ms · 10,42 FPS** |

Test tách theo tầng: `test_api_domain.py` (thuần logic) · `test_api_service.py` (use case + adapter
giả) · `test_api_routes.py` (hợp đồng HTTP + 1 test `Cv2VideoProbe` thật) · `test_worker_pipeline.py`.
Không test nào cần checkpoint SAM 2 hay HTTP server thật; adapter giả nằm trong `tests/conftest.py`.
E2E sau refactor còn xác nhận `GET /api/jobs/{id}/artifacts/job.json` → **404** (whitelist chạy đúng).

---

## 🧪 Bổ sung (cùng ngày) — Tự kiểm bằng trình duyệt thật + 3 bug tìm được

**Bối cảnh:** người dùng hỏi "bạn tự làm tự test luôn được không". Môi trường WSL **không** dựng
được Chromium (`libnss3`, `libasound2`… thiếu; `sudo` cần mật khẩu) ⇒ dùng **Chrome/Edge trên
Windows** lái từ WSL qua `cmd.exe` + Playwright (`channel: 'chrome'`, headless).

### Bộ kiểm mới (đã vào repo)

| Thành phần | Nội dung |
|---|---|
| `web/src/selection.ts` | tách **toàn bộ toán học** quy đổi toạ độ canvas → pixel video thành hàm thuần |
| `web/src/selection.test.ts` | 16 test vitest (tỉ lệ 3,2×, kéo ngược chiều, kẹp biên, khung width=0, NaN/∞) |
| `scripts/make_e2e_video.py` | sinh fixture 160×120 20 frame (kích thước cố định để tính kỳ vọng bằng tay) |
| `scripts/e2e_web.js` | E2E Playwright: upload → kéo chuột → chờ done → kiểm giải mã video + bảng số liệu + CSV |
| `./run webtest`, `./run e2e` | hai lệnh chạy 2 bộ trên (e2e tự bật server + sinh fixture) |

### 3 bug THẬT do E2E bắt được

1. **Canvas 300×150** — `<canvas>` chưa có `width/height` mặc định là 300×150, nên trước khi ảnh
   preview load xong nó vừa nhấp nháy sai tỉ lệ, vừa làm `getBoundingClientRect()` đổi giữa lúc kéo
   ⇒ toạ độ lệch (`16,24,48×32` thay vì `16,36,48×48`). Sửa: **chỉ render canvas sau khi biết kích
   thước thật** (`width={size.w} height={size.h}`).
2. **Video không phát được trên web** — OpenCV ghi fourcc `FMP4/mp4v`; Chrome trả
   `canPlayType('video/mp4; codecs="mp4v.20.9"') = ""`, `videoWidth = 0` (đo bằng probe Playwright).
   OpenCV **không** ghi được H.264 (`avc1` → `opened=False`, chỉ có encoder phần cứng
   `h264_v4l2m2m` không tồn tại). Sửa: `src/worker/web_export.py` chuyển `out.mp4` →
   **`out_web.mp4` (libx264 + yuv420p + faststart)** bằng `imageio-ffmpeg` (pip, **không cần sudo**,
   có sẵn libx264); UI phát bản web, vẫn cho tải bản gốc để xem bằng VLC.
3. **Job báo `done` trước khi có video phát được** — `summary.json` do pipeline ghi *trước* khi
   tiến trình thoát, còn bản H.264 xuất *sau* đó; service thấy summary là báo done ⇒ UI hiện player
   khi chưa có `out_web.mp4`. Sửa: adapter có cờ `_finalizing` — trong lúc xuất bản web,
   `is_running()` vẫn `True`; service **chỉ** `done` khi runner đã xong hẳn. Có test riêng cho cả
   service (`test_co_summary_nhung_con_dang_xuat_ban_thi_van_running`) và adapter
   (`test_xuat_ban_h264_van_tinh_la_dang_chay`).

**Bug phụ (không do E2E):** `summary.json` trả `lost_count` nhưng frontend đọc `lost_frames` → cột
"Frame mất dấu" hiện "—". Sửa FE + thêm `TestHopDongSummary` chốt danh sách khoá mà
`web/src/api.ts` phụ thuộc. Ngoài ra `list_ids` sắp theo tên thư mục (độ phân giải 1 giây + hex
ngẫu nhiên) → hai job cùng giây có thứ tự không xác định; đổi sang sắp theo `created_at`
(mili-giây).

### Kết quả E2E cuối cùng (Chrome 141 headless, Windows → server trong WSL)

```text
✓ trang tải được + frontend kết nối backend
✓ upload sai định dạng bị chặn + báo lỗi tiếng Việt — "định dạng không hỗ trợ (.txt)"
✓ canvas đúng kích thước video gốc — {"w":160,"h":120}
✓ kéo chuột sinh ra bbox hợp lệ — 16,36,48,48
✓ quy đổi canvas → pixel video ĐÚNG tỉ lệ — nhận 16,36,48×48 — kỳ vọng 16,36,48×48
✓ job kết thúc done — 4,6 s
✓ có player video kết quả — …/artifacts/out_web.mp4
✓ trình duyệt GIẢI MÃ được video kết quả (H.264) — {"readyState":4,"decoded":true,"w":160,"h":120}
✓ bảng số liệu có 7 dòng · độ trễ TB 142 ms · FPS 7,07
✓ tải được metrics.csv (200, 5 dòng) · artifact ngoài whitelist bị 404
✓ không có lỗi JS trên trang
KẾT LUẬN: PASS
```

Ảnh chụp `data/e2e_web.png` cho thấy **khung hình HUD thật** trong player
("FPS: 7.4 · Độ trễ: 136 ms/frame · Điểm tin cậy: 15.1") cùng ô đỏ bám vật và bảng số liệu.

**Tổng kiểm chứng sau khi thêm web_export:** `./run lint` xanh · `./run test` → **487 passed**
(38,52 s) · `./run webtest` → **16 passed** · `./run e2e` → **PASS**.

---

## 📡 PR #2 — Phase 4a: phát trực tiếp (MJPEG) trên kiến trúc ports & adapters

**Mục tiêu:** có luồng camera trực tiếp trên web **trước khi** làm bám đối tượng live (4b), để
đo được độ trễ/khung hình thật và tách rủi ro: sai nguồn/đường dẫn khác hoàn toàn sai tracker.

**Đã thêm (đúng khuôn kiến trúc cũ, không sửa service/route cũ):**

| Tầng | File | Nội dung |
|---|---|---|
| port | `src/api/ports.py` | `FrameSource` (start / read_jpeg / stop / label) — tách khỏi `VideoProbe` vì vòng đời khác |
| miền | `src/api/domain.py` | `LiveState`, `LiveStatus`, lỗi miền `SourceUnavailable` (→ 400) |
| service | `src/api/live.py` | `LiveStreamService`: thread đọc frame, **chỉ giữ frame mới nhất**, đo FPS thật, MJPEG generator có `idle_timeout` |
| adapter | `src/api/adapters/opencv_source.py` | `OpenCvFrameSource` — **tái dùng** `src/video_source.open_video_source` (webcam/RTSP/snapshot/file), tự **lặp file** để demo không cần webcam |
| API | `src/api/routes.py` | `POST /api/live/start|stop`, `GET /api/live/status|frame|stream` |
| FE | `web/src/components/LivePanel.tsx` | bật/dừng, `<img>` MJPEG (đổi `key` mỗi phiên), poll trạng thái 1 s |
| test | `tests/test_api_live.py` | 13 test: service (thread, lặp, lỗi, generator thoát), routes, và 1 test adapter OpenCV thật |

**Quyết định thiết kế đáng ghi:** giữ **1 frame mới nhất** thay vì hàng đợi — với live, độ trễ thấp
quan trọng hơn phát đủ frame; client chậm thì bỏ frame cũ. Ghi rõ trong docstring để lần sau không
ai "tối ưu" thành queue rồi làm tăng latency.

**Lỗi gặp phải & cách xử lý**

| Lỗi | Nguyên nhân | Xử lý |
|---|---|---|
| E2E `live-status` timeout | script gửi `data\\e2e_web.mp4` (path Windows) xuống server **Linux** → không mở được file | nguồn live phải là path **phía server** (`data/e2e_web.mp4`); thêm hằng `LIVE_SOURCE` + in banner lỗi của UI khi fail |
| deadlock tiềm ẩn | `_stop_locked()` gọi `self.status()` khi đang giữ `_lock` | bỏ gọi lồng; chỉ `stop()` công khai mới gọi `status()` sau khi nhả lock |
| test OpenAPI đỏ | thêm 5 endpoint live | cập nhật danh sách endpoint trong `TestHopDongOpenApi` |

**Kiểm chứng**

```text
./run lint     → All checks passed
./run test     → 500 passed, 5 deselected (62,7 s)
./run webtest  → 16 passed
./run e2e      → PASS, gồm 3 bước live:
   ✓ luồng MJPEG hiện được frame trong trình duyệt — {"w":160,"h":120}
   ✓ FPS live đo được > 0 — "frame: 16 · FPS đo được: 14.9"
   ✓ dừng phát sạch (state=stopped)
```

**Next:** Phase 4b — bám đối tượng trên live (VOS ~10 FPS + LK 30 FPS theo `docs/research/09`),
chọn bbox ngay trên luồng live, xuất quỹ đạo thời gian thực lên client.

---

## 🎯 PR #3 — Phase 4b: bám đối tượng trên luồng trực tiếp (worker tiến trình riêng)

**Ràng buộc quyết định thiết kế:** API **không được** import torch/SAM 2 (ADR-0005 — API phải chạy
được trên VPS 4 GB). Vì vậy bám live không thể chạy trong tiến trình API.

**Kiến trúc:** worker riêng + trao đổi qua file trong tmpfs.

```text
tools/live_worker.py  ──(frame.jpg, status.json, bbox.json)──  /dev/shm/doan-live  ──►  API /api/live/stream
   (torch + SAM 2)              ghi atomic bằng os.replace                        (chỉ đọc file)
        ▲
        └── khởi chạy bằng src/api/adapters/worker_source.py (FrameSource — cùng port với mode raw)
```

| Tầng | File | Nội dung |
|---|---|---|
| logic | `src/live_tracking.py` | `LiveTrackingSession`: đọc frame → chờ `bbox.json` (vẫn phát frame trơn để người dùng chọn) → bám → vẽ mask + ô bao + quỹ đạo → ghi `frame.jpg`/`status.json` |
| CLI | `tools/live_worker.py` | nạp `TrackerEngine`, ghi status `loading` NGAY (model 20–60 s), SIGINT/SIGTERM dừng sạch |
| port | `src/api/ports.py` → `FrameSource` (giữ nguyên) | adapter mới cùng chữ ký ⇒ **LiveStreamService không phải sửa** |
| adapter | `src/api/adapters/worker_source.py` | `WorkerFrameSource`: dọn thư mục, ghi bbox, chạy worker, chờ frame đầu (timeout 240 s), dừng bằng `SIGTERM` cả process group |
| lệnh | `src/worker/command.py` | `build_live_worker_command` (cùng cách activate conda) |
| API | `schemas.LiveStartRequest` + `routes` | thêm `mode: raw|track`, `bbox`, `image_size` |
| FE | `web/src/components/LivePanel.tsx` | bật/dừng, đóng băng `frame.jpg` → **kéo chuột chọn đối tượng** → gọi `mode=track` |

**Bug thật tìm thấy khi kiểm tích hợp (quan trọng nhất phiên này):**

API báo `measured_fps = 15,0` trong khi worker chỉ bám được **2 frame trong 6 s** (≈0,4 FPS).
Nguyên nhân: `LiveStreamService._run()` đếm **mỗi lần đọc file**, kể cả khi nội dung không đổi.
Sửa: chỉ đếm và phát khi `data != self._latest` (so sánh bytes — rẻ với ảnh JPEG vài chục KB).
Đồng thời đặt **`image_size` mặc định 192** cho mode track (1024 = mặc định SAM 2 → 0,4 FPS,
rất dễ tưởng là treo).

**Kiểm chứng tích hợp thật (engine SAM 2 thật, không phải fake):**

```text
POST /api/live/start {"source":"data/e2e_web.mp4","mode":"track","bbox":{5,25,45,50}}
→ trả về sau 4,5 s (worker nạp model nền)
API  : frames=34  fps=10,8  state=running
worker status.json: {"state":"tracking","frames":35,"measured_fps":10.6,
                     "inference_ms":98.0,"lost_streak":0,"bbox":[68,31,72,51]}
GET /api/live/frame → 200, JPEG hợp lệ
POST /api/live/stop → state=stopped; `pgrep live_worker.py` → KHÔNG còn tiến trình (dọn sạch)
```

→ **10,6 FPS · 98 ms/frame @image_size 192** — khớp số đo CLI (~97 ms trong `docs/research/11`).

**Kiểm chứng tự động:**

```text
./run lint     → All checks passed
./run test     → 513 passed, 5 deselected (57,8 s)   (+13 test mới: live_tracking, lệnh worker, route)
./run webtest  → 16 passed
./run e2e      → PASS, thêm 2 bước:
   ✓ UI gửi mode=track kèm bbox khi bấm "Bám đối tượng"
     — {"source":"data/e2e_web.mp4","mode":"track","bbox":{"x":32,"y":36,"w":48,"h":48}}
   ✓ bbox gửi đi nằm trong khung video live
```

**Bài học cho E2E (ghi để lần sau không mất thời gian):**
1. Trang có **2 canvas** (job + live) → phải **scope locator vào card** rồi mới kéo chuột.
2. `page.mouse` dùng toạ độ **viewport** → phải `scrollIntoViewIfNeeded()` trước khi kéo, nếu không
   chuột rơi ra ngoài canvas và không có sự kiện nào được bắn (mất 2 vòng sửa mới ra).
3. Muốn kiểm UI gửi payload gì mà không phải nạp model 20–60 s → `page.route()` chặn
   `/api/live/start` và đọc `postData()`.

**Còn lại (chưa làm):** hybrid **VOS ~10 FPS + LK 30 FPS** (`docs/research/09`) — hiện mỗi frame
hiển thị là 1 lần suy luận thật, nên HUD chỉ ~10 FPS chứ chưa mượt 30 FPS.
