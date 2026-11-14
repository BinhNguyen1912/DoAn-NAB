# 21: Thiết bị chạy model chưa hiện ở /api/live/status + mặc định image_size/vos_every chưa theo GPU

**What to build:** Đường live đã chạy được GPU (`--device cuda`, `$CAMERA_AI_DEVICE`, merge 10-11) nhưng báo cáo/demo vẫn chưa "nhìn thấy" thiết bị:

1. `status_payload` (`src/live_tracking.py`) không có khoá `device` ⇒ `/api/live/status`, HUD web và artifact chỉ biết thiết bị nhờ đọc `worker.log` (mẹo ở `scripts/measure_live_relay.py::_worker_device`). Thêm `device: str` vào status.json → adapter `LiveTelemetry` → schema → `api.ts` → HUD.
   - Nghiệm thu: xin `cuda` mà máy không GPU ⇒ `state=error`, message nêu thiết bị; phiên CPU ⇒ `device="cpu"`; test allowlist `status.json` cập nhật; `./run webtest` + `./run e2e` xanh.
2. Mặc định theo thiết bị: `src/api/main.py` ghim `image_size or 192` cho mode track — hợp lý cho CPU, nhưng trên GPU 512 vừa đủ nhanh hơn nhiều và chi tiết hơn. Đo trên GPU rồi mới chọn (AGENTS §6: đo trước, hứa sau), ghi số vào log.
   - Nghiệm thu: bảng 2 dòng (CPU 192/GPU ?) có `git_rev` + `device_worker_log`, ghi rõ ngưỡng nhiễu giữa các lần đo.

**Vì sao không làm ngay trong PR 10-11:** thêm field vào `status.json` là đổi hợp đồng API + `web/src` ⇒ cần plan/e2e riêng; mặc định GPU cần số đo trên Colab (agent không có tài khoản Google).

**Blocked by:** None (can start immediately)

**Status:** claimed

- [x] `status.json` có `device`, xuyên chuỗi tới `/api/live/status` và HUD web; allowlist test cập nhật; `./run webtest` + `./run e2e` xanh
- [ ] Bảng mặc định theo thiết bị (image_size, vos_every) kèm số đo thật trên GPU, có `git_rev` + `device_worker_log`, và ghi ngưỡng nhiễu
- [ ] Không làm mất đường CPU hiện tại: `./run test` + `testall` xanh, số CPU baseline trong `data/live_gpu_device_cpu_baseline_run1..3_2026-11-10_metrics.json` vẫn tái lập được

## Comments

12-11: **phần 1 đã merge** (`PR #10`, commit merge `7c05e6c`) — `device` giờ có trong `status.json` (cả lúc `loading`), `/api/live/status`, HUD web (`data-testid="device-line"`) và artifact của `measure_live_relay`/`measure_empty_window`. `""` = chưa biết (raw / worker bản cũ) ⇒ HUD ẩn dòng, không đoán `"cpu"`.

Kèm 2 fix CI **có sẵn từ 10-11** (main đỏ ở run 42834180353, không liên quan nhánh): (a) `TestThietBiXuongEngine` đi qua `resolve_checkpoint()` thật ⇒ 3 test đổ trên runner không có checkpoint (bị `.gitignore`); (b) `TestMoLaiSauPhienLoi` cho phiên đầu dùng nguồn chặn 5 s (sát timeout 5 s của `TestClient`) và đợi bằng `created[-1]` (có thể là nguồn CŨ đã `entered`) ⇒ đỏ oan. CI `main` nay **success** (run 43167972913).

Kiểm trên máy này (WSL, CPU, không GPU NVIDIA): lint xanh · test 815 · testall 820 · webtest 36 · e2e PASS; worker thật `--device "CPU "` ⇒ `status.json` `"device": "cpu"`.

**Còn mở:** tiêu chí 2 (mặc định `image_size`/`vos_every` theo thiết bị) — cần số GPU thật từ Colab: `python scripts/measure_live_relay.py --source data/<video>.mp4 --bbox "x,y,w,h" --device cuda --image-size 512 --seconds 30`. Tiêu chí 3 mới xác nhận phần `test`/`testall` xanh, **chưa** chạy lại 3 lần đo CPU baseline (`data/live_gpu_device_cpu_baseline_run1..3_2026-11-10_metrics.json`) nên chưa tick.

13-11 (lần chạy Colab thứ 2, `git_rev=58770a3`, `git_dirty_code=false`): **đường GPU qua API live đã chạy được trên T4** — `ket_qua=true`, `device_worker_log=cuda`, `state_cuoi=running`, 804–810 frame/30 s, `empty_runs=0`. Lỗi `worker dừng khi khởi động (mã 1)` của 12-11 đã hết (nhờ 2 fix `a30cca7` + artifact mang `worker.log`).

Số dùng được (T4, `--vos-every 3`):
- `vos_ms` **63,8 ms @image_size 512** vs **43,5 ms @192** (n=1/cấu hình) ⇒ 512 chậm 1,47×.
- `lk_ms` 16,49 vs 4,27; `mask_age_p95` 234,8 vs 138,8 ms; `measured_fps` 25,6 vs 30,0.
- `mask_fps_max` 10,4 vs 10,8 — **không phân biệt được** hai mức vì chạm trần `display_fps/vos_every` ≈ 10 lần/giây ⇒ chọn `image_size` phải dùng `vos_ms`.

**Chưa chốt được mặc định** (tiêu chí 2 vẫn mở): 2 artifact này có `drift_iou` 0,203/0,346 và `stability` 0,27/0,35 vì `data/input.mp4` là **clip tổng hợp** do cell 3b tự sinh (ô vuông ở `200,200`) nên bbox `104,308,209,287` trỏ vào nền — đã tái lập trên CPU (`data/repro_bbox_tro_nen_cpu_2026-11-13_metrics.json`: drift 0,118 / stability_shown 0,389) ⇒ lỗi chọn ô, không phải GPU.

Đã sửa để không lặp lại (PR #20, merge `4fad8b7`): mục 8 của notebook thành 3 cell — 8a kiểm video+bbox (in `WxH | số frame`, ghi `bbox_check.jpg`, chặn clip tổng hợp, cờ `DA_KIEM_8A`), 8b chạy **2 lần/cấu hình**, 8c in số kèm `*_n` + `device_worker_log`; thêm `tests/test_notebook_colab.py`.

Cần để đóng tiêu chí 2: chạy lại mục 8 với `data/binh1.mp4` (upload thành `input.mp4`, cell 8a phải in `720x1280 | 333 frame`), `BBOX="104,308,209,287"`, `LAN=(1,2)` ⇒ 4 artifact `live_{512,192}_lan{1,2}_metrics.json`; so `vos_ms` giữa 2 mức với ngưỡng nhiễu rồi chốt mặc định trong `src/api/main.py`.
