# 17-11-2026 — Ticket #36: chọn ô GIỮA phiên ⇒ tên file mask lệch frame của clip

## Mục tiêu

`--dump-mask-frames` đặt tên file theo `_frame_index` của **phiên** (bắt đầu từ 0 lúc `start()`). Đường
CLI `--bbox` chọn ô **ngay frame đầu** ⇒ tên file đúng là frame của clip. Nhưng khi người dùng **kéo
chuột chọn ô giữa phiên** (web `mode=track`), phiên đã đọc N frame trước khi có ô chọn ⇒
`mask_000042.png` là frame 42 của **phiên**, tức frame **42+N của clip** ⇒ ghép với `gt_000042.png` là
chấm hai frame khác nhau — **mIoU sai mà im lặng**.

## Input

- `src/live_tracking.py::run()`: nhánh `if bbox is None` (trạng thái `waiting_selection`) đọc và phát khung
  hình trơn liên tục; `_frame_index` chỉ tăng sau khi bắt đầu bám.
- `manifest.json` đã có `nguon`/`bbox_xywh`/`frames_yeu_cau`/`frames_da_ghi`; `score_miou.kiem_khop_manifest`
  đã đọc `so_file_ghi_de` (ticket #26) — cùng cơ chế "cảnh báo MỀM ở chỗ CHẤM".

## Công việc đã thực hiện

1. `src/live_tracking.py`: đếm **`_frame_goc`** = số frame bị đọc trong giai đoạn CHỜ CHỌN Ô (chỉ tăng ở
   nhánh `bbox is None`, nên chọn ô ngay từ đầu ⇒ 0).
2. `manifest.json` khai **`frame_goc_cua_phien`** (kèm comment: 0 = đúng frame của clip; > 0 = tên file
   lệch đúng offset này).
3. Cảnh báo **một lần** khi dump nếu `frame_goc > 0`: in tên file + frame tương ứng của clip + trỏ tới
   `frame_goc_cua_phien` trong manifest.
4. `scripts/score_miou.py::kiem_khop_manifest`: `frame_goc_cua_phien > 0` ⇒ cảnh báo MỀM ở chỗ CHẤM (nêu
   đúng "cắt GT theo offset này, nếu không mIoU ghép lệch frame"); manifest **thiếu khoá** (bản cũ, mọi
   lần dump đều từ frame 0) ⇒ **không** cảnh báo rỗng.

**Không đổi tên file**: đổi sang `offset + index` sẽ làm mọi quy trình GT đã có (`gt_0000NN.png`) hiểu
sai, và đường CLI (offset 0) không có gì phải đổi. Cảnh báo + khai offset là cách sửa ít rủi ro nhất —
đúng phương án ticket cho phép ("hoặc cảnh báo chặn").

## Output / Kết quả

- Test mới: `tests/test_mask_dump_frame_idx.py` 2 test (chọn ô ngay ⇒ `frame_goc_cua_phien == 0` + không
  cảnh báo; `_frame_goc = 37` ⇒ manifest khai 37 + cảnh báo "SAU 37 frame") · `tests/test_score_miou.py`
  3 test (offset dương ⇒ cảnh báo có "ticket #36"; offset 0 ⇒ không; manifest cũ thiếu khoá ⇒ không).
- `./run lint` xanh · `./run test` **1360 passed**, 5 deselected (1355 → 1360: +5 test).
- Không đổi hành vi đường CLI `--bbox` (offset luôn 0).

## Vấn đề & cách xử lý

- Bản đầu đếm offset **sau khi `read()`** cho mọi frame chưa `started` ⇒ frame dùng để `start()` cũng bị
  đếm ⇒ `frame_goc = 1` cho ca chọn ô ngay từ đầu (test bắt được ngay). Sửa: chỉ đếm trong nhánh
  `bbox is None` (frame thật sự bị bỏ).
- Nguồn có `loop_files` (file lặp) thì `_frame_goc` cộng cả frame của vòng lặp — đúng nghĩa "số frame đã
  đọc", nhưng khi đó "frame của clip" phải hiểu là frame trong **vòng hiện tại**; ghi lại ở đây để người
  sau không ngạc nhiên.

## Next steps

- Ticket riêng cho `_smooth` chạy hai lần ở frame `start()` (nợ của #35).
- Chờ người dùng: silhouette ≥ 30 frame `binh1` (mIoU phân đoạn thật), clip chai đen (#11), clip
  drift-trong-khung (#14).

## Tài liệu tham khảo

- Ticket #36 · `src/live_tracking.py` (`run`, `_dump_mask`, `_write_mask_manifest`) ·
  `scripts/score_miou.py` (`kiem_khop_manifest`) · ticket #26 (`so_file_ghi_de` — cùng cơ chế cảnh báo ở
  chỗ chấm) · AGENTS §6 ("số sai im lặng" tệ hơn số thiếu).
