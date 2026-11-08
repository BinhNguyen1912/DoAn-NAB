# ADR-0005: Kiến trúc web theo ports & adapters (hexagonal) cho backend FastAPI

## Bối cảnh

- Đề cương yêu cầu (1) thu nhận & xử lý video, (2) người dùng chọn đối tượng, (6) đánh giá FPS/độ trễ.
  Ba yêu cầu này cần **giao diện web** (upload + chọn vật + xem kết quả), không chỉ CLI.
- Bản dựng đầu tiên (08-11, buổi sáng) gom mọi thứ vào 2 file: `src/api/jobs.py` (vừa lưu file,
  vừa quản lý tiến trình, vừa đọc video bằng cv2, vừa giữ dict tiến trình toàn cục) và
  `src/api/main.py` (vừa khai báo route, vừa kiểm tra nghiệp vụ, vừa mount static). Hệ quả đo được:
  - **Không test được nghiệp vụ** nếu không dựng HTTP server (mọi test đều đi qua `TestClient`).
  - **Không thay được hạ tầng**: đổi sang GPU thuê (Modal/RunPod) hay SQLite/S3 phải sửa file trộn.
  - **Trạng thái toàn cục** (`_PROCS`) làm test phụ thuộc thứ tự chạy.
  - Một lỗi thật do trộn trách nhiệm: `start_job()` gọi `runner.start()` rồi mới ghi `running`
    ⇒ pipeline xong nhanh thì callback ghi `done` bị dòng `running` ghi đè → job treo "đang chạy".
- Yêu cầu của người dùng: *"code cho có cấu trúc, theo hướng SOLID, không làm tùm bậy, phải theo
  hướng architecture để sau này còn dễ mở rộng"*.

## Quyết định

Áp dụng **ports & adapters** (hexagonal) cho tầng API, giữ pipeline lõi (`src/tracker_engine.py`,
`src/live_pipeline.py`, `src/reid.py`…) **nguyên vẹn** — không refactor phần đã có 362 test và số đo.

```text
src/api/
├── domain.py     # JobState, Job, JobStatus, JobView, lỗi miền, quy tắc (progress, can_select, bbox)
├── ports.py      # Protocol: JobStore / PipelineRunner / VideoProbe  (KHÔNG import adapter)
├── service.py    # JobService — use case, chỉ phụ thuộc port
├── schemas.py    # DTO hợp đồng HTTP (Pydantic) — sinh /openapi.json
├── routes.py     # APIRouter mỏng: parse → service → DTO
├── config.py     # ApiSettings (frozen) — tham số cấu hình một chỗ
├── main.py       # create_app() = composition root DUY NHẤT biết chọn adapter
└── adapters/
    ├── fs_store.py           # FileSystemJobStore   → filesystem (đổi được sang SQLite/S3)
    ├── subprocess_runner.py  # SubprocessPipelineRunner → tools/run_live.py (đổi được sang GPU)
    └── cv2_probe.py          # Cv2VideoProbe        → OpenCV (nơi DUY NHẤT của API import cv2)
```

`src/worker/` tách theo trách nhiệm: `command.py` (dựng lệnh, hàm thuần), `artifacts.py`
(đọc progress/summary/metrics + whitelist), `process.py` (subprocess + callback),
`__init__.py` chỉ là facade. Bảng tiến trình là **thuộc tính của instance**, không phải biến global.

Ánh xạ SOLID:

| Nguyên lý | Cách hiện thực |
|---|---|
| **S**RP | domain (quy tắc) · service (use case) · adapter (I/O) · routes (HTTP) · command/artifacts/process (worker) |
| **O**CP | Thêm lưu trữ mới / backend GPU mới = **viết adapter mới**, không sửa service hay routes |
| **L**SP | Mọi adapter tuân `Protocol`; test thay `FakeRunner`/`FakeProbe`/`FileSystemJobStore` không đổi hành vi |
| **I**SP | 3 port nhỏ, mỗi port một nhu cầu (`JobStore`, `PipelineRunner`, `VideoProbe`) thay vì 1 "God interface" |
| **D**IP | service ↔ port (trừu tượng); adapter phụ thuộc vào port, composition root mới biết hiện thực |

Quy ước bổ sung:
- **Lỗi miền không phải HTTP**: `JobNotFound/JobConflict/InvalidBBox/UnsupportedMedia/PayloadTooLarge/
  RunnerStartFailed`; `main.register_error_handlers` ánh xạ sang 404/409/400/400/413/500. Routes
  không có `try/except` lặp lại, và service gọi được từ CLI mà không cần HTTP.
- **Race trạng thái** được luật hoá trong service: ghi `RUNNING` **trước** khi start, callback ghi
  `DONE/ERROR` sau ⇒ thứ tự nhân quả đúng, có test riêng.
- **Validate hai lớp có chủ đích**: Pydantic (`schemas.py`) chặn hình dạng request → 422;
  domain/service chặn quy tắc nghiệp vụ (đuôi file, cue, bbox trong khung) → 400.

Frontend theo cùng tinh thần: `api.ts` (adapter HTTP duy nhất) · `hooks/useJobPolling.ts`
(side-effect polling, tự clear interval) · `components/{UploadForm,SelectionCanvas,ResultPanel,SummaryTable}.tsx`
(hiển thị thuần) · `App.tsx` (composition root, không fetch, không đặt interval).

## Hệ quả

- **Test**: 476 pass (trước refactor 407). Tách 4 tầng test — `test_api_domain.py` (thuần logic),
  `test_api_service.py` (use case với adapter giả), `test_api_routes.py` (hợp đồng HTTP + 1 test
  adapter thật), `test_worker_pipeline.py` (dựng lệnh/đọc artifact/tiến trình). Không test nào cần
  checkpoint SAM 2 hay HTTP server thật.
- **Đo lại end-to-end sau refactor** (uvicorn 8012, video 160×120, `image_size=192`, 5 frame):
  `mean 96,0 ms · p95 158,0 ms · 10,42 FPS`, artifact đủ `out.mp4/metrics.csv/summary.json/worker.log`,
  `artifacts/job.json` bị chặn 404 (whitelist hoạt động) ⇒ **hành vi không đổi** so với bản trước refactor.
- **Chi phí**: nhiều file hơn (11 file Python thay vì 4) — chấp nhận, vì mỗi file đọc được độc lập
  và AI/hội đồng lần theo luồng `routes → service → port → adapter` rõ ràng.
- **Việc phải làm khi thêm tính năng**: nếu là quy tắc → `domain.py`; nếu là use case → `service.py`;
  nếu là hạ tầng mới → adapter + sửa `build_default_service`; nếu là API mới → `routes.py` + `schemas.py`.

## Phương án đã cân nhắc và loại

- **Giữ nguyên 2 file cho nhanh** (MVP 3 ngày): loại, vì đổi GPU worker là bước bắt buộc ở Phase 5 —
  làm bây giờ rẻ hơn nhiều so với refactor khi đã có UI phụ thuộc.
- **Django/ORM + Celery**: loại — nặng hơn nhu cầu (1 người dùng, job trên filesystem), và kéo
  thêm hạ tầng phải cài (Redis/broker) không cần cho đồ án.
- **Repository Pattern + Unit of Work đầy đủ**: loại — với 1 bảng "job" thì `JobStore` là đủ;
  thêm tầng nữa chỉ tăng code mà không tăng khả năng thay thế.
