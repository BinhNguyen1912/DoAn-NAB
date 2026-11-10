## Đường LIVE chạy được trên GPU — sửa lỗ "máy có GPU vẫn chạy CPU"

Nhánh này trả lời đúng một câu hỏi: **phiên live của sản phẩm (worker + `/api/live/*` + web, và job
upload→track→mp4) có dùng GPU không?** Trước PR: **không**. `tools/live_worker.py` gọi

```python
engine = TrackerEngine.build_default(image_size=args.image_size)   # ← thiếu device
```

mà `build_default(device="cpu", …)` ⇒ **mọi phiên live qua web chạy model trên CPU**, dù máy có GPU
NVIDIA/Colab. Đường CLI (`tools/run_live.py`) đã có `--device` từ lâu ⇒ hai đường lệch hành vi. Hệ quả
cho báo cáo: demo trên Colab T4 bằng web sẽ ra **số CPU** trong khi người đọc tưởng GPU (đúng bẫy
AGENTS §6 "số đo phải ghi rõ môi trường").

### Thay đổi

1. **`src/device.py` (mới)** — hàm thuần, **không** import torch: `normalize_device`,
   `validate_device(name, cuda_available=…)`, `device_from_env()` + `ENV_VAR = "CAMERA_AI_DEVICE"`.
2. **`tools/live_worker.py --device cpu|cuda`** — kiểm CUDA **trước** khi nạp checkpoint 156 MB; xin
   `cuda` mà máy không có GPU ⇒ `status.json` `state=error` + câu hướng dẫn Colab T4, `exit 2`;
   truyền `device=device` xuống `build_default` (đóng lỗ gốc).
3. **`src/worker/command.py`** — `build_live_worker_command(..., device=…)` **và**
   `build_command(..., device=…)` (job upload): chỉ thêm `--device` khi có yêu cầu, chuẩn hoá tên
   (typo ⇒ `ValueError`, không lọt xuống shell).
4. **API**: `WorkerFrameSource(device=…)`, `SubprocessPipelineRunner(device=…)`,
   `build_default_live()`/`build_default_service()` đọc `$CAMERA_AI_DEVICE` **một lần lúc khởi động**
   (gõ sai ⇒ lỗi ngay, không phải giữa demo). **Hợp đồng HTTP không đổi** — thiết bị do **máy chủ**
   quyết định, không nhận từ params của client.
5. **`scripts/measure_live_relay.py --device`** + artifact ghi `device_yeu_cau`,
   `device_worker_log` (đọc `worker.log` = **sự thật**), `ghi_chu_device`; `_post` giữ thân lỗi HTTP
   (bản trước ném `HTTPError: 400` trơn ⇒ mất đúng câu hướng dẫn).

### Bằng chứng

| Kiểm tra | Kết quả |
|---|---|
| `./run lint` | ✓ |
| `./run test` | **795 passed** (5 deselected, ~76 s) |
| `./run testall` | **800 passed**, 0 failed (271 s) |
| `./run e2e` | **PASS** (bắt buộc: có sửa `src/api/**`) — 2 lần, trước và sau khi sửa review |
| Test mới | 41 case (`test_device.py` 17, `test_worker_device.py` 17, `test_measure_live_relay.py` +5, `test_worker_pipeline.py` +3, `test_run_script.py` +1) |

### Số đo CPU baseline — 3 lần liền (commit `e34eb5c`, cả 3 `git_dirty_code=false`)

| Lần | FPS phát | Mask mới/giây | `drift_iou_p05` (`drift_n`) | `stability_shown` |
|---|---|---|---|---|
| run1 | 27,9 | 5,0 | 0,671 (34) | 0,911 |
| run2 | 29,7 | 6,0 | 0,689 (47) | 0,960 |
| run3 | 29,6 | 6,3 | 0,752 (51) | 0,960 |
| **TB** | **29,1** | **5,8** | 0,704 | 0,944 |

Nhiễu giữa 3 lần: mask **5,0–6,3 (±11 %)**, FPS phát 27,9–29,7 ⇒ **không** dùng mask_fps để A/B nếu
chưa có ngưỡng nhiễu (`scripts/repeatability.py`).

Số đo thật (artifact có `git_rev` + `git_dirty_code=false`, commit `ffc9f02`):

| Artifact | Nội dung |
|---|---|
| `data/live_gpu_device_cpu_baseline_run1..3_2026-11-10_metrics.json` | đường live qua API trên **CPU**: `device_yeu_cau=cpu`, `device_worker_log=cpu`, `ket_qua=true` (xem bảng trên) |
| `data/live_gpu_device_cuda_unavailable_2026-11-10_metrics.json` | xin `cuda` trên máy **không** GPU: `ket_qua=false`, `device_worker_log=null` (worker chết trước dòng log), `ly_do_khong_dat` nêu rõ, `loi` giữ câu `HTTP 400 … "đã xin device='cuda' … Colab → T4"` ⇒ **không âm thầm rơi về CPU** |

Test "có răng" (đã kiểm thật, có phục hồi):
- bỏ `device=device` khỏi `build_default(...)` ⇒ 2 test wiring đỏ (đúng lỗ của PR này);
- bỏ `device=self._device` khỏi lệnh runner ⇒ test job-upload đỏ;
- ca subprocess `--device cuda` trên máy CPU: mã thoát 2 + `status.json` chứa "GPU CUDA".

### Việc còn nợ (đã tạo ticket)

- **#21** — `device` chưa có trong `/api/live/status`/HUD (hiện chỉ đọc từ `worker.log`); mặc định
  `image_size`/`vos_every` của mode track chưa theo thiết bị (cần số đo trên GPU trước khi đổi).
- **#22** — `test_tracker_engine::test_process_theo_frames_iou_dat_o_cac_frame_mau` đỏ 1 lần khi chạy
  full suite trên máy đang tải (chạy riêng 8/8 xanh) — đo tần suất đỏ trước khi đổi ngưỡng/retry.
- **Chạy Colab T4** để có số GPU thật của đường live (người dùng bấm; agent không có tài khoản
  Google): `CAMERA_AI_DEVICE=cuda python scripts/measure_live_relay.py … --device cuda`.

### Cửa một chiều hay hai chiều?

**Hai chiều** — toàn bộ thay đổi là additive: không đặt `$CAMERA_AI_DEVICE` thì API truyền
`--device cpu` xuống worker/job, **trùng đúng** mặc định `device: cpu` của `configs/default.yaml`
⇒ hành vi + số đo cũ giữ nguyên (có test khoá cả hai chiều: `--device cpu` khi env trống, và không
có cờ khi constructor nhận `None`).

### Review độc lập 2 vòng

- **Vòng 1**: P0 = 0, **2 P1** (lệnh GPU trong `README`/`./run gpu` sai: `./run web` chỉ build; `./run video --device cuda` lỗi argparse) + 4 P2 (thiếu test ở composition root; script đo thừa hưởng env; `ket_qua` không xét thiết bị; thiếu log) + 8 P3.
- **Vòng 2**: review lại delta — xem kết quả trong `docs/task/10-11-2026-duong-live-chay-duoc-tren-gpu.md`.
