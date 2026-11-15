# 30: Chặn chặt hơn cho GT dạng hộp bao: đối chiếu `hop_bao_xywh` ↔ mask, clip ↔ manifest, tên khoá `mIoU`

**What to build:** Ba P3 còn lại từ review độc lập 15-11 về bộ GT hộp bao (`docs/gt/binh1_hopbao`, artifact `data/miou_binh1_hopbao_2026-11-15_metrics.json`):

1. **Tên khoá mời gọi trích sai**: artifact GT hộp bao vẫn dùng `ket_qua.mIoU` / `mIoU_p05`. Ai `grep mIoU` rồi copy sẽ chỉ thấy 0,6464, không thấy cảnh báo (REGISTRY đang trỏ đúng khoá đó). Thêm `ket_qua.gt_dang` (echo `dang_gt`) và/hoặc đổi sang `iou_theo_dang_gt` khi `dang_gt != "silhouette"`; nhét câu "GT hộp bao ⇒ IoU(mask, hộp)" vào `meta.dinh_nghia`.
2. **`hop_bao_xywh` không được kiểm**: `kiem_index` không đối chiếu `gt.sum()` với `w*h` của hộp khai báo ⇒ một file GT hỏng/lẫn frame vẫn "hợp lệ". Cũng chưa đối chiếu `index.clip` với `meta.mask_manifest.nguon` và `index.frames` với `frames_yeu_cau` — đúng lớp lỗi "ghép GT với mask của frame khác" đã từng xảy ra (P0 14-11).
3. **`mask_ngoai_gt_max_frame` khi hoà**: hiện `max()` lấy phần tử đầu (frame nhỏ nhất) — xác định nhưng KHÔNG có test khoá; thêm test + ghi rõ quy ước.

Không cần làm lại số: cả ba đều là cổng kiểm/tên khoá, không đổi giá trị mIoU.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `ket_qua.gt_dang` (echo `dang_gt`) có trong artifact + test; hoặc đổi tên khoá khi `dang_gt != silhouette`
- [ ] `kiem_index`: khi `dang_gt == hop_bao` và có `hop_bao_xywh` ⇒ CHẶN nếu `gt.sum() != w*h` (test)
- [ ] `main`: cảnh báo mềm khi `index.clip` khác `meta.mask_manifest.nguon`, hoặc `index.frames` không nằm trong `frames_yeu_cau` (đúng lớp lỗi 'ghép sai frame')
- [ ] Test ca hoà `mask_ngoai_gt_max_frame` (hai frame cùng leak lớn nhất ⇒ chọn xác định, ghi rõ chọn frame nào)
- [ ] `score_miou --check-index` in thêm dạng GT + nguồn GT để người chạy thấy ngay
