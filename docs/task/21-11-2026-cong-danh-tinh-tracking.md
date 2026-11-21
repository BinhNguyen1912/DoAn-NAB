# Ngày 21-11-2026 — Cổng danh tính tracking (PR-1: NEO + cos, LOG-ONLY)

## 🎯 Mục tiêu
- Trả lời câu hỏi "hệ có biết mình đang bám SAI vật không?" bằng **số đo**, không bằng cảm tính.
- Bối cảnh: phiên `demoip_1121-103854` bám sang **máy lạnh trắng** ~9 s (f110–f173) mà `score` còn **tăng**
  (5,85–6,02); hai cổng đã có (nhảy tâm, re-ID) **mù** với kiểu sai này — nhảy tâm cần 200/451 px trong khi
  cú nhảy thật 114 px, và **đường web không có re-ID**.
- Ship **PR-1 LOG-ONLY**: đo `cos(mask đang bám, NEO danh tính)` mỗi frame VOS, ghi ra CSV + `status.json`,
  **không hành động gì**. Cổng thật (PR-2) chỉ mở khi có số.

## 📥 Input
- Plan theo AGENTS §9.2 (3 ý kiến độc lập + phản biện chéo): `docs/plan/21-11-2026-cong-danh-tinh-tracking.md`.
- Clip có GT sẵn: `data/binh1.mp4` (ô chai `300,275,150,410`), `data/binh2.mp4` (`330,330,150,360`).
- Máy: CPU only (Iris Xe), `image_size 192`, checkpoint SAM 2.1 tiny. Không có GPU rời (AGENTS §6).
- Artifact trước đó về ngưỡng re-ID: `docs/task/21-11-2026-veto-nhan-lai-vao-mat-va-nguong-reid.md`.

## 🔨 Công việc đã thực hiện

### 1. Plan 3 ý kiến (bắt buộc vì > 4 h)
- 3 agent độc lập (chất lượng & số đo / sản phẩm & bằng chứng / độ bền & hiệu năng) → vòng 2 phản biện chéo
  → chốt: **3/3 bác** hướng "re-prompt SAM 2 bằng bbox cũ" (không có bằng chứng nó sửa được), chọn
  **NEO danh tính + cos** làm kênh phát hiện, và **chỉ LOG** ở PR-1.

### 2. Code PR-1 (commits `9e2acfa`, `214e74b`, `9e00d9d`)
- `src/track_identity.py` (**mới**): `NeoDanhTinh` — lấy **3–5 mẫu ĐẦU** từ **MASK** (không phải bbox), qua
  cổng chất lượng `signature_quality_ok` **+ cắt dải mép khung** như `ReIdSession._collect_reference`;
  `cos = MAX(dot(neo, mask hiện tại))`; **fail-open 2 lớp**; `None` = **CHƯA ĐO**, không phải 0.
  Tự tính max-dot tại chỗ để **không** tạo import vòng `reid ⇄ track_identity`.
- `src/reid.py`: `Step.track_cos` + `Step.neo`; chấm ở nhánh TRACKING; `neo.xoa()` trong `reset()`.
- `src/live_tracking.py`: `LiveTrackStats` + `bbox_w/bbox_h/mask_area/track_cos/track_cos_n`;
  `_cap_nhat_danh_tinh()` gọi ở **CẢ HAI** đường VOS (`_after_vos` inline và `_store_vos` có luồng);
  `_VosWorker` truyền **frame màu** xuống callback (trước đó chỉ `gray` ⇒ `object_signature` lỗi im lặng).
- `src/metrics_logger.py`: CSV +4 cột ở **cuối** (`bbox_w`, `bbox_h`, `mask_area`, `track_cos`) — CSV cũ vẫn
  đọc được bằng `csv.DictReader`.
- `src/drift_samples.py`: CSV **đường LIVE** +4 cột (xem mục review P1-1 — thiếu nó thì tiêu chí không đo được).

### 3. Hai bug tự bắt trong phiên (nhờ ĐO, không nhờ đọc code)
1. Neo đặt inline trong `_after_vos` ⇒ `--vos-every 3` đi qua `_store_vos` ⇒ `track_cos = None, n = 0`
   **6/6 lần chạy**. Tách `_cap_nhat_danh_tinh()` gọi ở cả hai đường.
2. `_store_vos` chỉ nhận `gray` ⇒ `object_signature` cần BGR→HSV ⇒ lỗi im lặng, `None` vĩnh viễn.

### 4. Review độc lập (AGENTS §9.1) — agent `reviewer`, 2 vòng
- **Vòng 1**: `NOT mergeable as-is` — **3 P1 + 8 P2 + 5 P3**.
- **P1-1**: đường **live** không có CSV nào mang `track_cos` (`drift_samples.csv` thiếu cột, `_worker_telemetry`
  lọc mất khoá) ⇒ tiêu chí "`track_cos` trong CSV live" mà plan tự đặt **không thể đạt**; mọi số công bố
  trước đó là **đường CLI**.
- **P1-2**: 6/6 `run_info` ghi `git_dirty_code = true` trong khi plan lại khẳng định `false`.
- **P1-3**: log ngày (file này) **không tồn tại** dù plan trỏ tới.
- **P2 đáng chú ý**: frame `start()` bị **chấm 2 lần** (neo #1 ≡ #2 ⇒ "đủ neo" sau 1 frame); neo **không**
  lọc dải mép khung; `MIN_ANCHORS = 2` nhưng docstring/plan nói 3; neo lấy `object_signature` **2 lần/frame**
  trên đường CLI (~1,5 ms) chứ không phải "tái dùng"; **4/108 mẫu 1,0 cấu trúc** (frame so với chính nó);
  3 lần chạy **bit-identical** ⇒ "gộp n = 324" không tăng thông tin; `p05` là **quy ước phân vị thứ 4**
  trong repo; `_smooth` thay mask bằng mask **giữ** ⇒ `track_cos` mù đúng lúc model mất vật.
- **Đã sửa toàn bộ P1 + 8 P2** (commit `9e00d9d`), thêm **test giết được mutant**:
  - bỏ call `_cap_nhat_danh_tinh` ở `_store_vos` ⇒ test `vos_every=3` **đỏ** (đúng bug `214e74b`);
  - test 2 neo ⇒ `cos is None` (khoá bất biến 3 neo);
  - test dải rác sát mép **không** được làm neo;
  - test `drift_samples.csv` có 4 cột, `None` ⇒ ô **trống** (không phải 0).
- Xoá 1 assert **chết** trong `tests/test_metrics_logger.py` (`... or True`).
- **P2 cuối (mask giữ)**: `_smooth` chạy TRƯỚC khi chấm danh tính ở **cả 2 đường**; với
  `--mask-smoothing 0.5` smoother có thể giữ mask cũ ⇒ `track_cos`/`mask_area` **mù đúng lúc model mất
  vật**. Nay giữ `mask_tho` trước `_smooth` và chấm trên mask thô; test `MaskTho` giết được mutant ở
  nhánh có luồng (`vos_every=3` đỏ khi bỏ tham số `mask`).

### 5. Đo lại trên **cây SẠCH** (`git_dirty_code = false` 7/7 lần chạy)
- CLI: 3 lần × 2 clip, ô chai đúng (lần đầu tôi quên `--bbox` ⇒ ô mặc định giữa frame 78×84 ⇒ số vô nghĩa;
  phát hiện bằng cách so `bbox_w/bbox_h` giữa CSV cũ và mới).
- LIVE: `scripts/measure_live_relay.py --source data/binh1.mp4 --bbox 300,275,150,410 --vos-every 3 --seconds 45`
  (worker thật qua API, không phải CLI).

## 📤 Output / Kết quả

> Provenance: 7 lần chạy (6 CLI + 1 LIVE) đều ghi `git_rev = 9e00d9d`, `git_dirty_code = false`. Commit
> sau đó (`05dedbc`) chỉ sửa nhánh `mask_smoothing ≠ 1.0` (mặc định 1.0 = TẮT) ⇒ số đo vẫn đúng với code
> đã chạy; không đo lại để tránh "số mới trên code mới" mà không có gì thay đổi.

### Số đo (artifact `data/track_cos_2026-11-21_metrics.json`, `git_dirty_code = false`)
| Đường | clip / cửa sổ | n | median | p05 | **min** | < 0,75 |
|---|---|---|---|---|---|---|
| CLI | `binh1` (ô chai) | 106 | 0,9604 | 0,9126 | **0,8588** | **0** |
| CLI | `binh2` | 106 | 0,9267 | 0,8141 | **0,8080** | **0** |
| **LIVE** | vật trong khung `0:110` | 29 | 0,9542 | `None` (n<30) | **0,9070** | **0** |
| LIVE | sau khi vật rời khung | 211 | 0,9586 | — | 0,3115 | 18 |

- **98,2 %** frame live có `mask_area > 0` có `track_cos` (222/226) ⇒ đạt tiêu chí ≥95 % đã đặt trước.
- 3 lần chạy CLI **bit-identical** về `track_cos` (latency khác nhau 107/110 dòng) ⇒ mask/ngoại hình tái lập
  trên clip cố định (**không** suy ra "SAM 2 tất định" nói chung — AGENTS §6 vẫn đúng cho ô bao cuối).
- **θ = 0,75 chặn oan 0/241 mẫu** khi vật trong khung (CLI 212 + LIVE 29).
- 18 mẫu < 0,75 (live, sau khi vật rời khung) đều có `mask_area` **2–4 170 px** ⇒ **mask sụp**, không phải
  "bám sang vật khác". (Con số "22–3 767" ở bản log trước là **sai** — chính review vòng 2 bắt được.)

### Kết luận trung thực (quan trọng cho báo cáo)
- θ ≈ 0,75 **chứng minh được** là bắt trạng thái **mask sụp**.
- **CHƯA chứng minh** θ bắt được ca "bám sang máy lạnh": các số 0,510–0,719 của ca đó là **BOX-cos**
  (mask = cả hình chữ nhật, lẫn nền) — **không so được** với phân bố mask-cos. Đã **rút lại** câu này trong plan.
- **Chưa mở cổng PR-2**: khung cửa cùng tông cho cos **0,912** (nằm trong dải ca đúng) ⇒ kênh ngoại hình
  **không** phân biệt được cùng tông. Cần 1 clip quay đúng cảnh bằng `scripts/record_raw.py` để chấm mask-cos
  của vùng sai.

### File thay đổi
- `src/track_identity.py` — **mới**: NEO + cos, fail-open, lọc dải mép, `MIN_ANCHORS = 3`
- `src/reid.py` — `Step.track_cos`/`Step.neo`, chấm TRƯỚC khi nạp neo
- `src/live_tracking.py` — 5 khoá `LiveTrackStats`, `_cap_nhat_danh_tinh` ở cả 2 đường VOS, chống chấm 2 lần
- `src/metrics_logger.py`, `src/drift_samples.py` — 4 cột danh tính (CSV CLI + CSV live)
- `src/live_pipeline.py`, `src/smooth_display.py` — truyền `track_cos`
- `tests/test_track_identity.py` (+12), `tests/test_live_tracking.py` (+2, giết mutant), `tests/test_drift_samples.py` (+1), `tests/test_metrics_logger.py` (xoá assert chết)
- `docs/plan/21-11-2026-cong-danh-tinh-tracking.md` — đính chính số + rút lại claim AC
- `data/track_cos_2026-11-21_metrics.json`, `data/sach_*`, `data/drift_samples_binh1_2026-11-21_113612.csv`, `data/live_danhtinh_sach_2026-11-21_metrics.json`

### Kiểm
- `./run lint` xanh · `./run test` **1688 passed**, 5 deselected (117 s).
- Review độc lập **vòng 1**: `NOT mergeable` (3 P1 + 8 P2) → đã sửa hết.
- Review độc lập **vòng 2**: `NOT mergeable` (1 P1 mới + 3 P2 + 5 P3) → P1 (dòng CSV trộn hai thế hệ
  VOS: **18/364 dòng** `empty=1` mà `mask_area = 59 333`) **đã sửa + có test giết mutant**; 3 P2 đã sửa
  (whitelist script đo, `read_samples`/`thong_ke_danh_tinh`, số `22–3 767` → **2–4 170**); P3 đã sửa
  (assert `bat_buoc` cho 5 khoá, xoá 12 file `data/neo_*` có provenance bẩn, ký hiệu neo nay đối xứng với
  `cos`), riêng "reset neo khi chọn lại đối tượng" ghi Next steps (chưa có đường chọn lại giữa phiên).
- Sau khi sửa P1: đo lại đường live ⇒ **0 dòng mâu thuẫn** (`thong_ke_danh_tinh`), 99,2 % frame có mask có
  `track_cos`.

## 🔬 Phiên live thật `demoip_1121-121732` — ca sai có thật, và nó BÁC PR-2
Người dùng chạy `./run demoip --image-size 192` (webcam qua relay). Đo từ CSV + xem ảnh từng pha:

| Pha | Frame | Chuyện gì (đã xem ảnh) | `track_cos` |
|---|---|---|---|
| A | f0–86 | bám **đúng** điện thoại be (ảnh `p3_f005.jpg`) | med 0,887 |
| – | f89–125 | điện thoại ra khỏi khung (mask rỗng 37 frame) | — |
| B | f126–175 | bám đúng lại | med 0,955 |
| **C** | **f179–243** | **bám sang CỬA/TƯỜNG be cùng tông**; điện thoại nằm NGOÀI ô (ảnh `p3_f180.jpg`, `p3_f200.jpg`) | **med 0,854** (0,752–0,887) |
| D | f264–277 | bám đúng lại | med 0,899 |

- Cổng **nhảy ô bao** đã báo ĐÚNG ở f178 ("nghi ngờ ĐỔI ĐỐI TƯỢNG … bấm r"), **nhưng chỉ in ra** rồi hệ vẫn
  vẽ mask sai 65 frame ⇒ tín hiệu phát hiện đã có, thiếu **hành động**.
- So 2 lớp (145 frame đúng vs 65 frame sai): θ = 0,75 bắt **0/65** vùng sai; θ = 0,85 bắt 43 % nhưng
  **chặn oan 15 %** frame đúng; θ = 0,90 chặn oan **46 %**. ⇒ **không tồn tại θ tách được** ⇒
  **BÁC PR-2 dạng cổng cos** (bằng số, không phải "chưa đo"). Artifact:
  `data/track_cos_vung_sai_2026-11-21_metrics.json`. **Không cần quay clip mới.**
- Chỉ số phiên: 278 frame · **158 ms mean / 199 ms p95** · 20 FPS hiển thị · mất dấu **42/278 (15 %)** ·
  `state`: tracking 235, reacquiring 40, lost 3 · `reacquired` 3 · `vetoed` 0.

## ✅ Việc tiếp theo đã làm: cổng nhảy **CÓ NHỚ** ⇒ ẩn overlay + phím `c`
Sau khi đo được "cổng nhảy báo đúng nhưng chỉ in ra", đã làm (đúng thứ tự: **đo trước, sửa sau**):

1. **Đo chi phí báo** (`data/jump_gate_replay_2026-11-21_metrics.json`, replay 18 phiên = **2 973 frame**):
   cổng nhảy (`|Δtâm| > 0,25 × đường chéo` = 200 px) báo **21 lần = 0,71 %** số frame ⇒ ẩn khi báo là RẺ.
2. **Đo chi phí latch** (`data/identity_latch_chi_phi_2026-11-21_metrics.json`): nếu ẩn từ lần báo đầu tới
   hết phiên và **không ai bấm gì** thì **1 033/2 973 frame (34,7 %)** bị ẩn; **5/18 phiên không bao giờ
   bị ẩn** (phiên sạch), 13/18 phiên có ≥ 1 lần báo. Trong dùng thật, người dùng bấm `r`/`c` trong ~1–2 s.
3. **Code**: `src/identity_guard.IdentityWatch` (latch + `reset()`); `visualizer.render` **không vẽ**
   mask/ô/quỹ đạo khi nghi (y như mất dấu) + banner `NGHI DOI TUONG — r: chon lai | c: van dung, tiep tuc`;
   nối vào **cả 2 vòng demo** (`live_pipeline.run_interactive` + `smooth_display.muc_smooth`); phím `c`
   = xác nhận vẫn đúng (không chọn lại ô); `r` = chọn lại (xoá nghi); chọn ô mới ⇒ xoá nghi.
4. **Đo được**: CSV thêm cột cuối `nghi_doi_tuong` (0/1/trống) ⇒ biết đã ẩn frame nào, soi lại được.
   KHÔNG che số: `_record_from` vẫn log bbox/mask THẬT của frame đó.
5. **Kiểm**: `IdentityWatch` giữ trạng thái sau cú nhảy và không coi ô rỗng là "đổi danh tính" (3 test);
   test end-to-end ẩn overlay + ghi cờ; test `c` không gọi `reset`; **mutant "bỏ latch" làm test ĐỎ**.
   `./run lint` xanh · `./run test` **1698 passed**, 5 deselected.

### Đã bổ sung vào ĐƯỜNG WEB (cùng ngày, theo yêu cầu)
1. **Worker** (`src/live_tracking.py`): `IdentityWatch` latch + `bam = "nghi_doi_tuong"` (lý do `o_nhay`);
   `_annotate` **không vẽ** mask/ô/quỹ đạo và HUD thêm `NGHI DOI TUONG (o nhay) — chon lai hoac XAC NHAN`;
   ô VOS của chính frame này so với **ô tốt gần nhất**; chọn ô mới (`start()` lần nữa) ⇒ xoá nghi.
2. **IPC** `confirm.json`: API ghi file, worker đọc + **tự xoá** (lệnh chỉ có hiệu lực 1 lần); dùng file vì
   worker là tiến trình riêng và hợp đồng sẵn có (`bbox.json`/`status.json`/`frame.jpg`) — không thêm socket.
3. **API**: `POST /api/live/confirm` → `LiveStreamService.confirm()` → adapter ghi `confirm.json`;
   nguồn không hỗ trợ ⇒ `SourceUnavailable` (400), không im lặng. `status.json`/DTO thêm
   `nghi_doi_tuong` + `nghi_doi_tuong_n`; mô tả `bam` có thêm giá trị mới.
4. **Web**: `LiveStatus` type + `confirmLive()`; `bamLine()` có nhánh riêng nói **2 lựa chọn**;
   `LivePanel` hiện banner `role="alert"` + nút **"Vẫn đúng, tiếp tục"** (gọi `/api/live/confirm`).
5. **Kiểm**: Python **1703 passed** (5 deselected) · `./run webtest` **80 passed** · `npm run build` OK ·
   **`./run e2e` PASS** với **3 phép kiểm mới** trên Chrome thật (banner + nút + bấm nút gọi đúng endpoint).
   Test Python khoá: latch bật ⇒ `bam/status.json` = `nghi_doi_tuong` + `nghi_doi_tuong_n > 0`; `confirm.json`
   ⇒ xoá nghi + file bị xoá; 3 test API (ghi file · nguồn không hỗ trợ ⇒ 400 · chưa có phiên ⇒ 4xx).

## 🐞 Vấn đề gặp phải & cách xử lý
- **P1 review vòng 2 (nghiêm trọng nhất)**: 4 cột danh tính trong `drift_samples.csv` đọc từ `self._stats`
  = lần VOS **gần nhất**, trong khi `empty`/`bbox` là của dòng đó ⇒ **18/364 dòng** mâu thuẫn
  (`empty=1` + `mask_area = 59 333`), tức chính tiêu chí `mask_area == 0 ⇔ empty == 1` của plan **fail**.
  Sửa: `_cap_nhat_danh_tinh` **trả về** `(bbox_w, bbox_h, mask_area, cos)`; đảo thứ tự để nó chạy **trước**
  `_measure_drift`; `identity` đi kèm tuple `_pending_drift` (9 phần tử) và `csv_row`; `_log_drift_sample`
  **không** đọc `self._stats` nữa. Bằng chứng: file CSV **lỗi** `data/drift_samples_binh1_2026-11-21_113612.csv`
  (giữ lại làm bằng chứng) vs file **đúng** `…_115421.csv` (0 dòng mâu thuẫn, đo bằng
  `src.drift_samples.thong_ke_danh_tinh`).
- **Neo không chạy ở đường có luồng** (`--vos-every 3`): đo ra `track_cos = None` 6/6 lần. Sửa: tách hàm,
  gọi ở **cả** `_after_vos` và `_store_vos`, cộng test giết mutant.
- **`object_signature` lỗi im lặng** trên `gray` ⇒ `None` vĩnh viễn. Sửa: truyền frame màu xuống callback.
- **Lần đo đầu vô nghĩa vì quên `--bbox`** (ô mặc định 78×84 giữa frame): phát hiện bằng cách so `bbox_w/h`
  giữa CSV cũ/mới, không phải bằng cách tin vào con số median.
- **Lệch hệ thống do quy ước mask**: nghi neo ký bằng mask đã cắt mép trong khi `cos` ký bằng mask đầy đủ ⇒
  đo 2 biến thể, số **giống hệt** ⇒ bác giả thuyết, nguyên nhân thật là `--bbox` thiếu. (Ghi lại vì đã
  suýt "sửa" một thứ không hỏng.)
- **Xoá nhầm artifact đã commit** (`rm -f data/sach_*` quét cả `data/sach_chai_binh1_1vong_metrics.json`) ⇒
  `git checkout --` phục hồi; đã kiểm `git status` sạch trước khi commit.

## 📌 Việc cần làm tiếp (Next steps)
- [x] ~~PR-2 (cổng dựa trên `track_cos`)~~ — **BÁC bằng số đo** (phiên `demoip_1121-121732`): dải cos vùng
  sai 0,752–0,989 nằm trong dải đúng ⇒ không θ nào tách được. **Không cần clip mới.**
- [x] **Hành động theo cổng NHẢY** — xong: `IdentityWatch` latch + ẩn overlay + `c`/`r`, cột CSV
  `nghi_doi_tuong`. Đã đo trước (0,71 % lần báo; 34,7 % frame bị ẩn nếu không ai bấm gì).
- [ ] **P2 còn nợ**: `object_signature` tính **2 lần/frame** trên đường CLI (`_collect_reference` + neo) — tái dùng `sig` để tiết kiệm ~1,5 ms; đo A/B wall-clock 3 lần chèn kẽ (CSV `latency_ms` = thời gian engine, **không** thấy chi phí này).
- [ ] **P2 còn nợ**: `post_ms` bao gồm chi phí neo ở đường có luồng nhưng **không** ở đường inline ⇒ `mask_age_total_ms` giữa 2 đường không so trực tiếp được; cần tách `identity_ms` riêng vào `status.json`.
- [ ] **P3**: `track_cos` gắn frame VOS còn `bbox` trong `status.json` là frame hiển thị ⇒ lệch thế hệ; thêm `vos_frame_idx` (đã defer ở V2 của plan).
- [ ] **P3**: `_auto_recover`/`_abandon_reacquire`/`_reacquire` trả `Step` **không** có `track_cos` — đúng những frame cần hiệu chuẩn θ nhất.
- [ ] `neo_n`/`track_cos_none_n` vào `status.json` để phân biệt "chưa đủ neo" với "mask rỗng mọi lần".
- [ ] **Reset neo + `_danh_tinh_frame_idx` khi `start()` lần hai** (chọn lại đối tượng giữa phiên — yêu cầu
  sản phẩm AGENTS §1, hiện chưa có đường nào làm việc này nên chưa phải bug; P3 review vòng 2).
- [ ] Đã xoá 12 file `data/neo_*` (provenance bẩn, chứa `min 0,7836` đã rút lại) — nếu cần đối chiếu lịch
  sử thì xem commit `214e74b`.

## 📚 Tài liệu tham khảo
- `docs/plan/21-11-2026-cong-danh-tinh-tracking.md` — plan 3 ý kiến + phản biện + đính chính số.
- `docs/task/21-11-2026-veto-nhan-lai-vao-mat-va-nguong-reid.md` — ngưỡng re-ID, veto khuôn mặt.
- `docs/demo-clip-va-o-chon.md` — ô chọn đúng cho `binh1`/`binh2`.
- AGENTS §6 (ngưỡng nhiễu, `git_dirty_code`, `p05` một cửa), §9.1 (review độc lập), §9.2 (plan 3 ý kiến).
