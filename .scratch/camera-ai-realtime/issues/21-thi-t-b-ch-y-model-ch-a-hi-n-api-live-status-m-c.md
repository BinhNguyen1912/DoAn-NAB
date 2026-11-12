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
