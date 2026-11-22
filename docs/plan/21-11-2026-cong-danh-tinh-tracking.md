# Plan 21-11-2026 — Cổng DANH TÍNH trên đường tracking (vật cùng màu nền)

> Plan theo `AGENTS.md` §9.2: 3 ý kiến độc lập (vòng 1) + 1 vòng phản biện chéo (vòng 2) rồi mới chốt.
> Log thực thi: `docs/task/21-11-2026-cong-danh-tinh-tracking.md` (đã tạo sau review P1-3).

## 🎯 Câu hỏi cần quyết

Hệ hay **bám sang vùng nền cùng màu** (phiên thật 21-11: **remote máy lạnh TRẮNG** trên nền **tường be
+ máy lạnh trắng** ⇒ ô trượt sang **máy lạnh ~9 s**, f110–f173). Làm gì để (a) **phát hiện** kiểu sai
này, (b) **không** phá đường demo khoẻ — trong **1 ngày**, máy CPU không GPU, mọi kết luận phải có số
trên artifact (`git_dirty_code = false`)?

Ràng buộc không được vi phạm:
- Không "sửa" bằng cách đổi vật/dán băng dính (đó là mẹo demo, không phải sửa kỹ thuật).
- Không hứa "bám đúng" khi chưa có **mIoU mask vs GT** (AGENTS §6).
- `drift_iou`/`stability` **không** phải thước đo độ chính xác.
- Không thêm chi phí làm `mean_latency_ms` tăng > 2 ms (nền 139 ms @192).

## 🧭 Ba góc nhìn (vòng 1 — độc lập, không biết nhau)

### A. Chất lượng & số đo
- Gốc lỗi: **ký ức bị thay bằng vật sai** — `_collect_reference` append mẫu **mỗi frame TRACKING**
  (`src/reid.py:478`), `deque(maxlen=8)` ⇒ **8 frame ≈ 0,4 s** là "ký ức" đã là khung cửa/máy lạnh ⇒
  remote quay lại cũng không nhận ra (đúng 66 frame cuối phiên).
- Đề xuất: giữ **neo** 3–5 mẫu ĐẦU; mỗi frame TRACKING chấm `cos(neo, sig(mask))`; `cos < θ` **3 frame
  liền** ⇒ cổng; chỉ append refs khi `cos ≥ θ`; `_match_object` chấm với neo. **Bắt buộc** đo phân bố
  cos trên frame ĐÚNG trước khi chốt θ. Clip mới quay sạch + GT ≥8 frame sau lúc trôi.
- Bác: re-prompt bằng bbox mask ("đã là hành vi hiện tại"), nới `ncc_min` 0,6–0,7 (mất ≥5 ca đúng),
  `obj_threshold > 0,90` (khung cửa 0,912 > ca đúng thấp nhất 0,7696).

### B. Sản phẩm & bằng chứng bảo vệ
- Việc trước: **ghi bằng chứng** — hiện CSV **không có** `bbox_w/h/mask_area`, `track_cos` **không tồn
  tại** trong `src/` (grep 0 hit); `reid_score = -1` ở mọi frame tracking = "chưa hỏi", không phải "đã
  chấm"; `score` còn **tăng** lên 5,85–6,02 khi bám máy lạnh ⇒ không artifact nào trả lời được "frame
  nào bám máy lạnh".
- `bam = no_evidence` chỉ bật khi **mask rỗng** (`src/live_tracking.py:1740-1780`) ⇒ 9 s bám máy lạnh
  vẫn vẽ như `tracking` bình thường.
- Việc: thêm cột; mở rộng mIoU lên **n ≥ 30** (`docs/gt/b1` có 9 png nhưng manifest chấm 7 ⇒ 2 frame
  miễn phí); trang "kiểu sai đã gặp + hệ phản ứng + cái chưa sửa".

### C. Độ bền & hiệu năng
- Đường sinh lỗi **không có LK** (`run_smooth_display` không dùng `LkBoxTracker`) ⇒ đừng tinh chỉnh LK.
- Hai báo động hiện có **im lặng, có số**: cú nhảy f109→f110 = **114 px**, trong khi
  `identity_guard.is_suspect_switch` cần **200 px** và `reid._is_suspicious_jump` cần **451 px**
  (1,5 × đường chéo ô 301 px).
- Cổng phải **đánh dấu**, không `_auto_recover()` (tốn 2× `engine.start` 210–280 ms; vùng code từng có
  bug 3 lần `reacquired` liên tiếp f172/176/180). Cổng đặt trong `reid.py` là **cổng mù** với đường web
  (`src/live_tracking.py` **không** import reid).

## ⚔️ Tranh chấp (vòng 2 — phản biện chéo)

| Điểm tranh chấp | A (số đo) | B (sản phẩm) | C (độ bền) | **Chốt** |
|---|---|---|---|---|
| Cổng đặt ở đâu | `reid.py` (đường CLI) | bất kỳ, miễn có số | **module dùng chung**, đo trên **live** | **`src/track_identity.py` dùng cho CẢ `live_tracking.py` và `reid.py`**; nghiệm thu phải kiểm field có trong `status.json` của worker live (chống "xanh trong test, mù trên web") |
| Neo vs ký ức rolling | neo 3–5 mẫu đầu | — | neo + refs chỉ append khi `cos ≥ θ` | **Neo 3–5 sig đầu (từ MASK, qua `signature_quality_ok`), fail-open <2 neo** |
| θ bằng bao nhiêu | đo phân bố trước | — | 0,75 (2 mẫu) **rủi ro**; cửa sổ bbox (0,719; 0,912) ⇒ 0,82 | **Chưa chốt — ship LOG-ONLY.** Đo `track_cos` ≥200 mẫu/clip × 3 clip × 3 lần rồi mới chọn; cần `p05(đúng) − p95(sai) ≥ 0,10` |
| Bật cổng thì làm gì | `_auto_recover` | ẩn ô (tệ cho demo) | **đánh dấu**, không recover | **Trạng thái thứ ba `suspect`: bỏ mask fill + quỹ đạo, GIỮ hộp + nhãn "nghi bám sai"** (trung thực, không mất cả đoạn demo) |
| cos trên mask ≠ cos trên bbox | chưa nói | — | **0,959/0,912/0,51–0,719 là cos trên Ô ỨNG VIÊN (mask = cả hình chữ nhật, lẫn nền)** | **Không dùng các số đó để chốt θ**; mask-vs-mask sạch nền nên cos hệ thống **cao hơn** ⇒ máy lạnh có thể vượt 0,75 ⇒ càng phải đo |
| Chi phí | — | — | `object_signature` **đã chạy** mỗi frame TRACKING ở `reid.py` (median 1,47 ms) ⇒ tái dùng sig | **Chỉ chấm thêm `best_match` (<0,05 ms) trên đường CLI; đường live thêm ~1,5 ms/frame VOS** (đo lại, nghiệm thu ≤ 2 ms) |
| Clip mới + GT 16–20 frame | bắt buộc | nên có | **BỎ** (≥3 h **người tô**) | **BỎ khỏi plan này** → ticket cho người; dùng `binh1`/`binh2` (GT có sẵn) + `scripts/record_raw.py` khi người dùng quay lại ca máy lạnh |
| `--record-raw` / V5 | — | — | **BỎ** — `scripts/record_raw.py` đã có | **BỎ** |
| V2 (snapshot `StampedResult`) | — | — | P2 (chưa có bằng chứng lệch thế hệ trong CSV live) | **BỎ khỏi PR này** → ticket P2 |

## ✅ Quyết định

- **Chọn:** **PR-1 LOG-ONLY (~4 h)** — module dùng chung `src/track_identity.py` (neo + `cos`, **không
  hành động**), nối vào **cả** `src/live_tracking.py` (đường web, ưu tiên đo) và `src/reid.py` (CLI);
  thêm `track_cos`, `bbox_w`, `bbox_h`, `mask_area` vào CSV + `status.json`; test; rồi **đo 3 lần ×
  `binh1` + `binh2`** và công bố `median/p05/min` của `track_cos`.
  **PR-2 chỉ mở khi** phân bố tách được (`p05(đúng) − p95(sai) ≥ 0,10`): bật cổng `suspect` 3 frame
  liền, có cờ tắt, fail-open tự tắt nếu 30 mẫu đầu không mẫu nào ≥ θ.
- **Vì sao:** cả 3 ý kiến độc lập đều bác hướng "re-prompt/đổi ngưỡng"? Không — chính xác hơn:
  (a) hướng re-prompt **vô hiệu** vì `TrackingResult.bbox` **chính là** bbox của mask
  (`src/tracker_engine.py:239`) và re-anchor **đang bị tắt khi bật re-ID** ⇒ không có gì mới để bật;
  (b) **không có tín hiệu nào đo được** kiểu sai này hôm nay (`track_cos` không tồn tại, `score` tăng
  trên vật sai, 2 cổng nhảy cần 200/451 px trong khi cú nhảy thật là 114 px) ⇒ mọi θ chọn bây giờ là
  **bịa**; (c) cổng đặt trong `reid.py` sẽ **mù** với đường web (không có re-ID) — đúng lỗi "xanh trong
  test, im lặng trên sân khấu" mà repo đã gặp.
- **Bác (để sau không mở lại):**
  1. **Re-prompt SAM 2 bằng bbox suy từ mask mỗi N frame** — đã là hành vi hiện tại (bbox = mask bbox);
     nếu mask đang sai thì nó **hợp thức hoá cái sai**; còn `set_bbox` **xoá sạch** mẫu re-ID
     (`src/smooth_display.py:175`) và `_stamped = None` làm UI nhảy về chế độ kéo chuột mỗi N frame.
  2. **Nâng `ncc_min` / `obj_threshold`** — số đã có: 17 ca đúng có NCC 0,4147–0,7412 và cosine
     0,7696–0,9754; khung cửa **0,912/0,612** ⇒ nâng ngưỡng **mất ca đúng trước khi bắt được ca sai**.
  3. **Bộ nhớ âm (negative memory)** — không cứu được **lần sai đầu** (f59), và không có dữ liệu để
     chứng minh "sai lặp lại".
  4. **Tinh chỉnh LK (`max_mad`/`lk_scale`)** — đường lỗi không có LK; đã A/B 3 lần "không phân biệt
     được" (#38/#40).
  5. **Đổi `image_size` 256/320** — chậm 1,8–2,5× và `drift_iou` **giảm**.
  6. **Replay `data/demoip_1121-103854.mp4`** — HUD + ô đỏ + quỹ đạo **đã cháy vào pixel**; `_web.mp4`
     hỏng `moov atom` ⇒ không dùng làm input.
- **Tiêu chí nghiệm thu (có SỐ):**
  - [ ] `track_cos`, `bbox_w`, `bbox_h`, `mask_area` có trong **CSV live** và **`status.json`** của
        worker; `mask_area == 0 ⇔ empty == 1`; ô trống (`""`) = **chưa đo**, không phải `0`.
  - [ ] `track_cos` xuất hiện ở **≥ 95 %** frame VOS của một phiên live thật (đếm từ CSV).
  - [ ] 3 lần × {`binh1`, `binh2`} @192: công bố **median / p05 / min** của `track_cos`; artifact có
        `git_rev`, `git_dirty_code = false`, `lenh`, `do_luc`.
  - [ ] `mean_latency_ms` tăng **≤ 2 ms** so với trước khi thêm (3 lần chèn kẽ).
  - [ ] **0 thay đổi hành vi**: cổng không hành động; test cũ xanh; đường **không re-ID** có
        `track_cos = ""` và `track_cos_n == 0` (không gọi `object_signature` lần nào).

## 📊 KẾT QUẢ ĐO PR-1 (đo lại 21-11 trên **cây SẠCH**, `git_dirty_code = false` 7/7 lần chạy)

> **ĐÍNH CHÍNH (review độc lập P1-2 + P2):** bảng đầu tiên của mục này ghi `n = 324`(**gộp 3 lần chạy**) và
> `min = 0,7836`, kèm dòng "artifact có `git_dirty_code = false`" — **cả hai đều sai**:
> (a) 6/6 `run_info` ghi `git_dirty_code = true` (đo trên cây bẩn), (b) 3 lần chạy **bit-identical** về
> `track_cos` nên gộp lại **không tăng thông tin** (n thật = 106/clip), (c) 4/108 mẫu mỗi lần chạy là **1,0
> cấu trúc** (frame được so với chính nó vì `thu()` nạp neo TRƯỚC `cos()`), (d) `p05` tính bằng quy ước
> phân vị thứ 4 trong repo. Đã sửa cả 4 (xem "Đã sửa sau review") và **đo lại toàn bộ**.

Artifact: **`data/track_cos_2026-11-21_metrics.json`** (per-run + per-clip, có `git_dirty_code`, ghi rõ
`vi_sao_sinh_lai`) · CSV CLI: `data/sach_<clip>_lan{1,2,3}_metrics.csv` · CSV **đường LIVE**:
`data/drift_samples_binh1_2026-11-21_113612.csv` (+ `.meta.json` có `git_rev`/`git_dirty_code`).

### Đường CLI (`tools/run_live.py`, 3 lần/clip, ô chai)
| clip | ô chọn | n (1 lần chạy) | median | p05 | **min** | < 0,75 | 3 lần giống nhau |
|---|---|---|---|---|---|---|---|
| `binh1` | `300,275,150,410` | **106** | 0,9604 | 0,9126 | **0,8588** | **0** | ✅ (bit-identical) |
| `binh2` | `330,330,150,360` | **106** | 0,9267 | 0,8141 | **0,8080** | **0** | ✅ |

### Đường LIVE (`scripts/measure_live_relay.py`, worker thật qua API, 45 s)
| cửa sổ | n | median | **min** | < 0,75 |
|---|---|---|---|---|
| **vật trong khung `0:110`** | 29 | 0,9542 | **0,9070** | **0** |
| sau khi vật rời khung | 211 | 0,9586 | 0,3115 | 18 |

> Đo lại sau **P1 review vòng 2**: bản trước ghi n=26/min 0,8901 và **18/364 dòng CSV mâu thuẫn**
> (`empty=1` mà `mask_area = 59 333`) vì 4 cột danh tính đọc từ `self._stats` (lần VOS **gần nhất**).
> Nay `identity` đi kèm dòng CSV + `pending` 9 phần tử ⇒ **0 dòng mâu thuẫn**, đo bằng
> `src.drift_samples.thong_ke_danh_tinh()` (`n_dong_mau_thuan_mask_area_vs_empty = 0`).

- **Tiêu chí "CSV live có `track_cos`" nay ĐO ĐƯỢC** (trước review là **không**: `drift_samples.csv` không
  có cột, whitelist trong script đo lọc mất khoá): **99,2 %** frame có `mask_area > 0` có `track_cos`
  (240/242) ⇒ đạt ngưỡng ≥95 % đã đặt. `p05` của cửa sổ trong-khung = `None` vì n = 29 < 30 (đúng ngưỡng
  công bố, **không** phải p05 = 0). `worker_status` trong artifact **có** 5 khoá danh tính
  (`track_cos = 0,9919`, `track_cos_n = 240`).
- **Toàn bộ 18 mẫu < 0,75 ở cửa sổ sau-khi-rời-khung có `mask_area` 2–4 170 px** ⇒ đó là **mask sụp**
  (vật đã ra khỏi khung), **không** phải "bám sang vật khác". (Con số "22–3 767" ở bản trước là **sai** —
  P2 review vòng 2 bắt được khi đối chiếu dòng CSV.)
- **Bất biến "mỗi dòng = một frame"** nay có test: `tests/test_drift_samples.py::
  test_thong_ke_danh_tinh_va_bat_bien_mot_frame` + `tests/test_live_tracking.py::
  TestDongCsvMotTheHeKhongTron` (test thứ hai **giết được mutant** "trả lại đọc `self._stats`").

**Hệ quả có số cho θ:**
- Trên **241 mẫu khi vật TRONG khung** (CLI 212 + LIVE 29), `min = 0,8080` ⇒ **θ = 0,75 chặn oan 0 mẫu**.
- ⇒ θ ≈ 0,75 **bắt được** trạng thái **mask sụp** (giá trị 0,46–0,71 chỉ xuất hiện khi `mask_area` rất nhỏ).
- ⚠️ **RÚT LẠI** câu "θ ≈ 0,75 BẮT được ca bám sang máy lạnh (0,51–0,72)": các số 0,510–0,719 đó là
  **BOX-cos** (mask = cả hình chữ nhật, lẫn nền), **không so được** với phân bố mask-cos ở đây (P2 review
  21-11). Muốn phát biểu phải có clip quay đúng cảnh + chấm **mask-cos** của vùng sai.
- Vẫn **KHÔNG mở cổng** (PR-2): chưa có mask-cos của vùng sai kiểu **cùng tông** (khung cửa 0,912 nằm
  **trong** dải ca đúng). Cần **1 clip sạch** bằng `scripts/record_raw.py` ở đúng cảnh.

### 🚫 QUYẾT ĐỊNH (21-11, phiên live thật `demoip_1121-121732`): **BÁC PR-2 dạng "cổng cos"**

Phiên live thật (webcam qua relay, `image_size 192`) có **đúng ca sai**: từ f178 hệ bám sang **cửa/tường be
cùng tông** với vật (điện thoại be) — xem ảnh `data/anh_tmp/p3_f180.jpg`, `p3_f200.jpg` (ô + mask phủ CỬA,
điện thoại nằm ở dưới, ngoài ô). Đây là lần đầu tôi có **mask-cos của vùng SAI** (thứ plan ghi "còn thiếu"):

| Cửa sổ (đã xem ảnh để phân loại) | n | median | min | p05 |
|---|---|---|---|---|
| **bám ĐÚNG** f0–86 ∪ f126–175 ∪ f264–277 | 145 | **0,9045** | 0,3762 | 0,8191 |
| **bám NỀN cùng tông** f179–243 | 65 | **0,8543** | **0,7521** | 0,7779 |

| θ | bắt được vùng sai | **chặn oan frame đúng** |
|---|---|---|
| 0,75 | **0/65 (0 %)** | 1/145 (1 %) |
| 0,80 | 6/65 (9 %) | 4/145 (3 %) |
| 0,85 | 28/65 (**43 %**) | 22/145 (**15 %**) |
| 0,88 | 44/65 (68 %) | 44/145 (30 %) |
| 0,90 | 49/65 (75 %) | 67/145 (**46 %**) |

⇒ **Không tồn tại θ tách được hai lớp này** (dải sai 0,752–0,989 nằm TRONG dải đúng): ngưỡng nào bắt ≥40 %
vùng sai thì chặn oan ≥15 % frame đúng. **PR-2 (cổng dựa trên `track_cos`) KHÔNG được làm** — đây là kết
luận TỪ SỐ ĐO, không phải "chưa đo được". Artifact: `data/track_cos_vung_sai_2026-11-21_metrics.json`.
Không cần clip mới: ca "remote cạnh máy lạnh" thực chất là **cùng tông**, và phiên này cho đúng lớp đó.

**Tín hiệu THAY THẾ có bằng chứng trong chính phiên này:** cổng **nhảy ô bao** đã báo ĐÚNG ở f178
(`[WARN] nghi ngờ ĐỔI ĐỐI TƯỢNG (ô bao nhảy từ (561,132,639,389) sang (376,43,476,122)) — bấm r chọn lại`),
nhưng nó chỉ **in ra** rồi hệ vẫn vẽ mask sai 65 frame. ⇒ Việc đáng làm tiếp không phải nuôi thêm kênh
ngoại hình, mà **hành động theo cổng nhảy đã có**.

**ĐÃ LÀM (21-11, cùng ngày) — đo trước, sửa sau:**
- Cổng báo **21 lần/2 973 frame = 0,71 %** (replay 18 phiên): `data/jump_gate_replay_2026-11-21_metrics.json`.
- Nếu ẩn từ lần báo đầu tới hết phiên, **không ai bấm gì**: **34,7 %** frame bị ẩn; **5/18 phiên không bao
  giờ bị ẩn**: `data/identity_latch_chi_phi_2026-11-21_metrics.json`.
- Code: `IdentityWatch` (latch) + `visualizer` **không vẽ** mask khi nghi + banner `r`/`c`; phím `c` =
  xác nhận vẫn đúng; cột CSV `nghi_doi_tuong` để soi lại. Test giết được mutant "bỏ latch".
- **Đã đồng bộ sang đường WEB** (cùng ngày): `bam = "nghi_doi_tuong"` + `nghi_doi_tuong(_n)` trong
  `status.json`/DTO; `POST /api/live/confirm` (IPC `confirm.json`, worker tự xoá file); web hiện banner
  `role="alert"` + nút "Vẫn đúng, tiếp tục". `./run e2e` PASS với 3 phép kiểm mới.

### Đã sửa sau review độc lập (P1-1, P1-2, 8 P2)
1. **P1-1** — 4 cột danh tính vào **`drift_samples.csv`** (CSV duy nhất của đường live) + `_worker_telemetry`;
   tiêu chí "CSV live" trước đó **không thể** đạt.
2. **P1-2** — đo lại trên cây sạch (`git_dirty_code = false`), `p05` qua `phan_vi` dùng chung, n **theo từng
   lần chạy**, artifact có `git_dirty_code` + `vi_sao_sinh_lai`.
3. **P1 (vòng 2)** — `drift_samples.csv`: 4 cột danh tính phải của **chính frame** đó (`identity` đi kèm
   dòng + `pending` 9 phần tử), không đọc `self._stats`; `thong_ke_danh_tinh()` parse lại + đếm dòng mâu
   thuẫn; whitelist trong `scripts/measure_live_relay.py` mang 5 khoá. Trước: **18/364 dòng** trộn hai
   thế hệ VOS ⇒ chính tiêu chí `mask_area == 0 ⇔ empty == 1` của plan **fail**.
4. **P2** — chấm `cos` **TRƯỚC** khi nạp neo (hết mẫu 1,0 cấu trúc); `MIN_ANCHORS` 2 → **3**; neo lọc
   **dải mép khung** như `_collect_reference`; frame `start()` **không chấm 2 lần**; `mask_area = None`
   (không phải 0) khi engine không trả mask; thêm test giết được mutant cho **cả 2 đường VOS** (bỏ call ở
   `_store_vos` ⇒ `vos_every=3` đỏ).
4. **Còn nợ (P2/P3, ghi ở log):** `object_signature` vẫn tính **2 lần/frame** trên đường CLI (`_collect_reference`
   + neo) ⇒ ~1,5 ms; `post_ms` bao gồm chi phí neo ở đường có luồng nhưng **không** ở đường inline ⇒
   `mask_age_total_ms` không so trực tiếp giữa 2 đường; `track_cos` gắn với frame VOS còn `bbox` trong
   `status.json` là frame hiển thị (lệch thế hệ, chờ V2).

**Đã kiểm trong phiên này (bug tự bắt):** bản đầu đặt neo inline trong `_after_vos` ⇒ đo thật với
`--vos-every 3` cho `track_cos = None, n = 0` **6/6 lần** vì đường có luồng VOS **không đi qua**
`_after_vos`; và `_store_vos` chỉ nhận `gray` nên `object_signature` (BGR→HSV) lỗi im lặng. Đã tách
`_cap_nhat_danh_tinh()` gọi ở **cả hai** đường + truyền **frame màu** xuống callback.

## 📌 Việc tách ra ticket

- [ ] Clip mới `data/remote_bg_*.mp4` (quay `scripts/record_raw.py`) + GT 16–20 frame có ≥8 frame **sau**
      lúc trôi — **việc của người tô**, ≥3 h.
- [ ] mIoU lên **n ≥ 30**: tận dụng 2 frame miễn phí (`docs/gt/b1` có 9 png, manifest chấm 7) rồi tô thêm.
- [ ] V2 `StampedResult` (1 lock cho 5 field) — P2, chỉ khi có bằng chứng lệch thế hệ trong CSV live.
- [ ] Cổng cho đường **web** cần `track_cos` ổn định trước (PR-1 là điều kiện).
- [ ] Ticket #42 (mask rỗng sát mép + "ô ma" ở frame `gt_rong`) vẫn **mở**.

## 📚 Tham chiếu

- `docs/task/21-11-2026-veto-nhan-lai-vao-mat-va-nguong-reid.md` (§5b–§5d: 3 vòng review veto).
- Phiên lỗi: `data/demoip_1121-103854_{metrics.csv,summary.json}.mp4` (⚠ **không có** `_run_info.json`:
  Ctrl+C, bug đã vá `b66370e`).
- `data/reid_2clip_calib.json` (17 ca đúng / 1 ca sai), `data/reid_ca_sai_vao_mat_2026-11-20_calib.json`.
- `src/reid.py:478` (append mẫu mỗi frame), `src/tracker_engine.py:239` (bbox = mask bbox),
  `src/smooth_display.py:175` (`set_bbox` reset re-ID), `src/live_tracking.py:1740-1780` (`bam`).
- `docs/thuoc-do-bam-dung.md`, `AGENTS.md` §6.
