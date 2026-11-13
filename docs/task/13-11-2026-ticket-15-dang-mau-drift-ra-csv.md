# Ngày 13-11-2026 — Ticket 15: ghi TỪNG mẫu drift ra CSV + đối chứng cảnh tĩnh

## 🎯 Mục tiêu
- Đóng **ticket 15** (`.scratch/camera-ai-realtime/issues/15-…`): `status.json` chỉ có mean/p05 của cửa
  sổ 200 mẫu ⇒ **không đo được** "phát hiện sau bao nhiêu mẫu" và "% cửa sổ báo oan", tức không thể
  chọn ngưỡng bằng số. Cần dãy mẫu từng dòng + phép đối chứng cảnh tĩnh.
- Trả lời bằng số hai câu đang chặn ticket 14: (a) ngưỡng p05 = 0,70 đăng ký trước 08-11 có **báo
  oan** trên clip khoẻ không? (b) có cửa sổ nào `p05 < 0,30` mà `empty_frac ≈ 0` (LK trôi thật, không
  phải model mất vật) để mở khoá cờ chẩn đoán không?
- **Không** làm: viết cờ chẩn đoán (ticket 14) — việc đó cần điều kiện tiên quyết ở câu (b).

## 📥 Input
- `AGENTS.md` §6 (mọi so sánh A/B phải nêu ngưỡng nhiễu; `0`/`None` = chưa đo; artifact phải có
  `git_rev`/`git_dirty_code`/`lenh`/`do_luc`), §9.1 (review độc lập), §7b (1 nhánh/nhiệm vụ).
- Ticket 15 + log `docs/task/08-11-2026-do-cai-gia-noi-suy-lk-va-nguong-nhieu.md` (định nghĩa
  `drift_iou`, cửa sổ 200, độ trễ bất đối xứng "bắt 1,2 s / nhả 23,3 s") +
  `docs/plan/09-11-2026-chan-doan-chat-luong-bam.md` (ngưỡng cờ 0,30/0,45 đề xuất).
- Mã hiện tại: `src/live_tracking.py` (`_measure_drift`, `_pending_drift`, `_apply_drift_locked`),
  `scripts/measure_live_relay.py` (harness đo có provenance), `src/metrics_logger.py` (quy ước CSV).
- Clip: `data/binh1.mp4` (bbox `104,308,209,287`), `data/binh2.mp4` (bbox `200,400,300,500`),
  `data/tinh_binh1.mp4` (mới sinh: 300 frame TĨNH = frame 30 của binh1 lặp lại).

## 🔨 Công việc đã thực hiện
1. **`src/drift_samples.py` (mới)**
   - `DriftSampleLog`: ghi `drift_samples.csv` (`frame_idx, seq, vos_ms, empty, drift_iou, bbox_x1..y2`).
     Mở file **lười** (phiên tắt LK không sinh file rỗng — tránh bị đọc là "đã đo, 0 mẫu"), có lock
     riêng vì ghi từ **2 luồng** (luồng VOS + luồng chính khi mẫu `_pending_drift` tới hạn), `flush`
     mỗi dòng để phiên bị `kill` vẫn giữ mẫu.
   - Hàm THUẦN: `rolling_p05` (khớp đúng định nghĩa p05 của phiên), `flag_rate` (tỉ lệ cửa sổ có p05
     dưới ngưỡng), `detect_latency` (số mẫu từ mẫu xấu đầu tới cửa sổ đầu tiên bị cờ), `static_control`
     (đối chứng cảnh tĩnh), `summarize`, `read_samples`.
2. **`src/live_tracking.py`** — ghi 1 dòng/mẫu ở **cả hai** nhánh chấm điểm; đóng file trong `finally`;
   `_start_worker` đăng ký `seq → frame` cho cả mẫu `start()` (để mọi dòng có `frame_idx`).
3. **`scripts/measure_live_relay.py`** — chép CSV ra `data/drift_samples_<clip>_<mốc>.csv` +
   `.meta.json` (git_rev/lenh/do_luc/thiết lập/thiết bị), **xoá CSV cũ trong `out_dir` trước khi đo**
   (nếu không, file của phiên trước bị chép ra như số của lần này), phân tích ngay vào artifact.
4. **`scripts/analyze_drift_samples.py` (mới)** — gộp nhiều CSV thành 1 artifact
   `data/drift_series_<mốc>_metrics.json`, có `--windows` để quét nhiều cửa sổ.
5. **`.gitignore`** — cho qua `data/drift_samples_*.csv` + `*.meta.json` (nhỏ, là bằng chứng số).
6. **Test**: 20 ca mới (`tests/test_drift_samples.py`, `tests/test_live_tracking.py`,
   `tests/test_measure_live_relay.py`) — gồm 2 test bắt lỗi thật gặp trong phiên (xem 🐞).

## 📤 Output / Kết quả

Môi trường: WSL laptop CPU (Iris Xe), torch CPU, SAM 2.1 tiny, `image_size 192`, `vos_every 3`,
`device=cpu`, đo qua **API live** bằng `scripts/measure_live_relay.py --seconds 55`. Provenance:
`git_rev = 301b961` (commit chứa code sinh ra số), `git_dirty_code = false`; artifact phân tích
`data/drift_series_2026-11-13_130246_metrics.json` ở `git_rev = 3b80dbc`, `git_dirty_code = false`
(`git_dirty = true` chỉ vì chính các file số liệu nằm trong `data/` — AGENTS §6 phân biệt hai cờ này).

| Lần đo | Dòng CSV | `vos_runs` | Mẫu drift | `drift_iou` | p05 | mask rỗng | Cửa sổ p05<0,70 | Cửa sổ p05<0,30 |
|---|---|---|---|---|---|---|---|---|
| binh1 · lần 1 | 378 | 379 | 364 | **0,8661** | 0,6453 | 0 | **165/165 = 100 %** | 0 % |
| binh1 · lần 2 | 356 | 357 | 346 | 0,8632 | 0,6453 | 0 | **147/147 = 100 %** | 0 % |
| binh1 · lần 3 | 359 | 360 | 352 | 0,8672 | 0,6475 | 0 | **153/153 = 100 %** | 0 % |
| **binh2** | 357 | 358 | 262 | **0,4665** | **0,000** | **21,8 %** (78/357) | 63/63 = 100 % | **100 %** |
| **cảnh tĩnh** (`tinh_binh1`) | 364 | 365 | 364 | **0,9951** | 0,9884 | 0 | 0/165 = 0 % | 0 % |

- **Quan hệ đếm**: `n_dong == vos_runs - 1` ở cả 5 lần đo — lệch 1 là `engine.start()` (chạy model
  nhưng là mẫu khởi tạo, không có nội suy để so). Có test khoá bất biến này; nếu P1 tái phát thì test
  đỏ ngay (trước khi sửa P1, lệch là 10–12 dòng ở binh1 và **20** ở binh2).
- Nhịp VOS trong harness này: `vos_fps` **6,1–6,7 lần/giây** (`vos_ms` 118–126 ms theo `status.json`;
  107–226 ms nếu đọc từng dòng CSV; `mask_fps` 6,1–6,6), nhịp dòng CSV 6,4–6,5 dòng/giây — chậm hơn
  8,6 lần/giây của bảng 08-11 (đo thẳng `tools/live_worker.py`); **đừng trộn hai bộ số**.
  `mask_age_p95` ở đây 271–303 ms.
- **Đối chứng cảnh tĩnh ĐẠT**: mean 0,9951 ≥ 0,99 (tiêu chí ticket), `n = 364` ⇒ bookkeeping
  so-cặp-frame đúng. `p05 = 0,9884` (0,0016 dưới ngưỡng) do **làm tròn toạ độ nguyên** của LK — đã ghi
  chú trong `static_control`, không dùng p05 để phán quyết.
- **Ngưỡng 0,70 đăng ký trước 08-11 BỊ BÁC làm cờ chẩn đoán**: trên clip khoẻ binh1 nó báo động
  **100 % cửa sổ** ở W ≥ 100, **74–84 %** ở W = 50, **45–47 %** ở W = 20. Ngưỡng 0,30 thì **0 % báo
  oan** trên binh1 (mọi cửa sổ) và bắt 100 % trên binh2.
- **Độ trễ phát hiện xấp xỉ BẰNG độ dài cửa sổ** (p05 chưa tồn tại trước khi có đủ W mẫu) — quét cửa
  sổ trên binh2: phát hiện sau **15 / 45 / 95 / 195 mẫu** ứng với W = 20 / 50 / 100 / 200. Ở nhịp
  6,5 dòng/giây, W = 200 ⇒ **~30 giây** sau mẫu xấu đầu; W = 20 ⇒ ~2–3 giây. Đây là lý do phải quét
  cửa sổ thay vì chọn 200 một cách tuỳ ý.
- **Ticket 14 vẫn bị chặn — nay đo được bằng code đã commit** (`low_p05_low_empty`, có trong artifact
  dưới khoá `p05_thap_va_empty`): binh2 có **158/158 cửa sổ** `p05 < 0,30` nhưng **0 cửa sổ** trong
  số đó có mask rỗng < 3 % (`empty_frac` cả phiên 21,8 %) ⇒ `p05` thấp và "VOS mất vật" vẫn dính nhau
  1:1. Thiếu đúng clip "LK trôi thật": vật đi qua vùng che khuất mà model vẫn thấy vật.
- File thay đổi:
  - `src/drift_samples.py` (mới) — logger CSV + 6 hàm phân tích thuần
  - `src/live_tracking.py` — ghi dòng cho mọi lần VOS, đóng file, đăng ký `seq_frame` của `start()`
  - `scripts/measure_live_relay.py` — chép CSV + `.meta.json`, xoá CSV cũ, in số dãy mẫu
  - `scripts/analyze_drift_samples.py` (mới) — gộp CSV thành artifact + quét cửa sổ
  - `.gitignore` — whitelist `data/drift_samples_*`
  - `tests/test_drift_samples.py` (mới), `tests/test_live_tracking.py`,
    `tests/test_measure_live_relay.py`
  - `data/drift_samples_{binh1×3,binh2,tinh_binh1}_2026-11-13_1256..1300.csv` + `.meta.json`,
    `data/drift_series_2026-11-13_130246_metrics.json`
- Kiểm tra trên máy này (sau vòng sửa theo review): `./run lint` xanh · `./run test`
  **867 passed** (65 s, 5 deselected) · `./run testall` **872 passed** (177 s).

## 🐞 Vấn đề gặp phải & cách xử lý
- **Lỗi thật #1 — CSV nói dối về "mask rỗng".** Lần đo binh2 đầu tiên: `status.json` ghi
  `empty_runs = 81` nhưng CSV báo `empty_frac = 0,0`. Nguyên nhân: mẫu rỗng có bbox `(0,0,0,0)` nên bị
  **bỏ trước khi kịp ghi dòng** ⇒ cột `empty` luôn 0, và "tỉ lệ báo oan" sẽ không bao giờ tách được
  "model mất vật" khỏi "LK trôi" — đúng thứ ticket cần. Sửa: mọi lần VOS đều có dòng (drift để trống
  khi không chấm được) + test hồi quy (`test_mask_rong_co_that_thi_dong_csv_ghi_empty_1`). Đo lại:
  68/339 = 20,1 %, khớp `empty_runs = 68`.
- **Lỗi thật #2 — phán quyết cảnh tĩnh theo p05 báo oan.** Bản đầu chấm `p05 ≥ 0,99`; số đo thật là
  mean 0,9955 / p05 0,9885 ⇒ báo "nghi lỗi bookkeeping" trong khi bookkeeping đúng (đuôi thấp do làm
  tròn toạ độ nguyên). Nay phán quyết theo **mean** đúng như tiêu chí ticket, p05 chỉ là ghi chú.
- **Dòng đầu tiên thiếu `frame_idx`**: mẫu của `engine.start()` không có ánh xạ `seq → frame` (chỉ
  `_result_threaded` đăng ký) ⇒ không chấm được drift và dòng CSV không truy về frame nào. Sửa ở
  `_start_worker`, có test khoá (`test_csv_khop_cua_so_trong_status` kiểm mọi dòng có `frame_idx`).
- **`summarize` bị che tên**: import `summarize` của `src.drift_samples` trong `measure_live_relay.main()`
  làm ruff báo `F823 Local variable 'summarize' referenced before assignment` (script đã có hàm
  `summarize` riêng) — dùng bí danh `summarize_series`.
- **P1 của review (xem mục review) — mất 10–20 dòng CSV**: phát hiện bằng cách đối chiếu
  `vos_runs` với số dòng. Bài học: khi thêm "ghi từng mẫu", **phải** khoá bất biến số dòng bằng test,
  nếu không sẽ chỉ thấy lệch khi tình cờ so hai con số.
- **Lần đo 35 giây không đủ mẫu**: 166–183 mẫu < cửa sổ 200 ⇒ `ti_le_bao = None` (đúng luật "0/None ≠
  đã đo"), nhưng không trả lời được câu hỏi. Nâng lên 55 giây ⇒ 269–368 mẫu.

## 🔎 Review độc lập (§9.1)
- **Ai review:** agent `reviewer` (phiên khác, chỉ đọc — không có shell nên không tự chạy `git`/`pytest`;
  các kết luận là bằng chứng đọc mã + **tính lại tay** số trong artifact từ CSV). Phạm vi: 3 commit đầu
  của nhánh `feat/drift-samples-csv`. Kết luận vòng 1: **NOT MERGEABLE** — 1 P1 + 3 P2 + 6 P3.
- **P1 (đã sửa, có test hồi quy + đo lại toàn bộ):** "ghi 1 dòng cho MỌI lần VOS" **không đạt** —
  `vos_runs 379` mà CSV chỉ 368 dòng (binh2: 359 vs 339). Nguyên nhân: `_shown_at_locked` trả `None`
  cho **cả** "frame chưa phát" và "frame đã phát nhưng không có ô bao hiển thị" ⇒ ca thứ hai bị hẹn
  `_pending_drift` cho một frame đã trôi qua rồi bỏ im lặng. Nay `_shown_state_locked` trả
  `(found, bbox)`, nhánh pending-trễ và mẫu còn treo lúc dừng phiên đều ghi dòng (`drift_iou` trống,
  không bịa 0) qua `_flush_pending_csv()`; test khoá bất biến `n_dong == vos_runs - 1` (đúng: start
  không có nội suy để so). **Đo lại 5 lần**: lệch đúng 1 ở cả 5.
- **P2 #1 (đã sửa):** `theo_cua_so[W]["drift_iou_p05"]` là p05 **toàn dãy** nên nhân bản vào mọi cửa
  sổ ⇒ người đọc kết luận sai "p05 không phụ thuộc cửa sổ". Đã bỏ khoá đó khỏi `theo_cua_so` và ghi rõ
  trong `dinh_nghia` rằng p05 top-level là p05 toàn dãy (khác p05 của 200 mẫu **cuối** trong
  `status.json`).
- **P2 #2 (đã sửa):** con số "140/140 cửa sổ" trong bản log đầu **không tái lập được** bằng công cụ đã
  commit (nó đến từ một phép tính nháp gán 0 cho mẫu rỗng ⇒ tautology). Nay có hàm
  `low_p05_low_empty()` + khoá `p05_thap_va_empty` trong artifact; số đúng là **158/158 cửa sổ p05<0,30,
  0 cửa sổ có mask rỗng < 3 %**.
- **P2 #3 (đã sửa):** `DriftSampleLog.close()` rồi còn `write()` (luồng VOS sống tới 5 s sau `join`) sẽ
  **mở lại file bằng mode `w` ⇒ xoá sạch dãy mẫu**. Nay `write()` sau `close()` là no-op + test.
- **P3 (đã sửa):** `MIN_SAMPLES` 20 → **30** (= `_STAT_MIN_SAMPLES` của phiên) + test khoá
  `WINDOW`/`MIN_SAMPLES` với `live_tracking`; `_opt_bool` chỉ nhận `1`/`0` (chuỗi lạ ⇒ `None`, không
  thành `False`); thêm test khoá "`_log_drift_sample` không được gọi khi đang giữ `_stats_lock`"; sửa
  các câu chữ trong log (nhịp VOS lấy từ artifact, `git_dirty_code` ≠ `git_dirty`, `n_dong` không dùng
  làm "số lần VOS").
- **"Đã kiểm, không phải lỗi" (reviewer xác nhận):** không I/O file trong `_stats_lock`, không deadlock
  giữa lock CSV và lock thống kê; `_pending_drift` 5 phần tử nhất quán ở code + test; `read_samples`
  không biến ô trống thành 0/False; p05 tái lập được bằng `numpy.percentile` (kiểm tay một giá trị);
  `.gitignore` whitelist hoạt động; `measure_live_relay` không đọc CSV của phiên trước.
- **Review vòng 2** (agent `reviewer` khác, chỉ đọc): **MERGEABLE — 0 P0, 0 P1**, 2 P2 + 7 P3. Reviewer
  xác nhận P1 đã hết bằng dữ liệu (lan can chứng cứ: binh2 có **17 dòng `empty=0` mà `drift_iou`
  trống** — đúng chữ ký "VOS thấy vật / frame đã phát không có hộp", loại mẫu từng bị bỏ). Đã sửa
  trong cùng PR:
  - **P2 (số cũ trong README):** README còn trích số của lần đo **trước** fix P1 (20,1 % / 0,9955 /
    44–48 %). Nay chép lại từ artifact mới (21,8 % / 0,9951 / 45–47 %) + ghi rõ file artifact.
  - **P2 (`min_measured` ghim 100):** `low_p05_low_empty` ghim ngưỡng "đủ mẫu" theo `WINDOW` ⇒ gọi
    `--window 20` cho **0 cửa sổ** và trả `False` im lặng. Nay suy từ `window // 2` và trả **`None`**
    khi không có cửa sổ đủ mẫu ("chưa đo" ≠ "đã đo, không có").
  - **P3:** ô `empty` trống không còn bị đếm thành "không rỗng"; pending là 1 slot nên mẫu thứ hai về
    trước khi frame được phát **không còn ghi đè** mẫu đang treo (mẫu cũ được ghi thành dòng); test
    mới khoá "`run()` luôn gọi `_flush_pending_csv`" (test cũ gọi thẳng hàm nên xoá khỏi `finally`
    vẫn xanh) + test bất biến số dòng cho ca **nguồn hết frame, không lặp**; docstring nêu rõ
    `n_dong == vos_runs - 1` chỉ đúng khi `vos_every > 1`; `dinh_nghia` của artifact nêu cửa sổ đếm
    trên trục dòng và `n_cua_so_du_mau` khác `n_cua_so` của `bao_dong_030`.
  - **Còn nợ (P3, ghi ở Next steps):** `_shown_at`/`_shown_at_locked` nay chỉ còn test dùng;
    `ghi_chu` trong 5 `.meta.json` đã ghi vẫn là câu cũ ("1 mẫu drift") — giữ nguyên vì đó là
    provenance của lần đo, code đã sửa câu này.

## 📌 Việc cần làm tiếp (Next steps)
- [x] **Vòng review 2** đã chạy: MERGEABLE, 0 P0/P1, đã sửa 2 P2 + 4 P3 trong cùng PR.
- [ ] **Ticket 14 vẫn chờ**: cần 1 clip "LK trôi thật" (`p05 < 0,30` mà mask rỗng < 3 %). Công cụ soi đã
      có: `python scripts/analyze_drift_samples.py --windows 20 50 100 200` → khoá `p05_thap_va_empty`.
- [ ] Hiểu vì sao nhịp VOS qua API (6,1–6,7 lần/giây) chậm hơn đo thẳng worker (8,6): nghi do đọc/ghi
      frame 720p + API poll, **chưa đo** — đừng trích số này cho báo cáo FPS.
- [ ] Báo cáo dùng: ngưỡng cờ chẩn đoán nên là **0,30 với cửa sổ ngắn (20–50)** (0 % báo oan trên
      binh1, phát hiện ~2–7 giây ở nhịp 6,5 dòng/giây); nêu rõ ngưỡng 0,70 đăng ký trước 08-11 đã bị
      bác vì báo oan 45–100 % trên clip khoẻ.
- [ ] Ticket 21 phần 2 (mặc định `image_size`/`vos_every` theo GPU) vẫn chờ số đo Colab.
- [ ] Dọn dần: `_shown_at`/`_shown_at_locked` nay chỉ còn test dùng (giữ vì test khoá bất biến lock) —
      quyết định bỏ hay chuyển test sang `_shown_state_locked` khi đụng lại file này.
- [ ] 5 file `.meta.json` đã ghi mang câu `ghi_chu` cũ ("1 mẫu drift"); code đã sửa thành "1 kết quả
      VOS" nhưng **không** sửa lại artifact cũ (đó là provenance của lần đo).

## 📚 Tài liệu tham khảo
- Ticket: `.scratch/camera-ai-realtime/issues/15-log-t-ng-m-u-drift-ra-csv-i-ch-ng-c-nh-t-nh-ng-n.md`
- `docs/task/08-11-2026-do-cai-gia-noi-suy-lk-va-nguong-nhieu.md` — định nghĩa `drift_iou`, ngưỡng nhiễu
- `docs/plan/09-11-2026-chan-doan-chat-luong-bam.md` — vì sao cờ chẩn đoán chưa được làm
- Artifact: `data/drift_series_2026-11-13_124245_metrics.json` + 5 file `data/drift_samples_*.csv`
