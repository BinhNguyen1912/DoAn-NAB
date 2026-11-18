# 18-11-2026 — Ticket #21 (tiêu chí 3): tái lập baseline CPU sau khi thêm `device`

## Mục tiêu

Tiêu chí 3 của ticket #21: "Không làm mất đường CPU hiện tại: `./run test` + `testall` xanh, số CPU
baseline trong `data/live_gpu_device_cpu_baseline_run1..3_2026-11-10_metrics.json` vẫn tái lập được".
Đây là phần **không** cần GPU (tiêu chí 2 — bảng mặc định theo thiết bị — vẫn chờ số trên Colab).

## Input

- `data/live_gpu_device_cpu_baseline_run{1,2,3}_2026-11-10_metrics.json` (commit `8501ff3`), lệnh:
  ```
  python scripts/measure_live_relay.py --source data/binh1.mp4 --bbox 104,308,209,287 \
      --image-size 192 --vos-every 3 --seconds 10 --out … --frame-dir /tmp/gN
  ```
- Cây hiện tại: `main` @ `c22c086` (sau 6 PR của ngày 17–18/11: #33,#34,#35,#36,#37 + docs).

## Công việc đã thực hiện

1. `./run testall` (cần checkpoint SAM 2): **1391 passed**, 5 warnings, 210 s.
2. Chạy lại **đúng lệnh** baseline 3 lần (10 s mỗi lần, `device=cpu`), ghi vào
   `data/live_cpu_baseline_run{1,2,3}_2026-11-18_metrics.json` (`git_rev c22c086`,
   `git_dirty_code false`).

## Output / Kết quả

| Chỉ số | 10-11 (`8501ff3`, 3 lần) | 18-11 (`c22c086`, 3 lần) |
|---|---|---|
| `measured_fps` | 29,4 · 27,5 · 29,9 | **29,93 ± 0,05** (29,9 · 30,0 · 29,9) |
| `vos_fps` | 6,1 · 3,3 · 5,0 | **8,3 ± 0,4** (8,8 · 8,0 · 8,1) |
| `vos_ms` | 122,9 · 326,9 · 132,6 | **99,5 ± 6,7** (108,6 · 92,8 · 97,1) |
| `drift_iou` | 0,889 · 0,879 · 0,882 | **0,910 ± 0,000** (0,908 · 0,913 · 0,909) |
| `mask_age_p95` (status) | — | 300,9 · 301,7 · 301,3 |

⇒ Đường CPU **không bị mất**, thậm chí `vos_ms`/`vos_fps` tốt hơn lần đo 10-11. **Không** được đọc
thành "code nhanh hơn 20 %": hai lần đo cách nhau 8 ngày, khác tải máy; repo **chưa có ngưỡng nhiễu cho
`vos_ms`** giữa hai phiên (AGENTS §6 cấm so p95 giữa hai artifact). Điều được khẳng định: cùng lệnh,
cùng `image_size`/`vos_every`, `git_dirty_code false` ⇒ số **tái lập được trong khoảng 1–2 %** cho
`measured_fps` và ±7 % cho `vos_ms` (3 lần trong cùng phiên 18-11).

## Vấn đề & cách xử lý

- `mask_age_p95_ms` không có trong khối `worker_status` mà `measure_live_relay` in (nó nằm ở khoá khác
  của artifact) ⇒ bảng trên lấy số từ stdout của script, không phải từ `worker_status`. Đã ghi rõ nguồn
  từng cột để lần sau không trích nhầm chỗ.
- Ô chọn `104,308,209,287` là **ô khuôn mặt** (mặc định cũ, AGENTS §6) — chấp nhận được cho một baseline
  **thông lượng**; nó **không** nói gì về chất lượng bám (mặt luôn nằm trong khung nên `empty_runs = 0`,
  `drift_iou` cao).

## Next steps

- Tiêu chí 2 của #21 (mặc định `image_size`/`vos_every` theo thiết bị) **cần GPU thật**: phải đo trên
  Colab T4 rồi mới chọn số, theo AGENTS §6 "đo trước, hứa sau". Ticket giữ mở.
- Chưa có ngưỡng nhiễu cho `vos_ms`/`vos_fps` giữa hai phiên ⇒ mọi so sánh A/B cũ↔mới phải dùng
  `./run ab` (chạy chèn kẽ), không so hai artifact khác ngày.

## Tài liệu tham khảo

- `data/live_cpu_baseline_run{1,2,3}_2026-11-18_metrics.json`
- `data/live_gpu_device_cpu_baseline_run{1,2,3}_2026-11-10_metrics.json`
- `AGENTS.md` §6 (ngưỡng nhiễu theo ô chọn; `measured_fps` bão hoà ~29,3–29,9)
