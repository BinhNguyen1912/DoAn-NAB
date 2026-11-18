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

**Status:** `resolved` — PR #39 merged `2c67143` (18-11); xem log `docs/task/17-11-2026-ticket-36-frame-goc-khi-chon-o-giua-phien.md`

**Blocked by:** None (can start immediately)

- [x] `manifest.json` có `frame_goc_cua_phien` (offset) và `score_miou` cảnh báo khi thiếu
- [x] Test: chọn ô giữa phiên + dump ⇒ tên file (hoặc cảnh báo) đúng frame của clip
- [x] Không đổi hành vi đường CLI `--bbox` (offset = 0)

## Answer

Xong: `src/live_tracking.py` đếm `_frame_goc` (số frame bị đọc trong giai đoạn CHỜ CHỌN Ô — chọn ô ngay
từ đầu ⇒ 0), `manifest.json` khai **`frame_goc_cua_phien`**, dump cảnh báo **một lần** khi offset > 0, và
`score_miou.kiem_khop_manifest` cảnh báo MỀM ở chỗ CHẤM ("cắt GT theo offset này"). Manifest cũ thiếu
khoá ⇒ không cảnh báo rỗng.

**Không đổi tên file**: đổi sang `offset + index` sẽ làm mọi GT đã có hiểu sai và đường CLI (offset 0)
không cần đổi — cảnh báo + khai offset là phương án ít rủi ro nhất mà ticket cho phép.

`./run test` **1360 passed** (+5 test: 2 ở `test_mask_dump_frame_idx`, 3 ở `test_score_miou`).
Log: `docs/task/17-11-2026-ticket-36-frame-goc-khi-chon-o-giua-phien.md`.

## Bổ sung sau review vòng 1

**P1 (ánh xạ sai frame clip)**: `_frame_goc` là số lần đọc THÔ; nguồn `loop_files=True` mặc định quay
vòng (`binh1.mp4` = 333 frame) ⇒ "frame N+offset của clip" **sai**. Bỏ hẳn cách ánh xạ, chọn phương án
ticket cho phép — **từ chối**:
- `tools/live_worker.py`: `--dump-mask-frames` + chưa có `<out-dir>/bbox.json` ⇒ `parser.error` (mã 2),
  trừ khi truyền `--bbox x,y,w,h` (nay `live_worker` tự ghi bbox.json ở dạng xywh, chặn `x1,y1,x2,y2`).
- `LiveTrackingSession._dump_mask`: phiên đã bỏ frame lúc chờ chọn ô ⇒ **TỪ CHỐI GHI** + cảnh báo
  một lần; không file, không manifest.
- `score_miou`: `frame_goc_cua_phien > 0` ⇒ **CHẶN** (exit 2, không artifact), `--cho-phep-offset` để
  người chấm tự nhận trách nhiệm; `_so_nguyen()` nhận `"37"`/`37.0` (trước bỏ qua im lặng — fail-open).

**P2 (test mù + doc sai đường)**: test cũ `_preselect`/gán tay state nên xoá dòng `_frame_goc += 1` mà
vẫn xanh. Nay có test **đúng nhánh chờ chọn ô** (`bbox.json` xuất hiện ở lần `is_set()` thứ 3 ⇒
`_frame_goc > 0`, không file mask, không manifest, có "TỪ CHỐI dump"), diễn tập ngược 1/1 đỏ.

**P3 đã sửa**: log ghi đúng đường tới được (CLI + bbox đến muộn — **không** phải web, web không bao giờ
dump); `docs/thuoc-do-bam-dung.md` thêm quy tắc "phiên phải bám từ frame đầu" + ví dụ `--bbox`;
`_da_canh_bao_offset` khai trong `__init__`.

## Bổ sung sau review vòng 2

- **P1 (lỗi thật)**: guard chỉ chặn lần ghi ĐẦU (cờ `_da_canh_bao_offset` chặn luôn cả khối `return
  False`) ⇒ các frame yêu cầu sau vẫn ghi file lệch frame. Diễn tập lại thấy `mask_000005.png` +
  `mask_000008.png`. Nay: cảnh báo 1 lần, **từ chối MỌI lần**, ghi `_tu_choi_offset` để báo đúng lý do.
- **P2**: `kiem_khop_manifest` trả `(chan, mem)` (hết "cổng danh nghĩa" nối bằng tiền tố chuỗi) + 2
  test mức `main` (exit 2 & không artifact; `--cho-phep-offset` ⇒ exit 1); offset **không đọc được**
  ⇒ CHẶN; đọc `frames_da_ghi` để bắt mask còn lại từ phiên khác (chỉ xét frame định chấm).
- **P3**: `--bbox` số nguyên không âm; chặn `bbox.json` hỏng; ghi bbox.json sau validate; `run()` lần
  hai ⇒ `RuntimeError`; doc sửa câu sai "chọn ô qua web/API" + tách comment nuốt cờ.

## Bổ sung sau review vòng 3

- **P2 (chặn oan)**: `frames_da_ghi` chỉ chặn khi **file có thật** trên đĩa (`kiem_khop_manifest` nhận
  `pred_dir`). Phiên bị cắt trước frame yêu cầu ⇒ "thiếu mask" (exit 1, `so_frame_thieu_mask`), không
  phải "mask của phiên khác". Diễn tập: `--stop-after-frames 8` + yêu cầu `0,6,12,18` ⇒ nay exit 1,
  `loi_chan = []`, `so_frame_thieu_mask 22`.
- **P2 (producer không ghim)**: thêm `test_manifest_ghim_frames_da_ghi`.
- **P3 đã sửa**: từ chối dump sau khi nguồn **quay vòng** (clip 12 frame + frame 15 ⇒ `mask_000015` là
  frame 3); `--cho-phep-offset` phân loại bằng nhãn (không hạ cấp "khoá không đọc được"); đọc
  `frames_da_ghi` dạng chuỗi; `cau_hinh.dump_mask_frames` là list số; doc bảng mã thoát.
- **Ticket mới**: #37 (`--bbox` cướp `bbox.json` của phiên API đang chờ chọn ô).
