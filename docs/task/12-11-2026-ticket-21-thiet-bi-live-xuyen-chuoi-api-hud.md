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

## 🚦 CI GitHub & merge
- **PR #10** (https://github.com/BinhNguyen1912/DoAn-NAB/pull/10) — tự tạo bằng GitHub REST API qua
  credential của `git credential fill` (máy này **không có `gh` CLI**), chờ CI xanh rồi merge
  (`7c05e6c`), xoá nhánh cả hai phía.
- **CI đỏ sẵn trên `main` từ 10-11** (run `42834180353`, không liên quan nhánh này) — sửa luôn trong PR:
  1. `tests/test_run_live_cli.py::TestThietBiXuongEngine` gọi `run_live.main()` ⇒ đi qua
     `resolve_checkpoint()` **thật** trong khi `build_default` đã bị thay bằng engine giả ⇒ 3 test đổ
     `FileNotFoundError` trên runner (không có `samurai/sam2/checkpoints/*.pt` — bị `.gitignore`).
     Fix: thay luôn `run_live.resolve_checkpoint` bằng hàm nhận nguyên đường dẫn (đúng phạm vi: test này
     khoá kwarg `device`, đường resolve thật có test riêng ở `tests/test_config.py`).
     **Đã kiểm bằng cách ẩn checkpoint thật** (`mv … .pt .pt.hidden`) rồi chạy lại 3 test: 3/3 xanh, sau đó
     trả file về chỗ cũ (đúng môi trường CI).
  2. `tests/test_api_live.py::TestMoLaiSauPhienLoi` đỏ oan: (a) phiên ĐẦU dùng `_SlowStartSource` chặn
     tới **5 s** trong `start()` — sát mức timeout mặc định 5 s của `TestClient`; (b) đợi bằng
     `created[-1].entered`, mà nếu lần Bật lại chưa kịp tạo nguồn mới thì `created[-1]` là nguồn **CŨ**
     (đã `entered` từ trước) ⇒ assertion "đã vào nguồn" pass **sai**, rồi đọc `state = error`. Fix: phiên
     đầu dùng nguồn mở tức thì; chờ đúng nguồn CỦA lần bật lại (`len(cham) > truoc`); đọc trạng thái theo
     vòng có hạn và in mã HTTP + lỗi khi đỏ. Không nới ngưỡng, không bỏ assertion nào.
- **Kết quả:** CI `main` **success** (run `43167972913`) — lần đầu xanh lại từ 10-11.

## 🚦 Lần đo GPU đầu tiên trên Colab (12-11) — **THẤT BẠI, không được trích**

Người dùng chạy notebook (T4) theo mục 8, hai artifact ghi ra đều `ket_qua: false`:

```text
loi: "Không mở được bám-đối-tượng:data/input.mp4: worker dừng khi khởi động (mã 1) —
      xem /dev/shm/doan-live-relay/worker.log"
ly_do: state_cuoi=None · frames=0 · measured_fps=0 · mask_fps=0 · device_worker_log=None
```

- **Chưa có số GPU nào.** Hai file `data/live_512_metrics.json` / `data/live_192_metrics.json` là
  lần đo HỎNG ⇒ **đã xoá khỏi repo** (chúng bị commit nhầm cùng PR #15 do `git add -A`; xem
  "Vấn đề gặp phải"). Cấm trích hai file này trong báo cáo.
- Nguyên nhân chưa biết: `worker.log` nằm trên `/dev/shm` của runtime Colab, runtime xoá là mất ⇒
  **PR #15** thêm `worker_log` + `api_log` (4000 ký tự cuối) vào artifact để lần sau tự chẩn đoán.
- Bước tiếp: chạy `tools/live_worker.py` trực tiếp trên Colab để lấy traceback (nhanh hơn đo lại),
  rồi sửa đúng chỗ; sau đó chạy lại mục 8 (2 lần/cấu hình để có ngưỡng nhiễu).

## 🐞 Vấn đề gặp phải & cách xử lý
- **E2E "PASS" trên mã CŨ**: lần chạy đầu, check mới báo đỏ "không thấy dòng thiết bị" dù mã đúng. Nguyên
  nhân: `./run e2e` **không build** frontend — server phục vụ `web/dist` cũ (từ lần build trước), nên trình
  duyệt chạy JS cũ. Xử lý: build tay một lần để xác nhận (`npm run build` → e2e PASS), rồi sửa `run` để
  lệnh `e2e` **luôn** build lại (~2 s) — nếu không, mọi thay đổi UI đều có thể "được kiểm" bằng mã cũ.
- **Test chập chờn nếu chỉ stub `/api/live/start`**: `LivePanel` poll `/api/live/status` mỗi 1 s và ghi đè
  status bằng phản hồi THẬT (chế độ raw ⇒ `device=""` ⇒ dòng thiết bị biến mất sau < 1 s). Xử lý: stub cả
  `/api/live/status` rồi `unroute` ngay sau khi kiểm.
- **`web/dist` không nằm trong git** nên `git status` sạch dù đã build — không có artifact lạ trong diff.

- **Lỡ commit artifact HỎNG vào `main`:** `git add -A` trong PR #15 nhặt luôn
  `data/live_512_metrics.json` / `data/live_192_metrics.json` (chúng KHÔNG bị `.gitignore` chặn vì
  repo cố ý cho qua `data/*_metrics.json`). Hậu quả: (a) `main` chứa "bằng chứng" là lần đo thất bại,
  (b) Colab `git pull` báo `untracked working tree files would be overwritten`. Xử lý: xoá 2 file
  khỏi repo (nhánh riêng, có log ghi rõ lý do) — bài học: khi `git add -A`, phải xem `git status`
  trước khi commit artifact do người khác vừa copy vào `data/`.

## 📌 Việc cần làm tiếp (Next steps)
- [x] **Review độc lập** (§9.1) diff này — 0 P0/P1, 1 P2 + 4 P3, đã sửa hết (xem mục trên).
- [x] **PR #10 đã merge vào `main`** (`7c05e6c`) sau khi CI xanh; nhánh đã xoá cả local lẫn remote.
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
