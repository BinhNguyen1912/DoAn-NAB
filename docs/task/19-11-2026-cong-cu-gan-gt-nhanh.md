# 19-11-2026 — Công cụ gán GT phân đoạn NHANH (gợi ý màu + tô trên trình duyệt)

## Mục tiêu

Lỗ hổng lớn nhất của báo cáo: **chưa có mIoU phân đoạn trên video thật** — chỉ có GT **hộp bao**
(`mIoU 0,6464`, 12 frame) và fixture tổng hợp (0,9354 — cận trên). Thước đo duy nhất của "bám đúng" là
mIoU mask vs **GT người gán** (`docs/thuoc-do-bam-dung.md`), nhưng đường gán cũ đòi mở phần mềm ảnh và
tô tay từ đầu 20–30 frame ⇒ ~2–3 giờ. Mục tiêu: hạ xuống **≤ 45 phút** mà vẫn trung thực.

## Input

- `data/binh1.mp4` (ô chai `300,275,150,410`), `docs/thuoc-do-bam-dung.md` (quy tắc chấm + cổng GT).
- `scripts/score_miou.py` (`cat_frames`, `label`, `score` — đã có: cắt frame, chấm, 4 cổng GT).

## Công việc đã thực hiện

1. `scripts/gt_gan_nhanh.py`:
   - `goi_y_hsv()` (hàm thuần): gợi ý = vùng bão hoà màu ⇒ blob lớn nhất ⇒ **bao lồi** (lấp nhãn trắng);
     ảnh xám trả mask **rỗng** (không ném lỗi cv2 khó hiểu).
   - `_viet_index()`: khai **đúng nguồn** GT (`nguon_gt`, `sai_so_bo_goi_y = CHƯA ĐO`,
     `gt_do_model_goi_y = false`, `dang_gt = silhouette`).
   - Server HTTP nhỏ (localhost) phục vụ frame + gợi ý + GT cũ, nhận `POST /luu/gt_NNNNNN.png` và ghi
     **thẳng** vào `docs/gt/<ten>/`; `_kiem_png()` từ chối PNG hỏng / sai kích thước / **mask rỗng**.
2. `scripts/gt_painter.html`: trình tô 1 file, không phụ thuộc mạng ngoài (kiểm bằng test): cọ/tẩy,
   nhận gợi ý (`A`), xoá (`C`), lưu & tiếp (`S`), hiện % diện tích vật.
3. `tests/test_gt_gan_nhanh.py`: **24 test**, gồm server thật trên cổng 0 (lưu đúng thư mục, từ chối
   `../` lạc đường dẫn, từ chối mask rỗng/sai cỡ, từ chối frame lạ).

## Output / Kết quả

- Chất lượng gợi ý trên `binh1` — IoU(gợi ý, mask model), 4 frame:

  | frame | diện tích gợi ý | mask model | IoU |
  |---|---|---|---|
  | 57 | 3,9 % | 6,2 % | **0,535** |
  | 69 | 4,0 % | 5,5 % | **0,625** |
  | 90 | 3,9 % | 5,9 % | **0,606** |
  | 108 | 2,7 % | 6,1 % | **0,436** |

  ⇒ gợi ý là **điểm khởi đầu** (không phải GT): người gán vẫn phải sửa viền/nắp. Không dùng hull thì
  IoU 0,43–0,56; có hull 0,44–0,63 (hull chỉ giúp, không làm hỏng).
- **Diễn tập thật end-to-end** (không commit dữ liệu): `--chi-sinh` sinh frame + gợi ý → POST 2 GT qua
  HTTP (200) → `score_miou score` chấm được: `mIoU 0,5706` trên 2 frame, `dang_gt silhouette`,
  `mask_ngoai_gt_mean 40,2 %`, `meta.nguon_gt` = "ngưỡng màu HSV + người sửa tay". Đúng như dự đoán từ
  IoU gợi ý (0,44–0,63) ⇒ chứng minh chuỗi công cụ chạy, **không** phải số để báo cáo.
- `./run lint` xanh · 24 test mới xanh.

## Vấn đề & cách xử lý

- Thử biến thể "không phải nền" (S thấp & V cao = nền) để lấy trọn chai: **tệ hơn** — bắt luôn cả người
  (IoU 0,00–0,29) ⇒ giữ bản bão hoà màu + bao lồi.
- Ảnh xám làm `cv2.cvtColor` ném lỗi ⇒ sửa thành trả mask rỗng + ghi rõ "không có gợi ý" (không được coi
  mask rỗng là GT — `IoU(rỗng, rỗng) = 1,0`).
- Test đầu tiên của mình sai: gửi mask rỗng **sai cỡ** nên cổng "kích thước" chặn trước ⇒ test không
  kiểm được bẫy "rỗng". Đã sửa thành mask rỗng **đúng cỡ**.
- `--dump-mask-frames` vẫn bắt buộc `--vos-every 1` (mask GT phải đúng cặp: cùng frame, cùng clip).

## Next steps

- **Cần người**: chạy lệnh ở `docs/thuoc-do-bam-dung.md` §2b, tô 13–20 frame (~30–45 phút) ⇒ mIoU phân
  đoạn **thật** đầu tiên của repo (hiện chỉ có GT hộp bao 0,6464).
- Sau đó: chấm bằng `python tools/live_worker.py ... --dump-mask-frames "<đúng các frame>"` rồi
  `score_miou score`, ghi artifact vào `data/` (có `git_rev`/`git_dirty_code`).

## Tài liệu tham khảo

- `docs/thuoc-do-bam-dung.md` (§1 quy tắc chấm, §1.2 cổng GT, §2b đường nhanh)
- `AGENTS.md` §6 (bẫy `IoU(rỗng, rỗng)`, ngưỡng 30 mẫu, `drift_iou` không phải độ chính xác)
