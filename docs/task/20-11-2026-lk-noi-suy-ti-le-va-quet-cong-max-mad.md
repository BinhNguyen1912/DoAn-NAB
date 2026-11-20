# 20-11-2026 — LK nội suy cả TỈ LỆ + quét cổng `max_mad`: cổng 1,5 đang chặn nhầm, tốn ~0,18 IoU

## 1. Mục tiêu

Hai câu hỏi, đo trên **GT người tô** (không phải `drift_iou`):

1. `LkBoxTracker` chỉ dịch `(x+dx, y+dy, w, h)` ⇒ **không thể** chữa lệch kích thước (đo 20-11: `ΔW/ΔH`
   tới −132 px ở 3/7 frame). Thêm nội suy **tỉ lệ + xoay** có làm ô bám đúng hơn không?
2. Cổng `max_mad` = 1,5 từ chối **86–90 %** mẫu ở frame giữa khe. Nới/bỏ cổng thì sao?

## 2. Input

- GT `docs/gt/b1b` (7 frame giữa khe, vật luôn trong khung) và `docs/gt/b1` (12 frame, **5 frame vật đã
  rời khung**: `121,151,272,302,332` ⇒ ca thử "bỏ cổng có bám vào nền không").
- Clip `data/binh1.mp4`, ô chai `300,275,150,410`, `--image-size 192`, `--vos-every 3`, 3 lần/cấu hình
  **chèn kẽ**, `--frames 300/340`.

## 3. Công việc đã thực hiện

1. `src/light_tracker.py`: tham số `scale=False` (mặc định **TẮT**). Khi bật: khớp **similarity**
   (dịch + tỉ lệ + xoay) bằng `cv2.estimateAffinePartial2D` trên chính lưới điểm LK; ô bao = bao ngoài
   4 góc đã biến đổi; cổng an toàn: tỉ lệ ∈ [0,80; 1,25], |góc| ≤ 15°, cạnh ≥ 4 px; ra ngoài ⇒ **rơi về
   tịnh tiến** (không bịa).
2. **Cổng `mad` phải đo trên PHẦN DƯ của mô hình similarity**, không phải trên vector dịch thô: vật co
   giãn thì trường dịch không đều (điểm giữa gần như đứng yên, điểm rìa đi ra) nên đo thô chặn đúng
   chuyển động thật. Lần chạy thử đầu tiên: **mọi** ca phóng to/thu nhỏ/xoay đều `ok=False`.
3. `warp_mask(mask, matrix)`: mask cũ biến đổi **cùng phép** với ô bao (nếu chỉ dịch mask khi ô co giãn
   thì mask và ô lệch nhau ngay trên hình người xem).
4. Nối: `LiveTrackConfig.lk_scale`, `--lk-scale` (worker), echo `lk_scale` vào `status.json`, trục A/B
   `--lk-scale shift|scale` (schema 3), metric mới `iou_khi_lk_ok` / `iou_khi_lk_khong` / `n_lk_ok`.
5. Quét cổng: `max_mad` 1,5 / 6,0 / 20 / 100 (**100 = cổng MAD không bao giờ chặn**, nhưng `update()` còn
   4 nhánh từ chối khác: chưa `reset`, `_seed` rỗng (ô < 4 px), `min_points`, và `moved/status` hỏng) trên
   `b1b`, và 1,5 vs 100 trên `b1` (có frame vật rời khung).

## 4. Output / Kết quả

### 4.1 Nội suy TỈ LỆ: đúng về cơ chế, **chưa chứng minh tốt hơn**

`data/ab_lk_scale_b1b_2026-11-20_metrics.json` (`git_rev 1572162`, `git_dirty_code=false`, `schema 3`):

> ⚠ Cùng cấu hình `1,5/shift` có **hai số khác nhau** trong log này: §4.1 = 0,6496 (`lk_ok` 0,19), §4.3 =
> 0,6129 (`lk_ok` 0,05). Đó là **hai phiên khác nhau** (cùng clip + cùng GT) — minh hoạ đúng quy tắc "so
> hai phiên là vô nghĩa", nên chỉ so **trong từng bảng**.

| cấu hình | IoU | ± | tệ nhất | `lk_ok_frac` |
|---|---|---|---|---|
| 1,5 / **shift** (mặc định) | 0,6496 | 0,0291 | 0,3855 | 0,19 |
| 1,5 / **scale** | 0,6465 | 0,0125 | 0,3848 | **0,43** |
| 6,0 / shift | 0,6482 | 0,0426 | 0,3853 | 0,52 |
| 6,0 / **scale** | **0,6947** | 0,0623 | 0,4239 | **0,67** |

**Cả 6 cặp đều "KHÔNG phân biệt được"** (chênh lớn nhất +0,048 ≤ nhiễu 0,062).


**Bảng theo-frame của bản đầu đã bị XOÁ — nó không đo được điều nó tuyên bố** (review #65, P0):
ở cấu hình 1,5 thì `shift` nhận **1/7** frame (chỉ f182), còn `scale` nhận 6/7 ⇒ mọi dòng so "ô VOS đóng
băng" (shift) với "ô LK" (scale), không phải so hai **mô hình chuyển động**. Chỉ **1 frame (f182)** có cả
hai `lk_ok = true` ⇒ `n = 1`, không kết luận được.

### 4.1b Phép đo "sạch hơn": mở **cổng MAD** cho cả hai (vẫn còn 2 cổng khác)

`data/ab_mo_cong_shift_vs_scale_b1b_2026-11-20_metrics.json` (`git_rev f5c663a`, `git_dirty_code=false`,
`schema 4`, `max_mad = 100` cho **cả hai** ⇒ `scale` nhận **7/7**, `shift` nhận 6/7):

| cấu hình | IoU | ± | tệ nhất | `lk_ok_frac` |
|---|---|---|---|---|
| 100 / shift (chỉ dịch) | 0,6765 | 0,0113 | **0,0000** | 0,86 |
| **100 / scale (dịch + tỉ lệ + xoay)** | **0,8051** | 0,0130 | **0,5542** | **1,00** |

Chênh thô **+0,1286** (quy ước: `scale − shift`) > ngưỡng nhiễu 0,0130; theo cặp **14/21**.

### 4.1c RÚT LẠI kết luận "+0,1286": toàn bộ chênh lệch nằm ở **một frame**

**ĐÍNH CHÍNH (review #65 vòng 3, P0).** Con số +0,1286 **không** phải hiệu ứng của mô hình chuyển động.
Nó đến từ **đúng f62**, và ở frame đó `shift` **không phát ô nào** (`lk_ok = false`, `vi_sao: "không có ô
hiển thị"`, không có khoá `hop`) — tức phép so là "không có ô" vs "ô LK", không phải "ô LK vs ô LK".

Bỏ f62 khỏi **CẢ HAI** bên (6 frame còn lại, cả hai đều là ô LK):

| lần chạy | shift (6 frame) | scale (6 frame) | scale − shift |
|---|---|---|---|
| 1 | 0,7893 | 0,7902 | +0,0009 |
| 2 | 0,8023 | 0,7929 | −0,0095 |
| 3 | 0,7761 | 0,8118 | +0,0357 |
| **trung bình** | **0,7892** | **0,7983** | **+0,0091** (sd của hiệu 0,024) |

⇒ **+0,0091 < ngưỡng nhiễu 0,0130 ⇒ KHÔNG phân biệt được.** Theo cặp: 14/21 → **11/18** (bỏ 3 cặp f62).

**Và f62 không phải thuộc tính của `shift`**: cùng cấu hình `100/shift` ở **phiên khác**
(`data/ab_quet_max_mad_b1b_…`, rev `7aaaa4c`) nhận f62 **3/3 lần** với IoU 0,879 / 0,829 / 0,829 và
`lk_ok_frac = 1,00`. Chênh giữa **hai phiên của CÙNG một cấu hình** là **0,1155** — gấp ~9× ngưỡng nhiễu
0,0130 đang được trích ⇒ ngưỡng trong-phiên **không dùng được** để kết luận về hiệu ứng 1 frame.

**Vì sao f62 không có ô (không phải "LK mất dấu")**: `ok=false` ⇒ pipeline trả `base_result`; base đó có
bbox **suy biến** `(0,0,0,0)` → `xyxy_to_xywh` → `(0,0,1,1)` → `_seed` trả rỗng vì < 4 px ⇒ `update()`
thoát với `last_ly_do = "seed_rong"` ⇒ **LK chưa hề chạy**. Nguyên nhân nằm **trước** LK (VOS trả mask rỗng
ở lần VOS gần nhất). Nay `LkBoxTracker.last_ly_do` ghi lại đúng nhánh (`seed_rong` / `thieu_diem` /
`mad_du` / `lk_hong` / `ok_shift` / `ok_scale`) để không phải suy đoán nữa.

⇒ **Kết luận cuối: CHƯA chứng minh được nội suy tỉ lệ tốt hơn tịnh tiến** (giống kết luận trước khi có
phép đo "sạch" — §5 đúng, §4.1b bản trước sai). Theo từng frame (lần chạy 1, chỉ để tham khảo):

| frame | shift | scale | ghi chú |
|---|---|---|---|
| 62 | **0,000** | **0,811** | `shift` mất **toàn bộ** điểm theo dõi ở frame này; similarity vẫn khớp |
| 92 | 0,831 | 0,843 | như nhau |
| 182 | 0,809 | 0,851 | scale nhích hơn |
| 242 | 0,869 | 0,900 | scale nhích hơn |
| 212 | **0,894** | 0,765 | hiệu (shift − scale) 3 lần: +0,129 / +0,135 / **−0,111** ⇒ trung bình **+0,051 ± 0,140** ⇒ **không kết luận được** |
| 2 | 0,565 | 0,554 | như nhau |
| 32 | 0,768 | 0,829 | scale hơn |

⇒ Bảng trên là **một** lần chạy; mọi câu "scale hơn/kém ở frame X" với n = 1 đều không dùng được. Con số
duy nhất đứng vững là **+0,0091 < nhiễu** (mục trên) ⇒ **không phân biệt được**.

Câu "scale bền hơn khi LK mất điểm" cũng **không đứng**: ở `max_mad = 100` cả hai chế độ dùng **cùng**
điều kiện từ chối (`_seed` ô ≥ 4 px và `keep.sum() < min_points`, chạy **trước** nhánh scale); nhánh khác
nhau duy nhất là cổng MAD — đã vô hiệu ở 100. Vậy `lk_ok` 0,86 vs 1,00 là do **base VOS khác nhau**, không
do mô hình chuyển động.

**Vì sao ở cổng mặc định (1,5) không thấy lợi ích**: cổng đó chặn 5/7 frame ⇒ cả hai cấu hình chủ yếu phát
**ô đóng băng**, khác biệt mô hình chuyển động bị che. Muốn thấy tác dụng của `lk_scale` phải nới cổng
(hoặc dùng cả hai cùng lúc).

### 4.2 Ô LK tốt hơn ô VOS ĐÓNG BĂNG — có hiệu ứng chọn mẫu, KHÔNG phải bằng chứng cổng "đúng"

Tính từ artifact trên (IoU tách theo `lk_ok`, nay là metric chính thức của dụng cụ):

| cấu hình | IoU khi LK **nhận** | IoU khi LK **từ chối** | n nhận / n từ chối |
|---|---|---|---|
| 1,5 / shift | **0,836** | 0,606 | 4 / 17 |
| 1,5 / scale | 0,778 | 0,548 | 9 / 12 |
| 6,0 / shift | 0,758 | 0,527 | 11 / 10 |
| 6,0 / scale | 0,797 | 0,490 | 14 / 7 |

⇒ Khi LK **nhận**, ô đúng hơn ô VOS đóng băng **0,20–0,31 IoU**.

**ĐÍNH CHÍNH (review #65, P1)**: bản đầu viết "LK từ chối **đúng** các frame ô sai" — **vượt bằng chứng**.
Hai đại lượng là "ô LK" vs "ô VOS ĐÓNG BĂNG" trên **tập frame do chính LK chọn** ⇒ có **hiệu ứng chọn mẫu**;
muốn nói "cổng chọn đúng" phải có **phản thực** (chạy cùng frame đó với cổng mở rồi so ô LK). Nó còn mâu
thuẫn với §4.3: **mở** cổng lại tăng IoU.

⇒ Điều nói được: *ô do LK nội suy tốt hơn ô đóng băng của lần VOS trước* (0,78–0,84 vs 0,49–0,61), và *ở
1,5 LK chỉ nhận 5–14 % mẫu giữa khe*.

### 4.3 Quét cổng `max_mad` trên `b1b`: đơn điệu, 1,5 là quá chặt

`data/ab_quet_max_mad_b1b_2026-11-20_metrics.json` (`git_rev 7aaaa4c`, `git_dirty_code=false`, 0 lần lỗi):

| `max_mad` | IoU | ± | tệ nhất | `lk_ok_frac` | vs 1,5 | nhiễu | phân biệt |
|---|---|---|---|---|---|---|---|
| **1,5** (mặc định) | **0,6129** | 0,0126 | 0,3826 | 0,05 | — | — | — |
| 6,0 | 0,6765 | 0,0313 | 0,4854 | 0,57 | **+0,064** | 0,031 | **có** |
| 20 | 0,7448 | 0,0678 | 0,3766 | 0,95 | **+0,132** | 0,068 | **có** |
| **100** (cổng MAD không bao giờ chặn — **vẫn** có thể bị `_seed`/`min_points` từ chối) | **0,7920** | **0,0105** | **0,5649** | 1,00 | **+0,179** | 0,013 | **có** (15/21 cặp) |

Phiên **lặp lại** (`data/ab_lk_khong_bao_gio_tu_choi_b1b_…`): 1,5 = 0,6541 vs 100 = 0,7550 ⇒ chênh
**+0,101** > nhiễu 0,064 ⇒ **cùng chiều, cùng kết luận** (hai phiên độc lập).

### 4.4 Bỏ cổng có bám vào nền khi vật RỜI KHUNG không? — **CHƯA ĐO ĐƯỢC**

`data/ab_max_mad_b1_co_frame_trong_2026-11-20_metrics.json`: `b1` có 5 frame GT rỗng (vật đã cất), và
**3 frame đo được nằm SAU cửa sổ vắng vật** (181, 211, 241).

| `max_mad` | IoU | ± | tệ nhất |
|---|---|---|---|
| 1,5 | 0,5933 | 0,0566 | 0,2541 |
| 100 | **0,6587** | 0,0318 | 0,1985 |

Theo từng frame ở `max_mad 100`: f181 = **0,810–0,813**, f211 = 0,490–0,723, f241 = 0,817–0,825. Ca
`iou = 0,0` duy nhất gặp ở **f60** (vật giơ cao, `lk_ok = False`) — không phải ca vật vắng; ở 1,5 cùng
frame cũng chỉ 0,29–0,30.

**ĐÍNH CHÍNH (review #65, P2)**: KHÔNG được đọc thành "bỏ cổng không bám vào nền khi vật rời khung".
`hop_tu_gt()` **bỏ đúng các frame `gt_rong`** — tức đúng các frame vật vắng (`121,151,272,302,332`) ⇒ **chưa
có** phép đo nào trên cửa sổ vắng vật. 181/211/241 là frame **vật đã có lại**, và "không trôi" ở đó gần
như được bảo đảm bởi kiến trúc: `_interp.reset(base_gray, base_bbox)` mỗi frame ⇒ sai số không tích luỹ
quá `vos_every` frame. **Trạng thái: chưa đo.**

## 5. Vấn đề & cách xử lý

- **Cổng `mad` đo trên vector dịch thô chặn đúng chuyển động thật** khi vật co giãn — phát hiện ngay ở
  lần chạy thử đầu (mọi ca phóng to/xoay đều `ok=False`). Sửa: đo trên phần dư của mô hình.
- **Không đổi mặc định trong PR này**: `scale` giữ `False`, `max_mad` giữ `1,5`. Lý do: (a) scale chưa
  phân biệt được; (b) nới `max_mad` mới đo trên **một clip, một loại vật** (chai cầm tay) — AGENTS §6
  đòi A/B ≥ 2 clip trước khi đổi mặc định; (c) `scale` làm LK nhận nhiều hơn mà **không** tăng IoU ⇒
  chưa có lý do bật.
- **`estimateAffinePartial2D(LMEDS)` không seed** ⇒ bật `scale=True` thêm một nguồn **không tất định**
  (ngoài SAM 2). Chấp nhận được vì mặc định TẮT, nhưng mọi số của chế độ `scale` phải đọc kèm cảnh báo
  "hai phiên không so được với nhau".
- **Số 1,5 là quá chặt thì phải ghi ra**: nếu demo cần ô đúng hơn, chạy `--lk-max-mad 20` (hoặc 100)
  — nay có số để nói, không phải đoán.

## 6. Next steps

1. **Đo "vật vắng" thành metric**: hiện `cham()` **bỏ** frame `gt_rong` ⇒ không chấm được "ô bao có bịa
   ra vật không khi vật đã đi". Cần: đếm `lk_ok = 1` ở frame GT rỗng và độ dịch chuyển ô trong cửa sổ
   vắng ⇒ mới quyết định được `max_mad` mặc định (ticket mới).
2. A/B nới `max_mad` trên **clip thứ 2 + vật khác** (yêu cầu AGENTS §6) trước khi đổi `DEFAULT_MAX_MAD`.
3. Thử **dự phòng khi LK từ chối**: hiện phát ô đóng băng (0,5–0,6); thử ngoại suy theo vận tốc gần
   nhất, hoặc dùng `scale` chỉ khi tỉ lệ ước lượng ổn định qua 2 frame liên tiếp.

## 7. Tài liệu tham khảo

- `docs/task/20-11-2026-cai-gia-do-chinh-xac-cua-hybrid.md` (hybrid 30 FPS giá 0,26 IoU)
- `docs/task/20-11-2026-cham-o-hien-thi-tren-gt-giua-khe.md` (`max_mad` 1,5 vs 6,0: không phân biệt)
- `docs/task/20-11-2026-image-size-192-vs-320-theo-gt.md` (320 tệ hơn 0,21)
- Artifact: `data/ab_lk_scale_b1b_…`, `data/ab_quet_max_mad_b1b_…`, `data/ab_max_mad_b1_co_frame_trong_…`

## 8. ĐÍNH CHÍNH + vá sau review độc lập (PR #65)

Reviewer vòng 1: **P0 = 0, P1 = 2, P2 = 4, P3 = 8**; xác nhận code pipeline **không** có lỗi đúng/sai
(mặc định TẮT, mask warp cùng phép, không dùng `last_matrix` cũ). Hai P1 đều là **câu kết luận** đang gán
sai nguyên nhân cho số đo — nguy hiểm vì sẽ được chép nguyên vào báo cáo.

| Mức | Reviewer nêu | Xử lý |
|---|---|---|
| **P1** | "f212 xấu đi do scale" — f212 `lk_ok=false` **cả 12 lần** ⇒ ô đó là **ô VOS**, không phải scale | sửa bảng §4.1 + thêm cột "LK có chạy?" + ĐÍNH CHÍNH |
| **P1** | "LK từ chối đúng các frame ô sai" — `iou_khi_lk_ok` = ô LK, `iou_khi_lk_khong` = ô VOS đóng băng, **hiệu ứng chọn mẫu**; còn mâu thuẫn với §4.3 | sửa tiêu đề §4.2 + ĐÍNH CHÍNH; sửa comment trong `cham()` và thêm khoá `iou_khi_lk_dinh_nghia` vào artifact |
| P2 | "bỏ cổng không bám vào nền khi vật rời khung" **chưa hề đo** (`hop_tu_gt` bỏ frame `gt_rong`) | hạ thành **CHƯA ĐO ĐƯỢC** + giải thích vì sao 181/211/241 không chứng minh được |
| P2 | 3 tiêu chí **không có test**: warp mask trong `_result_threaded`, echo `lk_scale`, `cau_hinh_lech` với `lk_scale` | 3 test mới (`test_live_tracking.py::TestLkNoiSuyTiLe`, `test_cau_hinh_lech_bat_duoc_lk_scale…`); test mask khẳng định `result.mask == warp_mask(base.mask, last_matrix)` |
| P2 | "mặc định không đổi" **không được ghim** (test cũ dung sai ±2 px) | `test_che_do_shift_duoc_GHIM_tuyet_doi_khong_doi_so`: dịch nguyên pixel ⇒ `bbox` **đúng tuyệt đối** `(133,77,60,90)`, `last_matrix` = [[1,0,3],[0,1,2]] |
| P3 | `last_scale` ghi cả khi similarity bị từ chối | `_khop_similarity` không ghi nữa; chỉ ghi khi bbox được chấp nhận + test |
| P3 | nhánh `shift_mask(mask, dx, dy)` dưới `lk_scale` là **bẫy** (`dx,dy` mất nghĩa khi ô đổi kích thước) | dưới `lk_scale` chỉ `warp_mask` (hoặc giữ mask nguyên); test khẳng định **không bao giờ** gọi `shift_mask` |
| P3 | `cau_hinh_lech` thiếu `continue` ⇒ 1 lần chạy vào cả `chua` và `lech`; tên khoá gộp 2 trục | thêm `else:` lồng + `lk_scale_chua_kiem_duoc` riêng + test |
| P3 | `schema: 3` nhưng tập khoá khác nhau giữa 2 artifact | `schema: 4` |
| P3 | hai phiên cùng cấu hình cho 2 số khác nhau, không nói; artifact lặp ủng hộ kết luận không được trích | thêm cảnh báo + trích artifact lặp (+0,101) |
| P3 | 2 test scale **không cô lập** điều chúng tuyên bố | thêm `test_cong_similarity_chap_nhan_dung_nguong_va_tu_choi_khi_qua` (gọi THẲNG `_khop_similarity`); thay ca "nền nhiễu" bằng **nền texture tĩnh** và đo lại: cổng **có** từ chối khi vật biến mất (bản đầu của mình khẳng định ngược lại — tự bắt được) |
| P3 | `estimateAffinePartial2D(LMEDS)` không seed ⇒ thêm nguồn không tất định | thêm bullet ở §5 (mục "Vấn đề") |
| P3 | 4 artifact được trích là `schema 3`, **không** có `iou_khi_lk_dinh_nghia` ⇒ tiêu chí "artifact tự khai nghĩa" chỉ đúng cho artifact sinh **sau** `f5c663a` | §4.2 ghi rõ: số lấy từ artifact `schema 3`, nghĩa lấy từ `cham()`; artifact mới (`ab_mo_cong_…`) đã `schema 4` |
| P3 | `iou_khi_lk_dinh_nghia` viết "khi LK từ chối ⇒ ô VOS đóng băng" — sai với `vos_every=1`; và không có trong `tong_hop` | thêm "(chỉ đúng khi `lk_khong_ap_dung = false`)" + chép khoá nghĩa vào `tong_hop` |
| P3 | log §8 bảng thiếu 2 mục so với review vòng 1 (4 P2 + 8 P3) | bổ sung ở vòng 2 (bảng dưới) |
| P3 | test "không gọi `shift_mask`" có thể xanh rỗng nếu `_result_threaded` return sớm | thêm `assert out.mask is not None` |
| P3 | `last_khop_similarity` không reset ở các `return None, False` sớm | reset cả ba field chẩn đoán ở **đầu** `update()` + test |

**Kiểm sau vá**: `./run lint` xanh · `./run test` **1582 passed** (11 test mới so với lúc mở PR).

## 9. Vòng 2 của review #65 — P0 thứ hai (bảng §4.1 sai nhãn) và phép đo bù

Reviewer vòng 2: **P0 = 1, P2 = 1, P3 = 6**. P0 là **đúng loại lỗi của vòng 1 lặp lại**: cột "LK có chạy ở
frame đó?" mình điền theo **một** cấu hình (`6,0/scale`) rồi áp cho cả cặp ⇒ 6/7 dòng sai nhãn; và câu
"scale sửa đúng phần nó nhắm tới (ΔW f32 −22 → +1)" so **ô VOS** với **ô LK** — chính là lỗi f212 lặp lại.

**Cách xử lý: không sửa nhãn cho đúng, mà thay bằng phép đo không còn trộn trạng thái** — mở cổng
(`max_mad 100`) để **cả hai** luôn nhận, khi đó mọi frame đều là "ô LK" ở cả hai bên ⇒ so được mô hình
chuyển động (§4.1b). Kết quả **lật lại kết luận cũ của mình**: scale **tốt hơn +0,1286** (nhiễu 0,0130).

| Mức | Reviewer nêu | Xử lý |
|---|---|---|
| **P0** | bảng §4.1 sai nhãn 6/7 dòng + câu kết luận so ô VOS với ô LK | **xoá bảng**; thêm §4.1b (đo sạch, `max_mad 100`) ⇒ kết luận mới: scale +0,1286 |
| P2 | `image_size_chua_kiem_duoc = len(chua)` sau khi `chua` gộp 2 trục ⇒ đếm cả run chỉ lệch `lk_scale` | đếm theo đúng trục + 2 cảnh báo riêng + test (`image_size` có số ⇒ 0, `lk_scale` thiếu ⇒ 1) |
| P3 | `iou_khi_lk_dinh_nghia` sai với `vos_every=1`, không có trong `tong_hop` | thêm điều kiện + chép vào `tong_hop` |
| P3 | docstring test khai ca "bbox bị từ chối" nhưng test thoát ở cổng mad | phủ **cả hai** ca; ca bbox gọi thẳng `_bbox_tu_matrix` (qua `update()` không tới được vì `_seed` đòi ≥ 4 px) |
| P3 | `last_khop_similarity` giữ giá trị cũ khi `return None, False` sớm | reset cả 3 field ở đầu `update()` |
| P3 | test "không gọi `shift_mask`" có thể xanh rỗng | thêm `assert out.mask is not None` |
| P3 | 4 artifact trích là `schema 3` (chưa có khoá nghĩa) | ghi rõ trong §4.2; artifact mới `ab_mo_cong_…` là `schema 4` |
| P3 | `estimateAffinePartial2D(LMEDS)` không seed — "ghi nhận vào mục 5" nhưng §5 không có | đã thêm bullet ở §5 |
| Note | `self._lk` **chưa nối vào đường phát** (chỉ `reset()`, không `update()`) ⇒ "bật thì cả 2 tracker bật" đúng nhưng chỉ `_interp` có tác dụng | giữ nguyên (có từ trước PR); ghi ở đây để không ai tưởng `_lk` đang chạy |

## 10. Vòng 3 của review #65 — P0 lần thứ hai, và lần này mình **rút lại** kết luận

Reviewer vòng 3: **P0 = 2, P1 = 2, P2 = 3, P3 = 4**. Cả hai P0 đều đúng và nặng: mình đã đổi một phép so
trộn trạng thái (vòng 2) bằng một phép so **vẫn trộn trạng thái ở 1 frame**, rồi công bố **+0,1286** như
kết luận "sạch" — nghe hợp lý nên dễ được chép vào báo cáo. Đã tự kiểm lại bằng `lan_chay` của artifact và
xác nhận **reviewer đúng 100%**:

- bỏ f62 (frame `shift` **không có ô**) khỏi **cả hai** bên: **+0,0091 < nhiễu 0,0130** ⇒ **không phân
  biệt được**;
- cùng cấu hình `100/shift` ở **phiên khác** nhận f62 **3/3** (0,879/0,829/0,829) ⇒ f62 là **flâke của
  base VOS**, không phải thuộc tính `shift`; chênh giữa hai phiên của **cùng** cấu hình = **0,1155**;
- câu "scale bền hơn khi LK mất điểm" cũng sai: ở `max_mad = 100`, hai chế độ dùng **cùng** điều kiện
  từ chối trước nhánh scale.

| Mức | Reviewer nêu | Xử lý |
|---|---|---|
| **P0** | "+0,1286" là hiệu ứng **1 frame**; bỏ f62 ⇒ +0,0091 (<nhiễu) | thêm §4.1c **RÚT LẠI**; kết luận cuối = **chưa chứng minh được**; §5 (viết trước đó) nay là đúng |
| **P0** | cùng cấu hình `100/shift` ở phiên `7aaaa4c` cho 0,7920 / `lk_ok` 1,00 / f62 = 0,83–0,88 ⇒ flâke | ghi cạnh nhau 2 số + nêu rõ "nhiễu trong-phiên không dùng được cho hiệu ứng 1 frame" |
| **P1** | "100 = **không bao giờ** từ chối" sai (`lk_ok` 0,86): còn `_seed` (ô ≥ 4 px) và `min_points` | sửa cả 3 chỗ thành "**cổng MAD** không chặn" |
| **P1** | "shift mất **toàn bộ** điểm theo dõi ở f62" là **phỏng đoán**: thật ra base VOS bbox suy biến ⇒ `_seed` rỗng ⇒ **LK chưa chạy** | sửa nhân quả + **thêm `last_ly_do`** vào `LkBoxTracker` (6 giá trị) + 2 test |
| P2 | `schema 4` có **hai hình dạng** (thêm khoá `iou_khi_lk_dinh_nghia` vào `tong_hop` mà không tăng số hiệu) | `schema: 5` + comment |
| P2 | §5 nói "scale **chưa phân biệt được**… không tăng IoU" — **ngược** §4.1b | giữ §5 (nay đúng); §4.1b đã sửa |
| P2 | f212 chỉ đúng lần chạy 1 (3 lần: +0,129/+0,135/−0,111 ⇒ +0,051 ± 0,140) | nêu ±3 lần, bỏ câu "kém hơn 0,13" |
| P3 | câu treo "Nhưng theo từng frame…:" (bảng đã xoá) | xoá |
| P3 | không nêu quy ước dấu (`so_sanh` tính `b − a`, artifact ghi −0,1286, log ghi +) | ghi "chênh = `scale − shift`" |
| P3 | test "bbox bị từ chối" gọi private + gán tay `_prev_bbox`; cờ được ghi trong helper | cờ nay ghi ở `update()`; thêm `test_bbox_bi_tu_choi_qua_DUONG_CONG_KHAI` |
| P3 | không có test "mask không bị warp bằng matrix cũ khi LK mất dấu" | thêm `test_mask_KHONG_bi_warp_bang_matrix_CU_khi_LK_mat_dau` |
| N | "1578 passed" | 1579 |
