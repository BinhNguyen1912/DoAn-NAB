# 25: `--expect-bbox` tự đoán dạng hộp ⇒ có thể báo "khớp" OAN với hộp `(x,y,w,h)` hợp lệ

**What to build:** `scripts/make_trajectory_media._canh_bao_bbox` phân biệt `(x,y,w,h)` vs `(x1,y1,x2,y2)`
bằng `x2 <= x1`. Một hộp `(x,y,w,h)` **hợp lệ** với `w > x` (vd `50,100,300,400`) bị đọc thành
`x1,y1,x2,y2` ⇒ script có thể in "ô bao khớp --expect-bbox" trong khi thực ra không khớp. Đây chính là
chốt chặn bẫy "ô chọn sai vật" (AGENTS §6: bbox trỏ vào nền vẫn cho `ket_qua = true`).

**Cách làm:** bắt buộc khai dạng (`--expect-bbox xywh|50,100,300,400`), hoặc từ chối khi không phân biệt
được thay vì đoán.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `"50,100,300,400"` ⇒ báo "không phân biệt được dạng", KHÔNG in "khớp"
- [ ] Dạng khai tường minh vẫn chạy được (test cho cả hai)
