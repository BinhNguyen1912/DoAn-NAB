# 14: Cờ phán quyết khi drift xấu — CHỜ clip có p05 thấp mà empty ≈ 0

**What to build:** Thêm cờ chẩn đoán (`ok | model_lost | drift_trend | not_measured`) vào `status.json` → API live → UI, với găng tay Schmitt (vào p05 ≤ 0,30 / ra > 0,45) và điều kiện `drift_n ≥ 100`.

ĐIỀU KIỆN TIÊN QUYẾT (đừng làm trước): phải có **một clip cho p05 thấp mà `empty_frac_window` ≈ 0**. Hiện chưa có: trên cả 3 clip đã đo, p05 và tỉ lệ mask rỗng đi cùng nhau 1:1 (binh1 0/798 = 0 % → p05 0,663–0,720; simloss 16/233 = 6,9 % → 0,644; binh2 26/233 = 11,2 % → 0,000) ⇒ cờ "LK nội suy lệch" sẽ chỉ là bản sao của `empty_frac_window`, tức claim vượt dữ liệu (AGENTS §6).

Quyết định + số đo: `docs/plan/09-11-2026-chan-doan-chat-luong-bam.md`.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Có ≥ 1 clip (che khuất đi ngang / LK trôi thật) cho `drift_iou_p05 < 0,30` với `empty_frac_window < 3 %`
- [ ] Hàm thuần `src/tracking_health.py` (không import torch) + test: binh1 ⇒ `ok`, simloss/binh2 ⇒ `model_lost`, `vos_every=1` ⇒ `not_measured`
- [ ] `drift_n < 100` ⇒ luôn `not_measured` (không bật cờ từ mẫu ít)
- [ ] Ghi rõ ngưỡng 0,30/0,45 là KHỞI TẠO, chưa hiệu lực ngoài các clip đã đo

## Comments

13-11: **điều kiện tiên quyết vẫn CHƯA đạt, nay có số tái lập được** (công cụ đã merge trong PR #18, ticket 15).

Số: `python scripts/analyze_drift_samples.py --windows 20 50 100 200` → `data/drift_series_2026-11-13_132004_metrics.json`, khoá `p05_thap_va_empty` (hàm `low_p05_low_empty`, đếm trên trục lần VOS, cửa sổ 200 dòng, cần ≥ 100 mẫu đo được):
- `binh2` (VOS mất dấu thật): **158/158** cửa sổ có `p05 < 0,30`, nhưng **0** cửa sổ có mask rỗng < 3 % (`empty_frac` cả phiên 21,8 %) ⇒ p05 thấp vẫn dính 1:1 với "model mất vật" ⇒ thêm cờ "LK nội suy lệch" lúc này chỉ là bản sao của `empty_frac_window`.
- `binh1` (khoẻ): 0 cửa sổ `p05 < 0,30` ⇒ không có gì để bắt.
- Clip "LK trôi thật" (vật đi qua vùng che khuất mà model vẫn thấy vật) **vẫn chưa có** ⇒ chưa được code cờ.

Kèm 2 số dùng được cho ngưỡng khi mở lại ticket: ngưỡng 0,70 đăng ký trước 08-11 **bị bác** (trên binh1 báo động 100 % cửa sổ ở W ≥ 100, 74–84 % ở W=50, 45–47 % ở W=20); ngưỡng 0,30 có 0 % báo oan trên binh1. Độ trễ phát hiện ≈ độ dài cửa sổ (15/45/95/195 mẫu ở W=20/50/100/200) ⇒ cờ nên dùng cửa sổ 20–50, không phải 200.
