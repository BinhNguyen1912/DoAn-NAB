# 35: Frame `start()` đi qua `_record_vos` VÀ `_store_vos` ⇒ `stability` nhận 2 mẫu cho cùng 1 frame (một mẫu = 1,0)

**What to build:** Phát hiện của audit sau merge 17-11 (mục "ngoài phạm vi 4 PR", có từ trước): ở đường CÓ luồng VOS, frame `engine.start()` đi qua **cả** `_after_vos` (→ `_record_vos` → `_measure_stability`) **và** `_store_vos` (→ `_record_vos` → `_measure_stability`) cho **cùng một frame video** ⇒ `stability` nhận 2 mẫu cho 1 frame, và một trong hai là `IoU(mask, mask) = 1,0` (so mask với chính nó) ⇒ `stability` bị **thổi lên** ở đầu phiên, `stability_n` đếm dư 1.

Vì sao quan trọng: `stability` là số UI hiển thị ("nhấp nháy") và từng bị dùng sai một lần (AGENTS §6: `stability` KHÔNG phải thước đo độ chính xác). Một mẫu 1,0 ở đầu phiên làm số của phiên ngắn (≤ 30 mẫu) lệch thấy được.

Việc:
- Chặn tại nguồn: khi `_use_lk` (đường có luồng), `_after_vos` của frame `start()` **không** gọi `_measure_stability` (worker sẽ đo đúng một lần ở `_store_vos`), hoặc đánh dấu `seq` của `start()` là "đã ghi".
- Test: `vos_every=3` trên clip ngắn ⇒ `stability_n` không vượt số lần VOS thật; và giá trị `stability` không có mẫu 1,0 "miễn phí" ở đầu phiên.
- Đo trước/sau trên `data/binh1.mp4` (3 lần, ghi `stability` + `stability_n`) ⇒ nêu rõ chênh lệch có vượt ngưỡng nhiễu không.

**Status:** resolved

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Frame `engine.start()` không đóng góp 2 mẫu `stability` cho cùng một frame video (một mẫu là IoU(mask, mask) = 1,0)
- [x] Test: phiên `vos_every=3` clip ngắn ⇒ `stability_n` không vượt số lần VOS thật (hoặc test ghim giá trị `stability` không bị kéo lên ở đầu phiên)
- [ ] Ghi số đo trước/sau **3 lần chạy** mỗi bên — ĐÃ ĐO **1 phiên** mỗi bên (3 mẫu/phiên, 18-11 12:18/12:19); chưa đạt "3 lần", repo cũng chưa có ngưỡng nhiễu cho `stability` ⇒ kết luận hiện tại là "không phân biệt được"

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

## Bổ sung sau review vòng 1

**P1 (test không có răng)**: bất biến của phiên dùng `stability_n <= len(khac) - 1` mà `_iou_window` là
`deque(maxlen=10)` ⇒ vế phải 13 nhưng `stability_n` bị cắt ở 10 ⇒ **luôn đúng** kể cả khi có mẫu trùng.
Nay: nới cửa sổ (`deque(maxlen=100)`) + dùng **đẳng thức** + assert `goi[0] == 0` (lần đo đầu phải có
`frame_video` thật). Diễn tập ngược đã chạy: bỏ bước so trùng ⇒ 2/2 đỏ; `_after_vos` truyền `None` ⇒ đỏ.

**P2 (lý do "không phân biệt được" sai cơ chế)**: mask rỗng **không** xoá `_iou_window` (chỉ ngắt cặp);
`stability_n = 10` vì deque **bão hoà**, và `worker_status.stability = 0,0` là "lần VOS cuối rỗng"
(`lost_streak` 4–6). Số của phiên là `mau_cuoi`: **0,680 ± 0,032** (trước) vs **0,694 ± 0,034** (sau),
chênh 0,014 < std ⇒ vẫn "không phân biệt được" nhưng **lý do đã đúng**.

P3 đã sửa: comment nói sai nguồn `frame_video=None` (thực ra chỉ khi `_seq_frame` bị prune, fail-safe =
đo bình thường); `measure_live_relay` đặt thư mục ảnh theo **giờ** (trước đây theo ngày ⇒ lần "sau" ghi
đè ảnh lần "trước"); log thêm danh sách file thay đổi + ngày giờ đo.
