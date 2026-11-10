# Ngày 11-11-2026 — Đường LIVE chạy được trên GPU: sửa lỗ "máy có GPU vẫn chạy CPU"

> Phiên thứ hai trong ngày (phiên 1: ticket 19/20 + merge `b4799d6`). Yêu cầu của người dùng:
> *"tập trung quan trọng vào realtime, GPU"*. Việc chọn làm là **lỗ chặn realtime trên GPU** lớn
> nhất mà đọc mã tìm ra, không phải thêm tính năng mới. Nhánh: `feat/live-gpu-device` (rẽ từ
> `main` tại `b4799d6`).

## 🎯 Mục tiêu

1. **Trả lời đúng câu "real-time trên GPU"**: đường sản phẩm (phiên live qua web) có dùng GPU không?
2. Nếu không: sửa để GPU dùng được, và **không bao giờ âm thầm rơi về CPU** (số FPS trong báo cáo
   sẽ bị gán sai thiết bị — AGENTS §6).
3. Ghi **số đo thật** cho phần làm được trên máy này (CPU baseline) + bằng chứng ca "xin cuda mà
   không có GPU thì báo lỗi rõ".

## 📥 Input

- `tools/live_worker.py`, `src/worker/command.py`, `src/api/adapters/worker_source.py`,
  `src/api/main.py`, `scripts/measure_live_relay.py` (bản trên `main` `b4799d6`).
- `tools/run_live.py` — đường CLI **đã có** `--device` từ trước (đối chứng: lệch hành vi giữa CLI và live).
- Quy ước: `AGENTS.md` §6 (số đo phải ghi thiết bị; `git_rev`/`git_dirty_code`), ADR-0002 (laptop CPU
  là môi trường demo, GPU là số/video minh hoạ), ADR-0005 (`src/worker` phải nhẹ, không torch/cv2).

## 🔨 Công việc đã thực hiện

### Phát hiện (đọc mã, xác nhận bằng chạy thật)

`tools/live_worker.py` gọi:

```python
engine = TrackerEngine.build_default(image_size=args.image_size)   # ← THIẾU device
```

`TrackerEngine.build_default(device="cpu", …)` ⇒ **mọi phiên live qua web chạy model trên CPU**, dù
máy có GPU. Đường CLI (`tools/run_live.py`) thì đã truyền `device` từ lâu ⇒ hai đường lệch nhau.
Hệ quả cho báo cáo: nếu đem demo lên Colab T4 mà dùng web, số đo ra là **số CPU**, nhưng người đọc
tưởng GPU (đúng bẫy AGENTS §6 "số đo phải ghi rõ môi trường").

### Sửa

1. **`src/device.py` (mới)** — hàm thuần, **không** import torch (API chạy trên VPS 4 GB):
   `normalize_device` (`None`/`""` ⇒ `cpu`, nhận hoa/thường + khoảng trắng, tên lạ ⇒ `ValueError`),
   `validate_device(name, cuda_available=…)` (xin `cuda` khi `False` ⇒ `ValueError` kèm câu hướng dẫn
   Colab → Runtime → T4), `device_from_env()` + `ENV_VAR = "CAMERA_AI_DEVICE"`.
2. **`tools/live_worker.py`** — thêm `--device {cpu,cuda}`; kiểm CUDA **trước** khi nạp checkpoint
   156 MB; lỗi ⇒ ghi `status.json` `state=error` + message (tới được UI/watchdog) rồi `exit 2`;
   truyền `device=device` xuống `build_default` (đóng đúng lỗ gốc); log in tên GPU qua `_device_note()`.
3. **`src/worker/command.py`** — `build_live_worker_command(..., device=None)`: chỉ thêm `--device`
   khi có yêu cầu, chuẩn hoá bằng `normalize_device` ⇒ một cái typo (`gpu`, `cuda:1`) **nổ ngay**
   thay vì lọt xuống worker.
4. **`WorkerFrameSource(..., device=None)`** + **`src/api/main.py`**: `build_default_live()` đọc
   `$CAMERA_AI_DEVICE` **một lần lúc dựng service** (gõ sai ⇒ lỗi khi khởi động, không phải giữa
   buổi demo) rồi truyền xuống worker. **Hợp đồng HTTP `/api/live/start` không đổi** (chọn env thay
   vì thêm field ⇒ không phải sửa schema/web, không phát sinh việc e2e mới).
5. **`scripts/measure_live_relay.py`** — thêm `--device` (đặt env cho uvicorn con) và artifact ghi:
   - `device_yeu_cau` (tham số), `device_worker_log` (**sự thật**: đọc `worker.log`),
   - `ghi_chu_device` (lệch nhau ⇒ đừng trích),
   - `_post` giờ **giữ thân lỗi HTTP**: bản trước ném `HTTPError: 400` trơn nên artifact mất lý do thật
     (đã gặp đúng lúc đo nhánh này).
6. **Job tải video lên cũng đi theo thiết bị** (cùng lỗi lớp trên, phát hiện thêm khi ráp đường API):
   `build_command(..., device=…)` + `SubprocessPipelineRunner(device=…)` +
   `build_default_service()` truyền `device_from_env()` ⇒ `CAMERA_AI_DEVICE=cuda` áp cho **cả**
   phiên live **và** job upload→track→mp4. Thiết bị do **máy chủ** quyết định, không lấy từ tham số
   job của client (giữ nguyên nguyên tắc chống rò rỉ tham số của `_ALLOWED_INT_PARAMS`).
7. **Docs**: `README.md` mục **3b** "Demo LIVE (web) trên GPU" (3 cách bật + 3 quy tắc trung thực);
   `./run gpu` in thêm lệnh live GPU và **bỏ số cũ sai** (`mean≈65 ms | FPS≈15,3` → `49,6 ms ≈ 20,15 FPS`
   theo `data/gpu_summary.json`, commit `8d64d59`).

## 📤 Output / Kết quả

| Kiểm tra | Kết quả |
|---|---|
| `./run lint` | ✓ |
| `./run test` | **787 passed** (5 deselected, ~74 s) |
| `./run testall` (lần 1, trước khi thêm đường job upload) | 786 passed + **1 failed** (`test_tracker_engine::test_process_theo_frames_iou_dat_o_cac_frame_mau`); chạy riêng: **8/8 pass**. Flaky do SAM 2 không tất định + máy tải, **không liên quan nhánh này** (engine do fixture tự dựng) ⇒ **ticket 22** |
| `./run testall` (lần 2, trạng thái cuối) | **792 passed**, 0 failed (205,7 s) — lần này test flaky kia xanh |
| `./run e2e` | **PASS** (bắt buộc vì có sửa `src/api/**`) — 7 dòng bảng số, MJPEG 29,8 FPS, dừng sạch, 0 lỗi JS |
| Test mới | **34** case: `tests/test_device.py` 17, `tests/test_worker_device.py` 11 (thêm 2 cho job upload), `tests/test_measure_live_relay.py` +3, `tests/test_worker_pipeline.py` +3 |

### Số đo thật (commit `ffc9f02`, `git_dirty_code = false`)

| Artifact | Nội dung | Số |
|---|---|---|
| `data/live_gpu_device_cpu_baseline_2026-11-11_metrics.json` | Đường live qua API trên **CPU** (nguồn `data/binh1.mp4`, bbox `104,308,209,287`, `image_size 192`, `vos_every 3`, 10 s) | `device_yeu_cau=cpu`, `device_worker_log=cpu`, `git_rev=ffc9f02`, `ket_qua=true` · **29,9 FPS phát** · **mask 6,9 lần/giây** · `drift_n 59` (p05 0,673) · `stability_shown 0,957 (n=10)` |
| `data/live_gpu_device_cuda_unavailable_2026-11-11_metrics.json` | Xin `cuda` trên máy **không** có GPU | `ket_qua=false`, `loi` = `HTTP 400 … "đã xin device='cuda' nhưng máy này không thấy GPU CUDA … Colab → T4"` ⇒ chứng minh **không âm thầm rơi về CPU** |

- Ca xin `cuda` trên máy không GPU: worker chết **trước khi nạp checkpoint** (chỉ ~3 s), lý do tới
  `status.json` **và** `data/*_metrics.json`.
- Lưu ý trung thực (3 lần đo cùng clip/cấu hình trong phiên này): `mask_fps` **6,7 · 6,8 · 6,9**
  (artifact cuối = 6,9), còn lần đo buổi sáng trước khi chạy `testall` ra **8,4**. Chênh ~20 % giữa
  các lần ⇒ **không** dùng các số này để A/B (AGENTS §6: A/B phải dùng `scripts/repeatability.py`
  lấy ngưỡng nhiễu; muốn trích thì đo 3 lần liền và ghi `mean ± spread`).
- Ca "xin cuda mà không GPU": `device_worker_log = null` là **đúng** (worker chết trước khi log dòng
  `device=`); lý do nằm ở `loi` + `status.json` của worker.

### Bằng chứng test "có răng" (đã kiểm thật, có phục hồi)

- Bỏ `device=device` khỏi `TrackerEngine.build_default(...)` trong `tools/live_worker.py` ⇒ **2 test
  wiring đỏ** (`TestWiringEngine`), đúng cái lỗ của phiên hôm nay.
- Ca subprocess `--device cuda` trên máy CPU: trả mã **2**, `status.json` `state=error` chứa "GPU CUDA"
  — không skip oan (skip chỉ khi máy **có** CUDA).
- `_post` giữ thân lỗi: test dựng `http.server` trả 400 + `{"detail": …}` ⇒ `RuntimeError` phải chứa lý do.

File thay đổi:
- `src/device.py` — **mới**: chuẩn hoá/kiểm tra thiết bị + đọc env.
- `tools/live_worker.py` — `--device`, kiểm CUDA trước khi nạp, `device=` xuống engine, log tên GPU.
- `src/worker/command.py` — dựng `--device` cho worker live.
- `src/api/adapters/worker_source.py`, `src/api/adapters/subprocess_runner.py`, `src/api/main.py` —
  chuyển `device` cho phiên live **và** job upload + đọc `$CAMERA_AI_DEVICE` một lần.
- `scripts/measure_live_relay.py` — `--device`, `device_yeu_cau`/`device_worker_log`, `_post` giữ lỗi.
- `tests/test_device.py`, `tests/test_worker_device.py` — **mới**; `tests/test_measure_live_relay.py` +3.
- `README.md` (mục 3b), `run` (lệnh `gpu`).
- `data/live_gpu_device_cpu_baseline_2026-11-11_metrics.json`,
  `data/live_gpu_device_cuda_unavailable_2026-11-11_metrics.json`.

## 🐞 Vấn đề gặp phải & cách xử lý

- **`--device cuda` trên máy không GPU trả HTTP 400 với `HTTPError: 400` trơn** ở script đo ⇒ artifact
  ghi một dòng lỗi vô nghĩa, mất đúng câu hướng dẫn. Sửa `_post` đọc thân lỗi; thêm test `http.server`.
- **Test `_pending_drift` cũ không dùng được `setattr` vào lớp thật** (đã gặp ở phiên 1) ⇒ ở đây dùng
  **lớp con** + `monkeypatch` (`TestWiringEngine`) thay vì sửa module thật.
- **`testall` đỏ 1 test `tracker_engine`** nhưng chạy riêng thì xanh: SAM 2 không tất định (AGENTS §6)
  + tranh CPU sau 6 phút chạy. Không sửa ngưỡng để "cho xanh" — ghi thành việc cần làm (ticket flaky).
- **`stability_shown` lần đầu `null`** ở artifact ca lỗi (`n=0`): đúng encoding ticket 19 vừa làm —
  phiên không chạy thì **chưa đo**, không phải "0 %".

## 📌 Việc cần làm tiếp (Next steps)

- [ ] **Chạy Colab T4 để có số GPU thật của đường live** (người dùng bấm; agent không có tài khoản):
      `CAMERA_AI_DEVICE=cuda python scripts/measure_live_relay.py --source <video> --bbox … --device cuda`
      ⇒ artifact có `device_worker_log=cuda` + tên GPU. **Đây là số cần cho mục "Đánh giá hiện năng"
      trên GPU**; số CPU trong log này **không** được trích như số GPU.
- [ ] Mặc định theo thiết bị: trên GPU nên `image_size 512` (API đang ghim `192` cho mode track) và
      có thể `vos_every 1` — đo rồi mới đổi (AGENTS §6: đo trước, hứa sau).
- [ ] Hiện thiết bị trong `/api/live/status` + HUD web (đổi schema + `api.ts` + e2e) — hiện chỉ có
      trong log/artifact.
- [ ] Ticket 15 (log từng mẫu drift ra CSV + đối chứng cảnh tĩnh) — vẫn là việc kế tiếp của chuỗi
      "chất lượng bám"; ticket 14 chờ dữ liệu, ticket 11 chờ người.
- [ ] **Ticket 22** (đã tạo): `test_tracker_engine::test_process_theo_frames_iou_dat_o_cac_frame_mau`
      đỏ khi chạy full suite trên máy đang tải (chạy riêng: 8/8 xanh) — phải đo tần suất đỏ trước khi
      đổi ngưỡng/retry.
- [ ] **Ticket 21** (đã tạo): `device` chưa có trong `/api/live/status`/HUD (hiện chỉ đọc từ
      `worker.log`), và mặc định `image_size`/`vos_every` của mode track chưa theo thiết bị.

## 📚 Tài liệu tham khảo

- `AGENTS.md` §6 (`0/None ≠ đã đo`, số đo phải kèm thiết bị + `git_rev`), §9.1 (review độc lập), §7b (git).
- `README.md` mục 3 (Colab GPU) + **3b** (live trên GPU) + mục 7 (bảng hiệu năng).
- `docs/task/22-10-2026-colab-gpu-so-lieu-va-fix.md` — số GPU T4 `49,6 ms ≈ 20,15 FPS` (commit `8d64d59`).
- `docs/research/11-do-encoder-repvit-tren-cpu-va-tran-realtime.md` — trần realtime trên CPU này.
- Log phiên sáng nay: `docs/task/11-11-2026-ticket-19-20-encoding-stability-shown-va-lock.md`.
