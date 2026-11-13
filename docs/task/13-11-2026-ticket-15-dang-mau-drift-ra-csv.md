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
`device=cpu`, đo qua **API live** bằng `scripts/measure_live_relay.py --seconds 55`
(`git_rev = 713f869`, cây sạch; artifact phân tích ở `b4c37a6`, `git_dirty_code = false`).

| Lần đo | Dòng CSV | Mẫu drift | `drift_iou` | p05 | mask rỗng | Cửa sổ p05<0,70 | Cửa sổ p05<0,30 |
|---|---|---|---|---|---|---|---|
| binh1 · lần 1 | 368 | 368 | **0,8684** | 0,6455 | 0 | **169/169 = 100 %** | 0 % |
| binh1 · lần 2 | 332 | 332 | 0,8631 | 0,6465 | 0 | **133/133 = 100 %** | 0 % |
| binh1 · lần 3 | 326 | 326 | 0,8615 | 0,6136 | 0 | **127/127 = 100 %** | 0 % |
| **binh2** | 339 | 271 | **0,4696** | **0,000** | **20,1 %** (68/339) | 72/72 = 100 % | **100 %** |
| **cảnh tĩnh** (`tinh_binh1`) | 357 | 357 | **0,9955** | 0,9885 | 0 | 0/158 = 0 % | 0 % |

- Nhịp VOS trong harness này: **6,2–6,7 lần/giây** (`mask_fps` 6,5; `vos_ms` ≈ 150 ms) — chậm hơn
  8,6 lần/giây của bảng 08-11 (đo thẳng `tools/live_worker.py`); **đừng trộn hai bộ số**. Nguyên nhân
  chênh chưa điều tra (ghi ở Next steps), chỉ ghi nhận `mask_age_p95` ở đây 284–307 ms.
- **Đối chứng cảnh tĩnh ĐẠT**: mean 0,9955 ≥ 0,99 (tiêu chí ticket), `n = 357` ⇒ bookkeeping
  `_shown_at`/`_pending_drift` đúng. `p05 = 0,9885` (0,0015 dưới ngưỡng) do **làm tròn toạ độ nguyên**
  của LK — đã ghi chú trong `static_control`, không dùng p05 để phán quyết.
- **Ngưỡng 0,70 đăng ký trước 08-11 BỊ BÁC làm cờ chẩn đoán**: trên clip khoẻ binh1 nó báo động
  **100 % cửa sổ** ở W ≥ 100, 72–87 % ở W = 50, 44–48 % ở W = 20. Ngưỡng 0,30 thì **0 % báo oan**
  trên binh1 và bắt 100 % trên binh2.
- **Độ trễ phát hiện xấp xỉ BẰNG độ dài cửa sổ** (p05 chưa tồn tại trước khi có đủ W mẫu) — quét
  cửa sổ trên binh2: phát hiện sau **14 / 44 / 94 / 194 mẫu** ứng với W = 20 / 50 / 100 / 200. Ở nhịp
  6,2 mẫu/giây, W = 200 ⇒ **~31 giây** sau mẫu xấu đầu. Đây là lý do phải quét cửa sổ, không chọn 200
  một cách tuỳ ý.
- **Ticket 14 vẫn bị chặn, nay có bằng chứng từng mẫu**: trên binh2, **140/140 cửa sổ** có
  `p05 < 0,30` đều có `empty_frac` 20–24 % (không cửa sổ nào < 3 %) ⇒ `p05` thấp và "VOS mất vật"
  vẫn dính nhau 1:1. Thiếu đúng clip "LK trôi thật": vật đi qua vùng che khuất mà model vẫn thấy.
- File thay đổi:
  - `src/drift_samples.py` (mới) — logger CSV + 6 hàm phân tích thuần
  - `src/live_tracking.py` — ghi dòng cho mọi lần VOS, đóng file, đăng ký `seq_frame` của `start()`
  - `scripts/measure_live_relay.py` — chép CSV + `.meta.json`, xoá CSV cũ, in số dãy mẫu
  - `scripts/analyze_drift_samples.py` (mới) — gộp CSV thành artifact + quét cửa sổ
  - `.gitignore` — whitelist `data/drift_samples_*`
  - `tests/test_drift_samples.py` (mới), `tests/test_live_tracking.py`,
    `tests/test_measure_live_relay.py`
  - `data/drift_samples_{binh1×3,binh2,tinh_binh1}_2026-11-13_*.csv` + `.meta.json`,
    `data/drift_series_2026-11-13_124245_metrics.json`
- Kiểm tra trên máy này: `./run lint` xanh · `./run test` **849 passed** · `./run testall`
  **857 passed** (224 s).

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
- **Lần đo 35 giây không đủ mẫu**: 166–183 mẫu < cửa sổ 200 ⇒ `ti_le_bao = None` (đúng luật "0/None ≠
  đã đo"), nhưng không trả lời được câu hỏi. Nâng lên 55 giây ⇒ 269–368 mẫu.

## 🔎 Review độc lập (§9.1)
- **Ai review:** agent `reviewer` (phiên khác), prompt có `parent_context` + `proposed_changes` + phạm
  vi = 3 commit của nhánh `feat/drift-samples-csv`.
- **Kết luận:** _(điền sau khi có kết quả review)_
- **Đã sửa trong cùng PR:** _(điền)_
- **Còn nợ (ghi ticket):** _(điền)_

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Ticket 14 vẫn chờ**: cần 1 clip "LK trôi thật" (`p05 < 0,30` mà `empty_frac < 3 %`). Nay có
      công cụ soi: `python scripts/analyze_drift_samples.py --windows 20 50 100 200`.
- [ ] Hiểu vì sao nhịp VOS qua API (6,2–6,7 lần/giây) chậm hơn đo thẳng worker (8,6): nghi do đọc/ghi
      frame 720p + API poll, **chưa đo** — đừng trích số này cho báo cáo FPS.
- [ ] Báo cáo dùng: ngưỡng cờ chẩn đoán nên là **0,30 với cửa sổ ngắn (20–50)**; nêu rõ độ trễ phát
      hiện ≈ độ dài cửa sổ (~3–8 giây ở W = 20–50, nhịp 6,2 mẫu/giây).
- [ ] Ticket 21 phần 2 (mặc định `image_size`/`vos_every` theo GPU) vẫn chờ số đo Colab.

## 📚 Tài liệu tham khảo
- Ticket: `.scratch/camera-ai-realtime/issues/15-log-t-ng-m-u-drift-ra-csv-i-ch-ng-c-nh-t-nh-ng-n.md`
- `docs/task/08-11-2026-do-cai-gia-noi-suy-lk-va-nguong-nhieu.md` — định nghĩa `drift_iou`, ngưỡng nhiễu
- `docs/plan/09-11-2026-chan-doan-chat-luong-bam.md` — vì sao cờ chẩn đoán chưa được làm
- Artifact: `data/drift_series_2026-11-13_124245_metrics.json` + 5 file `data/drift_samples_*.csv`
