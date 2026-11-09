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
