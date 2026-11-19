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

## Bổ sung 19-11 (chiều) — GIẢ THUYẾT về cơ chế `drift_iou = 0` (bằng chứng **bổ trợ**, chưa đo trực tiếp)

Câu hỏi treo: `drift_iou = 0` là **đường nội suy (LK) sai** hay **model sai**? Kết luận dưới đây là
**giả thuyết có bằng chứng bổ trợ**, KHÔNG phải phép đo trực tiếp: CSV drift **không** ghi lại ô đang
hiển thị (`bbox_hien_thi`) hay trạng thái LK (`lk_ok`) — chỉ có ô **VOS** của từng lần chạy.

Mọi số về `drift_iou` lấy từ **một** lần chạy: `data/drift_samples_binh1_2026-11-14_141609.csv`
(`bbox 300,275,150,410`, `image_size 192`, `vos_every 3`, `.meta.json`: `git_rev ab18c8b`,
`git_dirty_code false`).

### (1) Mask của model bám chai — mask dump ở phiên KHÁC (`--vos-every 1`)

`_use_lk = vos_every > 1` (`src/live_tracking.py:624`) và `--dump-mask-frames` bị **chặn** khi
`vos_every > 1` (`tools/live_worker.py:87-91`) ⇒ mask dump chỉ chạy được trên đường **không có LK**,
mask là **thô của model** (dump trước `_smooth`, `mask_smoothing = 1.0`):

```bash
python tools/live_worker.py --source data/binh1.mp4 --bbox 300,275,150,410 --image-size 192 \
    --vos-every 1 --dump-mask-frames 55,57,69,90,108 --dump-mask-dir docs/media/drift/masks \
    --out-dir /mnt/d/DOAN-NAB/.tmp_attr --stop-after-frames 115
```

⚠ **Hai giới hạn phải nói**: mask này ở phiên `vos_every=1`, **không phải** phiên sinh ra `drift_iou`
(`vos_every=3`), và SAM 2 **không tất định** (AGENTS §6) ⇒ mask **không** chứng minh được model bám
đúng *trong chính phiên kia*; đây là **corroboration** (cùng clip, cùng ô chọn), không phải mIoU vs GT.
`manifest.json` (đã commit) có `nguon`, `image_size 192`, `image_size_hieu_luc 192`, `vos_every 1`,
`mask_smoothing 1.0`, `bbox_xywh [300,275,150,410]`, `frame_goc_cua_phien 0` — nhưng **không** có
`git_rev` (writer `_write_mask_manifest` không phát khoá đó): dump này chạy trên cây `d2cd01a`+docs.

Ảnh (`python scripts/ve_anh_drift_binh1.py ...` — script đã commit, chạy lại ra đúng file đó):
`docs/media/drift/binh1_f48-108_mask_vos_bam_dung.jpg`, **4 panel** f57 · f69 · f90 · f108. Chú giải:

| màu | là gì |
|---|---|
| xanh lá | ô chọn ban đầu `300,275,150,410` — **cố định**, KHÔNG phải ô hiển thị |
| vàng | ô VOS của **base 48** — **mốc so sánh cố định** (chỉ trùng ô đang hiển thị ở f57/f108, xem (2)) |
| hồng | ô VOS của **chính frame đó** (từ CSV, phiên `vos_every=3`) |
| cyan | viền mask của model (từ PNG, phiên `vos_every=1`) |

Đọc ảnh: ô hồng + mask **nằm trên chai** ở cả 4 panel, **trừ** một lỗi thật: ở **f57 mask phủ thêm
phần cằm** (vòng cyan chạy qua cằm; blob xuống ~y≈510 trong khi hộp CSV `y2 = 435`) ⇒ **không** được nói
"model đúng" trần trụi — đúng vật chính, **rò sang cằm**. Ô vàng nằm trên **bàn tay/áo** ở f57/f108;
ở f69/f90 chai **chồng** ô vàng (109 px / 93 px) nên trông "gần đúng" — đừng đọc ảnh thành "LK bám tốt".

### (2) Bản phát lại theo đúng cơ chế pipeline — **chỉ 3 cặp khớp CSV**

Script (đã commit): `scripts/replay_lk_frame.py` — `reset(base_gray, base_bbox)` + **một** `update`,
`not ok ⇒` phát **ô base** (`src/live_tracking.py:847-856`), IoU tính bằng `_bbox_iou` (**toạ độ bao gồm
+1**, cùng công thức sinh ra cột `drift_iou`):

```bash
python scripts/replay_lk_frame.py --csv data/drift_samples_binh1_2026-11-14_141609.csv \
    --source data/binh1.mp4 --cap 48:51 51:57 66:69 105:108 252:255 48:57
```

```
 base→frame  lk_ok          bbox_hien_thi            VOS@frame    IoU     CSV khớp
 48→51     False        266,212,392,637        181,139,315,621 0.2075  0.0486 KHÔNG
 51→57     False        181,139,315,621           94,0,247,435  0.177     0.0 KHÔNG
 66→69     False          128,0,278,514          239,0,375,439 0.1461     0.0 KHÔNG
105→108    False        370,342,504,779        549,276,701,758    0.0     0.0 CÓ
252→255    False        503,330,630,727        641,344,719,744    0.0     0.0 CÓ
 48→57     False        266,212,392,637           94,0,247,435    0.0     0.0 CÓ
```

**Đọc đúng bảng này** (đây là chỗ bản trước của mình sai, review vòng 2 bắt):

- `lk_ok` là trạng thái **của bản phát lại**, không phải số đo của phiên ⇒ chỉ được dùng khi cặp đó
  **khớp CSV**. **3 cặp khớp** (48→57, 105→108, 252→255): `IoU(ô base, ô VOS) = 0` ⇒ `drift_iou = 0`.
  Đây là bằng chứng *"ô đang hiển thị = ô của một lần VOS CŨ, không theo vật"*.
- **3 cặp KHÔNG khớp** (48→51, 51→57, 66→69) ⇒ bản phát lại **không tái lập** được phiên đó. Không phải
  lỗi số học mà do **đường đa luồng**: `base` tại lúc *phát* một frame phụ thuộc kết quả VOS trước đã về
  chưa (CSV còn **thiếu dòng** `seq 19`/frame 54 và `seq 87`/frame 258 — ủng hộ "VOS@51 về muộn").
- Vì vậy **không** được nói "`lk_ok = False` liên tục". Ở frame 51 `drift_iou = 0,0486` **không khớp**
  với ô base nào (VOS@48 → 0,2075; VOS@45 → 0,0455; VOS@42 → 0,0187) ⇒ nhiều khả năng LK trả `ok = True`
  với ô **đã trượt**, tức **hai cơ chế**: (a) LK "ok" nhưng trượt (f51); (b) LK `not-ok` ⇒ phát ô base
  (f57/f108/f255, khớp 0,0000).

### Hệ quả cho ticket 14

- `drift_trend` là **tên enum trung tính** ("ô hiển thị và VOS bất nhất") — giữ như ticket #14.
  **"LK nội suy lệch" là nhãn NGUYÊN NHÂN**, tách riêng; plan 09-11 xếp "bật cờ ngay" vào **phương án bị
  bác #3**, nay có bằng chứng **bổ trợ** để **mở lại**, kèm điều kiện: cờ chỉ nói *"ô hiển thị đã trượt"*,
  **không** nói "model sai".
- Cờ bắt đúng thứ `empty_frac_window` **không thể** bắt: **mask không rỗng mà ô hiển thị đã trượt**.
- Trên clip này: **vật giơ nhanh**, có đoạn **chạm/vượt mép trên** (`y1 = 0` ở f57–75, f78 `y1 = 35`);
  clip **không có** vật che ⇒ **không** generalize thành "che khuất không sao".
- **Muốn nói "chứng minh"** thì phải thêm cột `bbox_hien_thi` + `lk_ok` vào `_log_drift_sample` (ticket
  #14) rồi chạy lại — hiện chưa có.

## Review độc lập PR #48 — 2 vòng

| Vòng | Mức | Nội dung | Xử lý |
|---|---|---|---|
| 1 | **P1** | Bản phát lại **chain** `LkBoxTracker.update()` qua nhiều frame ⇒ sai cơ chế (pipeline `reset(base)` mỗi frame, `not ok` ⇒ ô base); số `IoU = 0,158` so hai đại lượng khác nhau | **Sửa**: bỏ số đó, viết `scripts/replay_lk_frame.py` đúng cơ chế, `_bbox_iou` +1 |
| 1 | **P1** | Trộn **3 cấu hình** (ô start `120551`/256/every3, mask `192/every1`, drift `192/every3`) + danh sách frame là hợp của 2 file | **Sửa**: chỉ dùng `141609` (192/every3) cho số drift; mask tách riêng, nêu lý do bị chặn ở `every>1` |
| 1 | P2 | Ảnh: mô tả 6 panel (thật 5), ô xanh **cố định** bị đọc thành ô hiển thị | **Sửa**: caption nêu rõ từng màu; vẽ lại có ô base |
| 1 | P2 | Bỏ chữ "model đúng" trần trụi (chỉ là kết luận bằng mắt, không phải mIoU) | **Sửa**: "đúng vật chính, **rò sang cằm** ở f57" |
| 1 | P2 | Lẫn `drift_trend` (enum) với "LK nội suy lệch" (nhãn nguyên nhân) | **Sửa**: tách hai thứ, dẫn plan "phương án bị bác #3" |
| 1 | P2 | "chỉ chuyển động nhanh" bỏ mất điều kiện vật chạm/vượt mép khung | **Sửa**: nêu `y1 = 0` ở f57–75 |
| 1 | P3 | "chứng minh bằng 2 phép đo độc lập" quá mức; Next steps lỗi thời; mask PNG ở `/tmp` (WSL dọn) | **Sửa**: "bổ trợ"; PNG + manifest **commit** vào `docs/media/drift/masks/` |
| **2** | **P1** | Nhãn `lk_ok` trình bày như **số đo**; dòng 48→51 khai `False` ⇒ ô hiển thị = base ⇒ IoU phải 0,2075, nhưng CSV ghi 0,0486 ⇒ tại f51 LK **ok mà trượt**. Chú giải ảnh khẳng định vàng = ô hiển thị cho cả 4 panel, mâu thuẫn với bảng (f108 ô hiển thị là VOS@105) | **Sửa**: ghi `lk_ok` là "của bản phát lại"; bảng có cột **khớp CSV** (3 CÓ / 3 KHÔNG); nêu **2 cơ chế**; vàng = "mốc so sánh cố định", chỉ trùng ô hiển thị ở f57/f108 |
| **2** | P2 | Nhãn f69 `0.289` sai (đúng 0,281 — chép tay); ảnh **không có script** sinh ⇒ không tái lập | **Sửa**: commit `scripts/ve_anh_drift_binh1.py`, nhãn tính từ chính ô đã vẽ (0,281) |
| **2** | P2 | Bảng phát lại **không có script/lệnh** ⇒ không tái lập | **Sửa**: `scripts/replay_lk_frame.py` + dán lệnh + output |
| **2** | P2 | Log thiếu bảng review PR #48 | **đã thêm** (bảng ngay trên) |
| **2** | P3 | "hai frame khớp" → **ba**; dùng IoU thường thay `_bbox_iou`; f57/f69 gộp 1 số; "ô vàng trên tay/áo" chỉ đúng f57/f108; mask `55` không dùng | **Sửa**: ba cặp; dùng `_bbox_iou`; tách f57/f69; thêm "ở f57/f108"; nói rõ `mask_000055` là dự phòng |
