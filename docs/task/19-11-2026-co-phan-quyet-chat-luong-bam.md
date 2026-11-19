# 19-11-2026 — Cờ phán quyết chất lượng bám (`ok | model_lost | drift_trend | not_measured`) — ticket #14

## Mục tiêu

HUD hiện đang có **hai con số rời nhau** (`drift_iou_p05` và `empty_frac_window`), người xem phải tự
ghép. Ticket #14 yêu cầu **một phán quyết** + lý do, tách được hai nguyên nhân khác hẳn nhau:
model **mất vật** (mask rỗng) ≠ ô hiển thị **lệch** ô VOS (mask vẫn có).

Điều kiện tiên quyết của ticket ("cần clip có p05 thấp **và** empty ≈ 0") đã đạt từ 19-11 bằng cách
tính p05 **trong khung vật còn trong hình** (8 lần chạy `binh1`, p05 = 0,000, empty 1,6–1,8 %) — xem
comment cuối trong ticket #14.

## Input

- `src/drift_samples.py`: `phan_vi()` (một cửa duy nhất cho mọi `*_p05`, ngưỡng 30 mẫu — ticket #23),
  `MIN_SAMPLES`.
- Số đã đo: `binh1` cả phiên p05 0,663–0,720 (khoẻ) · đoạn 57–108 p05 **0,000** với empty 1,6–1,8 %
  (ô hiển thị lệch) · `binh2` p05 0,000 với empty 11 % (model mất vật) · `vos_every=1` **không có** cặp
  nội suy (chưa đo được).

## Công việc đã thực hiện

1. **`src/tracking_health.py`** (module mới, hàm THUẦN — không import torch/cv2 ⇒ test headless):
   `phan_quyet(drift, empty, vos_every=…, truoc=…)` trả `{co, ly_do, p05, n, empty_frac, …}`;
   `cau_co()` dịch sang một câu tiếng Việt cho HUD. Ngưỡng **găng tay Schmitt 0,30 vào / 0,45 ra**
   (đúng plan 09-11), `empty ≥ 3 %` ⇒ `model_lost`, dưới ngưỡng đó ⇒ `drift_trend`.
   `vos_every < 2` ⇒ `not_measured` (không có nội suy LK để so); `n < 30` ⇒ `not_measured`.
2. **Nối vào phiên live**: `LiveTrackStats.suc_khoe` (dict) + `suc_khoe_cau`; thêm
   `_drift_empty_window` **song song** với `_drift_window` (cùng maxlen, append ở **cả hai** chỗ ghi)
   để `empty_frac` ứng đúng với `p05`; tính lại trong `_apply_drift_locked` (đã giữ `_stats_lock`).
3. **`status.json`** echo cả hai khoá; allowlist khoá trong test cập nhật (thêm khoá lạ phải đỏ).
4. **Web**: type `LiveStatus.suc_khoe`/`suc_khoe_cau`; `sucKhoeLine()` + `sucKhoeIsAlert()` trong
   `web/src/live.ts`; dòng `.hint.hint-warn` trong `LivePanel` (`data-testid="suc-khoe-line"`).

## Output / Kết quả

- **11 test Python** (`tests/test_tracking_health.py`): binh1 khoẻ ⇒ `ok` · đoạn 57–108 ⇒ `drift_trend`
  · binh2 ⇒ `model_lost` · `vos_every=1` ⇒ `not_measured` · `n = 29` ⇒ `not_measured` (không `ok`) ·
  Schmitt: p05 0,405 **giữ** `drift_trend` nếu đang bật, `ok` nếu đang tắt · thoát cờ khi p05 > 0,45 ·
  `empty` chưa đo ⇒ vẫn báo `drift_trend` nhưng **khai** `empty_chua_do` · `nan` ⇒ `ValueError` ·
  `CUA_SO == MIN_SAMPLES`.
- **6 test vitest mới** (72 tổng) cho `sucKhoeLine`/`sucKhoeIsAlert`, gồm ca âm: worker bản cũ ⇒
  `null` (**không** in "tốt"), raw (`mask_fps = 0`) ⇒ `null`, `ok` ⇒ `null`.
- **e2e trình duyệt thật**: 2 mục dương (`drift_trend`, `model_lost` hiện đúng câu + `class=hint
  hint-warn`) + 1 mục **âm** (`ok` ⇒ **0** dòng). `./run e2e` **PASS**, không lỗi JS.
- `./run lint` xanh · `./run test` **1502 passed** · `./run webtest` 72 passed · `npm run build` OK.

## Vấn đề & cách xử lý

- **Tên cờ phải theo đại lượng đo được**: `drift_iou` là IoU(ô **đã phát**, ô **VOS** sửa lại) ⇒ nó
  chỉ chứng minh hai ô **bất nhất**, chưa chứng minh LK sai. Vì thế trạng thái tên là `drift_trend`,
  không phải "LK trôi" (ghi trong docstring + comment UI); muốn nói "LK sai" phải có mIoU vs GT.
- **`empty` chưa đo ≠ `empty = 0`**: worker bản cũ không ghi cột `empty` trong CSV; nếu coi `None` là 0
  thì mọi ca `model_lost` sẽ bị dán nhãn `drift_trend` — sai đúng chỗ nguy hiểm nhất. Nay giữ
  `drift_trend` nhưng kèm `empty_chua_do: True` + câu nói rõ.
- **Ticket ghi `drift_n ≥ 100`** nhưng `n_drift` trong khung của phiên 11 s chỉ 21–61 ⇒ nếu giữ 100 thì
  cờ **không bao giờ bật**. Đã dùng **cửa sổ 30 mẫu** (bằng ngưỡng công bố p05 của repo, ticket #23) và
  ghi rõ trong docstring; `drift_n ≥ 100` chỉ còn là điều kiện cho **p05 cấp phiên** (`status.json`).
- **Ngưỡng 0,30/0,45 là KHỞI TẠO**: hiệu lực trên các clip đã đo (binh1 báo oan 0 % ở 0,30; ngưỡng 0,70
  cũ báo oan 100 % — ticket #15). Đã ghi trong docstring để không ai trích như ngưỡng chuẩn hoá.

## Next steps

- Khi có **mIoU vs GT** (12 frame `binh1`): đổi tên/khẳng định "LK sai" nếu số cho phép, và hiệu chuẩn
  lại `EMPTY_TRAN`.
- Cân nhắc đưa cờ vào `metrics.csv`/artifact để báo cáo có mốc thời điểm BẬT/TẮT (hiện chỉ có ảnh chụp
  hiện tại trong `status.json`).

## Tài liệu tham khảo

- `src/tracking_health.py`, `tests/test_tracking_health.py`, `web/src/live.ts`, `web/src/live.test.ts`
- ticket #14, #15, #23; `docs/plan/09-11-2026-chan-doan-chat-luong-bam.md`
