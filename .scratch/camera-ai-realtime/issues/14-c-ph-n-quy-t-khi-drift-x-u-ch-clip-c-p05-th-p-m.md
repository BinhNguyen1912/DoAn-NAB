# 14: Cờ phán quyết khi drift xấu — CHỜ clip có p05 thấp mà empty ≈ 0

**What to build:** Thêm cờ chẩn đoán (`ok | model_lost | drift_trend | not_measured`) vào `status.json` → API live → UI, với găng tay Schmitt (vào p05 ≤ 0,30 / ra > 0,45) và điều kiện `drift_n ≥ 100`.

ĐIỀU KIỆN TIÊN QUYẾT (đừng làm trước): phải có **một clip cho p05 thấp mà `empty_frac_window` ≈ 0**. Hiện chưa có: trên cả 3 clip đã đo, p05 và tỉ lệ mask rỗng đi cùng nhau 1:1 (binh1 0/798 = 0 % → p05 0,663–0,720; simloss 16/233 = 6,9 % → 0,644; binh2 26/233 = 11,2 % → 0,000) ⇒ cờ "LK nội suy lệch" sẽ chỉ là bản sao của `empty_frac_window`, tức claim vượt dữ liệu (AGENTS §6).

Quyết định + số đo: `docs/plan/09-11-2026-chan-doan-chat-luong-bam.md`.

**Blocked by:** None (can start immediately)

**Status:** claimed

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

19-11: **ĐIỀU KIỆN TIÊN QUYẾT ĐÃ ĐẠT** — không cần clip mới, dữ liệu đã có trong repo. Cách tìm: lọc CSV drift theo **`--frame-window`** (khung vật còn trong khung) rồi mới tính p05, thay vì tính cả phiên.

Số (CSV `data/drift_samples_binh1_2026-11-14_*.csv`, khung `0:110` ∪ `165:262`, tính trên các dòng TRONG khung):

| nhóm | số lần chạy | `empty` trong khung | `drift_iou_p05` | `n_drift` |
|---|---|---|---|---|
| ô **chai** (`288,287,431,734` x1y1x2y2 ≈ `300,275,150,410`) | **8** | **1,6–3,6 %** | **0,000** | 54–61 |
| ô **khuôn mặt** (`109,330,333,662`) | 4 | 0,0 % | **0,725–0,730** | 55–60 |

⇒ có **p05 < 0,30 với `empty_frac_window` < 3 %** ⇒ cờ nói được điều `empty_frac_window` **không** nói (trước 13-11 kết luận "p05 và empty đi cùng nhau 1:1" là do tính **cả phiên**: ngoài khung thì chai đã rời khung nên `empty` cao).

Mẫu `drift_iou = 0` **tái lập giữa các lần chạy** (cùng frame, cùng chỗ): `57, 69, 75, 105, 108, 171, 255` — ô `≈ 93,0,247,437` … `378,0,526,484`, tức ô **chạm mép trên** (`y1 = 0`). `binh1` đoạn **57–108** là "ca xấu" thật, `empty = 0` suốt đoạn đó (mask **không** rỗng).

⚠ **Nhưng tên cờ phải theo đại lượng đo được**: `_log_drift_sample` ghi `bbox = result.bbox` = ô của **VOS**, nên `drift_iou = 0` chỉ chứng minh *ô hiển thị (LK) và ô VOS không giao nhau* — ở các mẫu này **ô VOS** mới là cái chạm `y1 = 0`, chưa chứng minh LK sai. Trước khi đặt tên "LK nội suy lệch" (§plan 09-11) phải chứng minh ai sai: chạy 1 phiên `--dump-mask-frames` phủ frame 50–110 rồi so mask vs ô hiển thị. Nếu không, gọi là **`drift_trend`** = "ô hiển thị và VOS bất nhất", đúng như số đo.

Cũng phải chốt lại `drift_n ≥ 100`: `n_drift` **trong khung** của một lần 11 s chỉ 54–61 ⇒ nếu giữ 100 thì cờ **không bao giờ bật** trên dữ liệu này. Đề xuất: cờ chạy trên **cửa sổ trượt 20–50 mẫu** (đúng khuyến nghị 13-11) với ≥ **30** mẫu đo được (ngưỡng công bố p05 của repo), còn `drift_n ≥ 100` giữ cho **p05 cấp phiên** — hai đại lượng khác tập mẫu, phải nói rõ trong tài liệu.
