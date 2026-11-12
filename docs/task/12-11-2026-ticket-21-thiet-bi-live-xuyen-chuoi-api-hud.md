# Ngày 12-11-2026 — Ticket 21 (phần 1): thiết bị chạy model đi xuyên chuỗi `status.json → API → HUD`

## 🎯 Mục tiêu
- Đóng **phần 1 của ticket 21** (`.scratch/camera-ai-realtime/issues/21-…`): đường live đã chạy được GPU từ
  10-11 nhưng **thiết bị** chỉ nằm trong `worker.log` (phải đọc bằng regex) ⇒ API, HUD web và artifact
  không biết phiên đang chạy CPU hay GPU.
- Thêm `device` (`cpu` | `cuda`) xuyên chuỗi: `status.json` → `LiveTelemetry` (domain) → `LiveStatusResponse`
  (schema) → `web/src/api.ts` → HUD; giữ đúng quy ước "chưa biết ≠ một khẳng định cụ thể" của AGENTS §6.
- **Không** làm trong phiên này: phần 2 của ticket (mặc định `image_size`/`vos_every` theo thiết bị) — cần
  số đo GPU thật, mà agent không có tài khoản Colab.

## 📥 Input
- `AGENTS.md` §6 (số đo phải gắn thiết bị; `0`/`None`/`""` = chưa đo, không được đổi thành khẳng định),
  §9.1 (review độc lập), §7b (git), `CODING_STANDARDS.md`.
- Ticket 21 + log `docs/task/10-11-2026-duong-live-chay-duoc-tren-gpu.md` (mục "Việc cần làm tiếp").
- Mã hiện tại: `src/live_tracking.py` (`status_payload`, `LiveTrackStats`, `LiveTrackConfig`),
  `tools/live_worker.py` (`_write_loading`, `validate_device`), `src/api/{domain,live,routes,schemas}.py`,
  `src/api/adapters/worker_source.py` (`telemetry()`), `web/src/{api.ts,live.ts}`, `web/src/components/LivePanel.tsx`.

## 🔨 Công việc đã thực hiện
1. **Worker ghi thiết bị** (`src/live_tracking.py`):
   - `LiveTrackConfig.device` (mặc định `cpu`), chuẩn hoá bằng `src.device.normalize_device` ngay trong
     `__post_init__` — cùng hàm với CLI/API nên `"CUDA "` → `cuda`, tên rác (`gpu`) bị từ chối tại cửa vào.
   - `LiveTrackStats.device` + `status_payload()` thêm khoá `"device"`; session khởi tạo
     `LiveTrackStats(device=config.device)`.
2. **Giai đoạn nạp model** (`tools/live_worker.py`): `_write_loading(out_dir, message, *, device=…)` — ghi
   `loading` **trước** `_cuda_available()` (import torch, vài giây) nhưng **kèm thiết bị định chạy**; nhánh
   lỗi thiết bị ghi `state=error` + `device` + message nêu thiết bị; truyền `device` vào `LiveTrackConfig`.
3. **API** (`src/api/domain.py`, `live.py`, `schemas.py`, `routes.py`, `adapters/worker_source.py`):
   `LiveStatus.device` / `LiveTelemetry.device` / `LiveStatusResponse.device` (mặc định `""` = **chưa biết**,
   KHÔNG tự điền `cpu`); adapter đọc `status.json["device"]`, thiếu khoá ⇒ `""`.
4. **HUD web** (`web/src/api.ts`, `live.ts`, `components/LivePanel.tsx`): hàm thuần `deviceLine()` →
   "Thiết bị chạy model: cuda (GPU) — FPS/độ trễ chỉ đúng cho thiết bị này"; `""`/null ⇒ **ẩn dòng**;
   render ở `<p data-testid="device-line">`.
5. **Test**: allowlist `status.json` thêm `device` (khoá lạ vẫn đỏ); `device` đi từ config → file; `"CUDA "`
   được chuẩn hoá; tên rác bị từ chối; `loading` có `device`; telemetry `device` → API; thiếu khoá ⇒ `""`;
   nhánh "xin cuda mà máy không GPU" có `device="cuda"` trong `status.json`; 4 ca vitest cho `deviceLine`.
6. **E2E** (`scripts/e2e_web.js`): stub thêm `/api/live/status` trả `device:"cuda"` và check HUD hiện dòng
   thiết bị (chỉ stub `/api/live/start` thì status bị poll thật ghi đè sau ~1 s ⇒ test chập chờn).
7. **`run e2e`**: build lại frontend trước khi lái trình duyệt — xem mục "Vấn đề gặp phải".

## 📤 Output / Kết quả
- `/api/live/status` và HUD giờ trả/hiện thiết bị; `status.json` (cả lúc `loading` và lúc chạy) có `device`.
- Kiểm tra đã chạy trên máy này (WSL, không có GPU NVIDIA), ngay trước review:
  - `./run lint` → **All checks passed**
  - `./run test` → **811 passed, 5 deselected** (88,8 s)
  - `./run testall` → **816 passed** (216 s) — gồm cả test cũ của tracker
  - `./run webtest` → **36 passed** (2 file)
  - `./run e2e` → **PASS**, có check mới: `HUD hiện thiết bị model (cuda) lấy từ /api/live/status —
    "Thiết bị chạy model: cuda (GPU) — FPS/độ trễ chỉ đúng cho thiết bị này"`
- Kiểm tra lại **sau khi sửa theo review**: `./run lint` xanh · `./run test` **815 passed** (84,6 s) ·
  `./run webtest` **36 passed** · `./run testall` **820 passed** (211 s). Lần `testall` ngay trước đó đỏ
  **1** test khác (`test_reap_khong_cho_zombie_5_giay`, chạy riêng 8/8 xanh) — đã ghi vào ticket 22
  (cùng loại flaky theo thời gian, không do nhánh này).
- Chạy worker THẬT trên máy này (`--device "CPU "`) ⇒ `status.json` có `"device": "cpu"` (chuẩn hoá
  đúng, không cần GPU).
- File thay đổi:
  - `src/live_tracking.py` — `device` trong config/stats/payload, chuẩn hoá ở `__post_init__`
  - `tools/live_worker.py` — `_write_loading(device=…)`, thứ tự ghi loading, nhánh lỗi thiết bị, truyền device
  - `src/api/domain.py` · `live.py` · `schemas.py` · `routes.py` — `device` xuyên tầng miền → HTTP
  - `src/api/adapters/worker_source.py` — đọc `device` từ `status.json` (thiếu khoá ⇒ `""`)
  - `src/api/live.py` — `status()` đọc thêm `_pending` (thiết bị hiện được **trong lúc nạp model**)
  - `scripts/measure_live_relay.py` · `scripts/measure_empty_window.py` — whitelist `status.json` thêm `device`
  - `web/src/api.ts` · `live.ts` · `components/LivePanel.tsx` · `live.test.ts` — kiểu + `deviceLine()` + HUD + test
  - `scripts/e2e_web.js` — stub `/api/live/status` + check mới
  - `run` — `e2e` build lại frontend trước khi chạy
  - `tests/test_live_tracking.py` · `tests/test_api_live.py` · `tests/test_worker_device.py` ·
    `tests/test_measure_live_relay.py` · `tests/test_measure_empty_window.py`
  - `README.md` (mục 3b) — thiết bị hiện trên HUD/API, `device: ""` = chưa biết

## 🔎 Review độc lập (§9.1)
- **Ai review:** agent `reviewer` (không phải phiên đã code), prompt có `parent_context` + `proposed_changes`
  + phạm vi = diff chưa commit của nhánh `feat/live-device-status-api`.
- **Kết luận:** **MERGEABLE — 0 P0, 0 P1**; 1 P2 + 4 P3. Reviewer nói rõ chỉ có `read/grep` (không shell) nên
  không tự chạy lại test; các kết luận là bằng chứng đọc mã.
- **Đã sửa trong cùng PR:**
  - **P2 (thật, có test hồi quy):** `src/api/live.py::status()` chỉ đọc `self._source` ⇒ trong 20–240 s
    **đang nạp model** `_pending` giữ nguồn còn `_source` là `None` ⇒ API trả `device=""`, HUD ẩn dòng
    thiết bị đúng lúc cần nhất. Nay `source = self._pending or self._source`; test mới
    `test_thiet_bi_hien_ra_TRONG_LUC_nap_model` (nguồn giả có `start()` block trên `Event`) — **đã kiểm: đỏ
    khi bỏ fix, xanh khi có**.
  - **P3:** comment `web/src/live.ts` ghi sai "~20 ms trên GPU T4" → **49,6 ms/frame (20,15 FPS)** kèm nguồn;
    `_write_loading(device="")` mặc định **chưa biết** (không mặc định `cpu`) + test "quên truyền ⇒ `""`";
    docstring `LiveTrackStats.device` ghi rõ `state=error` ⇒ đó là thiết bị **được yêu cầu**; whitelist
    `status.json` của `measure_live_relay`/`measure_empty_window` thêm `device` + 2 test.
- **Còn nợ (ghi ticket):** đường `cuda` thật chưa đo được trên máy này (chờ Colab — ticket 21 phần 2);
  nhánh flaky `test_reap_khong_cho_zombie_5_giay` gộp vào ticket 22.

## 🐞 Vấn đề gặp phải & cách xử lý
- **E2E "PASS" trên mã CŨ**: lần chạy đầu, check mới báo đỏ "không thấy dòng thiết bị" dù mã đúng. Nguyên
  nhân: `./run e2e` **không build** frontend — server phục vụ `web/dist` cũ (từ lần build trước), nên trình
  duyệt chạy JS cũ. Xử lý: build tay một lần để xác nhận (`npm run build` → e2e PASS), rồi sửa `run` để
  lệnh `e2e` **luôn** build lại (~2 s) — nếu không, mọi thay đổi UI đều có thể "được kiểm" bằng mã cũ.
- **Test chập chờn nếu chỉ stub `/api/live/start`**: `LivePanel` poll `/api/live/status` mỗi 1 s và ghi đè
  status bằng phản hồi THẬT (chế độ raw ⇒ `device=""` ⇒ dòng thiết bị biến mất sau < 1 s). Xử lý: stub cả
  `/api/live/status` rồi `unroute` ngay sau khi kiểm.
- **`web/dist` không nằm trong git** nên `git status` sạch dù đã build — không có artifact lạ trong diff.

## 📌 Việc cần làm tiếp (Next steps)
- [x] **Review độc lập** (§9.1) diff này — 0 P0/P1, 1 P2 + 4 P3, đã sửa hết (xem mục trên).
- [ ] **Ticket 21 phần 2** (chờ số GPU thật — người dùng chạy Colab):
      `python scripts/measure_live_relay.py --source data/<video>.mp4 --bbox "x,y,w,h" --device cuda
      --image-size 512 --seconds 30` ⇒ artifact có `device_worker_log=cuda` + tên GPU; từ đó mới chọn
      mặc định `image_size`/`vos_every` theo thiết bị trong `src/api/main.py`.
- [ ] **Ticket 22** (flaky test): `./run testall` hôm nay đỏ 1 lần ở `test_reap_khong_cho_zombie_5_giay` rồi
  xanh ở lần 2 — đã ghi bổ sung bằng chứng vào ticket (nay là 2 test cùng loại; cần n≥3 lần full suite).
- [x] Đồng bộ `scripts/measure_live_relay.py` / `scripts/measure_empty_window.py` — `device` nay vào
  artifact `worker_status` / dòng số (vẫn giữ phép so `device_worker_log` cũ để so với số 10-11).

## 📚 Tài liệu tham khảo
- Ticket: `.scratch/camera-ai-realtime/issues/21-thi-t-b-ch-y-model-ch-a-hi-n-api-live-status-m-c.md`
- `AGENTS.md` §6 (encoding "chưa đo", số đo phải kèm thiết bị), §9.1 (review độc lập), §7b (git)
- `docs/task/10-11-2026-duong-live-chay-duoc-tren-gpu.md` — số CPU baseline 3 lần + đường GPU của live
- `README.md` mục 3b — 3 cách bật GPU cho đường live
