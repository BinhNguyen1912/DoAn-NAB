# 20-11-2026 — Cái giá ĐỘ CHÍNH XÁC của hybrid "HUD 30 FPS": `vos_every` 1 vs 2 vs 3 trên GT người tô

## 1. Mục tiêu

Lượng hoá bằng số: chạy VOS mỗi 3 frame để HUD 30 FPS thì **ô bao mất bao nhiêu độ chính xác** so với
chạy VOS mọi frame (`vos_every 1`)? Đây là con số phải có trong báo cáo, thay cho câu định tính
"hybrid làm hình mượt hơn".

## 2. Input

- GT `docs/gt/b1b` (7 frame **giữa khe**, người tô), clip `data/binh1.mp4`, ô chai `300,275,150,410`.
- `--image-size 192`, `--max-mad 1.5` (mặc định), `--frames 300`, `--lan 3`, **chèn kẽ** 3 cấu hình.
- Dụng cụ `scripts/ab_o_hien_thi_vs_gt.py` sau khi mở rộng (`--vos-every` nhận danh sách).

## 3. Công việc đã thực hiện

Mở rộng A/B sang trục `vos_every` — và trong lúc làm **bắt được 3 lỗi chiều bảng nhãn↔khoá** liên tiếp
(xem mục 5), mỗi lỗi chỉ lộ khi ≥ 2 giá trị cấu hình nên 2 lượt chạy 9 lần liền mất công vô ích.

## 4. Output / Kết quả

`data/ab_vos_every_b1b_2026-11-20_metrics.json` — `git_rev d893517`, `git_dirty_code=false`,
`image_size_chua_kiem_duoc 0`, `cau_hinh_hieu_luc_lech []`, `so_lan_chay_loi` 0/0/0.

| `vos_every` | IoU(ô hiển thị, GT) | tệ nhất | `lk_ok_frac` | FPS phát | nhịp mask |
|---|---|---|---|---|---|
| **1** (không có khe) | **0,8460 ± 0,0000** | **0,8085** | 0,00 | **7,3** | 7,3/s |
| 2 | 0,6042 ± 0,0257 | 0,3440 | 0,10 | **30,0** | ~15/s |
| 3 (mặc định) | 0,5815 ± 0,0903 | 0,2934 | 0,14 | **29,9** | ~10/s |

- **every 1 vs every 3: −0,2645 IoU** (> ngưỡng nhiễu 0,0903; theo cặp **17/21** frame thắng) ⇒ chạy
  hybrid 30 FPS **mất ~0,26 IoU ô bao** (0,85 → 0,58). Đây là **cái giá** phải nêu trong báo cáo.
- **every 2 vs every 3: −0,0227 ≤ 0,0903 ⇒ KHÔNG phân biệt được** ⇒ giảm `vos_every` từ 3 xuống 2
  (mask tươi gấp ~1,5 lần) **không** cải thiện độ chính xác đo được. Đúng lại kết luận cũ
  ("`vos_every` không phải nút điều khiển độ tươi/độ chính xác") — nay có số trên GT thật.
- `every 1` có `std = 0,0000` (3 lần ra cùng 0,8460) — ở cấu hình này mỗi frame đều có VOS nên kết quả
  **tất định**, không phụ thuộc LK.
- `lk_ok_frac` 0,00 / 0,10 / 0,14 ⇒ ở frame giữa khe, **85–100 % mẫu là ô ĐÓNG BĂNG** của lần VOS
  trước (khớp phép đo `max_mad` cùng ngày: 1,5 → 0,048; 6,0 → 0,524).

### Đọc gộp ba phép đo trong ngày (cùng clip, cùng GT, cùng ô)

| Câu hỏi | Số | Kết luận |
|---|---|---|
| `max_mad` 1,5 vs 6,0 | +0,020 (nhiễu 0,034) / +0,029 (nhiễu 0,022) | **không chứng minh được**; giữ 1,5 |
| `image_size` 192 vs 320 | **−0,209…−0,242** (nhiễu 0,066…0,082) | 320 **tệ hơn hẳn**, lại còn mất dấu |
| `vos_every` 1 vs 3 | **−0,2645** (nhiễu 0,090) | hybrid **có giá 0,26 IoU** |
| `vos_every` 2 vs 3 | −0,0227 (nhiễu 0,090) | không phân biệt được |

## 5. Vấn đề & cách xử lý (3 lỗi tự bắt, cùng một lớp)

Mở rộng khoá cấu hình từ `(size, mad)` sang `(size, vos_every, mad)` làm lộ 3 chỗ **lẫn chiều** giữa
bảng `nhãn → tuple` và `tuple → nhãn`:

1. `KeyError: (192, 1.5)` — một chỗ còn khoá 2 thành phần.
2. `KeyError: '192/1/1.5'` ở phần ghép cặp — dùng `nhan` (tuple→nhãn) cho `theo_cau_hinh` (khoá tuple).
3. Phép vá (2) **viết sai chiều cho cả hai bảng** vì dùng comprehension hai lớp `{v: k for k, v in …}`
   cho cả hai ⇒ hai bảng cùng chiều. **Test mới bắt được chính phép vá của mình.**

Cách xử lý: dựng **một nguồn duy nhất** `danh_sach_cau_hinh()` + `thu_tu_vong()`; đặt tên theo chiều
(`khoa_cua = dict(cau_hinh)`, `nhan = {tup: nhan_ch …}`); thêm **test chạy hết `main()` với pipeline
giả** (vá `chay_mot_lan`) để lỗi ở đoạn cuối `main()` không lọt nữa; và **kiểm test ĐỎ** bằng cách đưa
lỗi cũ trở lại (đã làm: đỏ đúng, xanh sau khi sửa).

Bài học ghi vào AGENTS-worthy: lỗi "chỉ lộ khi > 1 giá trị cấu hình" ⇒ test phải dùng **≥ 2 giá trị**
cho mọi trục; và phép `sed`/`replace` không khớp indent **im lặng không áp dụng** — phải `assert` chuỗi
khớp trước khi ghi (một lần đã trượt vì indent 4 vs 8 dấu cách).

## 6. Next steps

1. **Nội suy cả TỈ LỆ trong `LkBoxTracker`** (`bbox = (x+dx, y+dy, w, h)` hiện giữ nguyên `w,h`): với
   `lệch W/H −7…−132 px` đo được, đây là phần sai số mà LK **không thể** chữa. Nhưng phải đi kèm nới
   `max_mad` (1,5 từ chối 85–100 % mẫu ⇒ sửa LK mà cổng vẫn đóng thì không có tác dụng).
2. A/B `(1,5 translate-only)` vs `(6,0 translate+scale)` **chèn kẽ** — cần thêm trục "LK mode" vào
   dụng cụ, cùng cách với `--vos-every`.
3. Nếu (1) không đóng được phần lớn 0,26 IoU: **nói thẳng trong báo cáo** rằng hybrid 30 FPS đánh đổi
   0,26 IoU, và demo nên chạy `vos_every 1` khi cần độ chính xác (7,3 FPS) / `vos_every 3` khi cần mượt.

## 7. Tài liệu tham khảo

- `docs/task/20-11-2026-cham-o-hien-thi-tren-gt-giua-khe.md` (max_mad), `docs/task/20-11-2026-image-size-192-vs-320-theo-gt.md`
- `docs/bang-cau-hinh.md` (chọn cấu hình theo `vos_fps`/`mask_age_p95`, không theo `measured_fps`)
- AGENTS §6: "`vos_every` KHÔNG phải nút điều khiển độ tươi của mask"
