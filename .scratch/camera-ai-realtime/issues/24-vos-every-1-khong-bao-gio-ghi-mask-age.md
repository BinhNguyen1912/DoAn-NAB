# 24: `vos_every = 1` không bao giờ ghi `mask_age_total_ms` (HUD im lặng ở cấu hình đơn luồng)

**What to build:** `_note_mask_age` chỉ được gọi ở đường **có luồng VOS** (`_result_threaded`). Đường
`vos_every = 1` chạy inline (`_after_vos`) nên `mask_age_total_ms = None` suốt phiên ⇒ HUD (#8) không
hiện tuổi mask, và `bang_cau_hinh --every 1` / `ab --b vos_every=1` sẽ có `mask_age_p95 = None`.
Không sai về ngữ nghĩa (`None` ≠ 0) nhưng là lỗ hổng của chính việc #8 ở cấu hình đơn luồng — đúng cấu
hình đã dùng để đo mIoU fixture và các số "1 luồng 8,8 FPS".

**Cách làm:** trong `_after_vos`, gọi `_note_mask_age(0.0, vos_ms=result.elapsed_ms, pre_ms=...,
queue_ms=None, post_ms=...)` (age = 0 vì frame vừa VOS chính là frame đang hiển thị), hoặc ghi rõ trong
docs/HUD là `vos_every=1` không đo tuổi.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] `vos_every=1`, chạy 2 frame ⇒ `mask_age_total_ms` khác `None`, `age_n = 2` (test ghim)
- [x] Bảng cấu hình / A/B chạy `--every 1` không còn `mask_age_p95 = None` (hoặc docs nói rõ là chưa đo)

## Answer

Đã xong (17-11, `fix/mask-age-vos-every-1`, PR #27):

- `_after_vos` đo `post_ms` (dump mask + làm mượt) rồi gọi
  `_note_mask_age(0.0, vos_ms=result.elapsed_ms, pre_ms=result.pre_ms, queue_ms=0, post_ms=post_ms)`.
  `age = 0` vì frame vừa VOS **chính là** frame đang phát (không có frame chen giữa như đường LK).
- Cố ý **không** gọi `_measure_drift` ở đây: `vos_every = 1` không có nội suy LK ⇒ không có cặp
  (VOS ↔ nội suy) để so; bịa một mẫu drift là làm sai số `drift_iou`.
- Test: `vos_every=1` chạy 2 frame ⇒ `age_n == 2`, `mask_age_total_ms = vos + pre + post`, `p95 None`
  (2 < 30); test cũ `age_n` đổi kỳ vọng cho `every=1` (trước `age_n == 0`) và ghim thêm
  `mask_age_ms == 0` + `drift_n == 0`; thêm 1 test canh "age không phải thời gian cả vòng lặp".
- Đo thật (cây sạch, `data/bang_cau_hinh_2026-11-17_every1_metrics.json`, `git_rev 3cc0248`,
  `git_dirty_code false`, 3 lần × 60 frame, `image_size 192`, ô chai `300,275,150,410`):
  **9,33 ± 0,55 FPS phát = nhịp mask** · `vos_ms 87,33 ± 4,52` · `pre_ms 10,96 ± 1,85` ·
  **`mask_age_p95 109,9 ± 9,32`** (`age_n 60`) ⇒ `--every 1` không còn `mask_age_p95 = None`.
  *(Bản đo đầu tiên trên nhánh `1f0c89a` — 9,5 ± 0,5 · vos 82,1 · p95 105,53 — đã bị artifact mới
  thay thế sau khi sửa P1/P2 của review; số dùng là bộ 3cc0248 ở trên.)*
- Docs: `docs/so-lieu-bao-cao.md` (qua `REGISTRY` + `--check` xanh) và `AGENTS.md` §6 ghi số + cảnh
  báo "FPS phát của dòng đơn luồng không so được với 29,8 của `vos_every ≥ 2`".
