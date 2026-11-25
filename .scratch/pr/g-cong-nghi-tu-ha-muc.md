# PR — fix(gate): cổng "nghi đổi đối tượng" tự hạ mức thay vì tắt overlay tới hết phiên

## Chuyện gì

Người dùng báo sau phiên `data/demoip_1124-125109_web.mp4` (246 frame, 57 s):

> "nếu sau 5–10 s tôi mới đưa vật vào lại khung hình, nó chỉ nghi → nghi đúng → nhưng **không focus lại**,
> chỉ nghi thôi"

Đo lại thì **đúng là lỗi hệ, không phải cảm giác**: cổng báo đúng ở f137 (ô nhảy sang **tóc người**),
rồi model **tự bám lại đúng cái thìa** ở t≈40 s — nhưng `IdentityWatch` (latch, 21-11) chỉ xoá được bằng
`r` / `c` / `reacquired`, mà re-ID đang **TẮT** (23-11 đo được nó tệ hơn: mIoU 0,4236 vs 0,7794).
⇒ **109/246 = 44,3 % phiên** chỉ còn ô nét đứt, hết phim.

## Sửa gì

`IdentityWatch` thành máy trạng thái **3 mức**:

| trạng thái | vẽ gì |
|---|---|
| `nghi` | **KHÔNG** mask, chỉ ô nét đứt (luật 21-11: ca bám sang cửa/tường cùng tông) |
| `chua_xac_minh` | **VẪN vẽ** nhưng **viền nét đứt, không tô, không quỹ đạo** + câu xin xác nhận |
| `ok` | vẽ đầy đủ (tin cậy) |

- `nghi` → `chua_xac_minh` sau **`settle_steps = 8` bước bám ổn định VÀ có mask**; cú nhảy mới ⇒ về
  `nghi`; **mask rỗng không tính là ổn định** (không hạ mức khi không có gì để tin).
- `settle_steps = 0` = tái lập **đúng** hành vi cũ (dùng để đo lại số các phiên trước 24-11).
- Áp cho **cả 3 đường**: CLI `./run demoip` (`smooth_display` + `visualizer`), `run_interactive`,
  và web worker (`live_tracking._annotate` + `LivePanel` + `status.json` + `POST /api/live/confirm`).
- Không in banner "MẤT DẤU" chồng lên "NGHI"; quỹ đạo **không** nối qua cú nhảy
  (`Visualizer.clear_trajectory()`).

## Số đo

**Replay trên CSV đã ghi** (`scripts/replay_latch_settle.py`, artifact
`data/replay_latch_settle_2026-11-24_metrics.json`, `git_dirty_code=false`) — **chỉ 22 phiên ĐO ĐƯỢC**
(4 346 frame; 17 phiên / 2 695 frame thiếu cột `mask_area` nên cổng **không thể** bật ⇒ loại khỏi mẫu số):

| luật | ẩn mask | ẩn khi CÒN mask | "chưa xác minh" |
|---|---|---|---|
| hành vi cũ (`settle 0`) | **32,67 %** | 29,71 % | 0 % |
| `settle 8` | **4,16 %** | **3,38 %** | **28,51 %** |
| `settle 12` | 5,59 % | 4,72 % | 27,08 % |

**Bằng chứng LIVE** (phiên `demoip_1124-141352`, 87 frame / 21,1 s, `loadavg 1,41`, re-ID TẮT): cổng báo
**2 lần**, mỗi lần **đúng 8 frame** ẩn (f29–36, f42–49) ⇒ `16/87 = 18,4 %`; **hành vi cũ trên chính CSV
đó = 58/87 = 66,7 %** (mất 2/3 buổi demo); replay `--settle 8` trên chính CSV ra **16 frame = trùng
khít**. `settle 8` ở nhịp VOS **4,12 bước/s** = **1,94 s**.

Ảnh tự kiểm 4 mốc: t=9,6 s "CHUA XAC MINH" (ô trên **vùng sai** — trung thực), t=11,2 s "NGHI",
**t=12,6 s ô quay lại đúng cái thìa**, t=14,5 s chỉ còn 1 banner "MẤT DẤU".

## Review độc lập (AGENTS §9.1) — 3 vòng

| vòng | phát hiện | xử lý |
|---|---|---|
| 1 | **P0**: `chua_xac_minh` **chết trong adapter API** (worker ghi, HTTP không mang ra ⇒ banner web không bao giờ hiện; e2e xanh vì mock route). Cùng lớp: `nghi_doi_tuong` **chết ở `routes._live_status` từ 21-11**. **P1-a**: HUD mời bấm `c` mà `c` không có tác dụng ở trạng thái mới. **P1-b**: số replay trộn mẫu số (đã đính chính 20,17 %→2,57 % thành 32,67 %→4,16 %) | vá đủ **6 điểm nối** + test giá trị qua HTTP; `c` xoá cả 2 trạng thái; script chia mẫu số + `git_loi` ⇒ exit 1 |
| 2 | mã đúng, **thiếu test hành vi** | 2 test hành vi (2 đường CLI) đọc `chua_xac_minh` visualizer nhận từng frame |
| 3 | **P1**: `quy_dao_sau_c` **không** chứng minh call-site `clear_trajectory` (giai đoạn `nghi` đã xoá mỗi frame ⇒ deque vốn sạch) — tôi tự kiểm bằng đột biến và reviewer **đúng** | **SENTINEL** `(30,30)` cắm ngay trước khi bấm `c`, assert nó biến mất + snapshot không rỗng; thêm đối chứng dương cho bộ đếm |

**Đột biến 6/6 bắt được**: điều kiện `c` · bỏ `watch.reset()` · xoá map `routes._live_status` · bỏ
`and not switch_warning` · xoá call-site `clear_trajectory` (2 đường) · xoá nhánh `+= 1` của bộ đếm.

## Cổng

`./run lint` sạch · **1 982 test** · `./run webtest` **102** · `npm run build` OK · **`./run e2e` PASS**
(+5 check mới: trạng thái "chưa xác minh", nút xác nhận, không hiện banner sai).

## Hạn chế đã ghi (đừng trích ngược)

1. Hạ mức ⇒ **"thấy mask" không còn đồng nghĩa "bám đúng"**: ca 21-11 (bám sang cửa/tường cùng tông) hệ
   sẽ vẽ **viền nét đứt của vùng sai**. Mọi metric đếm "có mask" như chỉ số đúng sẽ bị thổi.
2. `chua_xac_minh` **không tự hết** ngoài `c` / `r` / reacquire — nếu không ai bấm, phiên ở "viền nét
   đứt" tới hết buổi.
3. Số replay dựng lại ô từ `center/bbox_w/bbox_h` + một `frame_shape` ⇒ chỉ dùng **so hai luật trên cùng
   dữ liệu**, **không phải** số của phiên live.
4. `chua_xac_minh_n` nay có cho cả 2 đường CLI (`InteractiveSummary` + `run_info.json`), nhưng mới có
   **1 phiên live** (ticket #47 cần ≥3).
5. Hiệu năng phiên live: mean **232 ms** / p95 348 ms, `loadavg 1,41` (máy **rảnh**) ⇒ chính `--smooth`
   ăn 4,4 lõi; **không** so với 98 ms của headless, **không** trích làm "tốc độ model".

## Ticket

- Đóng: **#45** (cổng nghi = công tắc tắt vĩnh viễn khi không re-ID).
- Còn nợ: **#47** (`chua_xac_minh_n` ✔, còn ≥3 phiên live), **#48** (gom 2 cờ rời thành `che_do_ve`).

## Cách tái lập số

```bash
/home/msi/miniconda3/envs/samurai/bin/python scripts/replay_latch_settle.py \
  --glob 'data/demoip_*_metrics.csv' --settle 0,8,12 \
  --out data/replay_latch_settle_2026-11-24_metrics.json
python -m pytest tests/test_identity_guard.py tests/test_visualizer.py \
  tests/test_smooth_display.py tests/test_live_pipeline.py \
  tests/test_live_tracking.py tests/test_api_live.py tests/test_replay_latch_settle.py -q
```
