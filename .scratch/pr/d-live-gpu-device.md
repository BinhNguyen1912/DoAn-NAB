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

### Số đo CPU baseline — 3 lần liền trên máy rảnh (commit `8501ff3`, cả 3 `git_dirty_code=false`)

| Lần | FPS phát | Mask mới/giây | `vos_ms` | `mask_age_p95` | `drift_iou_p05` (`drift_n`) |
|---|---|---|---|---|---|
| run1 | 29,8 | 7,0 | 123 ms | 304 ms | 0,714 (60) |
| run2 | 29,9 | 6,7 | 327 ms | 668 ms | 0,673 (51) |
| run3 | 29,8 | 7,5 | 133 ms | 354 ms | 0,681 (55) |
| **TB** | **29,8** | **7,07** | — | — | 0,689 |

Nhiễu: mask **6,7–7,5 (±6 %)**, `vos_ms` 123–327 ms ⇒ **không** dùng mask_fps để A/B nếu chưa có
ngưỡng nhiễu (`scripts/repeatability.py`, AGENTS §6). Một bộ đo trước đó có lần đầu `vos_ms =
4 363 ms` (chậm 20×, `mask_age_p95` 1 935 ms) — đo lại trên máy rảnh **không tái hiện** ⇒ đó là phiên
suy giảm do máy đang tải, **đã loại khỏi** bảng (không trung bình hoá nó vào).

### Review độc lập 2 vòng

- **Vòng 1**: P0 = 0, **2 P1** (lệnh GPU trong `README`/`./run gpu` sai: `./run web` chỉ build; `./run video --device cuda` lỗi argparse) + 4 P2 (thiếu test ở composition root; script đo thừa hưởng env; `ket_qua` không xét thiết bị; thiếu log) + 8 P3.
- **Vòng 2**: P0 = 0, P1 = 1 (chỉ 1 dòng comment trong `src/device.py` vẫn dạy `CAMERA_AI_DEVICE=cuda ./run web` — đúng lệnh sai của vòng 1) + 5 P2 + 7 P3. Đã sửa hết trong nhánh này:

| Mức | Phát hiện | Xử lý |
|---|---|---|
| P1 | `src/device.py` comment dạy `CAMERA_AI_DEVICE=cuda ./run web` (web chỉ BUILD) | Sửa thành `./run web` rồi `CAMERA_AI_DEVICE=cuda ./run api` |
| P2 | `run_live.py --device` còn `choices` ⇒ `--device CUDA` bị argparse chặn, lệch worker | Bỏ `choices`, dùng chung `validate_device` |
| P2 | Script đo: `ket_qua` có xét thiết bị nhưng **mã thoát thì không** ⇒ ca lệch thiết bị exit 0, không cảnh báo | Tách `_ket_qua`/`_ma_thoat` + in `[THAT BAI]` khi `ket_qua` false + test |
| P2 | Artifact/log/PR trỏ `…_cpu_baseline_2026-11-10_metrics.json` (không tồn tại; thật là run1..3) | Sửa cả 3 chỗ theo bảng số thật |
| P2 | Bảng số liệu **trung bình hoá run1** dù run1 suy giảm 20× (`vos_ms 4 363 ms`, `mask_age_p95 1 935 ms`) | Bảng mới nêu rõ run1 là outlier, đo lại 3 lần trên máy rảnh (xem dưới) |
| P3 | Prose còn "11-11" trong ~16 file; cheatsheet còn số cũ 65 ms/15,3 FPS; `_cuda_co_san` có thể nổ lúc collect; `--out` mặc định không có giờ (ghi đè artifact) | Đã sửa: sed ngày, cheatsheet theo `data/gpu_summary.json`, `try/except`, tên file có `%H%M%S` |
