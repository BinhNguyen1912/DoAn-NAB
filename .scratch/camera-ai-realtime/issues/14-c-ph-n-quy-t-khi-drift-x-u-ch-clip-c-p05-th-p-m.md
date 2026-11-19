# 14: Cờ phán quyết khi drift xấu — CHỜ clip có p05 thấp mà empty ≈ 0

**What to build:** Thêm cờ chẩn đoán (`ok | model_lost | drift_trend | not_measured`) vào `status.json` → API live → UI, với găng tay Schmitt (vào p05 ≤ 0,30 / ra > 0,45) và điều kiện `drift_n ≥ 100`.

ĐIỀU KIỆN TIÊN QUYẾT (đừng làm trước): phải có **một clip cho p05 thấp mà `empty_frac_window` ≈ 0**. Hiện chưa có: trên cả 3 clip đã đo, p05 và tỉ lệ mask rỗng đi cùng nhau 1:1 (binh1 0/798 = 0 % → p05 0,663–0,720; simloss 16/233 = 6,9 % → 0,644; binh2 26/233 = 11,2 % → 0,000) ⇒ cờ "LK nội suy lệch" sẽ chỉ là bản sao của `empty_frac_window`, tức claim vượt dữ liệu (AGENTS §6).

Quyết định + số đo: `docs/plan/09-11-2026-chan-doan-chat-luong-bam.md`.

**Blocked by:** None (can start immediately)

**Status:** claimed

- [x] Có ≥ 1 clip (che khuất đi ngang / LK trôi thật) cho `drift_iou_p05 < 0,30` với `empty_frac_window < 3 %`
- [x] Hàm thuần `src/tracking_health.py` (không import torch) + test: binh1 ⇒ `ok`, simloss/binh2 ⇒ `model_lost`, `vos_every=1` ⇒ `not_measured`
- [ ] `drift_n < 100` ⇒ luôn `not_measured` (không bật cờ từ mẫu ít)
- [x] Ghi rõ ngưỡng 0,30/0,45 là KHỞI TẠO, chưa hiệu lực ngoài các clip đã đo

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

19-11 (đính chính comment trên): bảng "8 lần chạy · empty 1,6–3,6 %" là **trộn 2 tập mẫu** — reviewer PR #47 bắt đúng. Số đúng, nhóm theo **`meta.lenh --bbox`** (không theo bbox dòng đầu CSV — dòng đầu là ô đã trôi), khung `0:110` ∪ `165:262`, tái lập bằng `python scripts/analyze_drift_samples.py --frame-window 0:110 --frame-window 165:262 data/drift_samples_binh1_2026-11-14_*.csv` (PR #47 đã merge, `main` = `0c1bac0`):

| ô chọn | lần chạy | phán quyết | `empty_frac` | `p05` | `n_drift` |
|---|---|---|---|---|---|
| `300,275,150,410` (chai) | 15 | **8 ĐẠT** | **1,6–1,8 %** | **0,000** | 54–61 |
|  |  | 5 không đạt (vượt trần 3 %) | 3,0–3,6 % | 0,000 | 30–56 |
|  |  | 2 **CHƯA ĐO** (@256/320) | 0,0 · 3,0 % | `None` | 21 · 29 |
| `104,308,209,287` (mặt) | 4 | 4 không đạt | 0,0 % | 0,725–0,730 | 55–60 |

⇒ tiêu chí 1 của ticket **ĐẠT**: 8 lần chạy cá biệt có `p05 < 0,30` **và** `empty < 3 %` cùng lúc. Lệnh trên in `· điều kiện ticket 14 ở trong_khung: ĐẠT` cho đúng 8 file đó.

Ba điều phải nhớ khi làm cờ:
1. **`p05 = 0,000` là phân vị thật**, không phải "2 mẫu xui": mỗi lần ĐẠT có **6–9 mẫu `drift_iou` đúng bằng 0** trên `n_drift` 54–61 (cần ≥ 4 mẫu 0 thì p05 mới bằng 0 với n ≈ 60).
2. **`empty` 3,0–3,6 % ⇒ KHÔNG đạt** — trần 3 % là ràng buộc thật (5/15 lần chạy trượt ở đây). Đừng nới trần để "cho đủ mẫu".
3. **`n_drift` trong khung chỉ 21–61** ⇒ `drift_n ≥ 100` (tiêu chí 3) **không thể đạt** với phiên 11 s. Cần quyết: hạ xuống ≥ 30 (ngưỡng công bố p05 của repo) cho **cờ**, giữ ≥ 100 cho **p05 cấp phiên** — hoặc đo phiên dài hơn (55 s cho `n_drift` ~250 nhưng phần lớn ngoài khung).

Chưa chứng minh được **ai sai** ở các mẫu `drift = 0` (frame 57/69/75/105/108/171/255, ô chạm `y1 = 0`): CSV ghi `bbox = result.bbox` = ô **VOS**, nên số liệu chỉ nói *ô hiển thị (LK) và ô VOS không giao nhau*. Attribution cần `--dump-mask-frames` phủ frame 50–110 — bước tiếp theo trước khi đặt tên cờ "LK nội suy lệch".

19-11: **cờ đã ship** — PR #54 merged (`main` = `cbf3b92`). `src/tracking_health.py` (hàm thuần) → `LiveTrackStats.suc_khoe` → `status.json` → DTO/HTTP → HUD (`data-testid="suc-khoe-line"`, `class="hint hint-warn"`).

**Tiêu chí 3 (`drift_n < 100 ⇒ not_measured`) KHÔNG tick — đã cố ý thay bằng ngưỡng KHÁC, ghi lại để không ai tưởng là đã đạt:** cờ dùng **cửa sổ 30 mẫu** (`CUA_SO = drift_samples.MIN_SAMPLES`), tức đúng ngưỡng công bố p05 của repo (ticket #23). Lý do: `n_drift` **trong khung** của phiên 11 s chỉ 21–61 ⇒ giữ 100 thì cờ **không bao giờ bật** trên dữ liệu đã có (đúng cảnh báo trong comment trên). `drift_n ≥ 100` chỉ còn là điều kiện cho **p05 cấp phiên** (`drift_iou_p05`, cửa sổ 200) — hai đại lượng KHÁC tập mẫu, đã ghi rõ trong `LiveStatus`/`LiveTelemetry`/schema/api.ts và trong docstring `tracking_health`.

Ngưỡng vào/ra 0,30/0,45 là **KHỞI TẠO** (tiêu chí 4): hiệu lực trên các clip đã đo (0,30 báo oan 0 % cửa sổ trên `binh1`; ngưỡng 0,70 cũ báo oan 100 % ở W ≥ 100 — ticket #15). Chưa hiệu chuẩn ngoài `binh1`/`binh2`.

**Review độc lập PR #54: 1 P0 + 4 P2, đã sửa hết.** P0 đáng nhớ: bản đầu chỉ nối tới `status.json`, còn DTO → route dựng **từng field** ⇒ `/api/live/status` **không** trả `suc_khoe` ⇒ HUD thật không bao giờ hiện, mà e2e vẫn "PASS" vì nó **mock** route. Nay có 3 test HTTP (1 ca worker bản cũ ⇒ `null`, không phải `ok`) + e2e hỏi **API thật**; diễn tập ngược: bỏ field ở `routes.py` ⇒ test đỏ.

Còn mở: **attribution** ở các mẫu `drift = 0` (frame 57/69/75/105/108/171/255, ô VOS chạm `y1 = 0`) — cần `--dump-mask-frames` phủ 50–110 để biết LK sai hay VOS sai; tới lúc đó tên `drift_trend` ("ô hiển thị và VOS bất nhất") là mức khẳng định đúng với đại lượng đo được. Cũng còn: hiệu chuẩn lại `EMPTY_TRAN`/`EMPTY_MIN_MAU` khi có mIoU vs GT.

19-11 (bổ sung): **mục "attribution" ở comment trên ĐÃ XONG** — làm ở PR #48, không cần chạy lại.

Kết luận: ở các mẫu `drift_iou = 0` của `binh1`, **LK sai, model đúng**. Hai phép đo độc lập:
1. Chạy phiên `vos_every=1` (KHÔNG có LK ⇒ mask là 100 % model) + `--dump-mask-frames`: bbox mask in ra f55 `110,17,255,592`, f57 `95,0,235,526`, f69 `240,0,376,445`, f90 `298,342,441,831`, f108 `552,279,700,752`; ảnh `docs/media/drift/binh1_f48-108_mask_vos_bam_dung.jpg` (mask đỏ chồng frame + ô chai xanh) cho thấy mask **luôn trên chai**.
2. Phát lại chính `src/light_tracker.py::LkBoxTracker` từ ô VOS thật của frame 48 (`268,204,392,634`): LK@51 = `185,155,309,585`, **mất dấu từ frame 52**, `IoU(LK@57, VOS@57) = 0,158` — CSV ghi `drift_iou = 0,0000` (khớp: hai ô không giao nhau).

⇒ vì thế tên `drift_trend` vẫn giữ trong CODE (đại lượng đo được chỉ nói "ô hiển thị và ô VOS bất nhất"), nhưng khi viết báo cáo cho `binh1` **được phép** nói nguyên nhân là LK trượt, kèm 2 bằng chứng trên. Đừng suy rộng ra clip khác khi chưa có phép kiểm tương tự.

Còn lại của ticket: hiệu chuẩn `EMPTY_TRAN`/`EMPTY_MIN_MAU` và (nếu muốn) đổi nhãn HUD thành "LK trượt" khi có mIoU vs GT xác nhận.
