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

**Status:** claimed

- [x] Chỉ còn MỘT hằng ngưỡng cho phân vị (hoặc hằng riêng có lý do + test khoá giá trị)
- [x] Artifact in `n` cạnh mọi `*_p05`; p05 có n < ngưỡng ⇒ `None` (không công bố)
- [x] Test: `mIoU_p05` với 5 frame phải là `None` (hoặc ghi rõ "ngưỡng riêng = 5, lý do …"), không im lặng

## Comments

14-11 (review độc lập nhánh `feat/plan-con-lai`, P2): phát hiện khi đối chiếu 3 file cùng đại lượng.

## Answer

Đã xong (17-11, `feat/p05-mot-nguong`): mọi phân vị công bố ra artifact đi qua **một** cửa —
`phan_vi()` trong `src/drift_samples.py` với `MIN_SAMPLES = 30`, ghim bằng test bằng
`live_tracking._STAT_MIN_SAMPLES`:

- `scripts/score_miou.py`: bỏ hằng `5` → dùng `phan_vi`; artifact có thêm `mIoU_p05_n` +
  `mIoU_p05_nguong`; CLI in "CHƯA CÔNG BỐ (n < 30)" thay vì im lặng bỏ dòng.
- `scripts/make_trajectory_media.py`: bỏ hằng `20` → dùng `phan_vi`; `thong_ke` (kèm `nguong_p05`)
  nay nằm trong file provenance JSON, không chỉ stdout.
- `static_control`: tiêu chí đạt vẫn dùng `min_samples = 20` (ticket 15), nhưng `p05` chỉ công bố từ
  30 mẫu.

Hệ quả đã kiểm trên artifact thật (cây sạch, `git_dirty_code = false`):
`data/miou_binh1_hopbao_2026-11-15_metrics.json` → `mIoU_p05 = None`, `mIoU_p05_n = 12`, ngưỡng 30;
`docs/media/traj/binh1_vat_ra_khung.json` → `drift_iou_p05 = 0,0` vẫn công bố (`drift_n = 271`), `nguong_p05 = 30`.
Artifact `miou_synthetic_2026-11-14` (n = 5, p05 = 0,9239) sinh TRƯỚC thay đổi và mask của nó đã mất
(`/tmp/demo_gt4`) ⇒ không sinh lại được; đã ghi rõ trong `docs/so-lieu-bao-cao.md` là **cấm trích**
p05 của nó.

Test: 8 test mới; đã kiểm "có răng" — hạ `MIN_SAMPLES` về 20 ⇒ 4 test đỏ, về 5 ⇒ 6 test đỏ.
