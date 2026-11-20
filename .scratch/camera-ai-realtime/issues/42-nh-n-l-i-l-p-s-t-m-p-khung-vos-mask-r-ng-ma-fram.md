# 42: Nhận lại lặp ở sát mép khung (VOS mask rỗng) + "ô ma" ở frame vật đã rời (gt_rong 196, 359)

**Type:** research

**Blocked by:** None (can start immediately)

## Question

Nợ để lại từ plan `docs/plan/21-11-2026-nhan-lai-vat-tren-live-va-demo-webcam.md` (việc P1/P3/P4 đã xong trong nhánh `feat/nhan-lai-vat-live`).

**Hai hiện tượng còn lại, đều đã ĐO:**

1. **Nhận lại lặp 3 lần liên tiếp** trên `binh2`: `reacquired` ở frame **172/175/178** (và 244). A/B thật (300 frame, @192, `--reid --reid-cue object`):
   - TRƯỚC vá `_reacquire` → 5 lần (172, 176, 180, 241, 245), **16** frame `lost`
   - SAU vá → 4 lần (172, 175, 178, 244), **13** frame `lost`
   ⇒ Vá P0 có tác dụng thật nhưng **nhỏ**, và "3 lần liên tiếp" **vẫn còn** ⇒ nguyên nhân là **VOS trả mask RỖNG khi vật sát mép khung** rồi mất dấu lại sau 3 frame, **không** phải cổng chống-nhảy `_is_suspicious_jump`. Artifact: `data/reid_ab_p1_2026-11-21_{truoc-va,sau-va}.csv`.

2. **"Ô ma" ở frame người tô khai KHÔNG có vật**: `ty_le_o_ma` (metric mới, `scripts/ab_o_hien_thi_vs_gt.py`) trên 4 frame `gt_rong` của `binh2_tay` (196, 294, 326, 359): sau khi có `bam`/ẩn ô, **294 và 326 đã hết ô**, nhưng **196 và 359 VẪN có ô** — ô VOS "tự tin sai", `bam = tracking`. Nền tảng: `_cap_nhat_bang_chung` chỉ dựa mask rỗng; khi SAM 2 trả mask non-empty trên nền thì không có tín hiệu nào để biết.

**Gợi ý hướng (chưa chốt, cần đo trước khi hứa):**
- (1) Dùng `ncc`/`score` của VOS: đoạn 165–240 của `binh2` VOS vẫn `tracking` với `score` **+5…+18** (âm bản = mất dấu) ⇒ `score` **không** bắt được ca này (đã đo 21-11). Ứng viên còn lại: độ bền mask qua N frame, diện tích mask vs EMA, hoặc chấp nhận và chỉ báo cáo.
- (2) Ở sát mép khung: thử hạ `lost_after_frames` cho vùng mép, hoặc học mẫu khi mask chạm mép (đã có `EDGE_MIN_AREA_FRAC`) để nhận lại ngay frame sau.

**Không được làm:** nới `max_mad`/`lk_scale` (đã A/B 3 lần trong #38/#40 và KHÔNG phân biệt được); claim "hybrid luôn bám được".
