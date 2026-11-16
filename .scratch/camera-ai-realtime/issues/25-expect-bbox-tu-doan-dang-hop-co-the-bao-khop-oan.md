# 25: `--expect-bbox` tự đoán dạng hộp ⇒ có thể báo "khớp" OAN với hộp `(x,y,w,h)` hợp lệ

**What to build:** `scripts/make_trajectory_media._canh_bao_bbox` phân biệt `(x,y,w,h)` vs `(x1,y1,x2,y2)`
bằng `x2 <= x1`. Một hộp `(x,y,w,h)` **hợp lệ** với `w > x` (vd `50,100,300,400`) bị đọc thành
`x1,y1,x2,y2` ⇒ script có thể in "ô bao khớp --expect-bbox" trong khi thực ra không khớp. Đây chính là
chốt chặn bẫy "ô chọn sai vật" (AGENTS §6: bbox trỏ vào nền vẫn cho `ket_qua = true`).

**Cách làm:** bắt buộc khai dạng (`--expect-bbox xywh|50,100,300,400`), hoặc từ chối khi không phân biệt
được thay vì đoán.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [ ] `"50,100,300,400"` ⇒ báo "không phân biệt được dạng", KHÔNG in "khớp"
- [ ] Dạng khai tường minh vẫn chạy được (test cho cả hai)

## Answer

Xong trên nhánh `fix/expect-bbox-khong-doan-dang-hop` (commit `27991a0` → `ff5e159`). `_doc_hop` **không đoán dạng hộp**: khai `--expect-bbox-dang {xywh,xyxy}` hoặc tiền tố `xywh:`/`xyxy:`; chỉ suy ra `xywh` khi `x2<=x1`/`y2<=y1` (và **in rõ** đã suy ra); mọi ca mơ hồ (`50,100,300,400`) ⇒ **KHÔNG KẾT LUẬN**, không in "khớp", exit 1. Tiêu chí so đổi sang **IoU hai hộp ≥ 0,7** (`IOU_CUNG_VAT`) thay "lệch cạnh >10 %" — có số: ô chọn thật `300,275,150,410` vs ô bao dòng đầu CSV cho IoU **0,7115** nhưng lệch cạnh 10 % (chai dựng đứng) ⇒ ngưỡng-theo-cạnh báo oan. Provenance JSON ghi `expect_bbox`, `expect_bbox_dang`, `ket_qua_hop`, `iou_bbox`. Chặn thêm `nan`/`inf` (P1 review: `max()` bỏ NaN nên cổng từng in "khớp" với hộp NaN), `--expect-bbox ""`, CSV rỗng. `docs/media/traj/binh1_vat_ra_khung.{png,json}` sinh lại với **ô chọn thật** (`khop`, IoU 0,7115, `git_rev c5247cf`, `git_dirty_code false`) — bản trước dùng ô trùng CSV dòng đầu nên "khớp 0 %" là tautology. `./run lint` xanh · `./run test` **1291 passed** (5 deselected, +13 test). Review độc lập 1 vòng: 0 P0, đã đóng 1 P1 + 3 P2 + 4 P3. Log: `docs/task/16-11-2026-ticket-25-cong-expect-bbox.md`.
