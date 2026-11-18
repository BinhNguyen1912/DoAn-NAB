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

## Bổ sung sau review vòng 2 (P1 mới + 3 P2 + 5 P3)

### P1 — guard "TỪ CHỐI" chỉ chặn lần ghi ĐẦU (lỗi thật của mình)

`if self._frame_goc and not self._da_canh_bao_offset:` ⇒ sau lần từ chối đầu, cờ thành `True` nên các
frame yêu cầu sau **rơi xuống `cv2.imwrite`** và ghi `mask_*.png` mang tên lệch frame — đúng thứ ticket
cấm. **Diễn tập lại đã thấy thật**: `dump_mask_frames=(0,5,8)`, bbox.json đến ở `is_set()` #3 ⇒ bản cũ
sinh `mask_000005.png` + `mask_000008.png`. Nay tách hai việc: cảnh báo **một lần**, `return False`
**mọi lần**; theo dõi `_tu_choi_offset` (set) ⇒ `_canh_bao_mask_thieu` nêu đúng lý do "TỪ CHỐI n frame"
thay vì khuyên "dùng --vos-every 1" khi `vos_every` đã là 1 (P3).

### P2 — "cổng danh nghĩa" ở `score_miou`

- `kiem_khop_manifest` nay trả **`(chan, mem)`**; `main` cộng `chan` vào lỗi chặn. Trước đây việc CHẶN
  được nối bằng **so tiền tố chuỗi** `"CHẶN CHẤM: "` ⇒ xoá 2 dòng promotion là block biến mất mà mọi
  test vẫn xanh. Thêm 2 test mức `main`: offset 37 ⇒ `main(...) == 2` **và `not out.exists()`**;
  `--cho-phep-offset` ⇒ `== 1`, artifact có, `canh_bao_gt` nêu cờ. **Diễn tập ngược**: đổi `chan +=`
  thành `mem +=` ⇒ 2/2 đỏ.
- `frame_goc_cua_phien` **có khoá mà không đọc được** (`2.7`, `"abc"`, `""`, `true`, `[37]`, `inf`) ⇒
  CHẶN (trước là bỏ qua = fail-open đúng trên khoá dùng để chặn).
- Đọc thêm **`frames_da_ghi`**: GT định chấm mà phiên này không ghi ⇒ `mask_*.png` còn trên đĩa là của
  **phiên/lần chọn KHÁC** ⇒ CHẶN. Chỉ xét frame ĐỊNH CHẤM (GT ∩ `frames_yeu_cau`) — bản nháp đầu đòi
  phủ hết GT nên **CHẶN OAN** demo synthetic (GT 24 frame, chấm 5); phát hiện khi diễn tập lại, đã sửa
  + có test ghim (GT rộng hơn `frames_yeu_cau` ⇒ `chan == []`).

### P3

`--bbox` đòi **số nguyên** (`0.5` qua cửa rồi `read_bbox` `int()` ⇒ hộp rỗng), chặn `x/y < 0`;
`bbox.json` hỏng (`{"x":1}`) nay bị chặn ở cửa (kiểm `read_bbox(...) is not None`, không chỉ
`.exists()`); `bbox.json` chỉ được ghi **sau toàn bộ validate** (trước đây `--vos-every 0` bị từ chối
nhưng vẫn để lại ô cũ ⇒ lần sau lặng lẽ bám ô đó); `run()` gọi lần hai ⇒ `RuntimeError` (bộ đếm frame
không reset ⇒ tên file lệch); doc: bỏ câu sai "chọn ô qua web/API" (web không dump) + tách comment
`#` đang nuốt mất `--vos-every/--dump-mask-frames/--stop-after-frames` trong ví dụ demo.

### Diễn tập lại workflow tài liệu sau khi sửa

```
live_worker --source data/synthetic_gt.mp4 --out-dir /tmp/demo_gt2 --bbox 20,90,60,60 \
  --image-size 192 --vos-every 1 --dump-mask-frames "0,6,12,18,23" --stop-after-frames 30
score_miou score --gt docs/gt/synthetic_tong_hop --pred-dir /tmp/demo_gt2/masks
```
⇒ 30 frame, 12,2 FPS, 5 mask, `frame_goc_cua_phien = 0`, **mIoU 0,9354 / 5 frame**, `loi_chan = []`
— trùng số đã công bố, tức cửa vào mới không đổi kết quả workflow chuẩn.

**File thay đổi (vòng này)**: `src/live_tracking.py`, `scripts/score_miou.py`, `tools/live_worker.py`,
`tests/test_mask_dump_frame_idx.py`, `tests/test_live_worker_cli.py`, `tests/test_score_miou.py`,
`docs/thuoc-do-bam-dung.md`, ticket #36.
**Trạng thái**: `./run lint` xanh · `./run test` **1377 passed** (5 deselected).

## Bổ sung sau review vòng 3 (2 P2 + P3)

### P2 #1 — CHẶN OAN (lỗi thật của mình) + câu chẩn đoán sai

Cổng `frames_da_ghi` chỉ so **số**, không kiểm file có trên đĩa ⇒ phiên **bị cắt trước frame yêu cầu**
(`--stop-after-frames` nhỏ, Ctrl+C, `imwrite` fail) cũng bị CHẶN (exit 2) kèm câu sai sự thật "mask còn
lại trên đĩa là của PHIÊN KHÁC". Trái hợp đồng đã ghi ở `src/live_tracking.py` ("không ghi file ⇒ chấm
đếm là *thiếu mask*"). Nay `kiem_khop_manifest(index, manifest, pred_dir)` chỉ chặn khi **file đó có
thật** trên đĩa.

**Diễn tập đúng lệnh reviewer đề nghị** (`--stop-after-frames 8`, yêu cầu frame `0,6,12,18`):

| | trước | sau |
|---|---|---|
| exit của `score` | **2** (chặn) + câu "mask của PHIÊN KHÁC" (sai) | **1** |
| `loi_chan` | 1 mục | `[]` |
| `so_frame_thieu_mask` | — (không ghi artifact) | **22** |
| mIoU | không công bố | 0,9392 trên **2** frame (đúng: chỉ 2 frame có mask) |
| cảnh báo của worker | "dùng --vos-every 1" (vô nghĩa, đã là 1) | "phiên chỉ chạy tới frame 8" |

### P2 #2 — producer `frames_da_ghi` không được ghim

Xoá 1 dòng `"frames_da_ghi": sorted(self._dumped)` thì cổng ở `score_miou` biến mất **vĩnh viễn** mà
không test nào đỏ. Đã thêm `test_manifest_ghim_frames_da_ghi` (⇒ đỏ khi xoá dòng đó, đã diễn tập).

### P3 đã sửa

- **Quay vòng nguồn** (`loop_files` mặc định BẬT): clip 12 frame + yêu cầu frame 15 ⇒ `mask_000015.png`
  là frame **3** của clip, tên SAI. Nay `_dump_mask` **từ chối** mọi dump sau lần quay vòng đầu (đếm ở
  `_rewind`), test: yêu cầu frame 0..19 trên clip 12 frame ⇒ chỉ có `mask_000000..000011`.
- **`--cho-phep-offset`** trước so **chuỗi con** `"frame_goc_cua_phien"` ⇒ hạ cấp luôn ca "khoá có mà
  KHÔNG đọc được" (mở khoá đúng lúc không biết offset). Nay nhãn loại `[offset]` vs
  `[offset-khong-doc]`: cờ chỉ hạ cấp nhóm đầu; test mức `main` với `"abc"` + cờ ⇒ vẫn **exit 2**.
- **`frames_da_ghi` dạng chuỗi** (`"0,6"`) nay được đọc (trước bỏ qua im lặng = fail-open trên đúng cổng
  này); thêm test; thêm test nhánh `frames_yeu_cau` dạng chuỗi (trước không có ⇒ xoá nhánh đó sẽ gây
  CHẶN OAN mà test vẫn xanh).
- **`status.json.cau_hinh.dump_mask_frames`** từng là danh sách **ký tự** (`['0', ',', '6']`) vì main
  truyền chuỗi vào `cau_hinh_yeu_cau`; nay main parse TRƯỚC rồi truyền list số (2 test).
- **Doc**: bảng mã thoát của `score` thêm hai cổng manifest + nhắc `--cho-phep-offset`.

### Ticket tạo mới (không im lặng bỏ)

`.scratch/camera-ai-realtime/issues/37-live-worker-bbox-ghi-de-bbox-json-cua-phien-api.md` — `--bbox`
của CLI có thể cướp `bbox.json` của phiên API đang chờ chọn ô (P3, cần bàn cách nhận biết phiên sống).

**Trạng thái**: `./run lint` xanh · `./run test` **1384 passed** (5 deselected) · diễn tập ngược 3/3
đỏ→xanh (quay vòng, `frames_da_ghi` producer, "file không tồn tại thì không chặn").

## Bổ sung sau review vòng 4 (1 P2 + P3)

### P2 — chẩn đoán SAI ở tổng kết phiên (lỗi thật của mình)

Frame bị từ chối vì **quay vòng** được nhét vào CÙNG set `_tu_choi_offset` với ca "chọn ô muộn" ⇒
`_canh_bao_mask_thieu` in `"TỪ CHỐI dump n frame … (phiên bắt đầu sau 0 frame) — chạy lại với ô chọn có
sẵn từ frame đầu"` — vừa sai sự thật (offset = 0) vừa khuyên đúng thứ **không** chữa được nguyên nhân
(nguồn lặp). Nay hai lý do có **set riêng** (`_tu_choi_offset` / `_tu_choi_quay_vong`) và **hai câu
riêng**; câu quay vòng khuyên `--stop-after-frames <= độ dài clip`. Test ghim: `"phiên bắt đầu sau 0
frame" not in out` + `"--stop-after-frames" in out`.

### P3 đã sửa

- **Fail-open trên đúng cổng CHẶN**: `frames_yeu_cau` CÓ mặt mà không parse được phần tử nào (`" "`,
  `[]` rác) ⇒ `dinh_cham = set()` rỗng ⇒ vòng kiểm `continue` **mọi** frame ⇒ cổng `frames_da_ghi` bị
  tắt im lặng. Nay: fail-**closed** (`dinh_cham = None` ⇒ kiểm mọi frame GT) + 1 dòng `mem`; 2 test mới
  (chuỗi rỗng ⇒ vẫn chặn; `pred_dir=None` ⇒ fail-closed, ghim để ai "sửa" thành fail-open sẽ đỏ).
- **Docstring** `kiem_khop_manifest` khớp hành vi thật: trả `(chan, mem)` (không còn "chỉ cảnh báo
  mềm"), `pred_dir=None` = fail-closed.
- **Test producer** `frames_da_ghi` trước đây **không có răng** với hồi quy nguy hiểm hơn (producer ghi
  *danh sách YÊU CẦU*): yêu cầu `[0,4,9]` mà mọi frame đều ghi ⇒ hai danh sách bằng nhau ⇒ test xanh.
  Nay dừng phiên trước frame 9 ⇒ `frames_yeu_cau [0,4,9]` vs `frames_da_ghi [0,4]`.
- **Câu chặn hạ giọng**: cửa sổ `kill -9`/manifest chưa kịp ghi (giữa `imwrite` và
  `_write_mask_manifest`) từng bị khẳng định chắc chắn "mask của PHIÊN KHÁC" ⇒ nay nêu cả khả năng đó.
- **`cau_hinh.dump_mask_frames`** lệch giữa `loading` và `running` của **cùng phiên** (`6,0,6` ⇒
  `[6,0,6]` vs `[0,6]`) ⇒ nay `sorted(set(...))` ở cả hai; test đổi sang `6,0,6 ⇒ [0,6]`.
- **Doc**: dòng "Giới hạn" của `manifest.json` (vẫn nói "chỉ có `nguon` + `frames_yeu_cau`") nay liệt kê
  đủ khoá + nói rõ cổng chứng minh *điều kiện sinh mask*, **không** chứng minh nội dung frame.
- Bỏ **nhãn nội bộ** (`[offset] `) khỏi stdout người đọc; bỏ assert "ghim hành vi xấu" (chuỗi ⇒
  char-list) trong test `cau_hinh` — nó sẽ đỏ oan nếu sau này ai chuẩn hoá chuỗi đúng chỗ.

**Diễn tập ngược 4/4 đỏ→xanh**: dồn set quay vòng về `_tu_choi_offset`; tắt fail-closed của
`frames_yeu_cau`; `cau_hinh` truyền `dump_frames` thô; (trước đó) xoá producer `frames_da_ghi`.

**Trạng thái**: `./run lint` xanh · `./run test` **1387 passed** (5 deselected).
