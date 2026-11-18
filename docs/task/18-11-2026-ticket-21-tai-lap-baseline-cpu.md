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
- Cây đo: **`c22c086`** (nhánh `docs/ticket-32-ra-so-p95-latency`, sau 6 PR của ngày 17–18/11:
#33,#34,#35,#36,#37 + docs) — **không phải** `main` hôm nay (`bf6382f`, có thêm PR #41): mọi số dưới
đây gắn với `c22c086` trong `git_rev` của artifact.

## Công việc đã thực hiện

1. `./run test` trên `c22c086`: **1386 passed**, 5 deselected. `./run testall` (cần checkpoint SAM 2,
   gồm 5 test `slow`): **1391 passed**, 5 warnings, 210 s. (Hai số này thuộc **cùng** cây `c22c086`;
   `main` hôm nay thêm test của PR #40/#41 nên số nhanh là 1390 — đừng trộn hai cây.)
2. Chạy lại **đúng lệnh** baseline 3 lần (10 s mỗi lần, `device=cpu`), ghi vào
   `data/live_cpu_baseline_run{1,2,3}_2026-11-18_metrics.json` + CSV từng mẫu
   (`data/drift_samples_binh1_2026-11-18_1403{06,21,36}.csv` + `.meta.json`, đúng khoá
   `drift_samples_csv` trong artifact). Điều kiện tái lập là **`git_dirty_code = false`** (và
   `git_loi = null`, `ket_qua = true`); `git_dirty` **vẫn `true`** vì chính file artifact trong `data/`
   đang được ghi — đừng đòi `git_dirty = false`.

## Output / Kết quả

| Chỉ số | 10-11 (`8501ff3`, 3 lần) | 18-11 (`c22c086`, 3 lần) |
|---|---|---|
| `measured_fps` | 29,4 · 27,5 · 29,9 | **29,93 ± 0,05** (29,9 · 30,0 · 29,9) |
| `vos_fps` | 6,1 · 3,3 · 5,0 | **8,3 ± 0,4** (8,8 · 8,0 · 8,1) |
| `vos_ms` | 122,9 · 326,9 · 132,6 | **99,5 ± 6,7** (108,6 · 92,8 · 97,1) |
| `drift_iou` (**tự nhất quán**, KHÔNG phải chất lượng bám) | 0,889 · 0,879 · 0,882 | 0,910 ± 0,002 (`pstdev`, n=3: 0,908 · 0,913 · 0,909) — **không so với 10-11** (AGENTS §6) |
| `worker_status.mask_age_p95` (ms) · `age_n` | 303,5 · 667,8 · 354,1 (không so được) | 300,9 · 301,7 · 301,3 · `age_n` 200 mỗi lần |

⇒ Đường CPU **không bị mất**. Điều được khẳng định là **định tính**: cùng lệnh, cùng bbox/`image_size`/
`vos_every`, `git_dirty_code = false`, `git_loi = null`, `ket_qua = true`, `device_worker_log = cpu` ⇒
chạy lại **cùng bậc** (FPS phát 29,93 · `vos_fps` 8,3 · `vos_ms` 99,5).

**Cấm đọc thành "nhanh hơn 10-11"**: hai lần đo cách nhau 8 ngày, khác tải máy (10-11 run2 là outlier
326,9 ms), và repo **chưa có ngưỡng nhiễu cho `vos_ms` giữa hai phiên** (AGENTS §6). Bản nháp đầu của
mình ghi "tái lập trong 1–2 % cho `measured_fps` và ±7 % cho `vos_ms`" — **sai**: `measured_fps` lệch tối
đa **0,22 %** (không phải 1–2 %, đó chỉ là bound rộng), còn `vos_ms` lệch tới **+9,15 %** so với mean
(108,6 vs 99,5) nên band ±7 % **loại chính lần đo thứ nhất**; `±` của `vos_ms` là `pstdev` 6,7 (**6,7 %**
CV), không phải "tái lập trong ±7 %". Muốn có ngưỡng thật thì phải `./run ab` / `scripts/repeatability.py`
trên cùng clip + cùng bbox.

## Vấn đề & cách xử lý

- **Tên khoá**: artifact **không có** `mask_age_p95_ms`; khoá đúng là `worker_status.mask_age_p95`
  (đơn vị ms, đi kèm `worker_status.age_n`). Dòng stdout của `measure_live_relay` **chỉ in lại đúng field
  đó** — bản nháp đầu ghi "lấy từ stdout, không phải `worker_status`" là **sai** (review bắt đúng).
  Ba artifact này có `age_n = 200` mỗi lần.
- Ô chọn `104,308,209,287` là **ô khuôn mặt** (mặc định cũ, AGENTS §6) — chấp nhận được cho một baseline
  **thông lượng**; nó **không** nói gì về chất lượng bám: mặt luôn nằm trong khung nên `empty_runs = 0`
  là **hiển nhiên**, `drift_iou` chỉ là *tự nhất quán*. Vì thế kết luận "CPU không mất đường" chỉ dựa
  trên `state = running`, `frames`, `measured_fps`, `vos_fps`, `device = cpu` — **không** dựa trên drift.

## Next steps

- Tiêu chí 2 của #21 (mặc định `image_size`/`vos_every` theo thiết bị) **cần GPU thật**: phải đo trên
  Colab T4 rồi mới chọn số, theo AGENTS §6 "đo trước, hứa sau". Ticket giữ mở.
- Chưa có ngưỡng nhiễu cho `vos_ms`/`vos_fps` giữa hai phiên ⇒ mọi so sánh A/B cũ↔mới phải dùng
  `./run ab` (chạy chèn kẽ), không so hai artifact khác ngày.

## Tài liệu tham khảo

- `data/live_cpu_baseline_run{1,2,3}_2026-11-18_metrics.json`
- `data/live_gpu_device_cpu_baseline_run{1,2,3}_2026-11-10_metrics.json`
- `AGENTS.md` §6 (ngưỡng nhiễu theo ô chọn; `measured_fps` bão hoà ~29,3–29,9)

## Review độc lập (AGENTS §9.1)

Reviewer **không đọc được nhánh** (worktree ở `main`, phiên chỉ-đọc) nên kết luận "blocked", nhưng vẫn
bắt được **2 lỗi số học + 3 lỗi trình bày** — tất cả đã sửa:

- **P2 (số sai)** `drift_iou` ghi `0,910 ± 0,000`: thật ra `pstdev` = **0,0022** (0,908 · 0,913 · 0,909);
  `±0,000` là do mình làm tròn `round(...,2)`. Nay `±0,002` + ghi rõ là **pstdev**, n=3.
- **P2 (claim không suy được)** "tái lập trong 1–2 % cho `measured_fps` và ±7 % cho `vos_ms`": sai —
  `measured_fps` lệch tối đa **0,22 %**; `vos_ms` lệch tới **+9,15 %** (108,6 vs 99,5) nên band ±7 % loại
  chính lần đo thứ nhất. Nay chỉ nói **"cùng bậc"**, kèm chỉ dẫn `./run ab`/`repeatability.py` nếu cần
  ngưỡng thật.
- **P2 (nguồn sai)** mình ghi `mask_age_p95_ms` lấy "từ stdout": artifact **không có** khoá đó, khoá đúng
  là `worker_status.mask_age_p95` và stdout **chỉ in lại cùng field**. Đã sửa tên + bỏ nhận "nguồn thứ hai".
- **P2 (diễn giải)** bảng cũ xếp `drift_iou` 10-11 vs 18-11 như thể so sánh được. Đã ghi rõ **không so
  giữa hai ngày** (AGENTS §6), `empty_runs = 0` do **ô khuôn mặt** là hiển nhiên, và kết luận "CPU không
  mất đường" chỉ dựa trên `state`/`frames`/`measured_fps`/`vos_fps`/`device`.
- **P3 (khoá provenance)** `git_dirty` **vẫn `true`** (file artifact trong `data/` đang được ghi) — điều
  kiện tái lập là **`git_dirty_code = false`**; đã ghi rõ.
- **P0 mà reviewer nêu (provenance)**: `git_rev c22c086` **không** là tổ tiên của `main` **lúc review**
  (`4a2788c`). Nay PR #41 đã merge bằng **merge commit** (`bf6382f`) ⇒
  `git merge-base --is-ancestor c22c086 main` = **0** (đã kiểm). PR #42 phải merge bằng **merge commit**
  (không squash/rebase) để giữ tính chất này; nếu squash thì phải **đo lại** trên `main` và sinh lại
  artifact, không chỉ sửa `git_rev`.
- **Kiểm bổ sung reviewer yêu cầu**: 3 artifact có `drift_samples_csv` trỏ tới
  `data/drift_samples_binh1_2026-11-18_1403*.csv` — **đã commit kèm** `.meta.json` trong cùng PR ⇒ kiểm
  lại được từng mẫu, không có link chết.
