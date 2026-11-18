# 17-11-2026 — Ticket #36: chọn ô GIỮA phiên ⇒ tên file mask lệch frame của clip

## Mục tiêu

`--dump-mask-frames` đặt tên file theo `_frame_index` của **phiên** (bắt đầu từ 0 lúc `start()`). Đường
CLI `--bbox` chọn ô **ngay frame đầu** ⇒ tên file đúng là frame của clip. Nhưng khi người dùng **kéo
chuột chọn ô giữa phiên** (web `mode=track`), phiên đã đọc N frame trước khi có ô chọn ⇒
`mask_000042.png` là frame 42 của **phiên**, tức frame **42+N của clip** ⇒ ghép với `gt_000042.png` là
chấm hai frame khác nhau — **mIoU sai mà im lặng**.

**Đường tới được (đính chính so với bản log đầu):** web `mode=track` **không** dump mask
(`build_live_worker_command` không truyền `--dump-mask-frames`, `LiveTrackConfig.dump_mask_frames` mặc
định `()`), nên ca thật là `tools/live_worker.py --dump-mask-frames` chạy **trước khi** có
`bbox.json` (người dùng chạy CLI rồi mới đặt ô chọn) — và nguồn `loop_files=True` mặc định **quay
vòng** (`binh1.mp4` 333 frame) ⇒ `offset + idx` **không** phải frame của clip khi đã chờ > 11 s.

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

## Bổ sung sau review vòng 1 (P1 + 2 P2)

Reviewer bắt đúng **P1**: `_frame_goc` là số lần đọc THÔ, không phải offset trong clip — với nguồn
quay vòng, "frame N+offset của clip" là **sai**; cả manifest, cảnh báo lúc dump và lời dặn của
`score_miou` đều dựa trên ánh xạ sai đó. Đã đổi sang phương án **từ chối** (ticket #36 cho phép):

1. `tools/live_worker.py`: `--dump-mask-frames` mà `<out-dir>/bbox.json` chưa có ⇒ `parser.error` (mã 2)
   ngay ở cửa vào — dump chỉ đúng khi bám từ frame đầu.
2. `LiveTrackingSession._dump_mask`: nếu phiên đã bỏ frame lúc chờ chọn ô ⇒ **TỪ CHỐI GHI** + cảnh báo
   một lần (không ghi file mang tên sai frame, không ghi manifest như thể đã đo).
3. `scripts/score_miou.py`: `frame_goc_cua_phien > 0` ⇒ **CHẶN CHẤM** (exit 2, **không ghi artifact**)
   thay vì "cảnh báo mềm nhưng vẫn công bố mIoU" (P2: số chắc chắn sai, không có cờ nào chấm bù);
   `--cho-phep-offset` chỉ dùng khi người chấm ĐÃ tự cắt GT lệch. Thêm `_so_nguyen()` để nhận
   `"37"`/`37.0` — bản trước bỏ qua im lặng (fail-open đúng ở khoá dùng để chặn).
4. `docs/thuoc-do-bam-dung.md`: thêm quy tắc "phiên phải bám từ frame đầu" + giải thích chặn.
5. Test: **đúng nhánh chờ chọn ô** (không `_preselect`, `bbox.json` xuất hiện ở lần `is_set()` thứ 3) ⇒
   `_frame_goc > 0`, **không** có `mask_*.png`, **không** có manifest, có cảnh báo "TỪ CHỐI dump";
   + 2 test cửa vào `live_worker` (chưa có bbox ⇒ mã 2; có bbox ⇒ không bị chặn vì lý do này);
   + test `score_miou`: offset `"37"`/`37.0`/`37` ⇒ khoá CHẶN; offset 0/thiếu khoá ⇒ **`mem == []`**
   (thay vì kiểm theo chuỗi — P3).
   Diễn tập ngược: tắt guard "TỪ CHỐI" ⇒ test chờ-chọn-ô **đỏ**, phục hồi ⇒ xanh.

**Sửa lời theo P3**: log ghi đúng đường tới được (CLI + `bbox.json` đến muộn, **không** phải web);
ticket đổi câu "cảnh báo chặn" → "**từ chối** dump" như issue gốc; bỏ tick tiêu chí "test nêu đúng frame
của clip" (không đúng khi nguồn quay vòng — nay tiêu chí là "từ chối"), `_da_canh_bao_offset` khai trong
`__init__`.

### Diễn tập lại workflow tài liệu (`docs/thuoc-do-bam-dung.md` mục 3) — 18-11

Cửa vào mới có thể phá chính workflow mà tài liệu dạy, nên chạy lại nguyên lệnh:

```
live_worker --source data/synthetic_gt.mp4 --out-dir /tmp/demo_gt --bbox 20,90,60,60 \
  --image-size 192 --vos-every 1 --dump-mask-frames "0,6,12,18,23" --stop-after-frames 30
score_miou score --gt docs/gt/synthetic_tong_hop --pred-dir /tmp/demo_gt/masks
```

Kết quả: 30 frame, 12,0 FPS, 5 mask `mask_{000000,000006,000012,000018,000023}.png`,
`manifest.frame_goc_cua_phien = 0`, **mIoU 0,9354 trên 5 frame** — trùng số đã công bố trong tài liệu
(`0,9354`, 5 frame, `coverage 0,208`) ⇒ cửa vào mới **không** đổi kết quả của workflow chuẩn.
`--bbox 20,90,60,60` lấy từ `docs/gt/synthetic_tong_hop/index.json` (`frames[0].bbox_xywh`) — bản nháp
đầu của mình ghi `10,10,60,60` (đoán) sẽ cho mask lệch, không được để vào tài liệu.
