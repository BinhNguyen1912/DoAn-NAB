# 21-11-2026 · Ticket #40 — A/B `max_mad` trên VẬT THỨ 2 (`binh2`): KHÔNG tái lập được lợi ích ⇒ giữ 1,5

## 1. Mục tiêu

Ticket #38 chốt `DEFAULT_MAX_MAD = 1,5` với luật "phải tái lập trên clip thứ 2". PR #65 đo trên `binh1`
(GT `b1b`): nới 1,5 → 100 cho **+0,1745** IoU(ô hiển thị, ô GT), sd hiệu 0,0205 — hiệu ứng **lớn nhất**
trong chuỗi 5 PR về LK. Câu hỏi: **trên `binh2` (vật khác, người khác cầm) có còn ≥ ngưỡng nhiễu không?**

## 2. Input

- GT người tô `docs/gt/binh2_tay` (12 frame trải đều clip, **4 frame `gt_rong`** ⇒ chấm 8 frame;
  `dang_gt: silhouette`, người gán Binh, 21-11).
- Ô chai `330,330,150,360` (theo `docs/demo-clip-va-o-chon.md`; ô `200,400,300,500` phủ 2 chai + 2 tay ⇒
  **không** dùng).
- `scripts/ab_o_hien_thi_vs_gt.py --dump-shown-csv` (dụng cụ của ticket #38/#39).

## 3. Cách chạy

```
python scripts/ab_o_hien_thi_vs_gt.py --gt docs/gt/binh2_tay --clip data/binh2.mp4 \
  --bbox 330,330,150,360 --max-mad 1.5 6 100 --lan 3 --frames 400 \
  --out data/ab_max_mad_binh2_2026-11-21_metrics.json
```

3 cấu hình × **3 lần chèn kẽ**, @192, `vos_every 3`. Artifact:
`git_rev ea38a42`, **`git_dirty_code false`**, `schema 6`, `so_lan_chay_loi 0/0/0`, `cau_hinh_hieu_luc_lech []`.

## 4. Kết quả

### (A) Phân tích ĐĂNG KÝ TRƯỚC — toàn bộ 8 frame GT

| `max_mad` | IoU(ô hiển thị, ô GT) | tệ nhất | `lk_ok_frac` | `ly_do_dem` (3 lần) |
|---|---|---|---|---|
| **1,5** | **0,4466 ± 0,1441** | 0,000 | **0,208** | `mad_du` 4–6 · `ok_shift` 2–3 · `seed_rong` 0–1 |
| 6,0 | 0,5629 ± 0,0343 | 0,000 | 0,500 | `ok_shift` 4 · `mad_du` 2–3 |
| 100 | **0,5660 ± 0,0083** | 0,000 | **0,833** | `ok_shift` 6–7 · `mad_du` 0–1 |

| cặp | chênh | ngưỡng nhiễu | `phan_biet_duoc` |
|---|---|---|---|
| 1,5 vs 6,0 | **+0,1163** | 0,1441 | **false** |
| 1,5 vs 100 | **+0,1194** | 0,1441 | **false** |
| 6,0 vs 100 | +0,0031 | 0,0343 | false |

⇒ **3/3 cặp "không phân biệt được"** ⇒ theo luật đăng ký trước (**AND trên mọi clip**) — `binh2` không đạt
⇒ **giữ `DEFAULT_MAX_MAD = 1,5`**.

### (B) Vì sao nhiễu to bất thường: 2 frame hỏng ở MỌI cấu hình

`iou_min = 0,000` ở **cả 9 lần chạy**. Truy ra: frame **163** và **228** có IoU ≈ 0 trong **mọi** cấu hình ⇒
không phải hiệu ứng `max_mad`. Ảnh kiểm `docs/media/gt/binh2_gt_khong_nhat_quan_vat.jpg` (frame 98 · 163 ·
261, GT xanh lá / ô hiển thị đỏ) cho thấy **frame 163 mô hình bám sang CHAI ĐEN** trong khi GT là **chai
trắng** (ô `[428,300,546,678]` vs GT `[179,314,304,637]`, hai vùng rời nhau); frame 228 ô co còn
`30×65` px nghiêng góc dưới — cũng lệch hẳn GT. Đây là **lỗi base VOS (đổi vật / mất dấu)**, xảy ra trước
khi LK tham gia.

Phân tích **hậu nghiệm** trên 6 frame còn dùng được (nói rõ là hậu nghiệm — **không** thay thế phân tích
đăng ký trước):

| `max_mad` | IoU 6 frame (mean ± sd) | 3 lần |
|---|---|---|
| 1,5 | 0,5931 ± **0,1896** | 0,731 · **0,377** · 0,672 |
| 6,0 | 0,7475 ± 0,0441 | 0,703 · 0,748 · 0,791 |
| 100 | **0,7500 ± 0,0087** | 0,748 · 0,760 · 0,743 |

Chênh 1,5 vs 100 = **+0,1568**, nhưng `max(std) = 0,1896` ⇒ vẫn **không phân biệt được**. Nguyên nhân
nhiễu: ở `1,5`, `lk_ok_frac` chỉ **0,208** ⇒ 79 % frame hiển thị **ô VOS ĐÓNG BĂNG**, mà ô đó có lần tốt
(0,731) có lần tệ (0,377) ⇒ phương sai của chính cấu hình 1,5 **nuốt** chênh lệch. Ở 100, LK nhận 83 % nên
ô luôn chuyển động và kết quả ổn định (sd **0,0087**, nhỏ hơn **22×**).

## 5. Quyết định

**GIỮ `DEFAULT_MAX_MAD = 1,5`.** Không sửa mặc định trên cơ sở `binh2`, vì:
1. Luật đăng ký trước là AND trên mọi clip — `binh2` **không** đạt (3/3 cặp "không phân biệt được").
2. Chênh trên 6 frame dùng được (+0,157) **vẫn nhỏ hơn** sd của 1,5 (0,190) ⇒ không phân biệt được kể cả
   khi loại frame hỏng.
3. Cái đo được một cách chắc chắn là **hành vi**, không phải **độ đúng**: `lk_ok_frac` 0,208 → 0,833 (×4) và
   **phương sai giảm 22×**. Cùng chiều với `binh1` (+0,1745) nhưng **chưa** phải bằng chứng "chính xác hơn".

**Cách viết trong báo cáo (bắt buộc đúng mức bằng chứng):**
- ✅ "Nới cổng MAD làm ô **chuyển động** (LK nhận 21 % → 83 %) và **ổn định hơn** (sd giữa lần chạy
  0,19 → 0,009) trên `binh2`; trên `binh1` nó còn cho IoU **cao hơn** +0,1745 (sd hiệu 0,0205)."
- ❌ "Nới cổng làm bám chính xác hơn" — trên `binh2` **không** chứng minh được.
- ❌ "Cổng 1,5 là lựa chọn tốt hơn" — hai clip cùng chiều, không có bằng chứng 1,5 tốt hơn ở bất kỳ đâu.
  Giữ 1,5 chỉ vì **chưa đủ bằng chứng để đổi** (nguyên tắc: không đổi mặc định khi chưa chứng minh).

## 6. Phát hiện phụ (quan trọng hơn `max_mad`) → ticket mới

Frame **163**: mô hình bám **sang chai đen** (đổi vật) — IoU 0,00 ở **cả 9 lần chạy**, không phụ thuộc
`max_mad`. Frame **228**: ô co còn 30×65 px lệch hẳn GT. Đây là **lỗi chất lượng base VOS** đúng loại mà
đề cương gọi là "bám bắt đối tượng" ⇒ cần ticket riêng, không được gộp vào `max_mad`.

## 7. Tài liệu tham khảo

- Artifact: `data/ab_max_mad_binh2_2026-11-21_metrics.json` (`git_dirty_code false`).
- Ảnh kiểm: `docs/media/gt/binh2_gt_khong_nhat_quan_vat.jpg`.
- GT: `docs/gt/binh2_tay/index.json` (12 frame, `gt_rong` = 196/294/326/359).
- Ticket #38 (câu hỏi gốc + luật AND trên mọi clip), PR #65 (số `binh1` +0,1745).
- AGENTS §6: `drift_iou` không phải độ đúng; `0/None ≠ đã đo`; `measured_fps` bão hoà.

## 8. Kiểm máy

`./run lint` xanh · `./run test` 1596 passed (trước khi thêm log) · artifact `git_dirty_code false`,
`so_lan_chay_loi 0/0/0`, `image_size_hieu_luc` khớp ở cả 9 lần chạy.
