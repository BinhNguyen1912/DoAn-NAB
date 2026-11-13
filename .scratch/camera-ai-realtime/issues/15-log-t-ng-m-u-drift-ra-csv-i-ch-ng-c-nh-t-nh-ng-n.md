# 15: Log từng mẫu drift ra CSV + đối chứng cảnh tĩnh (để ngưỡng thành tái lập được)

**What to build:** Hiện chỉ có mean/p05 của cửa sổ 200 mẫu ⇒ **không đo được** độ trễ phát hiện, tỉ lệ báo oan, và không thể chọn ngưỡng bằng số.

1. Ghi `data/drift_samples_<clip>.csv` (`frame_idx, seq, vos_ms, empty, drift_iou, bbox_x1..y2`) trong `src/live_tracking.py` (`_record_drift`), có `git_rev`/`lenh`/`do_luc` trong file riêng hoặc header.
2. Đối chứng **cảnh tĩnh**: vật đứng yên (hoặc chuỗi frame tĩnh), `vos_every=3`, 300 frame ⇒ `drift_iou ≥ 0,99`, `drift_n ≥ 20`. Nếu thấp hơn ⇒ lỗi bookkeeping `_shown_at/_pending_drift`, **không** phải lỗi LK.

Vì sao: p05@200 có độ trễ bất đối xứng (bắt ~1,2 s khi hỏng hoàn toàn, nhả **23,3 s** @8,6 lần/giây) — cần dãy thời gian mới nói được "phát hiện sau bao lâu, báo oan bao nhiêu %".

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Có `data/drift_samples_*.csv` cho ít nhất binh1 (3 lần) + binh2 (1 lần), mỗi dòng có `frame_idx` và `drift_iou` hoặc cột `empty`
- [x] Artifact kèm `git_rev`, `git_dirty_code`, `lenh`, `do_luc` (quy tắc AGENTS §6)
- [x] Đối chứng cảnh tĩnh: `drift_iou ≥ 0,99` với `drift_n ≥ 20` (hoặc kết luận lỗi bookkeeping kèm chứng cứ)
- [x] Từ dãy mẫu: báo cáo `phát hiện sau N mẫu` và `% cửa sổ báo oan` trên binh1 (khoẻ)

## Comments

13-11 (nhánh `feat/drift-samples-csv`): **4/4 tiêu chí xong**, số đo trên WSL CPU (SAM 2.1 tiny, image_size 192, vos_every 3, đo qua API live `measure_live_relay --seconds 55`).

- Dãy mẫu: `data/drift_samples_{binh1×3,binh2,tinh_binh1}_2026-11-13_1256..1300.csv` + `.meta.json` (git_rev/lenh/do_luc/git_dirty_code). `n_dong == vos_runs - 1` ở cả 5 lần (lệch 1 là `engine.start()`, không có nội suy để so).
- Phân tích: `data/drift_series_2026-11-13_130246_metrics.json` (`git_rev=3b80dbc`, `git_dirty_code=false`), sinh bằng `python scripts/analyze_drift_samples.py --windows 20 50 100 200 --static "data/drift_samples_tinh_*.csv"`.
- Đối chứng cảnh tĩnh (clip `data/tinh_binh1.mp4` = frame tĩnh lặp 300 lần): **mean 0,9951** (tiêu chí ≥ 0,99), n = 364 ⇒ bookkeeping đúng. p05 = 0,9884 (dưới ngưỡng do **làm tròn toạ độ nguyên** của LK, không phải lỗi so cặp frame — đã ghi chú trong `static_control`).
- **% cửa sổ báo oan trên binh1 (clip khoẻ)**: ngưỡng p05 = 0,70 ⇒ **100 %** ở W ≥ 100, 74–84 % ở W=50, 45–47 % ở W=20 ⇒ **ngưỡng 0,70 đăng ký trước 08-11 bị bác** làm cờ chẩn đoán. Ngưỡng 0,30 ⇒ **0 %** báo oan trên binh1, 100 % trên binh2.
- **Phát hiện sau N mẫu** ≈ độ dài cửa sổ: binh2 cho 15/45/95/195 mẫu ứng với W=20/50/100/200 (nhịp 6,5 dòng/giây ⇒ W=200 là ~30 s). Đây là lý do phải quét cửa sổ, không chốt 200.
- **Ticket 14 vẫn bị chặn, nay có số tái lập được** (`low_p05_low_empty`): binh2 **158/158 cửa sổ p05<0,30** nhưng **0 cửa sổ** có mask rỗng < 3 % ⇒ p05 thấp vẫn dính 1:1 với "VOS mất vật"; thiếu clip "LK trôi thật".
- Review độc lập vòng 1: NOT MERGEABLE (1 P1 + 3 P2 + 6 P3) — **P1 thật**: CSV mất 10–20 dòng vì frame "đã phát nhưng không có ô bao" bị coi là "chưa phát". Đã sửa + test khoá bất biến `n_dong == vos_runs - 1` + đo lại toàn bộ 5 lần.

## Answer

Đã merge PR #18 (merge commit `8d9e73d`) sau 2 vòng review độc lập. 4/4 tiêu chí xong.

Công cụ: `src/drift_samples.py` (DriftSampleLog + `rolling_p05`/`flag_rate`/`detect_latency`/`static_control`/`low_p05_low_empty`), `scripts/analyze_drift_samples.py` (`--windows`, `--static`), `scripts/measure_live_relay.py` tự chép CSV + `.meta.json` ra `data/`.

Số đo (WSL CPU, SAM 2.1 tiny, image_size 192, vos_every 3, qua API live, 55 s/lần, `git_rev=301b961`, `git_dirty_code=false`; artifact `data/drift_series_2026-11-13_132004_metrics.json`):
- binh1 ×3: drift 0,8661/0,8632/0,8672 · p05 0,6453/0,6453/0,6475 · 0 % mask rỗng.
- binh2: drift 0,4665 · p05 0,000 · **21,8 %** lần VOS trả mask rỗng.
- Cảnh tĩnh (`data/tinh_binh1.mp4`, 300 frame lặp): **mean 0,9951 / p05 0,9884, n = 364** ⇒ bookkeeping so-cặp-frame đúng (tiêu chí ≥ 0,99 ĐẠT).
- Bất biến `n_dong == vos_runs − 1` ở cả 5 lần (lệch 1 = `engine.start()`, không có nội suy để so) — có test khoá; trước khi sửa P1 lệch 10–20 dòng.

Kết luận cho báo cáo: ngưỡng p05 0,70 đăng ký trước 08-11 **bị bác** (báo oan 100 % ở W ≥ 100, 74–84 % ở W=50, 45–47 % ở W=20 trên clip khoẻ); ngưỡng 0,30 có 0 % báo oan trên binh1 và bắt 100 % trên binh2. Độ trễ phát hiện ≈ độ dài cửa sổ (binh2: 15/45/95/195 mẫu ở W=20/50/100/200 ⇒ W=200 ≈ 30 s ở nhịp ~6,3 lần VOS/giây).

Ticket 14 vẫn chặn (đã ghi số vào ticket đó): 158/158 cửa sổ `p05 < 0,30` của binh2 đều có mask rỗng ≥ 3 % ⇒ chưa có clip "LK trôi thật".
