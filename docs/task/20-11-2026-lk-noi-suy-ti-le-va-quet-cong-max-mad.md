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
5. Quét cổng: `max_mad` 1,5 / 6,0 / 20 / 100 (**100 = không bao giờ từ chối**) trên `b1b`, và 1,5 vs 100
   trên `b1` (có frame vật rời khung).

## 4. Output / Kết quả

### 4.1 Nội suy TỈ LỆ: đúng về cơ chế, **chưa chứng minh tốt hơn**

`data/ab_lk_scale_b1b_2026-11-20_metrics.json` (`git_rev 1572162`, `git_dirty_code=false`, `schema 3`):

| cấu hình | IoU | ± | tệ nhất | `lk_ok_frac` |
|---|---|---|---|---|
| 1,5 / **shift** (mặc định) | 0,6496 | 0,0291 | 0,3855 | 0,19 |
| 1,5 / **scale** | 0,6465 | 0,0125 | 0,3848 | **0,43** |
| 6,0 / shift | 0,6482 | 0,0426 | 0,3853 | 0,52 |
| 6,0 / **scale** | **0,6947** | 0,0623 | 0,4239 | **0,67** |

**Cả 6 cặp đều "KHÔNG phân biệt được"** (chênh lớn nhất +0,048 ≤ nhiễu 0,062).

Nhưng theo từng frame, scale **sửa đúng phần nó nhắm tới** — so `1,5/shift` với `6,0/scale`:

| frame | IoU shift | IoU scale | ΔW (px) shift → scale |
|---|---|---|---|
| 32 | 0,583 | **0,851** | −22 → **+1** |
| 92 | 0,382 | **0,821** | 0 → −2 |
| 182 | 0,826 | 0,869 | −19 → −10 |
| 242 | 0,867 | 0,900 | −7 → −4 |
| 2 | 0,579 | 0,554 | −30 → −32 |
| 212 | 0,660 | **0,504** | −26 → −49 |

⇒ 4/7 frame tốt hơn rõ, nhưng f212 (cận cảnh, vật to 5,5×) **xấu đi**. Trung bình bị nhiễu giữa lần chạy
nuốt (`std` 0,062 vì LK chỉ nhận 43–86 % mẫu nên *frame nào được nội suy* thay đổi mỗi lần).

### 4.2 Phát hiện QUYẾT ĐỊNH: LK từ chối **đúng** các frame ô sai

Tính từ artifact trên (IoU tách theo `lk_ok`, nay là metric chính thức của dụng cụ):

| cấu hình | IoU khi LK **nhận** | IoU khi LK **từ chối** | n nhận / n từ chối |
|---|---|---|---|
| 1,5 / shift | **0,836** | 0,606 | 4 / 17 |
| 1,5 / scale | 0,778 | 0,548 | 9 / 12 |
| 6,0 / shift | 0,758 | 0,527 | 11 / 10 |
| 6,0 / scale | 0,797 | 0,490 | 14 / 7 |

⇒ Khi LK nhận, ô đúng hơn **0,20–0,31 IoU**. Cổng `mad` KHÔNG phải "chống trôi vô ích" — nó chọn đúng
frame khó. **Nhưng** nó từ chối 83 % mẫu ở 1,5, và các mẫu đó sau đó là **ô đóng băng** (0,5–0,6).

### 4.3 Quét cổng `max_mad` trên `b1b`: đơn điệu, 1,5 là quá chặt

`data/ab_quet_max_mad_b1b_2026-11-20_metrics.json` (`git_rev 7aaaa4c`, `git_dirty_code=false`, 0 lần lỗi):

| `max_mad` | IoU | ± | tệ nhất | `lk_ok_frac` | vs 1,5 | nhiễu | phân biệt |
|---|---|---|---|---|---|---|---|
| **1,5** (mặc định) | **0,6129** | 0,0126 | 0,3826 | 0,05 | — | — | — |
| 6,0 | 0,6765 | 0,0313 | 0,4854 | 0,57 | **+0,064** | 0,031 | **có** |
| 20 | 0,7448 | 0,0678 | 0,3766 | 0,95 | **+0,132** | 0,068 | **có** |
| **100** (không từ chối) | **0,7920** | **0,0105** | **0,5649** | 1,00 | **+0,179** | 0,013 | **có** (15/21 cặp) |

### 4.4 Bỏ cổng có bám vào nền khi vật RỜI KHUNG không? — kiểm trên `b1`

`data/ab_max_mad_b1_co_frame_trong_2026-11-20_metrics.json`: `b1` có 5 frame GT rỗng (vật đã cất), và
**3 frame đo được nằm SAU cửa sổ vắng vật** (181, 211, 241).

| `max_mad` | IoU | ± | tệ nhất |
|---|---|---|---|
| 1,5 | 0,5933 | 0,0566 | 0,2541 |
| 100 | **0,6587** | 0,0318 | 0,1985 |

Theo từng frame ở `max_mad 100`: f181 = **0,810–0,813**, f211 = 0,490–0,723, f241 = 0,817–0,825 ⇒ **sau
khi vật rời khung rồi quay lại, ô không bị trôi** (không có sụp hàng loạt). Ca `iou = 0,0` duy nhất gặp ở
**f60** (vật giơ cao, `lk_ok = False`) — không phải ca vật vắng, và ở 1,5 cùng frame cũng chỉ 0,29–0,30.

## 5. Vấn đề & cách xử lý

- **Cổng `mad` đo trên vector dịch thô chặn đúng chuyển động thật** khi vật co giãn — phát hiện ngay ở
  lần chạy thử đầu (mọi ca phóng to/xoay đều `ok=False`). Sửa: đo trên phần dư của mô hình.
- **Không đổi mặc định trong PR này**: `scale` giữ `False`, `max_mad` giữ `1,5`. Lý do: (a) scale chưa
  phân biệt được; (b) nới `max_mad` mới đo trên **một clip, một loại vật** (chai cầm tay) — AGENTS §6
  đòi A/B ≥ 2 clip trước khi đổi mặc định; (c) `scale` làm LK nhận nhiều hơn mà **không** tăng IoU ⇒
  chưa có lý do bật.
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
