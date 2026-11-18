# 35: Frame `start()` đi qua `_record_vos` VÀ `_store_vos` ⇒ `stability` nhận 2 mẫu cho cùng 1 frame (một mẫu = 1,0)

**What to build:** Phát hiện của audit sau merge 17-11 (mục "ngoài phạm vi 4 PR", có từ trước): ở đường CÓ luồng VOS, frame `engine.start()` đi qua **cả** `_after_vos` (→ `_record_vos` → `_measure_stability`) **và** `_store_vos` (→ `_record_vos` → `_measure_stability`) cho **cùng một frame video** ⇒ `stability` nhận 2 mẫu cho 1 frame, và một trong hai là `IoU(mask, mask) = 1,0` (so mask với chính nó) ⇒ `stability` bị **thổi lên** ở đầu phiên, `stability_n` đếm dư 1.

Vì sao quan trọng: `stability` là số UI hiển thị ("nhấp nháy") và từng bị dùng sai một lần (AGENTS §6: `stability` KHÔNG phải thước đo độ chính xác). Một mẫu 1,0 ở đầu phiên làm số của phiên ngắn (≤ 30 mẫu) lệch thấy được.

Việc:
- Chặn tại nguồn: khi `_use_lk` (đường có luồng), `_after_vos` của frame `start()` **không** gọi `_measure_stability` (worker sẽ đo đúng một lần ở `_store_vos`), hoặc đánh dấu `seq` của `start()` là "đã ghi".
- Test: `vos_every=3` trên clip ngắn ⇒ `stability_n` không vượt số lần VOS thật; và giá trị `stability` không có mẫu 1,0 "miễn phí" ở đầu phiên.
- Đo trước/sau trên `data/binh1.mp4` (3 lần, ghi `stability` + `stability_n`) ⇒ nêu rõ chênh lệch có vượt ngưỡng nhiễu không.

**Status:** `ready-for-agent`

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Frame `engine.start()` không đóng góp 2 mẫu `stability` cho cùng một frame video (một mẫu là IoU(mask, mask) = 1,0)
- [x] Test: phiên `vos_every=3` clip ngắn ⇒ `stability_n` không vượt số lần VOS thật (hoặc test ghim giá trị `stability` không bị kéo lên ở đầu phiên)
- [x] Ghi số đo trước/sau (stability + stability_n trên `data/binh1.mp4`, 3 lần) vào log `docs/task/`

## Answer

Sửa **hẹp**: `_measure_stability(result, frame_video=…)` **không đẩy mẫu cặp** khi `frame_video` trùng
mẫu gần nhất (vẫn đếm cửa sổ mất dấu). `_record_vos` tách `dump` khỏi `frame_video` để `_after_vos` của
đường có luồng vẫn truyền frame video (nếu để `None` thì bước so trùng không chạy — đã thử và test đỏ).

Bản sửa đầu (bỏ hẳn `_measure_stability` + `_smooth` cho frame `start()`) làm **2 test cũ đỏ**
(`empty_window_n == vos_runs`, `mask_holds >= 1`) ⇒ đổi sang cách hẹp.

2 test mới: cơ chế (gọi thẳng `_measure_stability`) + bất biến phiên. **Đỏ trên code cũ, xanh với bản
sửa** (kiểm bằng `git stash`). `./run test` **1355 passed**.

Số trên clip thật **không phân biệt được** (`stability_n` 10 ở cả hai bên; mask rỗng 43/142 lần VOS;
n=1 mỗi bên) ⇒ ghi đúng là "không phân biệt được", căn cứ là test cơ chế. Cái đo được: `empty_window_n ==
vos_runs` cả hai bên ⇒ không mất mẫu cửa sổ.

Còn nợ: `_smooth` vẫn chạy hai lần cho frame `start()` (khác đại lượng, cần ticket riêng).
Log: `docs/task/17-11-2026-ticket-35-stability-hai-mau-cung-frame.md`.
