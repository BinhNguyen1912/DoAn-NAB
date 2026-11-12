# PR: thiết bị chạy model đi xuyên `status.json` → API → HUD (ticket 21, phần 1)

Nhánh: `feat/live-device-status-api` · mở PR tại
https://github.com/BinhNguyen1912/DoAn-NAB/pull/new/feat/live-device-status-api
(máy này không có `gh` CLI — người phụ trách bấm mở rồi dán thân dưới đây)

---

## Summary

```text
LiveTrackConfig.device ──┐
                         ├─> status.json { "device": "cpu" | "cuda" }
live_worker._write_loading(device) ┘            │   (cả lúc loading 20–240 s)
                                                ▼
                     WorkerFrameSource.telemetry()  (thiếu khoá ⇒ "" = chưa biết)
                                                ▼
         LiveTelemetry.device → LiveStatus.device → LiveStatusResponse.device
                                                ▼
                     api.ts LiveStatus.device → live.ts deviceLine() → HUD
                     "Thiết bị chạy model: cuda (GPU) — FPS/độ trễ chỉ đúng cho thiết bị này"
```

Trước PR này, thiết bị **chỉ** có trong `worker.log` (phải regex) ⇒ `/api/live/status`, HUD và artifact
không biết phiên chạy CPU hay GPU, trong khi mọi số FPS/độ trễ trong báo cáo phải gắn với một thiết bị
(AGENTS §6, `docs/task/10-11-2026-duong-live-chay-duoc-tren-gpu.md`).

Encoding "chưa biết" giữ đúng quy ước repo: `device: ""` = **chưa biết** (chế độ `raw`, hoặc worker bản
cũ) ⇒ HUD **ẩn** dòng đó; không chỗ nào tự điền `"cpu"` (bẫy `0/None ≠ đã đo`).

## Evidence

- **Before:** `status.json` không có khoá `device`; `status_payload()` chỉ trả `state/frames/vos_*…`;
  `/api/live/status` không có `device`; HUD không có dòng thiết bị.
  **After:** chạy worker thật trên máy này:

  ```text
  $ python tools/live_worker.py --source data/e2e_web.mp4 --out-dir /tmp/live_dev --device "CPU " --stop-after-frames 5
  [worker] nạp model (image_size=mặc định 1024, device=cpu)...
  $ cat /tmp/live_dev/status.json
  {"state": "stopped", "device": "cpu", ...}      # "CPU " được chuẩn hoá
  ```

- **Test hồi quy cho P2 của review (thiết bị phải hiện TRONG lúc nạp model):**

  ```text
  bỏ fix (source = self._source)      → FAILED test_thiet_bi_hien_ra_TRONG_LUC_nap_model
                                        AssertionError: đang nạp model mà API báo device='' ⇒ HUD ẩn dòng thiết bị suốt 20–240 s
  có fix (source = self._pending or self._source) → 53/53 passed (test_api_live.py)
  ```

- **E2E trình duyệt thật (`./run e2e`, Chrome/Edge lái từ Windows):**

  ```text
  ✓ HUD hiện thiết bị model (cuda) lấy từ /api/live/status —
    Thiết bị chạy model: cuda (GPU) — FPS/độ trễ chỉ đúng cho thiết bị này
  ✓ FPS live đo được > 0 — Trạng thái: running · frame: 31 · FPS đo được: 29.8
  KẾT LUẬN: PASS
  ```

- **Cả bộ kiểm tra trên máy này (WSL, không GPU NVIDIA):** `./run lint` xanh · `./run test` **815 passed**
  · `./run testall` **820 passed** (211 s) · `./run webtest` **36 passed** · `./run e2e` **PASS**.

- **Review độc lập (§9.1):** 0 P0, 0 P1, 1 P2 + 4 P3 — P2 và cả 4 P3 đã sửa trong PR này
  (chi tiết: `docs/task/12-11-2026-ticket-21-thiet-bi-live-xuyen-chuoi-api-hud.md`).

- **Chưa đo được:** đường `cuda` thật (không có GPU NVIDIA trên máy này) ⇒ `device="cuda"` mới chứng minh
  tới mức "worker nhận cờ → engine nhận kwargs → status/HUD hiển thị", **chưa có số FPS GPU**. Phần 2 của
  ticket (mặc định `image_size`/`vos_every` theo thiết bị) giữ nguyên trạng thái chờ Colab.

## Merge Danger

**Door:** two-way — thêm một khoá additive vào `status.json` + `LiveStatusResponse` + một dòng HUD.
Không đổi hành vi tracking, không đổi mặc định `image_size`/`vos_every`, không đổi artifact cũ (khoá mới
chỉ xuất hiện thêm; `measure_*` chỉ đọc khoá đã whitelist).

**Blast Radius:** nhỏ, nhưng **chạm hợp đồng HTTP** (`/api/live/status` thêm `device`) và `run` (lệnh `e2e`
nay build frontend trước khi chạy, ~2 s) ⇒ ai có script riêng parse `status.json` phải chấp nhận thêm
một khoá; ai đang dựa vào "e2e không build" sẽ thấy nó build.

**Ghi chú vận hành:** `device` **không** chứng minh engine thật sự dùng GPU ở mọi bản SAM 2 — nó là điều
worker tự báo. Phép so `device_worker_log` (regex `worker.log`) trong `scripts/measure_live_relay.py` vẫn
giữ để phát hiện lệch.

---

### Checklist (AGENTS §9.4)

- [x] `./run lint` xanh
- [x] `./run test` 815 · `./run testall` 820 · `./run webtest` 36 · `./run e2e` PASS
- [x] Review độc lập đã chạy, P0 = 0, P1 = 0 (1 P2 + 4 P3 đã sửa)
- [ ] CI GitHub xanh (chờ PR)
- [x] Log `docs/task/12-11-2026-ticket-21-thiet-bi-live-xuyen-chuoi-api-hud.md` có kết quả review
- [x] Số liệu trong log lấy từ lần chạy thật trên máy này, ghi rõ môi trường (WSL, CPU, không GPU)
