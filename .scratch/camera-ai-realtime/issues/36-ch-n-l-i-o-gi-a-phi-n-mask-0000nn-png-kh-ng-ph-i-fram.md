# 36: Chọn lại ô GIỮA phiên: `mask_0000NN.png` không phải frame NN của clip ⇒ mIoU lệch nếu dump qua UI

**What to build:** Phát hiện của audit sau merge 17-11 (mục "ngoài phạm vi 4 PR", có từ trước).

`--dump-mask-frames` đặt tên file theo **chỉ số frame VIDEO của phiên** (`self._frame_index`, tính từ 0
khi `start()`). Đường CLI (`--bbox`) thì đó đúng là frame của clip. Nhưng khi người dùng **kéo chuột
chọn ô giữa phiên** trên web (`mode=track`), phiên đã chạy N frame trước khi có ô chọn ⇒ `_frame_index`
vẫn tính từ 0 tại thời điểm `start()`, tức `mask_000042.png` là **frame 42 của PHIÊN**, không phải frame
42 của clip. Ghép với `gt_000042.png` cắt từ clip ⇒ **mIoU sai mà không có cảnh báo**.

Hiện chưa gây hại trong thực tế (mIoU đang chạy bằng `--bbox`/CLI), nhưng đúng lớp lỗi "số sai im lặng"
mà repo đã gặp 3 lần (P0 14-11 về tên file theo bộ đếm engine; ticket #26 về ghi đè).

Việc:
- Khi phiên bắt đầu bằng "chọn ô giữa phiên" (nguồn đã đọc N frame), ghi rõ **offset** vào
  `manifest.json` (`frame_goc_cua_phien` = số frame đã đọc trước `start()`), và đặt tên file theo
  `offset + _frame_index`, hoặc **từ chối** dump kèm cảnh báo "dump qua UI chưa ghép được GT".
- `score_miou.kiem_khop_manifest` đọc offset đó: thiếu ⇒ cảnh báo ở chỗ CHẤM (giống cách xử lý
  `so_file_ghi_de`).
- Test: phiên `mode=track` chọn ô sau N frame + `--dump-mask-frames` ⇒ tên file / manifest nêu đúng
  frame của **clip** (hoặc có cảnh báo chặn).

**Status:** `ready-for-agent`

**Blocked by:** None (can start immediately)

- [ ] `manifest.json` có `frame_goc_cua_phien` (offset) và `score_miou` cảnh báo khi thiếu
- [ ] Test: chọn ô giữa phiên + dump ⇒ tên file (hoặc cảnh báo) đúng frame của clip
- [ ] Không đổi hành vi đường CLI `--bbox` (offset = 0)
