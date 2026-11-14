# 23: Ngưỡng công bố phân vị (p05) có BA giá trị trong repo: 5 / 20 / 30 mẫu

**What to build:** `src/live_tracking.py` đã chốt `_STAT_MIN_SAMPLES = 30` (kèm lý do: "với n = 5, p05 ≈
min"; "nếu CSV công bố p05 từ 20 mẫu thì nó nói một điều mà status.json từ chối nói"). Nhưng hai script
mới tự đặt ngưỡng riêng: `scripts/score_miou.py` dùng **5** (⇒ artifact đang công bố `mIoU_p05 = 0,9239`
từ **5 frame**), `scripts/make_trajectory_media.py` dùng **20**.

**Vì sao cần xử lý:** cùng một đại lượng (`*_p05`) mà ba ngưỡng khác nhau ⇒ người đọc báo cáo không biết
con số p05 nào đáng tin. Đây là bẫy "số 0/None ≠ đã đo" phiên bản phân vị.

**Cách làm:** import `_STAT_MIN_SAMPLES` (hoặc `drift_samples.MIN_SAMPLES`) thay vì hằng riêng; nếu một
thước đo **phải** dùng ngưỡng khác (vd p05 cần ≥ 20 để có nghĩa) thì khai `NGUONG_P05` + lý do ngay tại
đó và in kèm `n` trong artifact.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Chỉ còn MỘT hằng ngưỡng cho phân vị (hoặc hằng riêng có lý do + test khoá giá trị)
- [ ] Artifact in `n` cạnh mọi `*_p05`; p05 có n < ngưỡng ⇒ `None` (không công bố)
- [ ] Test: `mIoU_p05` với 5 frame phải là `None` (hoặc ghi rõ "ngưỡng riêng = 5, lý do …"), không im lặng

## Comments

14-11 (review độc lập nhánh `feat/plan-con-lai`, P2): phát hiện khi đối chiếu 3 file cùng đại lượng.
