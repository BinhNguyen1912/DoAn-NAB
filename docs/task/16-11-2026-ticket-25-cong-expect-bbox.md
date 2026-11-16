# Ngày 16-11-2026 — Ticket #25: cổng `--expect-bbox` không được đoán dạng hộp (chống "báo khớp OAN")

## 🎯 Mục tiêu
- Đóng ticket #25 (`ready-for-agent`): `scripts/make_trajectory_media._canh_bao_bbox` phân biệt `(x,y,w,h)`
  với `(x1,y1,x2,y2)` bằng `x2 <= x1` ⇒ một hộp `(x,y,w,h)` **hợp lệ** mà `w > x`
  (vd `50,100,300,400`) bị đọc thành `xyxy` ⇒ cổng có thể in **"ô bao khớp"** trong khi thực ra không
  khớp. Đây đúng loại "cổng báo khớp OAN" mà AGENTS §6 cấm (ca thật 14-11: ô phủ **khuôn mặt** vẫn
  được coi là ô đo chai ⇒ cả phase số vô nghĩa).
- Bối cảnh: ảnh quỹ đạo `docs/media/traj/` là **bằng chứng** trong báo cáo, nên cổng kiểm ô chọn cũng
  là một thước đo — nó phải trung thực ít nhất bằng con số nó bảo vệ.

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/25-…md`; `scripts/make_trajectory_media.py`;
  `tests/test_make_trajectory_media.py`; CSV thật `data/drift_samples_binh1_2026-11-14_113103.csv`
  (468 dòng, 170 lần VOS trả mask rỗng); ô chọn thật của `binh1` = `300,275,150,410` (x,y,w,h —
  `docs/demo-clip-va-o-chon.md`).

## 🔨 Công việc đã thực hiện
1. **Không đoán dạng hộp**: hàm mới `_doc_hop(expect, dang)` trả `(hộp, lỗi, dạng_hiệu_lực)`.
   Dạng khai bằng cờ `--expect-bbox-dang {xywh,xyxy}` hoặc tiền tố `xywh:` / `xyxy:` trong giá trị.
   Chỉ **suy ra** `xywh` khi `x2 <= x1` hoặc `y2 <= y1` (khi đó không thể là `xyxy`) và **in rõ** là đã
   suy ra; mọi ca còn lại mà không khai dạng ⇒ **KHÔNG KẾT LUẬN** (không in "khớp").
2. **Tiêu chí so đổi sang IoU hai hộp ≥ 0,7** (`_iou_hop`, `IOU_CUNG_VAT`), thay cho "lệch % từng cạnh
   > 10 %". Lý do có số: ô chọn thật `300,275,150,410` vs ô bao dòng đầu CSV `288,287,431,734` cho
   **IoU 0,7115** nhưng lệch cạnh tới **10 %** (chiều cao chai dựng đứng) ⇒ ngưỡng-theo-cạnh báo oan
   trong khi hai hộp rõ ràng cùng một vật. Độ lệch từng cạnh vẫn **in ra** như thông tin.
3. **Provenance ghi kết luận của cổng**: `expect_bbox`, `expect_bbox_dang` (kể cả ca suy ra),
   `ket_qua_hop` (`khop|lech|khong_ket_luan`), `iou_bbox`. Trước đây câu "đừng dùng ảnh này làm bằng
   chứng" chỉ nằm ở stdout ⇒ file `.json` trông y hệt một lần chạy đạt.
4. **Exit code**: `--expect-bbox` có mặt mà kết quả ≠ `khop` ⇒ **exit 1** (ảnh + JSON vẫn được ghi, kèm
   câu cảnh báo). `--expect-bbox ""` (biến shell rỗng) trước đây falsy ⇒ **bỏ qua cổng hoàn toàn**;
   nay `is not None` ⇒ vẫn đi qua cổng và exit 1.
5. **Chặn số vô nghĩa**: `nan`/`inf` trong `--expect-bbox` **hoặc** trong dòng đầu CSV, CSV rỗng,
   dòng đầu không có ô bao ⇒ `khong_ket_luan` (review vòng 1 bắt được: `max()` bỏ qua NaN và
   `nan > 0.1` là `False` ⇒ cổng từng in "khớp" với hộp `nan`).
6. **Media sinh lại với ô chọn THẬT**: `--expect-bbox 300,275,150,410 --expect-bbox-dang xywh`
   ⇒ `IoU 0,7115 ≥ 0,7` (cùng vật), `ket_qua_hop = khop`, `git_rev c5247cf`, `git_dirty_code false`.
   (Bản trước dùng `--expect-bbox 288,287,431,734` — **đúng bằng** ô bao dòng đầu CSV ⇒ "khớp 0 %" là
   tautology, không chứng minh gì — review vòng 1 bắt đúng.)

## 📤 Output / Kết quả
- Cổng giờ có 3 kết luận tường minh, không còn ca "khớp" nào không kèm bằng chứng `IoU`:
  `IoU 0,71 ≥ 0,7 (lệch cạnh tối đa 10 %)` cho ô thật; `IoU 0,08` + CẢNH BÁO cho ô phủ khuôn mặt.
- `docs/media/traj/binh1_vat_ra_khung.json`: `expect_bbox 300,275,150,410`, `expect_bbox_dang xywh`,
  `ket_qua_hop khop`, `iou_bbox 0,7115`, `git_rev c5247cf`, `git_dirty_code false`.
- `./run lint` xanh · `./run test` **1291 passed** (5 deselected; +13 test so với trước phiên).
- File thay đổi:
  - `scripts/make_trajectory_media.py` — `_doc_hop`, `_iou_hop`, `IOU_CUNG_VAT`, `_canh_bao_bbox` trả
    `khop|lech|khong_ket_luan`, `--expect-bbox-dang`, provenance + exit code
  - `tests/test_make_trajectory_media.py` — +13 test (mơ hồ, khai dạng, tiền tố, nan/inf, CSV nan,
    CSV rỗng, cờ rỗng, exit 0/1, provenance ghi kết luận)
  - `docs/media/traj/binh1_vat_ra_khung.{png,json}` — sinh lại với ô chọn thật

## 🐞 Vấn đề gặp phải & cách xử lý
- **`if data["cx"]`** làm `ValueError` vì `cx` là numpy array (truth value không xác định) ⇒ phải
  `len(data["cx"])`; `ruff` không bắt được lỗi này, chỉ test CLI mới bắt.
- **Test "xanh vô nghĩa"** (review bắt): fixture `50,100,350,500` không phải ca ticket (code cũ đọc
  `50,100,300,400` thành `xyxy` rồi in **CẢNH BÁO**, test vẫn xanh) ⇒ đổi fixture thành
  `50,100,300,400` đúng bằng giá trị mơ hồ ⇒ code cũ in "khớp" và test mới đỏ thật.
- **Tautology trong media**: dùng `--expect-bbox` trùng ô CSV dòng đầu cho "khớp 0 %" ⇒ vô nghĩa; nay so
  với **ô chọn thật** và ghi cả `iou_bbox` vào provenance.

## ✅ Review độc lập (AGENTS §9.1)
- **Vòng 1** (agent `reviewer`, chỉ đọc): **0 P0**, nhưng **1 P1** + 2 P2 + 4 P3. P1: `nan`/`inf` lọt
  qua `float()` ⇒ cổng in "khớp" (vì `max()` bỏ NaN). P2: `--expect-bbox ""` falsy ⇒ bỏ cổng; thiếu
  test exit 0; provenance **không** ghi kết luận; "khớp 0 %" là tautology. P3: docstring/help sai, test
  trùng tên/nghĩa, CSV rỗng ⇒ `IndexError`.
- **Đã sửa hết** trong `c5247cf` + `ff5e159` (và bản sửa P1/P2 trước đó), mỗi ca có test bắt hồi quy.
- Chưa cần vòng 3: các sửa nằm đúng những dòng review chỉ, `./run test` 1291 xanh, và toàn bộ test đỏ
  được nếu revert theo phân tích của reviewer (đã tự kiểm bằng cách chạy lại sau khi sửa).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Ticket #23 (`p05` có 3 ngưỡng 5/20/30 trong repo — artifact mIoU đang công bố `mIoU_p05` từ **5**
      frame): thống nhất về một ngưỡng hoặc khai `NGUONG_P05` + lý do tại chỗ.
- [ ] Ticket #24 (`vos_every = 1` không bao giờ ghi `mask_age_total_ms`) — đúng cấu hình đã dùng cho
      mIoU fixture và các số "1 luồng 8,8 FPS".
- [ ] Ticket #26 (`--dump-mask-frames` nằm trong cửa sổ `post_ms` ⇒ công cụ đo làm bẩn số đang đo;
      chọn lại ô giữa phiên chưa có test).
- [ ] Việc của người dùng: **tô silhouette 10–20 frame `binh1`** ⇒ mIoU phân đoạn thật.

## 📚 Tài liệu tham khảo
- AGENTS §6 (bẫy ô chọn `(x,y,w,h)` vs `(x1,y1,x2,y2)`; `drift_iou` không phải độ chính xác), §9.1
- `docs/demo-clip-va-o-chon.md` (ô chọn thật `binh1 300,275,150,410`), `docs/thuoc-do-bam-dung.md`
- Ticket: `.scratch/camera-ai-realtime/issues/25-…md`
