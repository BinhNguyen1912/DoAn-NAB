# 25-11-2026 — Chế độ "Ảnh từng bước" cho UI gán nhãn (dán nhanh, không phải dừng video)

## 1. Mục tiêu

Người dùng báo: *"mày có thể cắt từng frame được không, video bấm dừng rồi gán mất thời gian quá"*.
Yêu cầu: dán nhãn `đúng/sai` cho từng bước suy luận mà **không phải phát video rồi bấm dừng**.

## 2. Input

- `tools/label_ui.py` (server HTTP nội bộ), `tools/label_ui.html` (UI), `scripts/e2e_label_ui.js`.
- Session thật `data/demoip_1125-121456_web.mp4` (H.264, 30 fps, 2 939 frame, 98 s) để đo.
- Đo trên máy này (`git_rev 2cbe817`, WSL2, không GPU).

## 3. Công việc đã thực hiện

### 3.1. Server: cắt frame theo bước + cache (`tools/label_ui.py`)

- `chi_so_khung(phien, buoc)`: bước VOS ⇒ **chỉ số frame** trong video, dùng **đúng phép bù của UI**
  `t_map = t_uoc_luong × (thời lượng video / tổng latency)` — chia đều `thời lượng/số_bước` lệch tới
  12 s trên phiên 98 s (bài học đã ghi trong AGENTS §6).
- `anh_buoc(phien, buoc)`: seek + đọc + nén JPEG (thu nhỏ ≤ 960 px ngang, quality 85), **cache trên
  đĩa** `data/nhan/.anh/<phiên>/<buoc>.jpg` (thư mục bắt đầu bằng `.` nên không bị liệt kê là phiên).
- Route mới `GET /anh?phien=&buoc=` → `image/jpeg`, `Cache-Control: max-age=86400` (ảnh của một bước
  là bất biến); lỗi ⇒ 404 kèm JSON lý do (không trả ảnh rỗng).
- `/api/frames` trả thêm `rong`/`cao` (**pixel video gốc**) để UI quy đổi ảnh đã thu nhỏ về toạ độ
  video khi lưu `bbox_dung`.

### 3.2. UI: một nguồn sự thật cho "đang xem bước nào" (`tools/label_ui.html`)

- Ô chọn `cheDo` (**mặc định `anh`**) + `<img id="anh">`; chế độ `video` giữ nguyên hành vi cũ.
- `chiSoDangXem()` = ảnh ⇒ `state.i`, video ⇒ suy từ `currentTime`. **Ba chỗ trước đây tự gọi
  `chiSoHienTai()`** (`ghimBuoc`, `veO.buoc` khi mousedown, `luuVaTiep`) — đã chuyển hết.
- Prefetch 4 ảnh kế; `←/→` ở chế độ ảnh chỉ đổi `state.i` (không seek).
- `ghiNhan` chặn theo **nguồn đang xem**: ảnh ⇒ cần `state.anhOk`, video ⇒ cần `state.videoOk`.

## 4. Output / Kết quả

| Chỉ số | Số đo |
|---|---|
| Ảnh bước mới (lần đầu) | 62–346 ms (3 bước đo: 0 → 346, 141 → 62, 294 → 153) |
| Ảnh đã cache | **9 ms** |
| 8 request ảnh **song song** (prefetch) | 0,83 s, 8/8 thành công |
| `./run test` | **2 202 passed**, 6 deselected (217 s) |
| `./run labeluie2e` | **PASS 30/30** (thêm 5 mục mới cho chế độ ảnh) |
| `./run lint` | sạch |

## 5. Vấn đề & cách xử lý

1. **`libavcodec` assert ⇒ chết cả tiến trình.** Prefetch 4 ảnh song song = 4 request của
   `ThreadingHTTPServer` cùng seek/đọc **một** `VideoCapture`; OpenCV/FFmpeg không thread-safe:
   `Assertion fctx->async_lock failed at libavcodec/pthread_frame.c:174` rồi abort (log
   `data/labelui_e2e_server.log`). Sửa: `_CAP_LOCK` (threading.Lock) bọc seek+read; test
   `test_cap_khong_bi_dung_song_song` (12 thread) bắt hồi quy.
2. **E2E bắt 2 bug thật của bản đầu** (đúng loại "chỉ số đẹp, kết quả sai"):
   - `ghimBuoc` chưa đổi ⇒ ở chế độ ảnh, nhãn vẫn ghim **giờ video đứng yên** ⇒ cả 3 nhãn rơi vào
     `buoc 150` thay vì bước đang xem. Phát hiện nhờ in file JSONL của e2e (3 dòng cùng `buoc`).
   - `veO.buoc = chiSoHienTai()` ⇒ ô vẽ ở chế độ ảnh bị coi là "của bước khác" ⇒ `bbox: []`.
3. **Hai mục e2e cũ kiểm khái niệm chỉ có ở chế độ VIDEO** (`tua được video`, `cảnh báo LỆCH`) ⇒
   chuyển chúng vào khối chuyển sang chế độ Video thay vì xoá (vẫn giữ độ phủ).
4. **Chế độ ảnh từng bị khoá oan bởi `<video>`** (tự phát hiện sau khi dựng xong): `datTrangThaiVideo(false)`
   disable mọi nút ghi nhãn + phủ banner đỏ lên khung ⇒ đúng phiên `mp4v` (lý do sinh ra chế độ ảnh) vẫn
   không dán được. Nay `capNhatKhoa()` khoá theo **nguồn đang xem** (`anhOk` / `videoOk`), banner video
   chỉ hiện ở chế độ video; test `test_html_khoa_ghi_nhan_theo_nguon_dang_xem`.
5. **`git add -A` trong cây bẩn nuốt dữ liệu của người dùng** (đúng anti-pattern AGENTS): commit
   `ca794f7` kéo theo **13 JPEG cache** (`data/nhan/.anh/`) và 1 file nhãn đang dán dở. Đã sửa:
   `.gitignore` thêm `data/nhan/.anh/` — **phải đặt SAU** các ngoại lệ `!data/nhan/...` (git lấy mẫu
   khớp CUỐI CÙNG; để trước thì ngoại lệ thắng, đúng lỗi lần 1), `git rm -r --cached`, test
   `test_cache_anh_khong_duoc_commit`. **Bài học: file nhãn `data/nhan/*.jsonl` được track có chủ ý
   (là bằng chứng) ⇒ từ nay stage theo ĐƯỜNG DẪN CỤ THỂ, không `git add -A`.**
6. Test cũ `test_html_CHAN_ghi_nhan_khi_video_khong_phat_duoc` ghim chuỗi `if (!state.videoOk)` ⇒
   cập nhật sang điều kiện theo chế độ (hợp đồng mới: *nguồn đang xem* phải hiện được).

## 6. Next steps

- Đo tốc độ dán thật (số nhãn/phút) trước và sau khi có chế độ ảnh — hiện chỉ có số ms/ảnh.
- Nếu dán nhiều clip: thêm nút "chỉ hiện bước có sự kiện" (mất dấu/nghi) để nhảy cóc.

## 7. Tài liệu tham khảo

- `docs/cach-gan-nhan.md` mục 2 (đã thêm mô tả chế độ ảnh).
- AGENTS.md §6: hệ số bù thời gian (chia đều lệch 12 s), `_CAP_LOCK`.
