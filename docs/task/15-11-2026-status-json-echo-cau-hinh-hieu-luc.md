# Ngày 15-11-2026 — `status.json` echo cấu hình hiệu lực + tự kiểm "yêu cầu == hiệu lực"

> Nhánh `feat/cau-hinh-hieu-luc`, tách từ `main` `bc9f127`. Đây là **việc đầu tiên** trong mục
> "Next steps" của `docs/task/14-11-2026-nam-viec-con-lai-cua-plan.md` (phát hiện của góc "độ bền &
> hiệu năng", P2): *"`status.json` echo cấu hình hiệu lực + test 'yêu cầu == hiệu lực' để artifact tự
> kiểm"*.

## 🎯 Mục tiêu
- Trả lời được câu **"phiên này chạy cấu hình nào"** bằng file `status.json`, cả lúc đang nạp model
  (20–240 s) lẫn khi đã chạy, thay vì phải tin tham số CLI hay đọc `worker.log`.
- Chặn "xanh giả": `--image-size 192` là **yêu cầu**; nếu hydra override không được áp thì model
  chạy 1024 mà không báo gì ⇒ số đo bị gán cho một cấu hình model **không hề chạy**.
- Hai script sinh artifact số đo (`./run bangcau`, `./run ab`) phải **từ chối** lần chạy không kiểm
  được cấu hình, thay vì lặng lẽ đưa số vào bảng.

## 📥 Input
- `AGENTS.md` §6 (`None` = CHƯA ĐO; ngưỡng nhiễu; "drift ≠ độ chính xác"), §9.1 (review độc lập).
- `docs/task/14-11-2026-nam-viec-con-lai-cua-plan.md` — mục Next steps, dòng đầu.
- Code: `src/live_tracking.py` (`LiveTrackConfig`, `LiveTrackStats`, `status_payload`,
  `_write_mask_manifest`), `src/tracker_engine.py` (`build_overrides`, predictor SAM 2),
  `tools/live_worker.py` (hai tác giả của `status.json`), `scripts/bang_cau_hinh.py`,
  `scripts/ab_test.py`, `scripts/measure_live_relay.py`.
- Dữ liệu: `data/binh1.mp4` + ô chai đúng `288,287,431,734` (`docs/demo-clip-va-o-chon.md`),
  checkpoint `sam2.1_hiera_tiny.pt`.

## 🔨 Công việc đã thực hiện

### 1. Phân biệt "yêu cầu" với "hiệu lực" ở đúng chỗ
- `src/tracker_engine.py`: property **`image_size_hieu_luc`** đọc `self._predictor.image_size` — giá
  trị mà `_to_input_tensor` **thật sự** dùng để resize. (`self.image_size` chỉ là giá trị đã truyền
  vào `build_overrides`, tức **yêu cầu**.)
- `src/live_tracking.py`: ba hàm thuần có test riêng
  - `cau_hinh_yeu_cau(...)` → dict cấu hình **yêu cầu** (`source`, `image_size_yeu_cau`, `vos_every`,
    `display_fps`, `mask_smoothing`, `device`, `mask_age_dinh_nghia`), trong đó
    `image_size_hieu_luc = None` + `image_size_kiem_duoc = False`;
  - `cau_hinh_hieu_luc(yeu_cau, engine)` → ghép `image_size_hieu_luc` từ engine + cờ
    `image_size_kiem_duoc`;
  - `so_khop_cau_hinh(cau_hinh)` → danh sách khoá **lệch** (hiện chỉ `image_size`).
- Hằng `DINH_NGHIA_TUOI_MASK`: `mask_age_total_ms = queue + pre + vos + post + age` vs
  `mask_age_cu_ms = age + vos` (định nghĩa cũ), kèm ghi chú "pha chưa đo tính 0; chỉ đo ở đường LK ⇒
  `vos_every=1` thì `age_n=0`". Lý do: repo có **hai** định nghĩa tuổi mask, người trích số không
  phải đi đọc mã để biết đang dùng cái nào.
- `LiveTrackStats.cau_hinh` / `cau_hinh_lech` + `status_payload` echo **nguyên khối**: mọi người đọc
  `status.json` (API, watchdog, script đo) thấy cùng một bộ khoá.

### 2. Ba trạng thái, không được lẫn
| Trạng thái | Dấu hiệu | Đọc đúng là |
|---|---|---|
| Khớp | `image_size_kiem_duoc = true`, `image_size_hieu_luc == image_size_yeu_cau` | "đã kiểm và khớp" |
| Lệch | `cau_hinh_lech = ["image_size"]` | "model chạy khác yêu cầu" ⇒ số không dùng được |
| **Chưa kiểm được** | `image_size_hieu_luc = null`, `image_size_kiem_duoc = false` | "CHƯA ĐO", **cấm** đọc thành khớp |

Giai đoạn `loading` (chưa nạp model) và worker bản cũ đều rơi vào hàng thứ ba — cố ý: thà nói "chưa
kiểm được" còn hơn khẳng định "khớp" trên bằng chứng không có.

### 3. Ghi cấu hình ngay từ giai đoạn nạp model
`tools/live_worker.py::_write_loading(..., cau_hinh=...)` — trước đây file `status.json` trong 20–240 s
nạp model chỉ có `device`; nay có cả cấu hình **định** chạy (nguồn, `image_size` yêu cầu, `vos_every`,
`display_fps`, `mask_smoothing`). Nhánh lỗi tên thiết bị cũng ghi khối này.

### 4. Artifact tự kiểm cấu hình
- `scripts/bang_cau_hinh.py::_run_once` (dùng chung cho `./run bangcau` và `./run ab`): lần chạy bị
  coi là **LỖI** khi (a) `cau_hinh_lech != []`, (b) `image_size_hieu_luc` khác `--sizes`/`--image-size`
  đã truyền, (c) `image_size_hieu_luc = None` (chưa kiểm được), (d) worker bản cũ không echo. Dòng lỗi
  nêu cả giá trị yêu cầu và giá trị model **thật sự** chạy.
- Artifact: mỗi dòng bảng có `cau_hinh` + `image_size_hieu_luc_da_thay` (danh sách giá trị hiệu lực
  khác nhau đã thấy; `None` khi mọi lần đều chưa kiểm được — không phải `[null]`).
- `scripts/measure_live_relay.py::_worker_telemetry`: whitelist thêm `cau_hinh`/`cau_hinh_lech` ⇒
  artifact "camera thật chạy được" cũng có bằng chứng cấu hình.
- `_write_mask_manifest` (manifest cạnh mask dump) ghi thêm `image_size_hieu_luc` — trước chỉ có
  `image_size` (yêu cầu), `null` khi dùng mặc định ⇒ không phân biệt được "1024 của model" với "chưa biết".
- `./run bangcau` nay thoát mã 1 khi **mọi** lần chạy đều lỗi (trước đó in bảng toàn `—` rồi trả 0).

## 📤 Output / Kết quả

**Đo thật trên máy này** (checkpoint tiny, CPU; `git_rev 58bb629`, chạy trên cây sạch):

| ca chạy | `image_size_yeu_cau` | `image_size_hieu_luc` | `cau_hinh_lech` |
|---|---|---|---|
| `--image-size 192 --vos-every 3 --stop-after-frames 6` (`data/binh1.mp4`) | 192 | **192** | `[]` |
| **không** truyền `--image-size --vos-every 1 --stop-after-frames 1` | `null` | **1024** | `[]` |

Hàng thứ hai là bằng chứng quan trọng: giá trị hiệu lực là **giá trị model thật sự dùng** (1024 của
`model_cfg`), không phải chép lại tham số CLI (`null`). Đó chính là thứ trước đây không kiểm được.

**Diễn tập đường TỪ CHỐI** (fault injection: tạm cho `build_overrides()` trả `[]`, rồi
`./run bangcau --sizes 192 --every 3 --lan 2 --frames 5`):
```
[192/3] lần 1/2: LỖI: cấu hình yêu cầu ≠ hiệu lực ở ['image_size']: yêu cầu image_size=192
        (worker ghi 192), model chạy 1024 — None = KHÔNG kiểm được (...)
[192/3] lần 2/2: LỖI: ...
| 192 | 3 | — | — | — | — | — | 2 | 2 |
[bang] KHÔNG ĐO ĐƯỢC lần nào (2/2 lần lỗi) ⇒ thất bại; xem `loi` trong artifact
```
⇒ lệch **không** vào bảng, thoát mã 1. Injection đã revert (`git diff src/tracker_engine.py` rỗng).

**Kiểm tra tự động:** `./run lint` xanh · `./run test` **1181 passed, 5 deselected** (thêm 23 test
trong `tests/test_cau_hinh_hieu_luc.py` + 1 khoá allowlist `status.json`).

**File thay đổi:**
- `src/tracker_engine.py` — property `image_size_hieu_luc`.
- `src/live_tracking.py` — `DINH_NGHIA_TUOI_MASK`, `cau_hinh_yeu_cau`/`cau_hinh_hieu_luc`/
  `so_khop_cau_hinh`, 2 field mới của `LiveTrackStats`, echo trong `status_payload`, cảnh báo trong
  `LiveTrackingSession.__init__`, `image_size_hieu_luc` trong manifest mask.
- `tools/live_worker.py` — `_write_loading(..., cau_hinh=...)` + ghi ở nhánh lỗi thiết bị.
- `scripts/bang_cau_hinh.py` — tự kiểm cấu hình trong `_run_once`, echo vào dòng, `_cau_hinh_chung`,
  thoát mã 1 khi mọi lần lỗi.
- `scripts/measure_live_relay.py` — `cau_hinh`/`cau_hinh_lech` vào `worker_status`.
- `tests/test_cau_hinh_hieu_luc.py` (mới, 23 test) · `tests/test_live_tracking.py` (allowlist khoá).
- `AGENTS.md` §6 — 1 bullet kết luận đã đo (192→192, null→1024, ba trạng thái, artifact cũ chưa có echo).
- `docs/task/14-11-2026-nam-viec-con-lai-cua-plan.md` — tick dòng Next steps tương ứng.
- Ticket mới: `#27` (chạy lại `./run bangcau` để artifact đã commit có echo), `#28` (`cau_hinh_lech`
  lên API/HUD), `#29` (ẩn userinfo của `source` trước khi echo).

## 🐞 Vấn đề gặp phải & cách xử lý
- **`cau_hinh_lech == []` mang hai nghĩa** ("khớp" và "chưa kiểm được"). Review độc lập bắt đúng (P2)
  ⇒ thêm cờ tường minh `image_size_kiem_duoc` thay vì bắt người đọc suy từ `image_size_hieu_luc`.
- **P1 thật do review bắt:** `_run_once` phiên bản đầu **chỉ tin** `cau_hinh_lech` do worker tự khai ⇒
  worker bản cũ (không echo) hoặc predictor không khai báo `image_size` lọt vào bảng. Nay so với chính
  tham số `--sizes`; `None` = chưa kiểm được ⇒ từ chối. Đã diễn tập bằng fault injection (ở trên).
- **"Chạy được" ≠ "không phá hành vi cũ":** thêm 2 khoá vào `status.json` làm đỏ test allowlist
  (`tests/test_live_tracking.py`) — đúng thiết kế của test đó (thêm khoá phải khai), đã cập nhật.
- **Không sửa code trong lúc đo** (bài học 14-11): mọi lần chạy thật ở trên làm với cây sạch; fault
  injection được revert ngay và kiểm bằng `git diff` rỗng trước khi commit.

### Review độc lập (§9.1) — kết quả và xử lý
Agent `reviewer` (read-only) review nhánh `feat/cau-hinh-hieu-luc` so với `main`. Kết luận: **không có
P0, mergeable sau khi vá 1 P1**. Đã xử lý:

| Mức | Phát hiện | Xử lý |
|---|---|---|
| **P1** | `_run_once` tin `cau_hinh_lech` do worker tự khai: (a) predictor không khai báo `image_size` ⇒ hiệu lực `None` ⇒ `so_khop_cau_hinh` trả `[]` ⇒ dòng **vẫn vào bảng** mà md không có cột nào lộ `null`; (b) nếu `TrackerEngine` sau này không nhận `image_size` thì `yeu_cau = None` ⇒ `lech = []` ⇒ bảng "192" có thể chứa số của model 1024 | So trực tiếp với tham số `size` của lần chạy (`None` = chưa kiểm được ⇒ LỖI) + 3 test (hiệu lực `None`, worker bản cũ, echo tự khai `yeu_cau = null`). Đã diễn tập thật bằng fault injection |
| **P2** | `cau_hinh_lech == []` mang hai nghĩa | Thêm `image_size_kiem_duoc` (bool) vào dict echo + ghim trong test |
| **P2** | `image_size_hieu_luc_da_thay = [null]` đọc như một giá trị thật | `None` khi mọi lần chưa kiểm được + test |
| **P3** | Docstring `_write_loading` nói "KHÔNG có `image_size_hieu_luc`" nhưng khoá **có mặt** = `None` | Sửa docstring ("có mặt nhưng luôn `None`, `kiem_duoc = False`) |
| **P3** | `sorted(..., key=(v is None, v))` giòn nếu một lần chạy báo chuỗi | `key` chịu được kiểu lạ (`-1` cho không phải int) |
| **P3** | `DINH_NGHIA_TUOI_MASK` đọc như 5 pha luôn được cộng | Thêm "pha chưa đo tính 0; chỉ đo ở đường LK ⇒ `vos_every=1` thì `age_n=0`" + test |
| **P3** | `./run bangcau` trả 0 dù 27/27 lần lỗi | Thoát mã 1 khi mọi lần lỗi (giống `ab_test`) |
| **P3** | `cau_hinh.source` là chuỗi thô ⇒ `rtsp://user:pass@…` vào artifact | **Không sửa trong PR này** → ticket **#29** (mẫu này đã có từ trước ở `meta.nguon`) |
| **P3** | Chưa có `cau_hinh_lech` ở `/api/live/status` + HUD | **Tách ticket #28** (phải sửa adapter + DTO + `web/src/api.ts` + HUD + e2e) |
| **P3** | Artifact 14-11 **chưa có** `cau_hinh` ⇒ bảng đang trích vẫn chưa tự kiểm | Ticket **#27** + ghi rõ trong log/AGENTS: "**từ nay** artifact tự kiểm được" |
| **"đã kiểm, không phải lỗi"** | Race/aliasing `cau_hinh` (chỉ gán 1 lần trong `__init__`, giá trị bất biến); loading không có khoảnh khắc mất `cau_hinh`; `--check` của `bangcau` không dùng `cau_hinh` nên artifact cũ vẫn khớp; API đọc theo tên nên thêm khoá không vỡ; `image_size_hieu_luc` đúng là giá trị model dùng (`sam2_base.py` lấy từ config) | Đồng ý cả 5 |

Review nói rõ **không tự chạy được** `./run lint`/`./run test`/2 lần chạy worker (phiên reviewer không
có shell) ⇒ các số đó là của phiên này, reviewer không tái lập.

**§9.2 plan 3 ý kiến:** không áp dụng — việc nhỏ (≤ ~1 ngày, không đổi kiến trúc/hợp đồng API), đúng
mục "Next steps" đã có tiêu chí từ plan 14-11.

## 📌 Việc cần làm tiếp (Next steps)
- [x] **#27** Chạy lại `./run bangcau` trên cây sạch để artifact **đã commit** có `cau_hinh`, rồi sinh
      lại `docs/bang-cau-hinh.md` + `docs/so-lieu-bao-cao.md` — **xong trong phiên này** (xem mục bổ sung
      dưới). `./run ab` **chưa** chạy lại (đã ghi trong ticket, để lần đo A/B sau).
- [x] **mIoU trên video THẬT** — xong dạng **hộp bao**: `docs/task/15-11-2026-gt-hop-bao-va-mask-ngoai-gt.md`
      (IoU 0,6464 · tràn 3,9 % · n=12). Còn nợ: GT **silhouette** để có mIoU phân đoạn.
- [ ] **#28** Đưa cờ lệch lên `/api/live/status` + HUD (`role="alert"`) để người vận hành thấy.
- [ ] **#29** Ẩn userinfo của `source` trước khi echo vào `status.json`/artifact.
- [ ] Cân nhắc đưa `cau_hinh` vào `worker/artifacts.py` cho **job upload** (đường batch hiện chưa có
      echo cấu hình; chưa đo nên chưa làm).

## ➕ Bổ sung sau khi merge — #27 xong: bảng cấu hình MỚI đã tự kiểm cấu hình

Nhánh đã merge vào `main` (`96b0c3e`, không tạo được PR: máy này **không có `gh` CLI lẫn token GitHub**).
Sau merge, chạy lại bảng cấu hình trên **cây sạch** để artifact đã commit có echo cấu hình:

- Lệnh: `./run bangcau --bbox 288,287,431,734 --sizes 192,256,320 --every 2,3,6 --lan 3 --frames 60`
  (đúng ô chai trong `docs/demo-clip-va-o-chon.md`).
- Artifact: `data/bang_cau_hinh_2026-11-15_metrics.json` — `git_rev 96b0c3e`, `git_dirty_code false`,
  **27/27 lần chạy không lỗi**, mỗi dòng có `cau_hinh.image_size_hieu_luc_da_thay` = **một giá trị duy nhất**
  đúng bằng `image_size` của dòng đó (192/256/320), `image_size_kiem_duoc = true`.
- `docs/bang-cau-hinh.md` + `docs/so-lieu-bao-cao.md` sinh lại từ artifact mới (REGISTRY trỏ file mới).

**Số 15-11 (mean ± std, 3 lần, 59 mẫu tuổi mask mỗi lần):**

| image_size | vos_every | FPS phát | Nhịp mask | vos_ms | tuổi mask p95 |
|---|---|---|---|---|---|
| 192 | 2 | 29,6 ± 0,26 | 7,2 ± 1,31 | 120,83 ± 26,87 | 390,17 ± 111,31 |
| 192 | 3 | 29,67 ± 0,32 | 7,4 ± 1,11 | 100,77 ± 14,0 | 373,57 ± 97,85 |
| 192 | 6 | 29,8 ± 0,1 | 5,17 ± 0,06 | 105,3 ± 10,91 | 303,57 ± 1,44 |
| 256 | 3 | 29,83 ± 0,06 | 4,77 ± 0,12 | 187,8 ± 6,93 | 447,6 ± 18,34 |
| 320 | 3 | 29,57 ± 0,49 | 3,2 ± 0,2 | 262,3 ± 12,9 | 656,53 ± 65,09 |
| 320 | 6 | 29,8 ± 0 | 3,43 ± 0,06 | 295,2 ± 26,53 | 707,17 ± 32,42 |

⇒ Kết luận **giữ nguyên**: chọn **192** cho demo (mask gần **gấp đôi** 320; p95 373–390 ms vs 656–707 ms).

**Phát hiện khi làm #27 (đã ghi vào AGENTS §6) — p95 KHÔNG so được giữa hai phiên:**

| phiên | 192/3 nhịp mask | 192/3 p95 | 320/3 p95 | nguồn |
|---|---|---|---|---|
| 14-11 | 7,57 ± 0,15 | 315,8 ± 16,36 | 637,43 ± 34,91 | `data/bang_cau_hinh_2026-11-14_metrics.json` |
| 15-11 (A) | 7,4 ± 1,11 | **373,57 ± 97,85** | 656,53 ± 65,09 | `data/bang_cau_hinh_2026-11-15_metrics.json` |
| 15-11 (B, lặp lại 2 cấu hình) | 7,77 ± 0,74 | **362,43 ± 59,52** | 637,27 ± 68,82 | `data/bang_cau_hinh_2026-11-15_lan2_192va320_every3_metrics.json` |

- Cùng cấu hình, cùng commit: p95 chênh **~50–60 ms** giữa 14-11 và 15-11, và **±97,9** ở một phiên ⇒
  dùng ± của phiên 14-11 (±16,4) để so số 15-11 là **sai**. Chỉ so **trong cùng một lần chạy** (`./run ab`).
- 192/3 vs 192/6 ở 15-11 chênh 70 ms < `±` 97,9 ⇒ **“không phân biệt được”** (14-11 xếp ngược chiều)
  ⇒ đúng kết luận cũ: **`vos_every` không phải nút điều khiển độ tươi của mask**.
- 192 vs 320 thì chênh ~280 ms >> mọi `±` đo được (kể cả phiên nhiễu nhất) ⇒ "192 tươi hơn hẳn" **bền**.

Artifact 14-11 **vẫn giữ** (là bằng chứng lịch sử, các log 14-11 trỏ tới) nhưng REGISTRY + AGENTS nay trỏ
`2026-11-15`; ghi rõ rằng bảng 14-11 **không** tự kiểm được cấu hình.

## 📚 Tài liệu tham khảo
- `docs/task/14-11-2026-nam-viec-con-lai-cua-plan.md` — nguồn của việc này (Next steps + góc "độ bền").
- `docs/task/12-11-2026-ticket-21-thiet-bi-live-xuyen-chuoi-api-hud.md` — tiền lệ: thêm `device` vào
  `status.json` để số đo không bị trích mà thiếu ngữ cảnh.
- `docs/bang-cau-hinh.md`, `docs/so-lieu-bao-cao.md` — nơi số được trích (và là lý do phải tự kiểm).
- `AGENTS.md` §6 — bẫy `0/None`, "ngưỡng nhiễu theo ô chọn", "artifact phải có provenance".
