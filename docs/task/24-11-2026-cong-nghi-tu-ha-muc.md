# Ngày 24-11-2026 — Cổng "nghi đổi đối tượng" tự hạ mức (hết cảnh "chỉ nghi thôi")

## 🎯 Mục tiêu
Sửa đúng khiếu nại của người dùng sau phiên `data/demoip_1124-125109_web.mp4`:
> "nếu sau 5–10 s tôi mới đưa vật vào lại khung hình, nó chỉ nghi → nghi đúng → nhưng **không focus
> lại**, chỉ nghi thôi"

Cụ thể: (A) cổng nghi phải **tự hạ mức** khi đường bám đã ổn định lại (không ẩn tới hết phiên),
(B) bỏ banner "MẤT DẤU" in chồng lên banner "NGHI", và **tag backup** phiên bản demo này.

## 📥 Input
- Phiên live của người dùng: `data/demoip_1124-125109_web.mp4` + `_metrics.csv` + `_run_info.json`
  (`git_rev 4c8c074`, 246 frame, 57,4 s, `image_size 192`, re-ID TẮT).
- `AGENTS.md` §6 (bullet 21-11 về `IdentityWatch` latch, bullet 23-11 "cổng từng là công tắc tắt
  vĩnh viễn khi không có re-ID").
- `src/identity_guard.py`, `src/visualizer.py`, `src/smooth_display.py`, `src/live_pipeline.py`,
  `src/live_tracking.py`.

## 🔨 Công việc đã thực hiện

### 1. Phân tích phiên bằng SỐ + ẢNH (không bằng cảm giác)

Đo từ `_metrics.csv` + `_run_info.json`:

| chỉ số | giá trị | đọc thế nào |
|---|---|---|
| 246 frame / 57,4 s wall | video 57,2 s ⇒ tỉ lệ **0,997** | bản ghi đúng thời gian |
| mean **223 ms** / p95 **353 ms** | 4,49 lần model/giây | **loadavg 4,74**, CPU 439 % ⇒ máy đang bận; cùng code lúc rảnh (loadavg 1,89) đo 142 ms ⇒ **không trích 223 ms làm số công bố** |
| hiển thị **18,9 FPS** | LK lấp phần giữa | đúng thiết kế (mask ~4,5 Hz) |
| mất dấu **43/246 = 17,5 %**, 8 đoạn (dài nhất 11 frame) | — | phần lớn là lúc người dùng **cất vật khỏi khung** ⇒ không phải "model mất dấu" |
| **`nghi_doi_tuong` = 109/246 = 44,3 %** | liên tục **f137 → f245** | nửa sau video không có mask |

Ba mốc kiểm bằng ảnh (`data/tmp_an/s33|s40|s47|s54.jpg`):

| thời điểm | ô nét đứt ở đâu | kết luận |
|---|---|---|
| t≈**33 s** (f137) | **tóc/đầu người**, cái thìa trắng ở bên trái | cổng báo **ĐÚNG** |
| t≈**40 s** | **đã về đúng cái thìa** nhưng vẫn in "NGHI ĐỔI ĐỐI TƯỢNG" | **đúng ca người dùng nói** |
| t≈**47 s** | vật ngoài khung ⇒ **2 banner chồng nhau** (NGHI + MẤT DẤU) | lỗi UI |
| t≈**54 s** | ô trên **trần trống** (mask bịa) | may là không vẽ |

### 2. Nguyên nhân (đọc từ code, không suy đoán)
`watch.reset()` chỉ có **3 chỗ gọi**: nhánh `reacquired` (cần re-ID → đang TẮT), phím `r`, phím `c`
(`src/smooth_display.py:428,494,509`; `src/live_pipeline.py:382,408,421,451`). Không có đường tự xoá
⇒ **một lần nghi = tắt overlay tới hết phiên**. Phiên này là bằng chứng mạnh nhất: model **đã tự bám
lại đúng vật** mà người xem vẫn thấy "NGHI".

### 3. Sửa: `IdentityWatch` thành máy trạng thái 3 mức
`src/identity_guard.py`:
- `nghi` — vừa có cú nhảy vô lý ⇒ **KHÔNG vẽ mask**, chỉ ô nét đứt (giữ nguyên luật 21-11).
- `chua_xac_minh` — sau **`settle_steps = 8`** bước bám ổn định **và có mask** ⇒ **VẪN vẽ** nhưng kiểu
  chưa xác minh (viền nét đứt, không tô, không quỹ đạo) + câu xin xác nhận.
- `ok` — `r` / `c` / reacquire.
- Cú nhảy mới trong `chua_xac_minh` ⇒ về `nghi`; mask rỗng ⇒ **không** đếm bước ổn định.
- `update()` vẫn trả **bool** (`watch.nghi`) để không phá `switch = watch.update(...) or switch`.
- `settle_steps=0` tái lập **đúng hành vi cũ** (dùng để đo lại số của phiên trước 24-11).

Vẽ (`src/visualizer.py`): thêm `chua_xac_minh=` — mask chỉ **viền contour** (`_ve_vien_mask`),
ô **nét đứt** + nhãn "CHUA XAC MINH", **không quỹ đạo**, câu "CHUA XAC MINH — c: van dung, tin cay |
r: chon lai"; và **không in banner MẤT DẤU khi đang NGHI**.

Đường web giữ **cùng luật**: `src/live_tracking.py` (`_Stats.chua_xac_minh/_n`, `_annotate` vẽ viền
nét đứt, HUD nói rõ), `src/live_pipeline.py` (truyền `co_mask`), `web/src/{api.ts,live.ts}` +
`LivePanel.tsx` (banner "CHƯA XÁC MINH" + nút "Vẫn đúng, tiếp tục").

### 4. Đo lại trên chính các phiên đã ghi
`scripts/replay_latch_settle.py` (mới) — replay `IdentityWatch` trên CSV, **không model**:

```
22 phiên ĐO ĐƯỢC / 4 346 frame  (bỏ qua 17 phiên / 2 695 frame thiếu cột `mask_area`)
hành vi CŨ     | bật 14 lần | ẨN 1420 frame (32,67 %) — còn mask 1291 (29,71 %) | CHƯA XÁC MINH    0
settle 8 bước  | bật 18 lần | ẨN  181 frame ( 4,16 %) — còn mask  147 ( 3,38 %) | CHƯA XÁC MINH 1239 (28,51 %)
settle 12 bước | bật 18 lần | ẨN  243 frame ( 5,59 %) — còn mask  205 ( 4,72 %) | CHƯA XÁC MINH 1177 (27,08 %)
```
Riêng phiên của người dùng (`demoip_1124-125109`, n = 246): **ẩn 44,3 % → 10,6 %** (frame còn mask:
38,2 % → 8,5 %), thêm **33,7 %** frame "chưa xác minh". Artifact:
`data/replay_latch_settle_2026-11-24_metrics.json`.

**ĐÍNH CHÍNH (review độc lập 24-11, P1-b)**: bản đầu tôi công bố **20,17 % → 2,57 %** — SAI mẫu số: nó
cộng cả **17 phiên thiếu cột `mask_area`**, ở đó ô dựng lại là rỗng nên cổng **không thể** bật. Số
đúng là **32,67 % → 4,16 %** trên 22 phiên đo được. Script nay in `so_phien_do_duoc` và thoát 1 khi
không có phiên nào đo được hoặc `git_rev` không đọc được.

Ảnh so 3 kiểu vẽ (`data/tmp_an/so_sanh_3_kieu.jpg`): tin cậy = mask **tô cam** + ô liền; chưa xác minh
= **viền mảnh** + ô nét đứt + nhãn; nghi = ô nét đứt, **không mask**.

### 5. Backup
`git tag -a demo-ok-24-11` trên `4c8c074` (đúng rev của phiên demo, trước khi sửa).

## 📤 Output / Kết quả
- Cổng nghi **không còn là công tắc tắt vĩnh viễn**: sau ~1,3–1,8 s bám ổn định, hệ vẫn hiện vùng
  đang bám (kiểu chưa xác minh) thay vì im lặng 44 % phiên.
- Có script **tái lập được** chi phí ẩn overlay trên CSV (`scripts/replay_latch_settle.py`), có
  provenance (`git_rev`, `git_dirty_code`, `lenh`, `do_luc`, `frame_shape`).
- Kiểm tra: `./run lint` sạch · **1 980 test** · `./run webtest` **102** · `npm run build` OK ·
  `./run e2e` **PASS** (thêm 4 check cho trạng thái "chưa xác minh").
- File thay đổi:
  - `src/identity_guard.py` — máy trạng thái 3 mức (`TRANG_THAI_*`, `settle_steps`, `chua_xac_minh`)
  - `src/visualizer.py` — `chua_xac_minh=` trong `render`/`update`, `_ve_vien_mask`, bỏ banner chồng
  - `src/smooth_display.py` — truyền `co_mask` + `chua_xac_minh` (đường `./run demoip`)
  - `src/live_pipeline.py` — truyền `co_mask`; `src/live_tracking.py` — trạng thái + kiểu vẽ web
  - `web/src/api.ts`, `web/src/live.ts`, `web/src/components/LivePanel.tsx` — khoá + banner web
  - `scripts/replay_latch_settle.py` — đo chi phí ẩn overlay (mới)
  - `tests/test_identity_guard.py`, `tests/test_visualizer.py`, `tests/test_smooth_display.py`,
    `tests/test_live_tracking.py`, `tests/test_replay_latch_settle.py`, `web/src/live.test.ts`,
    `scripts/e2e_web.js` — test/bằng chứng
  - `AGENTS.md` §6 — bullet kết luận (cấm hạ mức thành "tin cậy", cấm đếm bước khi mask rỗng)
  - `data/replay_latch_settle_2026-11-24_metrics.json` — artifact số

### 6. Review độc lập (AGENTS §9.1) — và 3 lỗi THẬT nó bắt được

Reviewer độc lập verdict **"chưa mergeable"**. Đã xác nhận + vá:

| mức | lỗi | bằng chứng | đã sửa |
|---|---|---|---|
| **P0** | `chua_xac_minh` **chết trong adapter API** — worker ghi `status.json` nhưng `GET /api/live/status` không mang ra ⇒ banner + nút trên web **không bao giờ hiện**; e2e vẫn xanh vì nó mock route | `grep chua_xac_minh src/api` = **0 dòng** | vá đủ **6 chỗ** (`LiveTelemetry`, `LiveStatus`, `telemetry()`, `live.status()`, `LiveStatusResponse`, `routes._live_status`) + test khẳng định **GIÁ TRỊ** qua HTTP |
| **P0-b** | cùng lớp: `nghi_doi_tuong` (+`_n`) **cũng chết** ở `routes._live_status` từ **21-11** — allowlist xanh vì nó chỉ so **TÊN** khoá của schema | `routes.py` không map 2 field đó | map lại + test `nghi_doi_tuong is True` |
| **P1-a** | HUD **mời bấm `c`** nhưng `c` chỉ có tác dụng ở `nghi` ⇒ ở `chua_xac_minh` bấm **không có gì xảy ra** = kẹt tới hết phiên | `if key == CONTINUE_KEY and watch.nghi:` (2 file) | `(watch.nghi or watch.chua_xac_minh)` + 2 test hành vi (CLI `smooth_display` và `run_interactive`, đọc `chua_xac_minh` mà visualizer nhận ở từng frame) + sửa 2 test cũ index theo chuỗi |
| **P1-b** | số replay **trộn mẫu số** (P1-b ở trên) | 17 phiên thiếu cột | đo lại, đính chính AGENTS + log |
| **P2** | `chua_xac_minh` không bị xoá khi mất bằng chứng (metric bị thổi); `_check_confirm` không xoá `chua_xac_minh*`; **quỹ đạo nối qua cú nhảy** (đường tím xuyên khung trong video demo) | code + test | vá cả 3 + `Visualizer.clear_trajectory()` |
| **P3** | `_ve_vien_mask` vẽ mask khác cỡ frame ở toạ độ sai (im lặng); `settle_steps` âm không cảnh báo; git hỏng ⇒ artifact trông "tái lập được" | code | guard shape + kẹp 0 + `git_loi` ⇒ exit 1 |

### 7. Review vòng 2 — 3 lỗi TEST (mã đúng, bằng chứng chưa đủ)

Reviewer vòng 2 kết luận "chưa mergeable **vì test**, không vì mã": 4 vá P0/P1-a/P1-b/P2 "có thật, đúng
chỗ, không tạo lỗi mới", nhưng thiếu test hành vi. Đã bổ sung và **kiểm bằng ĐỘT BIẾN** (sửa mã cho
sai rồi xem test có đỏ):

| mục | đột biến thử | kết quả |
|---|---|---|
| P1-a (2 test hành vi mới: `run_smooth_display` + `run_interactive`) | trả điều kiện về `watch.nghi` | **2/2 ĐỎ** ✔ |
| P1-a (cùng 2 test) | giữ điều kiện, **bỏ `watch.reset()`** | **2/2 ĐỎ** ✔ |
| P0 (test qua HTTP) | xoá 2 dòng map trong `routes._live_status` | **ĐỎ** ✔ |
| P2 (test banner) | bỏ `and not switch_warning` | **ĐỎ** ✔ |

Ngoài ra đã sửa: test banner trước đó **vô nghĩa** (`consecutive_lost = 0` ⇒ banner không bao giờ được
vẽ kể cả khi bỏ điều kiện) → nay dùng đúng ca bug `consecutive_lost = 3` + `switch_warning=True`; assert
`chua_xac_minh_n` trước đó cũng vô nghĩa (gọi hàm không tăng bộ đếm) → nay đi qua
`_update_stats_locked`; thêm test guard `mask.shape` (bỏ guard ⇒ `drawContours` được gọi ⇒ đỏ) kèm đối
chứng mask đúng cỡ; thay 2 docstring còn trích con số **đã rút** (20,17 %/2,57 %) bằng số đúng.

### 8. Bằng chứng LIVE đầu tiên (phiên `demoip_1124-141352`, 87 frame / 21,1 s, `git_rev e18b953`)

| chỉ số | giá trị | đọc thế nào |
|---|---|---|
| video / wall | 631 frame @30 = **21,03 s** vs **21,11 s** ⇒ tỉ lệ **0,996** | bản ghi đúng thời gian |
| `nghi_doi_tuong` | **16/87 = 18,4 %**, hai đoạn **đúng 8 frame** (f29–36, f42–49) | đúng `settle_steps = 8` |
| hành vi CŨ trên cùng CSV | **58/87 = 66,7 %** ẩn (từ f29 tới hết) | phiên này code cũ sẽ mất **2/3** demo |
| replay `--settle 8` trên chính CSV | **16 frame** ẩn | **trùng khít** số live ⇒ mô hình replay đúng |
| `settle 8` ở nhịp VOS 4,12 bước/s | **1,94 s** | phải nói kèm nhịp VOS, không chỉ "1,3–1,8 s" |
| mean / p95 | **232 / 348 ms**, hiển thị 19,3 FPS | `loadavg 1,41` (máy RẢNH) mà vẫn 232 ms vì `--smooth` ăn 4,4 lõi; headless cùng clip = 98 ms ⇒ **không so hai đường** |
| mất dấu | 8/87 = 9,2 % (đoạn 56–60, 62, 83–84) | phần lớn là vật ra khỏi khung |

Kiểm bằng ảnh (4 mốc): t=9,6 s **"CHUA XAC MINH"** với ô trên vùng SAI (đúng ca 21-11 — hệ vẽ nhưng
nói thật là chưa xác minh); t=11,2 s **"NGHI"** (không mask); **t=12,6 s ô quay lại ĐÚNG cái thìa**;
t=14,5 s chỉ còn **1 banner "MẤT DẤU"** (hết cảnh 2 banner chồng nhau). ⇒ Đúng khiếu nại ban đầu
"chỉ nghi thôi, không focus lại": nay sau ~1,9 s hệ hiện lại vùng đang bám.

### 9. Review vòng 3 — P1 là **lỗi bằng chứng thật** (tôi đã tự kiểm bằng đột biến)

Reviewer vòng 3 chỉ ra `quy_dao_sau_c` **không** chứng minh call-site `clear_trajectory` ở nhánh `c`:
giai đoạn `nghi` đã xoá quỹ đạo mỗi frame nên deque vốn đã sạch trước khi `c` được bấm. **Tôi đã thử
đột biến và reviewer đúng**: xoá call-site ⇒ test vẫn XANH.

Đã sửa bằng **SENTINEL**: cắm một điểm "vùng CŨ" `(30, 30)` vào `viz._trajectory` **ngay trước** khi
bấm `c`, rồi assert điểm đó **biến mất** và snapshot **không rỗng** (có điểm của vùng mới). Làm cho cả
2 đường CLI, và thêm **đối chứng dương** cho bộ đếm `chua_xac_minh_n`.

Bảng đột biến đầy đủ (6/6 bắt được):

| # | đột biến | test phải đỏ | kết quả |
|---|---|---|---|
| 1 | điều kiện `c` về `watch.nghi` | 2 test hành vi `c` | ✔ |
| 2 | bỏ `watch.reset()` ở nhánh `c` | 2 test hành vi `c` | ✔ |
| 3 | xoá 2 dòng map `routes._live_status` | test HTTP | ✔ |
| 4 | bỏ `and not switch_warning` | test banner | ✔ |
| 5 | xoá call-site `clear_trajectory` (`smooth_display`) | test quỹ đạo sentinel | ✔ |
| 6 | xoá nhánh `+= 1` của `chua_xac_minh_n` | đối chứng dương bộ đếm | ✔ |

## 🐞 Vấn đề gặp phải & cách xử lý
- **Test hành vi đầu tiên của tôi ĐO SAI**: engine giả trả kết quả tức thời ⇒ luồng suy luận chạy
  trước hàng trăm nghìn bước, mỗi lần render chỉ thấy **kết quả CUỐI** (bỏ qua cú nhảy) ⇒ test báo
  "cổng nhảy KHÔNG bật". Sửa bằng `time.sleep(0.05)` trong `process()` cho chậm hơn nhịp vẽ — đúng
  bài học "engine tức thời làm test đo nhầm chỗ".
- Ảnh so sánh lấy từ `_web.mp4` (đã cháy HUD) ⇒ HUD bị vẽ đè. Đã cắt phần HUD khi xuất ảnh; ghi rõ
  để không ai đọc nhầm chữ nhoè là lỗi mới.
- `status.json` thêm 2 khoá ⇒ test allowlist `test_status_duoc_ghi_moi_frame` đỏ (đúng thiết kế):
  đã khai báo `chua_xac_minh`, `chua_xac_minh_n` vào `bat_buoc`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Chạy lại **một phiên live thật** (`./run demoip`) để xác nhận trên webcam: kỳ vọng ô/mask
      quay lại sau ~1,5 s thay vì mất tới hết phiên (số hiện có là **replay**, không phải live).
- [ ] Đo trên phiên live xem `chua_xac_minh` có bị "đứng" vĩnh viễn (không ai bấm `c`/`r`) không —
      nếu có thì cân nhắc nhắc lại phím trên HUD mỗi ~10 s.
- [ ] Chọn ô chọn **ôm sát vật**: `f0` của phiên này = 95×356 px từ y=123 **xuống đáy khung** ⇒ gồm cả
      tay + nền, là lý do gốc khiến model trôi sang tóc ở t≈30 s (chưa sửa được bằng code).
- [x] Review vòng 2 trên phần vừa vá: xác nhận mã đúng, chỉ thiếu bằng chứng test → đã bổ sung
      (mục 7) và **kiểm bằng đột biến** (4/4 đột biến làm test đỏ).
- [x] **Bằng chứng live #1** (mục 8): 2 lần cổng báo, mỗi lần đúng 8 frame ẩn (16/87 = 18,4 % so với
      66,7 % của hành vi cũ); replay `--settle 8` trên chính CSV ra đúng 16 frame.
- [ ] **Ticket #47** — còn: thêm `chua_xac_minh_n` cho đường CLI + **≥3 phiên** live (mới có 1).
- [ ] **Ticket #48** — gom 2 cờ rời (`switch_warning` + `chua_xac_minh`) thành một `che_do_ve` để
      điểm nối không thể nửa vời (P3).
- [ ] `frame_shape` của replay dùng một hằng cho mọi phiên (`run_info.json` không lưu kích thước khung)
      ⇒ các phiên 1104/1105 (nhóm thiếu `mask_area`) chưa đối chứng được.

## 📚 Tài liệu tham khảo
- `AGENTS.md` §6 — bullet 21-11 (latch), 23-11 (latch = công tắc tắt khi không re-ID), 24-11 (mới).
- `docs/task/21-11-2026-cong-nghi-doi-tuong-latch.md` (lý do phải có latch), `docs/task/23-11-2026-*`
  (A/B bác re-ID).
- Code: `src/identity_guard.py`, `src/visualizer.py`, `src/live_tracking.py`.
