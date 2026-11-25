# 25-11-2026 — "Lag dữ vậy" + cổng báo oan khi máy chậm (bước VOS dài bất thường)

## 1. Mục tiêu

Người dùng chạy `./run demoip` (phiên `demoip_1125-084425`) và báo:

> "sao nó lag dữ vậy, đưa vật vào 1 hồi mới có bỏ đỏ"

Log: **6 frame / 10,4 s**, `mean = 2004 ms`, p95 3148 ms (bình thường **137–141 ms**), và cổng báo
"NGHI ĐỔI ĐỐI TƯỢNG" ở `f2→f3`. Phải tách **hai** vấn đề: máy chậm (môi trường) và cổng báo oan
(lỗi thiết kế bị máy chậm phơi ra).

## 2. Input

- `data/demoip_1125-084425_metrics.csv` (6 frame) + `_run_info.json` + `_web.mp4`
- `data/demoip_1125-084257_metrics.csv` (1 frame, 4083 ms — lần chạy trước đó cùng buổi)
- So sánh: `data/demoip_1124-193026_metrics.csv` (141 ms, cùng máy, cùng `image_size 192`)

## 3. Công việc đã thực hiện

### 3.1. Chẩn đoán lag: **môi trường, không phải code**

| kiểm | kết quả |
|---|---|
| `run_info.loadavg_1m` phiên 25-11 | **2,02** (không cao) |
| `run_info.live_workers_khac` | **0** (không có worker mồ côi — ca đã gặp 21-11) |
| `run_info.image_size` | **192** (đúng yêu cầu, không bị rơi về 1024) |
| `git_rev` | `fa5fd8e`, `git_dirty_code = false` |
| **Headless cùng model, cùng clip, chạy lại 15 phút sau** | **137 ms mean / 188 ms p95** (n = 15) |

⇒ Máy **bây giờ bình thường**. `loadavg` trong WSL **không thấy** tiến trình phía Windows (Windows
Update/Defender chạy lúc 8h45 là ca rất thường), mà torch lại tranh đúng số lõi vật lý đó — nên đây là
**suy đoán có bằng chứng gián tiếp** (cùng code, cùng cấu hình, 15 phút sau nhanh gấp 15 lần), **không**
phải kết luận đo được. Muốn chắc thì lần sau mở Task Manager lúc đang chậm.

### 3.2. Lỗi thật bị phơi ra: ngưỡng cổng tính **px/BƯỚC**, không phải px/giây

Cú báo ở `f3`:

| | số |
|---|---|
| `f2` bbox | `(368, 153, 469, 405)` → tâm (418,5 · 279) |
| `f3` bbox | `(115, 201, 259, 479)` → tâm (187 · 340) |
| tâm nhảy | **239,4 px** |
| bán kính cho phép | `max(0,10·800=80, 1,5·252=378)` nhưng **trần 0,25·800 = 200 px** ⇒ **200** |
| **thời gian bước** | **851 ms** ⇒ tốc độ thật **281 px/s** (tay cầm vật đi bình thường) |

⇒ Cổng báo oan **chỉ vì máy chậm**. Với `vos_every=1` và máy bị chiếm, mỗi bước dài gấp 6–20 lần ⇒
cùng một tốc độ tay luôn vượt ngưỡng. Đây đúng là lý do AGENTS từng ghi cho `theo_dt` — nhưng `theo_dt`
(với `1500 px/s × dt` **luôn bật**) đã bị bác ngày 24-11 vì làm mất ca báo đúng.

### 3.3. Luật mới: nới theo thời gian **CHỈ khi bước dài bất thường**

`src/identity_guard.py`:

- `DT_CHAM_BI_THUONG_S = 0.5` — ngưỡng "bước dài bất thường" (bình thường 77–352 ms).
- `TOC_DO_TOI_DA_PX_S = 1500.0`, `TRAN_CHAM_RATIO = 0.35`.
- `search_window_radius(..., step_seconds=None)`: nếu `step_seconds > 0,5 s` **và** người dùng không tự
  siết `max_jump_ratio` (< 0,25) ⇒ `radius = max(base, 1500 × dt)`, trần `0,35 × đường chéo`.
- `is_suspect_switch(..., step_seconds=None)`, `IdentityWatch.update(..., step_seconds=None)`.
- Ba đường runtime đo `step_seconds` bằng **đồng hồ thực** (`time.monotonic()`) giữa 2 lần đẩy cổng —
  không dùng `elapsed_ms` (ở frame nội suy LK, `elapsed_ms` là `lk_ms`, không phải độ dài bước VOS).

Vì sao **không** nới trần vô điều kiện: 24-11 đo `0,25 → 0,30` làm **mất** ca báo đúng `092343#264`
và đuôi xấu đi 146 → 159. Luật này chỉ kích hoạt ở chế độ máy chậm.

## 4. Output / Kết quả

`data/eval_gate_rules_2026-11-25_metrics.json` (`git_rev 3591f19`, `git_dirty_code = false`, 28 phiên
đọc được, nhóm chi phí 10 phiên đóng băng / 1 509 frame):

| luật | báo | ẩn | chưa xác minh | bắt ca ĐÚNG |
|---|---|---|---|---|
| `hien_tai` (trước 25-11) | 6 | 3,71 % | 4,24 % | **7/7** |
| **`cham_noi_theo_dt` (nay)** | 6 | 3,71 % | 4,24 % | **7/7** |

⇒ Trên nhóm đóng băng **y hệt** (bước của 7 ca đúng là **131–352 ms** < 500 ms ⇒ luật **không kích hoạt**).
Khác biệt nằm đúng ở phiên người dùng báo:

| phiên | `hien_tai` | `cham_noi_theo_dt` |
|---|---|---|
| `demoip_1125-084425` | `fire = [3]`, ẩn 3 frame | **`fire = []`** |
| `demoip_1125-084257` | 0 | 0 |

## 5. Vấn đề & cách xử lý

1. **Lag 2004 ms KHÔNG phải regression của code.** Cùng commit, 15 phút sau: 137 ms. Không có worker
   mồ côi, `image_size` đúng 192. Không sửa gì cho phần lag — chỉ ghi cách kiểm (Task Manager phía
   Windows, vì `loadavg` của WSL không thấy).
2. **Không được trích "máy chậm 15× vì cổng"**: hai chuyện khác nhau. Lag làm **phơi ra** lỗi ngưỡng
   px/bước; lag tự nó là môi trường.
3. **Hệ quả của luật mới với máy RẤT chậm**: bước 2 s ⇒ bán kính 280 px (trần) ⇒ vẫn bắt được cú nhảy
   thật ≥ 280 px trong 1 bước. Đây là **đánh đổi có chủ ý**: máy chậm thì mất độ nhạy cổng, đổi lấy
   không báo oan. Số `7/7` không đổi ⇒ không mất ca nào **đã biết**.
4. **`step_seconds` là ước lượng tốt hơn `latency_ms`** trong CSV: runtime dùng đồng hồ thực; script
   chấm vẫn dùng `latency_ms` (đã ghi rõ trong docstring là xấp xỉ) ⇒ số của script là **so sánh giữa
   hai luật trên cùng dữ liệu**, không phải số live.

## 6. Next steps

- [ ] **Chạy lại `./run demoip` lúc máy rảnh** — kỳ vọng ~137 ms/frame, và **không còn WARN** khi đưa
      vật ra/vào khung.
- [ ] Nếu lag lặp lại: mở **Task Manager (Windows)** lúc đó chụp lại cột CPU/Process — đó là bằng chứng
      duy nhất `loadavg` của WSL không thấy.
- [ ] Ticket đã ghi từ 24-11 (dedupe cổng theo `frame_idx` cho frame `engine.start()`) vẫn còn.
- [ ] **Tầng 2** (verified re-anchor / Cutie) cho ca trôi-dần-sang-tường — vẫn là việc > 4 h, cần plan.

## 7. Tài liệu tham khảo

- `docs/task/24-11-2026-vat-roi-khung-khong-bi-nghi.md` (luật "vật rời khung ≠ đổi đối tượng")
- `docs/plan/24-11-2026-cong-nghi-bao-oan.md` (vì sao **cấm** nới trần vô điều kiện; 7 luật bị bác)
- `src/identity_guard.py` (hằng số + docstring luật), `scripts/eval_gate_rules.py` (luật `cham_noi_theo_dt`)
