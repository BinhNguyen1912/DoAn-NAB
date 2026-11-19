# 19-11-2026 — `p05` **theo khung** (tái lập được bằng 1 lệnh) + mở khoá ticket 14

## Mục tiêu

1. Vá lỗ hổng do PR #46 tạo ra: phụ lục báo cáo công bố *"`p05` **trong khung** của `binh1` = 0,000
   với n = 60"*, nhưng **không công cụ nào tính được** đại lượng đó (`low_p05_low_empty` chạy trên cả
   dãy; `thong_ke_mau` chỉ có `mean`). Số không tái lập được bằng lệnh = đúng thứ repo này cấm.
2. Kiểm lại **điều kiện tiên quyết của ticket 14** ("có clip `p05 thấp` mà `empty ≈ 0`") — hoá ra
   **đã đạt** trên dữ liệu có sẵn, nếu lọc theo khung vật còn trong khung.

## Input

- `data/drift_samples_binh1_2026-11-14_*.csv` (19 file) + `.meta.json` bên cạnh.
- Khung frame theo `docs/demo-clip-va-o-chon.md`: `binh1` = `0:110` ∪ `165:262`.
- `scripts/analyze_drift_samples.py --frame-window` (đã có từ PR #18), hàm `tach_theo_cac_khung`.

## Công việc đã thực hiện

1. `src/drift_samples.py`:
   - `thong_ke_mau()` thêm `drift_iou_p05` (**đi qua `phan_vi`** ⇒ `None` khi < `MIN_SAMPLES` = 30),
     `drift_iou_p05_n`, `drift_iou_p05_nguong`;
   - hàm thuần mới `_dieu_kien_ticket_14(nhom)` → `{dat, ly_do}` với **3 trạng thái**;
   - `tach_theo_cac_khung()` trả thêm `dieu_kien_ticket_14.{trong_khung,ngoai_khung,ghi_chu}`.
2. `scripts/analyze_drift_samples.py`: in `p05` + `n_drift` cho cả hai bên khung, và in điều kiện
   ticket 14 với nhãn **`ĐẠT` / `không đạt` / `CHƯA ĐO`** (`None` **không** được in thành "không đạt").
3. Test: **5 test mới** — 4 trong `TestP05TheoKhung` + 1 test cấp lệnh
   (`test_in_dieu_kien_ticket_14_theo_khung_ba_trang_thai`); 3 test cũ cập nhật kỳ vọng dict (không
   nới assert). *(Bản log đầu ghi "6 test mới" — sai, đã đính chính theo review 19-11.)*

## Output / Kết quả

Lệnh tái lập (một dòng, không cần tính tay):

```
python scripts/analyze_drift_samples.py --frame-window 0:110 --frame-window 165:262 \
    data/drift_samples_binh1_2026-11-14_141609.csv
→ trong n=63 rỗng=0.016 p05=0.0 (n_drift=60) drift_tb=0.4929 · ngoài n=40 rỗng=0.9 p05=None
  · điều kiện ticket 14 ở trong_khung: ĐẠT
```

Nhóm theo **`meta.lenh`'s `--bbox`** (KHÔNG theo bbox dòng đầu CSV — dòng đầu là ô đã trôi), khung
`0:110` ∪ `165:262`:

| ô chọn | số lần chạy | phán quyết | `empty_frac` | `drift_iou_p05` | `n_drift` |
|---|---|---|---|---|---|
| `300,275,150,410` (chai) | 15 | **8 ĐẠT** | **1,6–1,8 %** | **0,000** | 54–61 |
|  |  | 5 không đạt (empty vượt trần 3 %) | **3,0–3,6 %** | 0,000 | 30–56 |
|  |  | 2 **CHƯA ĐO** (`image_size` 256/320) | 0,0 · 3,0 % | `None` | 21 · 29 |
| `104,308,209,287` (mặt) | 4 | 4 không đạt | 0,0 % | **0,725–0,730** | 55–60 |

⇒ **điều kiện tiên quyết của ticket 14 ĐẠT** (8/15 lần chạy ô chai): có `p05 < 0,30` **và**
`empty_frac < 3 %` cùng lúc, nên
cờ chẩn đoán nói được điều `empty_frac_window` **không** nói. Kết luận cũ ("p05 và empty đi cùng nhau
1:1", 13-11) là do tính **cả phiên** — ngoài khung thì chai đã rời khung nên `empty` cao.

- `./run lint` xanh · `./run test` **1410 passed** (5 deselected).

## Vấn đề & cách xử lý

- **Ba test cũ so sánh dict nguyên khối** ⇒ thêm khoá làm đỏ. Sửa bằng **cập nhật kỳ vọng đầy đủ**
  (kèm chú thích vì sao `p05` là `None` với 3 mẫu), **không** đổi sang `>=`/`in` để né.
- **Test cấp lệnh có nguy cơ "cổng danh nghĩa"** (assert chỉ khớp một chuỗi luôn được in). Đã diễn tập
  ngược **2 mutant**: (a) nhãn luôn `"không đạt"`; (b) in `p05=None` — **2/2 test đỏ**, khôi phục rồi
  xanh lại.
- ⚠ Lúc viết mục "Công việc" thì **chưa** biết ai sai ở các mẫu `drift_iou = 0`. Mục "Bổ sung 19-11
  (chiều)" ở cuối đã trả lời (đường nội suy LK đóng băng ô cũ; model vẫn bám chai, có rò mask sang cằm).

## Next steps

- Ticket 14 (đã claim, đã comment số): chốt lại `drift_n ≥ 100` — `n_drift` trong khung chỉ **54–61**/11 s
  ⇒ giữ 100 thì cờ **không bao giờ bật**; đề xuất cờ dùng **cửa sổ trượt 20–50 mẫu, ≥ 30 mẫu đo được**
  (ngưỡng công bố p05 của repo), còn `≥ 100` giữ cho p05 cấp phiên.
- Còn **thiếu phép đo trực tiếp**: thêm cột `bbox_hien_thi` + `lk_ok` vào `_log_drift_sample`
  (ticket #14) rồi chạy lại — chỉ khi đó mới được dùng chữ "chứng minh" cho cơ chế đóng băng ô.
- Tên cờ: `drift_trend` (enum, trung tính) — nhãn nguyên nhân "LK nội suy lệch" để riêng.

## Tài liệu tham khảo

- `docs/plan/09-11-2026-chan-doan-chat-luong-bam.md` · `.scratch/camera-ai-realtime/issues/14-*.md`
- `docs/demo-clip-va-o-chon.md` (ô + khung frame) · `AGENTS.md` §6 (ngưỡng 30 mẫu, `0/None ≠ đã đo`)

## Review độc lập PR #47 — 1 P1 + 3 P2 + 3 P3, đã sửa hết

| Mức | Nội dung | Xử lý |
|---|---|---|
| **P1** | Bảng log **trộn 2 tập mẫu**: ghi "ô chai · 8 lần chạy · empty 1,6–3,6 %". Thực tế ô chai có **15** lần chạy: 8 ĐẠT (empty 1,6–1,8 %), 5 không đạt (3,0–3,6 %), 2 CHƯA ĐO (n_drift 21 · 29 @256/320). Review cũng chỉ ra phải nhóm theo **`meta.lenh --bbox`** chứ không theo bbox dòng đầu CSV (ô đã trôi) | **Đã sửa** bảng thành 4 dòng; đếm lại bằng shell: **8 / 5 / 2** (review nói 8/4/3 — khác ở file `113932`: `n_drift = 30` nên **có** p05 = 0,000 và `empty = 0,030` ⇒ `False`, không phải `None`; đúng ca biên của P3 dưới) |
| **P2** | `_dieu_kien_ticket_14` bỏ qua `n_empty_do_duoc` ⇒ 1 dòng khai `empty=0` cạnh 59 dòng trống vẫn cho `ĐẠT` | **Đã sửa**: cần ≥ `min(MIN_SAMPLES, n)` mẫu khai `empty`, nếu không ⇒ `dat = None`; + **test mới** `test_dieu_kien_ticket_14_none_khi_qua_it_mau_khai_empty` (diễn tập ngược: bỏ guard ⇒ **đỏ**) |
| **P2** | Ghi chú trộn nguồn: `p05 0,663–0,720` là của **`status.json` phiên 08-11** (cửa sổ 200 mẫu, `empty_runs 0/267`), **không** phải p05 toàn dãy của CSV 14-11 (bằng 0,0) | **Đã sửa** `ghi_chu` nói rõ hai tập mẫu khác nhau, cảnh báo đừng gộp |
| **P2** | Script in `p05` bên `ngoai_khung` mà **không in `n_drift`** ⇒ `None` không phân biệt n=0 / n=1 / n=29 | **Đã sửa**: in `(n_drift=…)` cả hai bên |
| **P3** | `phan_vi` kiểm `nan/inf` **sau** cổng đếm mẫu ⇒ 29 giá trị `nan` trả `None`, 30 giá trị `nan` ném lỗi | **Đã sửa**: kiểm `isfinite` **trước** |
| **P3** | `0,03` hard-code lần 2; so trên `empty_frac` **đã làm tròn** (2,99 % ⇒ 0,030 ⇒ trượt) | **Đã sửa**: hằng số `MAX_EMPTY` dùng chung + so trên `n_empty / n_empty_do_duoc` **chưa làm tròn** |
| **P3** | Log ghi "6 test mới", thực tế **5** | đã đính chính ở mục Công việc |
| **P3** | Thiếu test cho nhánh `empty ≥ 0,03 ⇒ False` (đúng 5 lần chạy thật) | **Đã thêm** `test_dieu_kien_ticket_14_false_khi_empty_vuot_tran` (diễn tập ngược: bỏ vế `empty` ⇒ **đỏ**) |

Diễn tập ngược sau khi sửa: **4/4 mutant bị bắt** (nhãn luôn "không đạt" · in `p05=None` · bỏ guard đếm
mẫu `empty` · bỏ vế `empty < MAX_EMPTY`).

## Bổ sung 19-11 (chiều) — đường **nội suy (LK)** sai; model bám chai nhưng mask còn **rò sang cằm**

Câu hỏi treo: các mẫu `drift_iou = 0` là **LK sai** hay **model sai**? Hai phép đo **bổ trợ** dưới đây
cùng đường code path ⇒ kết luận: **ô hiển thị (đường nội suy) không theo vật**; model vẫn bám chai (có
một lỗi riêng: mask rò sang cằm ở frame 57). **Chưa** phải phép đo trực tiếp — CSV drift **không** có cột
`bbox_hien_thi`/`lk_ok` (xem Next steps).

Mọi số dưới đây lấy từ **một** lần chạy: `data/drift_samples_binh1_2026-11-14_141609.csv` · `bbox
300,275,150,410` · `image_size 192` · `vos_every 3` · `git_rev` theo `.meta.json` của file.

### (1) Mask của model bám chai — mask dump ở `--vos-every 1` (KHÔNG có LK)

`_use_lk = vos_every > 1` (`src/live_tracking.py:624`) và `--dump-mask-frames` bị **chặn** khi
`vos_every > 1` (`tools/live_worker.py:87-91`) ⇒ mask dump chỉ chạy được trên đường **không có LK**,
nên mask là **thô của model** (dump trước `_smooth`, `mask_smoothing = 1.0`):

```bash
python tools/live_worker.py --source data/binh1.mp4 --bbox 300,275,150,410 --image-size 192 \
    --vos-every 1 --dump-mask-frames 55,57,69,90,108 --dump-mask-dir docs/media/drift/masks \
    --out-dir /mnt/d/DOAN-NAB/.tmp_attr --stop-after-frames 115
```

`docs/media/drift/masks/manifest.json` (đã commit): `nguon = data/binh1.mp4`, `image_size 192`,
`image_size_hieu_luc 192`, `vos_every 1`, `mask_smoothing 1.0`, `bbox_xywh [300,275,150,410]`,
`frame_goc_cua_phien 0`, `ghi_chu = "mask THÔ của model (trước bước làm mượt)"`.

Ảnh: `docs/media/drift/binh1_f48-108_mask_vos_bam_dung.jpg` (4 panel: f57 · f69 · f90 · f108). Chú giải:
**xanh lá** = ô chọn ban đầu `300,275,150,410` (**cố định**, KHÔNG phải ô hiển thị); **vàng** = ô VOS@48 =
ô **đang hiển thị** (LK đóng băng, xem (2)); **hồng** = ô VOS của chính frame đó; **cyan** = viền mask.

Đọc ảnh: mask/ô hồng **nằm trên chai** ở cả 4 panel (chai được giơ cao rồi hạ xuống, đưa sang phải) —
nhưng ở **f57 mask phủ thêm phần cằm** của người (vòng cyan chạy qua cằm) ⇒ **không** được nói "model
đúng hoàn toàn": đúng vật chính, **rò sang cằm**. Ô vàng (ô hiển thị) nằm trên **bàn tay/áo**, không trên
chai.

### (2) Ô "đang hiển thị" = **ô VOS cũ đóng băng**, vì LK trả `not-ok`

Đường thật (`src/live_tracking.py:847-856`): mỗi frame phát, `_interp.reset(base_gray, base_bbox)` với
**base = lần VOS gần nhất** rồi **một** `update(gray)`; nếu `not ok` thì phát **`base_result`** (ô của lần
VOS gần nhất) — tức **không** phải ô LK cuối. Phát lại đúng cơ chế đó trên `141609`:

| base → frame | `lk_ok` | ô đang hiển thị | ô VOS của frame | `IoU` | `drift_iou` trong CSV |
|---|---|---|---|---|---|
| 48 → 51 | **False** | `266,212,392,637` (= VOS@48) | `181,139,315,621` | 0,204 | 0,0486 |
| 51 → 57 | **False** | `181,139,315,621` (= VOS@51) | `94,0,247,435` | 0,175 | **0,0000** |
| 48 → 57 | — | `266,212,392,637` (= VOS@48) | `94,0,247,435` | **0,000** | **0,0000** |
| 66 → 69 | **False** | `128,0,278,514` (= VOS@66) | `239,0,375,439` | 0,143 | **0,0000** |
| 105 → 108 | **False** | `370,342,504,779` (= VOS@105) | `549,276,701,758` | **0,000** | **0,0000** |
| 252 → 255 | **False** | `503,330,630,727` (= VOS@252) | `641,344,719,744` | **0,000** | **0,0000** |

⇒ **`lk_ok = False` liên tục** trong đoạn chai được giơ nhanh (48→51, 51→57, 66→69, 105→108, 252→255):
ô đang hiển thị **đứng yên ở ô VOS cũ** trong khi chai đã đi xa hàng trăm pixel ⇒ `drift_iou` sụp về 0.
Hai frame khớp **chính xác** `0,0000` (`IoU(VOS@48, VOS@57) = 0`, `IoU(VOS@105, VOS@108) = 0`).

**Giới hạn của phép phát lại (phải nói)**: ở f57/f69 CSV cho 0,0000 nhưng phát lại từ base 51 cho 0,175 —
vì ở đường **đa luồng**, `base` tại lúc **phát** frame 57 phụ thuộc việc VOS@51 đã kịp về hay chưa; phát
lại tuần tự không tái lập được thứ tự đó. Bản phát lại đầu tiên của mình (chain `update()` qua nhiều
frame) **sai cơ chế** — reviewer bắt đúng — nên đã bỏ; số ở bảng trên là bản đúng cơ chế (`reset(base)` +
một `update`). Muốn **chứng minh** (không chỉ suy ra) phải thêm cột `bbox_hien_thi` + `lk_ok` vào CSV.

### Hệ quả cho ticket 14

- `drift_trend` là **tên enum trung tính** ("ô hiển thị và VOS bất nhất") — giữ nguyên như ticket #14.
  **"LK nội suy lệch" là nhãn NGUYÊN NHÂN**, tách riêng; plan 09-11 đã xếp "bật cờ ngay" vào **phương án
  bị bác #3**, nay có bằng chứng để **mở lại** — kèm điều kiện: cờ chỉ nói *"ô hiển thị đã trượt"*,
  **không** nói "model sai" (model còn bám; mask có thể rò).
- Cờ bắt đúng thứ `empty_frac_window` **không thể** bắt: **mask không rỗng mà ô hiển thị đã trượt**.
- Cơ chế trên clip này: **vật được giơ nhanh**, có đoạn **chạm/vượt mép trên** (`y1 = 0`, frame 57–75);
  clip **không có** vật che ⇒ **không** được generalize thành "che khuất không sao".
