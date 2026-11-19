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
- ⚠ **Chưa chứng minh được ai sai** ở các mẫu `drift_iou = 0` (frame 57/69/75/105/108/171/255): CSV
  ghi `bbox = result.bbox` = ô của **VOS**, nên số liệu chỉ nói *ô hiển thị (LK) và ô VOS không giao
  nhau*, **chưa** nói LK sai. Tên cờ "LK nội suy lệch" của plan 09-11 **chưa được dùng** cho tới khi có
  phiên `--dump-mask-frames` phủ frame 50–110.

## Next steps

- Ticket 14 (đã claim, đã comment số): chốt lại `drift_n ≥ 100` — `n_drift` trong khung chỉ **54–61**/11 s
  ⇒ giữ 100 thì cờ **không bao giờ bật**; đề xuất cờ dùng **cửa sổ trượt 20–50 mẫu, ≥ 30 mẫu đo được**
  (ngưỡng công bố p05 của repo), còn `≥ 100` giữ cho p05 cấp phiên.
- Chứng minh attribution (LK vs VOS) bằng `--dump-mask-frames` ⇒ rồi mới đặt tên cờ.

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

## Bổ sung 19-11 (chiều) — **AI SAI** ở các mẫu `drift_iou = 0`: **LK**, không phải model

Đây là câu hỏi treo từ đầu phiên ("chưa chứng minh được ai sai"). Đã chứng minh bằng **hai phép đo độc lập**.

### (1) Mask của model BÁM ĐÚNG chai — kiểm bằng ảnh

```bash
python tools/live_worker.py --source data/binh1.mp4 --bbox 300,275,150,410 --image-size 192 \
    --vos-every 1 --dump-mask-frames 55,57,60,63,69,72,75,80,90,105,108 \
    --dump-mask-dir /tmp/attr/masks --out-dir /tmp/attr --stop-after-frames 115
```

`--vos-every 1` ⇒ **không có LK**, nên mask là 100 % của model. Bbox của mask (`cv2.imread` + `np.nonzero`):

| frame | bbox mask (x1,y1,x2,y2) | chai ở đâu trong frame |
|---|---|---|
| 55 | `110,17,255,592` | đang **giơ cao**, sát mép trên |
| 57 | `95,0,235,526` | chạm mép trên (đúng — chai bị giơ quá khung) |
| 69 | `240,0,376,445` | vẫn trên cao |
| 90 | `298,342,441,831` | đã **hạ xuống**, mask theo kịp |
| 108 | `552,279,700,752` | đưa sang **phải**, mask theo kịp |

Ảnh chồng mask + ô chai gốc: `docs/media/drift/binh1_f48-108_mask_vos_bam_dung.jpg` ⇒ mask **luôn nằm trên
chai**, kể cả những frame có `drift_iou = 0`. Nghĩa là **model đúng**, không phải "model lệch".

### (2) LK **mất dấu** trước đó — phát lại bằng chính `src/light_tracker.py`

Đặt mốc ở ô VOS **thật** của frame 48 (`268,204,392,634`), rồi cho `LkBoxTracker` chạy tiếp từng frame:

```
LK frame 51: box = (185,155,309,585)
LK MẤT DẤU ở frame 52
IoU(LK@57, VOS@57) = 0,158  ← so với drift_iou = 0,0000 trong CSV
```

⇒ **LK trượt/mất dấu từ frame 52** (chai được giơ lên **rất nhanh**), nên ô hiển thị là ô cũ; VOS ở frame 57
khoá lại đúng chỗ chai (sát mép trên) ⇒ hai ô **không giao nhau** ⇒ `drift_iou = 0` trong khi `empty = 0`
(mask vẫn có, và đúng). Không mâu thuẫn với (1): (1) nói *mask model* đúng, (2) nói *ô LK* sai.

### Hệ quả cho ticket 14

- Tên cờ **`drift_trend` = "LK nội suy lệch"** của plan 09-11 **đã có bằng chứng** — không còn là suy đoán.
- Cờ này bắt đúng thứ `empty_frac_window` **không thể** bắt: **mask không rỗng mà ô hiển thị đã trượt** —
  đúng loại lỗi làm người xem thấy ô bao lệch khỏi vật dù HUD báo "ổn định".
- Cơ chế là **chuyển động nhanh** (giơ chai lên), **không phải che khuất** — báo cáo phải nói đúng thế,
  không được gọi đây là "ca che khuất" của ticket #14.
