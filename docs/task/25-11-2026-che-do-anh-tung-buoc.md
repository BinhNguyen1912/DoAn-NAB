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

Số đo có **artifact** (`scripts/do_toc_do_anh.py` → `data/labelui_anh_2026-11-25_metrics.json`,
`git_rev 0bb2b33`, `git_dirty_code = false`, `loadavg_1m 0,63`; 10 bước × 3 lần, cache xoá trước khi đo):

| Chỉ số | Số đo |
|---|---|
| Ảnh bước **chưa cache** (seek + decode + nén + ghi) | mean **38,1 ms** · max **192,1 ms** (n = 10; max là lần mở `VideoCapture` đầu tiên — **không** gọi là p95) |
| Ảnh **đã cache** (đọc file) | mean **9,7 ms** · max **14,9 ms** (n = 20) |
| Kích thước JPEG | 29 980–40 018 B (mean 34 773) |
| **8 request song song** (prefetch) | **99,7 ms** tổng, mở đúng **1** `VideoCapture` (`song_song`) |
| `./run test` | **2 216 passed**, 6 deselected (213 s) |
| `./run labeluie2e` | **PASS 37/37** (thêm 7 mục: ảnh tải được, ←/→ đổi ảnh, CLICK nút nhãn, giữ bước khi đổi chế độ…) |
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
6. **Ảnh lấy từ FILE GỐC, không qua `video_de_phat`**: hàm đó có thể **chuyển mã cả clip** (0,5–30 s)
   trước khi trả ảnh đầu tiên. `cv2` đọc được `mp4v` (Chrome thì không) nên chỉ khi **không có** file
   gốc mới đi qua đường chuyển mã. Test `test_khong_transcode_khi_lay_anh`.
7. Test cũ `test_html_CHAN_ghi_nhan_khi_video_khong_phat_duoc` ghim chuỗi `if (!state.videoOk)` ⇒
   cập nhật sang điều kiện theo chế độ (hợp đồng mới: *nguồn đang xem* phải hiện được).

## 5b. Review độc lập (bắt buộc §9.1) — 1 vòng, P0 = 0

Reviewer độc lập (task `mwvuydnk-47f9`) kết luận **P0 = 0** nhưng bắt 2 **P1** và 11 P2/P3. Đã sửa hết
P1 + các P2 ảnh hưởng dữ liệu:

| Mức | Lỗi | Sửa |
|---|---|---|
| P1 | Nút nhãn **chết** sau mỗi `←/→`: `napAnh` disable 5 nút, `onload` không bật lại (`capNhat` không gọi `capNhatKhoa`) — e2e cũ chỉ bấm PHÍM nên không thấy | `capNhatKhoa()` trong `onload`; **thêm mục e2e CLICK nút** (bắt được hồi quy) |
| P1 | `_CAP_LOCK` hở: docstring khai "gọi dưới khoá" nhưng `chi_so_khung` + `/api/frames` không khoá ⇒ mở trùng `VideoCapture`, cái bị đuổi **không `release()`** | Khoá nằm **trong** `_mo_video` (`RLock`), `release()` khi đuổi, cache luôn `rong/cao`; test đếm constructor (12 thread ⇒ **1** capture) |
| P2 | `t_video` ở chế độ ảnh là `t_uoc_luong × he_so` (giá trị SUY RA); nếu `<video>` không có metadata thì công thức **không bù** trong khi ảnh đã bù ⇒ nhãn lệch vài giây | Server trả `idx` + `t_video_thuc` (= `idx/fps` của đúng frame đã cắt); UI ghi số đó |
| P2 | Đổi ảnh↔video **mất vị trí** (video về 0 s) | `datCheDo` đồng bộ hai chiều + mục e2e |
| P2 | Đổi TÊN người dán gọi `chonPhien` ⇒ nạp lại cả phiên, `dangTai = true` ⇒ **nuốt phím nhãn** | Tách `capNhatNhanCuaToi()` (chỉ làm mới nhãn, nhớ `veTienDo`) |
| P2 | `/anh` không qua chốt chống DNS-rebinding | thêm vào điều kiện `_host_hop_le()` |
| P2 | Cache trả ảnh cho bước **ngoài dải** (CSV sinh lại); cache **cụt** do ghi không atomic; cache không biết nguồn đã đổi | kiểm dải TRƯỚC cache; ghi `*.tmp` + `os.replace`; `manifest.json` chứa fingerprint (`mtime_ns` CSV + size video) |
| P2 | `cap.set()` thất bại bị bỏ qua ⇒ cắt **frame của bước khác** rồi cache | kiểm giá trị trả về; kẹp `idx` ngay trong `chi_so_khung`; `he_so_bu()` trả `bi_kep` và UI hiện cảnh báo |
| P2 | 2 test **giả** (`0 <= idx < 30` vẫn xanh khi xoá phép bù; test song song chỉ "không ném") | assert số thật (`idx_cuoi == 28`), test đếm constructor/release, thêm test cache cũ/cụt/đổi nguồn |
| P2 | Số ms trong log **không có artifact** (AGENTS §6) | `scripts/do_toc_do_anh.py` → `data/labelui_anh_2026-11-25_metrics.json` |
| P3 | `/anh` thiếu `buoc` mặc định về bước 0; `/api/frames` dùng `doc_phien` không cache; AGENTS ghim "29 mục" | 400 khi thiếu `buoc`; dùng `doc_phien_cached`; AGENTS bỏ số ghim |

**Bài học quy trình**: 5 lần `str.replace` của tôi **không khớp** nhưng script vẫn in "ok" ⇒ khối e2e
"chế độ ảnh" tưởng đã có mà thực ra **chưa bao giờ được chèn**, và reviewer đếm ra 30 mục thay vì 35.
Từ nay: sau mỗi lần thay chuỗi phải `assert` chuỗi mới **có trong file** rồi mới tin.

## 5c. Review độc lập vòng 2 — P0 = 0, nhưng tôi vừa tạo 1 P1

Vòng 2 bắt đúng một hồi quy **do fix vòng 2 sinh ra**: `/api/frames` trang trí `da_gan`/`rong`/`idx`
lên **chính dict trong cache** `doc_phien_cached` (dùng chung giữa các thread) ⇒ 2 người dán chung một
server có thể **nhận nhãn của nhau**, và `rong/cao` có thể mất key ⇒ ô vẽ sai tỉ lệ. Đã sửa bằng
**copy-on-read** (chép dict + chép từng frame) + 2 test (1 test 2 thread qua `Barrier`, 1 test assert
cache không bị thêm key).

Sửa thêm 6 P2/P3: `state.i` không reset khi đổi **phiên** (guard so sau khi đã gán ⇒ phiên ngắn hơn thì
`/anh` 404 ⇒ khoá sạch nút); nhánh "src không đổi" bật khoá ghi nhãn mà không kiểm ảnh có thật (nhãn
mù); cảnh báo `LỆCH` bắn sai ở chế độ Ảnh khi `<video>` thiếu metadata (ca mp4v) ⇒ ép `lech = 0`;
`Cache-Control: max-age=86400` vô hiệu hoá fingerprint ⇒ `no-cache`; fingerprint đọc lại **trước khi
ghi cache** (chống cache ảnh nguồn cũ dưới fingerprint mới); file tạm dùng `tempfile.mkstemp`; nhãn ghi
thêm `che_do`; script đo bỏ "p95" khi n < 100 + thêm mục `song_song`.

## 6. Next steps

- Đo tốc độ dán thật (số nhãn/phút) trước và sau khi có chế độ ảnh — hiện chỉ có số ms/ảnh.
- Nếu dán nhiều clip: thêm nút "chỉ hiện bước có sự kiện" (mất dấu/nghi) để nhảy cóc.

## 7. Tài liệu tham khảo

- `docs/cach-gan-nhan.md` mục 2 (đã thêm mô tả chế độ ảnh).
- AGENTS.md §6: hệ số bù thời gian (chia đều lệch 12 s), `_CAP_LOCK`.
