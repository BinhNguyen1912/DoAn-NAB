# 35: Frame `start()` đi qua `_record_vos` VÀ `_store_vos` ⇒ `stability` nhận 2 mẫu cho cùng 1 frame (một mẫu = 1,0)

**What to build:** Phát hiện của audit sau merge 17-11 (mục "ngoài phạm vi 4 PR", có từ trước): ở đường CÓ luồng VOS, frame `engine.start()` đi qua **cả** `_after_vos` (→ `_record_vos` → `_measure_stability`) **và** `_store_vos` (→ `_record_vos` → `_measure_stability`) cho **cùng một frame video** ⇒ `stability` nhận 2 mẫu cho 1 frame, và một trong hai là `IoU(mask, mask) = 1,0` (so mask với chính nó) ⇒ `stability` bị **thổi lên** ở đầu phiên, `stability_n` đếm dư 1.

Vì sao quan trọng: `stability` là số UI hiển thị ("nhấp nháy") và từng bị dùng sai một lần (AGENTS §6: `stability` KHÔNG phải thước đo độ chính xác). Một mẫu 1,0 ở đầu phiên làm số của phiên ngắn (≤ 30 mẫu) lệch thấy được.

Việc:
- Chặn tại nguồn: khi `_use_lk` (đường có luồng), `_after_vos` của frame `start()` **không** gọi `_measure_stability` (worker sẽ đo đúng một lần ở `_store_vos`), hoặc đánh dấu `seq` của `start()` là "đã ghi".
- Test: `vos_every=3` trên clip ngắn ⇒ `stability_n` không vượt số lần VOS thật; và giá trị `stability` không có mẫu 1,0 "miễn phí" ở đầu phiên.
- Đo trước/sau trên `data/binh1.mp4` (3 lần, ghi `stability` + `stability_n`) ⇒ nêu rõ chênh lệch có vượt ngưỡng nhiễu không.

**Status:** `ready-for-agent`

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Frame `engine.start()` không đóng góp 2 mẫu `stability` cho cùng một frame video (một mẫu là IoU(mask, mask) = 1,0)
- [ ] Test: phiên `vos_every=3` clip ngắn ⇒ `stability_n` không vượt số lần VOS thật (hoặc test ghim giá trị `stability` không bị kéo lên ở đầu phiên)
- [ ] Ghi số đo trước/sau (stability + stability_n trên `data/binh1.mp4`, 3 lần) vào log `docs/task/`
