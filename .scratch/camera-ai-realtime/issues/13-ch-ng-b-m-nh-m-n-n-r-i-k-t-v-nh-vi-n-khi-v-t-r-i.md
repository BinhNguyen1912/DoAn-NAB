# 13: Chống "bám nhầm nền rồi kẹt vĩnh viễn" khi vật rời khỏi khung

**What to build:** Ca thật người dùng gặp: remote/ly/chén/bút ra khỏi khung rồi vào lại thì không được focus lại.

Đo trên fixture (vật bị xoá hẳn f10–17, image_size 320):
- f10 mask rỗng, `score=-4,98` → f11 `lost` ✅
- **f12 bám NHẦM vào nền: mask 782 px, `score=+19,40` (giả), reid=0,50** → khoá vào nền
- f13–f22 mask ~1500 px với score giảm dần (+1,77 → -0,94) → **không bao giờ tự sửa**, vì hệ thống chỉ coi là mất dấu khi mask RỖNG.

Ba sửa:
1. `lost_score_threshold` (mặc định 0.0): "còn thấy vật" = mask không rỗng **VÀ** score > ngưỡng → SAM 2 tưởng tượng mask vẫn bị coi là mất dấu.
2. `reid_reacquire_confirm` (mặc định 2): ứng viên phải khớp cùng một chỗ 2 frame liên tiếp.
3. `reid_verify_frames` (mặc định 2): sau khi bám lại phải kiểm chứng — mask mới không giống vật → `engine.reset()` + về LOST.

Kết quả sau sửa: f12–f17 vẫn `reacquiring` và LOẠI ứng viên nền 0,50; f18 khớp 0,93; **f19 bám lại đúng vật (0,94)** rồi tiếp tục tracking.

Không làm: đổi backbone, thêm model, đổi ngưỡng mặc định của cue mặt.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Mất dấu khi `score ≤ lost_score_threshold` (không chỉ mask rỗng) — đo: SAM 2 trả mask 782 px nhưng score -4,98
- [x] Ứng viên phải khớp CÙNG MỘT CHỖ `reid_reacquire_confirm` frame liên tiếp mới nhận lại
- [x] Sau khi nhận lại, kiểm chứng `reid_verify_frames` frame; mask không giống vật → reset engine + về LOST (không kẹt trên vùng nhầm)
- [x] Config + CLI: `lost_score_threshold`, `reid_reacquire_confirm`, `reid_verify_frames`
- [x] Test: mask giả + score âm vẫn là mất dấu; xác nhận 2 frame; bám nhầm → tự bỏ
- [x] Fixture kiểm chứng: vật bị xoá f10–17 → f19 bám lại đúng (reid 0,94), không bám nhầm nền ở f12 (0,50)
- [x] `pytest -m "not slow"` + `ruff check .` xanh
