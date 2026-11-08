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
