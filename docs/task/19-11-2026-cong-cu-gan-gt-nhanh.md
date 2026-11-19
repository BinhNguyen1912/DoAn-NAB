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

  Tái lập (số truy được về file, không phải chép tay):

  ```bash
  python - <<'EOF'
  import cv2, sys; sys.path.insert(0, '.')
  from scripts.gt_gan_nhanh import goi_y_hsv
  cap = cv2.VideoCapture('data/binh1.mp4')
  for fr in (57, 69, 90, 108):
      cap.set(cv2.CAP_PROP_POS_FRAMES, fr); _, img = cap.read()
      g = goi_y_hsv(img) > 127
      m = cv2.imread(f'docs/media/drift/masks/mask_{fr:06d}.png', 0) > 127
      print(fr, round((g & m).sum() / (g | m).sum(), 3))
  EOF
  ```

  Kết quả: `57 0.535 · 69 0.625 · 90 0.606 · 108 0.436` (mask model lấy từ
  `docs/media/drift/masks/`, phiên `vos_every=1` — nên đây là **IoU với mask model**, không phải mIoU
  với GT người).
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

## Review độc lập PR #49 — 2 P0 (JS) + 3 P1, đã sửa hết, thêm `./run gte2e`

| Mức | Nội dung | Xử lý |
|---|---|---|
| **P0** | `ve(null, …)` ⇒ `drawImage(null)` ném TypeError ⇒ **người tô "vẽ mù"** (nét vẫn lưu nhưng màn hình không đổi) | Giữ ảnh ở biến module `anhHien`, `ve()` không nhận `null` |
| **P0** | `demPhu()` đọc `d.data` trên `.data` ⇒ TypeError ngay lần vẽ đầu, **dòng trạng thái không bao giờ hiện** | Sửa `d[p]`, và **tách** `#tt` (frame/%) khỏi `#canh` (gợi ý) — bấm "Nhận gợi ý" từng xoá mất % |
| **P0 (e2e tự tìm)** | `document.getElementById('luu').onclick = luu` ⇒ hàm nhận **MouseEvent** vào tham số `khaiRong` ⇒ **mọi lần "Lưu & tiếp" đều xoá trắng mask và khai `gt_rong`** | `onclick = () => luu(false)`; e2e thêm assert "lưu thường KHÔNG bị hiểu thành không có vật" |
| **P1** | Danh sách frame §2b có frame **không có vật** (150/280/310) mà server **từ chối mask rỗng** ⇒ kẹt, không ra được số nào | Thêm đường khai **"Không có vật"** (`?rong=1` ⇒ GT toàn đen + `index.json.gt_rong`), sửa §2b sang khung có vật + tên bộ GT mới |
| **P1** | `index.json` **thiếu `frame_hw`** ⇒ hai cổng kích thước của `score_miou`/`gt_check_silhouette` **bỏ qua im lặng** ⇒ GT sai cỡ vẫn "hợp lệ, exit 0" | Ghi `frame_hw = [cao, rộng]`, kiểm mọi frame cùng cỡ, không cùng cỡ ⇒ dừng |
| **P1** | Chạy lại cùng `--ten` **ghi đè** `index.json` ⇒ frame cũ rơi khỏi index (`n_cham` nhỏ đi, `coverage` vẫn 1,0) và xoá cờ `dung_duoc: false` | Hợp `frames` + giữ mọi khoá lạ; index hỏng vẫn ghi được |
| P2 | Confirm "chưa lưu" hiện **sau khi đã lưu** | Cờ `dirty` |
| P2 | Thiếu `pointercancel`/`blur`, `pointermove` không kiểm `e.buttons` ⇒ kẹt chế độ tô | Đã thêm |
| P2 | `luu()` đọc `danhSach[i]` **sau** `await` ⇒ ghi GT vào tên frame khác | Chốt `so` trước `await`, chặn `dangLuu` gọi chồng |
| P2 | Caveat "sai số bộ gợi ý CHƯA ĐO" không đi vào artifact | Đưa vào `phuong_phap_gt` (khoá này `score_miou` copy vào `meta`) |
| P2 | `--ten ../../docs` ghi ra ngoài `docs/gt/` | `TEN_HOP_LE` + test 8 ca |
| P3 | `Content-Length: abc` làm handler chết; POST từ origin khác ghi được; index ghi danh sách **yêu cầu** thay vì **cắt được**; `A` không có undo; `nap().then(veLai)` vẽ 2 lần | Đã sửa hết (400/403, index từ `kich_thuoc`, undo `Z`, bỏ `.then`) |

**`./run gte2e` (mới) — E2E Chrome thật cho trình tô**: 12 mục, PASS. Kiểm: canvas đúng 720×1280 ·
"nhận gợi ý" ⇒ canvas **đổi thật** (bắt P0 vẽ mù) · HUD hiện % vật · kéo chuột ⇒ % **tăng** 3,9 → 4,4 ·
lưu ⇒ file nằm thẳng `docs/gt/<ten>/` + **không** khai rỗng oan · tự sang frame kế · **không** hộp thoại
sai · "Không có vật" ⇒ `gt_rong [90]` · `frame_hw [1280,720]` · **0 lỗi JS**. Bài học: 24 unit test
Python **không** bắt được 2 P0 JS — UI phải có e2e (AGENTS §5.4).
