# 15: Log từng mẫu drift ra CSV + đối chứng cảnh tĩnh (để ngưỡng thành tái lập được)

**What to build:** Hiện chỉ có mean/p05 của cửa sổ 200 mẫu ⇒ **không đo được** độ trễ phát hiện, tỉ lệ báo oan, và không thể chọn ngưỡng bằng số.

1. Ghi `data/drift_samples_<clip>.csv` (`frame_idx, seq, vos_ms, empty, drift_iou, bbox_x1..y2`) trong `src/live_tracking.py` (`_record_drift`), có `git_rev`/`lenh`/`do_luc` trong file riêng hoặc header.
2. Đối chứng **cảnh tĩnh**: vật đứng yên (hoặc chuỗi frame tĩnh), `vos_every=3`, 300 frame ⇒ `drift_iou ≥ 0,99`, `drift_n ≥ 20`. Nếu thấp hơn ⇒ lỗi bookkeeping `_shown_at/_pending_drift`, **không** phải lỗi LK.

Vì sao: p05@200 có độ trễ bất đối xứng (bắt ~1,2 s khi hỏng hoàn toàn, nhả **23,3 s** @8,6 lần/giây) — cần dãy thời gian mới nói được "phát hiện sau bao lâu, báo oan bao nhiêu %".

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Có `data/drift_samples_*.csv` cho ít nhất binh1 (3 lần) + binh2 (1 lần), mỗi dòng có `frame_idx` và `drift_iou` hoặc cột `empty`
- [ ] Artifact kèm `git_rev`, `git_dirty_code`, `lenh`, `do_luc` (quy tắc AGENTS §6)
- [ ] Đối chứng cảnh tĩnh: `drift_iou ≥ 0,99` với `drift_n ≥ 20` (hoặc kết luận lỗi bookkeeping kèm chứng cứ)
- [ ] Từ dãy mẫu: báo cáo `phát hiện sau N mẫu` và `% cửa sổ báo oan` trên binh1 (khoẻ)
