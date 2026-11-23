# Ngày 23-11-2026 — Quyết định lớn (tắt re-ID mặc định) + 3 ticket UI/video

## 🎯 Mục tiêu

1. Trả lời câu "nếu sửa xong thì kết quả sẽ như thế nào" **bằng số**, và **luôn có đường lui** trước
   một quyết định lớn.
2. Biến 3 lỗi đo được của phiên demo thật `demoip_1123-144505` thành 3 ticket và làm xong:
   HUD nói dối (`#43`), video nén thời gian 1,48× (`#44`), cổng nghi = công tắc tắt vĩnh viễn (`#45`).
3. Mở plan 3 ý kiến cho lỗi gốc còn lại — mask tràn nền cùng tông (`#46`).

## 📥 Input

- Phiên demo thật của người dùng: `data/demoip_1123-144505_metrics.csv` (194 frame),
  `_summary.json`, `_run_info.json`, `_web.mp4`; `git_rev 42efc56`; `git_dirty_code` sạch.
- Ảnh trích từ `_web.mp4` (giây 15,7 / 17,3 / 19,3 / 20,5) — dùng để xác nhận bằng MẮT.
- Clip + GT đã có: `data/binh1.mp4` + `docs/gt/b1` (7 frame), `data/clip_be2.mp4` +
  `docs/gt/vat_be_vaolai` (6 frame vẽ xong, 5 frame còn trống chưa tô).
- `AGENTS.md` mục 6 (kinh nghiệm đã đo) + mục 9.1/9.2 (review độc lập, plan 3 ý kiến).
- Yêu cầu người dùng: "sửa xong thì kết quả thế nào, luôn có 1 nhánh backup lại không thôi sai là sai
  hết" và "ok chạy các ticket đi, khi nào cần tôi thì cứ nói".

## 🔨 Công việc đã thực hiện

### 1. Đo nốt bảng 2×2 (re-ID × cổng đóng băng) — để biết "sửa" mua được gì

| clip (GT) | không re-ID | không re-ID + cổng mở | có re-ID | có re-ID + cổng mở |
|---|---|---|---|---|
| `binh1` (7 frame) | **0,7794** | 0,7794 | **0,4236** | 0,7794 |
| `clip_be2` (6 frame) | **0,8754** | 0,8754 | 0,8577 | **0,5668** |

Ba kết luận:
1. Cờ `--lost-after-frames` **không có tác dụng gì khi không bật re-ID** — cơ chế "đóng băng" nằm
   trong `ReIdSession`, không phải vòng lặp pipeline. ⇒ "để model tự bám lại" = **tắt re-ID**, không
   phải sửa cờ.
2. re-ID **không thắng ô nào** trong 4 ô; ô tệ nhất mất **0,31 mIoU** và mask tràn ra ngoài GT **19,6 %**.
3. ⇒ Quyết định: `./run demoip` mặc định `--no-reid`. **Không đổi mặc định `tools/run_live.py`**
   (artifact cũ vẫn tái lập được).

### 2. Đường lui (yêu cầu trực tiếp của người dùng)

- Tag `demo-ok-23-11` + nhánh `backup/demo-ok-23-11` = trạng thái **trước** quyết định.
- Quay lại: `git switch backup/demo-ok-23-11`; chạy kiểu cũ **không cần đổi nhánh**:
  `./run demoip --reid`.

### 3. Ticket `#43` — HUD nói dối

Phiên `144505` (re-ID tắt) in **"MẤT DẤU — TỰ TÌM LẠI"** trong khi hệ **không có re-ID** ⇒ hứa một
việc không làm được, và câu đó nằm trong video nộp bài.

Sửa: hàm thuần `lost_banner_text(tu_tim_lai, co_font)`; `Visualizer.reid_enabled` (mặc định `False`);
set ở **cả ba** đường (`smooth_display.run_smooth_display`, `live_pipeline.run_tracking`,
`live_pipeline.run_interactive`). Rà toàn repo: worker/web **không** in câu đó ⇒ không có chỗ thứ hai.

### 4. Ticket `#44` — video nén thời gian 1,48×

Đo: thời gian suy luận thật **30,76 s** nhưng `_web.mp4` = **625 frame @30 fps = 20,83 s**.

Sửa: `Visualizer._write()` giữ nhịp theo **đồng hồ thực** (`int((now-t0)*fps)+1`, lặp frame đang vẽ),
có trần `_MAX_LAP_FRAMES = 60` và **REBASE** mốc khi vượt trần (không rebase thì mọi lần ghi sau đều
dính trần ⇒ slideshow). Cờ `pace_realtime` **mặc định TẮT**; chỉ `tools/run_live.py` bật cho nguồn
live qua `_la_nguon_live()` (webcam / rtsp / http) — nguồn file phải ghi 1:1 đúng fps clip, nếu không
một clip 333 frame sẽ thành 29 s thay vì 11 s.

Diễn tập live (model giả 100 ms/bước, hiển thị 20 fps, phiên 6,08 s):

| | số frame | thời lượng file | sai lệch |
|---|---|---|---|
| KHÔNG pace (trước #44) | 68 | **2,27 s** | thiếu **62,7 %** |
| CÓ pace (sau #44) | 174 | **5,80 s** | lệch **4,6 %** |

### 5. Ticket `#45` — cổng nghi = công tắc tắt vĩnh viễn

Đo trên chính phiên `144505`: `nghi_doi_tuong = 1` trên **50/194 frame (25,8 %)**, liên tục từ f144
tới hết phiên; `reacquired_count = 0`, `reselect_n = 0` ⇒ **không có gì tự xoá latch** khi re-ID tắt.
Ảnh giây 20,5: vật (remote vàng) **rõ trong khung** mà màn hình **không vẽ gì**.

Chọn phương án (a): khi nghi ⇒ **ô NÉT ĐỨT màu vàng + nhãn "NGHI"**, không tô mask, không vẽ quỹ
đạo, ở **cả hai** đường (`visualizer.render` và `live_tracking._annotate`). Bác (b) "tự xoá sau 8 s"
(vẽ lại đúng vùng sai mà không có bằng chứng mới — đúng lỗi 21-11) và (c) "chỉ thêm nút web" (CLI vẫn
trắng màn hình). Giữ nguyên luật 21-11 cho `no_evidence` (ô do LK suy diễn vẫn ẩn sạch).

### 6. Ticket `#46` — lỗi gốc còn lại, đang mở plan 3 ý kiến

Mask tràn nền be cùng tông: **63/194 frame (32 %)** có `mask_area` > 2,5× vật; **115/181 (63,5 %)**
ô chạm mép khung; `mask_area` p90 = 31 898 px = **5,5×** vật; `score` âm trên 44 frame bắt đầu **f133**
(11 frame TRƯỚC khi cổng bắt ở f144).

## 📤 Output / Kết quả

- Commit `42efc56` — `./run demoip` mặc định `--no-reid` (kèm chú thích số đo + đường lui).
- Commit `681a464` — 3 ticket `#43`, `#44`, `#45` + test.
- Cổng đã chạy: `./run lint` **All checks passed**; `./run test` **1880 passed, 5 deselected**
  (3:38); `./run webtest` **98 passed**; `./run e2e` **PASS**; `./run democheck --source <relay>`
  **7 OK · 0 LỖI**.
- File thay đổi:
  - `run` — `demoip` dùng `--no-reid`, in rõ chế độ + lý do + đường lui.
  - `src/visualizer.py` — `lost_banner_text()`, `ve_o_net_dut()`, `_COLOR_NGHI`, `reid_enabled`,
    `_write()` pacing (trần + rebase), `open_recorder(..., pace_realtime=…)`.
  - `src/smooth_display.py`, `src/live_pipeline.py` — set `visualizer.reid_enabled`.
  - `src/live_tracking.py` — `_annotate` vẽ nét đứt khi `bam == "nghi_doi_tuong"`.
  - `tools/run_live.py` — `_la_nguon_live()` + truyền `pace_realtime`.
  - `tests/test_visualizer.py`, `tests/test_smooth_display.py`, `tests/test_live_tracking.py`,
    `tests/test_run_live_cli.py`, `tests/test_run_live_helpers.py` — test mới cho cả 3 ticket.
  - `.scratch/camera-ai-realtime/issues/43..46-*.md` — 4 ticket.
  - `docs/phan-tich-dung-sai-model-may-code.md` — thêm mục 7 (bảng 2×2 + đường lui).

## 🐞 Vấn đề gặp phải & cách xử lý

1. **`open_recorder` bỏ rơi cờ `pace_realtime`** khi `frame_size` khác `None` (nhánh `return` sớm) ⇒
   3 test pacing đỏ. Sửa: đặt cờ TRƯỚC nhánh rẽ. Test đã bắt được ngay — giữ lại làm hồi quy.
2. **`_make_visualizer` đọc `args.source`** làm vỡ test cũ dùng stub `args` không có `source`
   (`AttributeError: 'A' object has no attribute 'source'`). Sửa: `getattr(args, "source", None)` và
   `_la_nguon_live(None) → False` (không biết nguồn thì coi như KHÔNG live — mặc định an toàn).
3. **Test cũ `test_ghi_mp4_doc_lai_du_frame_dung_kich_thuoc` (n == 3)** trở thành phụ thuộc tốc độ
   máy sau khi thêm pacing ⇒ đóng băng đồng hồ trong test đó.
4. **Đo bằng heredoc bash bị sai** (`$T0` bị thay ngay trong heredoc) ⇒ chuyển sang Python đọc
   `cv2.VideoCapture` để lấy `n`/`fps`.

## 📌 Việc cần làm tiếp (Next steps)

- [ ] **Người dùng**: tô 5 frame còn trống của `docs/gt/vat_be_vaolai` (f258, f270, f300 = "vật vắng";
      f344, f348 = tô remote) tại http://localhost:8766 — để câu "hệ không vẽ bừa khi vật vắng" có số
      chính thức (`mask_px_gt_rong`) thay vì đọc bằng mắt.
- [ ] **Người dùng**: chạy lại `./run demoip` và kiểm 3 điều: (1) đưa vật ra khỏi khung ⇒ không vẽ gì;
      (2) đưa vào lại ⇒ bám ngay; (3) che tay ⇒ mask thu đúng phần thấy.
- [ ] `#46`: plan 3 ý kiến (đang chạy) → chốt → triển khai ràng buộc hình học/diện tích cho mask.
- [ ] Đo lại `mask_age`/`vos_ms` trên webcam với code mới để cập nhật bảng số báo cáo (pacing không
      đổi tốc độ suy luận, nhưng lần đo cũ là trước #43–#45).

## 📚 Tài liệu tham khảo

- `docs/phan-tich-dung-sai-model-may-code.md` (mục 1–7, gồm bảng 2×2 đầy đủ).
- `docs/plan/23-11-2026-chon-co-che-tu-tim-lai.md` (vì sao tắt re-ID).
- `docs/thuoc-do-bam-dung.md` (quy tắc chấm mIoU: GT rỗng ⇒ không chấm; model rỗng mà GT có vật ⇒ 0,0).
- `AGENTS.md` §6 (các kết luận đã đo) và §9.1/§9.2.

## 🖼️ Ảnh minh hoạ (chèn được vào báo cáo)

`docs/img/ba-trang-thai-o-bao-23-11.jpg` — ba trạng thái của overlay trên cùng một frame thật
(`data/binh1.mp4`), để chứng minh luật vẽ mới:

| | trạng thái | overlay |
|---|---|---|
| **A** | đang bám | ô đặc đỏ + tô mask cam |
| **B** | **nghi đổi đối tượng** (ticket #45) | **ô NÉT ĐỨT vàng + nhãn "NGHI"**, KHÔNG tô mask, banner `NGHI DOI TUONG — r: chon lai \| c: van dung, tiep tuc` |
| **C** | mất dấu, **không** re-ID (ticket #43) | banner `MẤT DẤU — bấm r chọn lại` (trước 23-11 in sai: "TỰ TÌM LẠI") |

## ➕ Bổ sung 15:20 — sau khi một agent độc lập (góc "sản phẩm & bằng chứng") phản biện

### Đính chính 1: `bbox_h` KHÔNG phải 479

Tôi từng viết "ô chạm mép khung vì `bbox_h` = 479 = hết chiều cao khung". **Sai**: 479 là **toạ độ
`y2`** in trong log `run_live` (`bbox=(x1,y1,x2,y2)`), còn cột CSV `bbox_h` có **max = 376** (78 %
chiều cao 480). Con số tổng **63,5 % tái lập được** (115/181 frame, đã kiểm chéo 4 frame: `f0`
CSV→`(171,319,247,395)` khớp đúng log), nhưng **lý do** phải viết lại theo phân rã mép:

| mép | số frame (n=181) |
|---|---|
| **dưới** `y2 ≥ 478` | **104 (57,5 %)** |
| phải `x2 ≥ 638` | 13 (7,2 %) |
| trái `x1 ≤ 2` | 5 (2,8 %) |
| trên `y1 ≤ 2` | **0 (0,0 %)** |

⇒ Bản chất là "mask ăn **xuống mặt bàn**", không phải "lan mọi phía". Một agent khác đo cùng câu
hỏi ra 28,7 % ⇒ **lên slide phải ghi rõ công thức + n**, tốt nhất là dùng dòng phân rã này.

### Đính chính 2: phiên live **KHÔNG replay được** (tôi đã nói ngược trong một tin nhắn)

`data/demoip_1123-144505.mp4` **không phải nguồn thô** — nó là bản **đã cháy HUD**, giống `_web.mp4`
(so frame 300 hai file: trùng khít). `prompt_bbox` + CSV đầy đủ cột nghĩa là **chẩn đoán được**, không
phải **chạy lại được**. Muốn có bằng chứng tái lập: **ghi raw trước** (`./run raw 20 --source …`),
rồi chạy pipeline trên chính clip đó.

### Đính chính 3: tiêu chí "worker in cùng câu" của #43 là tiêu chí SAI

`_annotate` **cố ý** không có banner chữ; lời giải thích cho người xem web nằm ở panel
(`web/src/components/LivePanel.tsx:408` + nút "Vẫn đúng, tiếp tục"). `grep` toàn repo: **0 chỗ** in
"TỰ TÌM LẠI" ngoài `visualizer.lost_banner_text` ⇒ chỉ CLI (đường ghi video nộp bài) cần sửa, và đã
sửa. Ghi chú đã đóng vào ticket `#43`.

### Thêm mục 10 cho `./run democheck` — cổng hồi quy cho #44

Đây là lỗi **kiểm được bằng máy tính bỏ túi** (194 × 158,5 ms = 30,76 s vs file 20,83 s) mà **không
mục nào** của preflight từng đọc ⇒ sống nhiều tuần, chỉ lộ khi chiếu.

- `check_video_duration()`: đọc `total_frames × mean_latency_ms` từ `<phiên>_summary.json`, so với
  `frame/fps` của `<phiên>_web.mp4` / `<phiên>.mp4`; lệch **> 5 %** ⇒ **LỖI** với phiên ghi sau mốc
  `23-11-2026 15:00`, còn phiên cũ (mắc lỗi 1:1 đã biết) chỉ **CẢNH BÁO** (không chặn buổi demo).
- Chạy thật trên repo: `7 OK · 3 cảnh báo · 0 LỖI`, in đúng
  `demoip_1123-144505_web.mp4: 20.8 s vs thực 30.8 s (+32 %)`.
- 5 test mới trong `tests/test_demo_preflight.py`; 2 test cũ đổi số mục (9 → 10, 10 → 11).

### Việc bị bác (kèm lý do) — không làm trong phiên này

- **Sửa thuật toán tràn nền (#46) ngay**: đổi thuật toán ⇒ AGENTS §9.2 bắt buộc plan 3 ý kiến
  (> 4 h chỉ để quyết), và ngưỡng diện tích đo trên **1 phiên** là over-fit. Đang chạy plan.
- **Bật lại re-ID / hạ ngưỡng re-ID / thêm "cổng cos"**: đã bị số đo bác (bảng 2×2 + `track_cos`
  vùng sai 0,752–0,989 nằm trong dải ca đúng 0,905 ⇒ không có θ tách được).
- **Sửa tại chỗ `docs/gt/b1`** (12 frame, 7 chấm được): tạo bộ GT mới, giữ `b1` nguyên để **0,7794 vẫn
  tái lập được**.

## ✅ Review độc lập (AGENTS §9.1) — 23-11 15:10, agent `reviewer`

**Verdict của reviewer:** *"CHƯA merge được — 3 lỗi nhỏ (≤1 h tổng) rồi merge được. Không có P0."*
(Reviewer không có shell trong phiên của nó ⇒ verify bằng đọc code + grep, không chạy test — tôi đã
tự chạy lại toàn bộ cổng ở dưới.)

| Mức | Phát hiện | Đã sửa |
|---|---|---|
| **P1** | `_recorder_fps` **chỉ được khai báo, không bao giờ gán** ⇒ pacing luôn 30 fps kể cả khi `--record-fps 15` ⇒ file **dài gấp 2 lần** thực, im lặng | Gán trong `_open_writer`. Test `fps=15` — **đã chứng minh test bắt được lỗi**: sau sửa 14 frame, giả lập bản cũ (=30) cho **28** frame cho cùng 0,9 s |
| **P1** | **Lỗi tôi gây ra ở đường web**: banner vẫn nói "ô đã được ẩn khỏi ảnh" trong khi #45 đổi worker sang **vẽ ô nét đứt**; tệ hơn, `live.test.ts` và `scripts/e2e_web.js` **khoá câu chữ sai** nên e2e vẫn PASS | Sửa 4 chỗ (`live.ts`, `live.test.ts` + test mới "KHÔNG được nói 'đã ẩn'", `e2e_web.js`, `schemas.py`). e2e PASS với câu mới |
| **P1** | `--no-reid` bị `configs/default.yaml` (`reid_enabled: true`) **đè ngược** ⇒ re-ID vẫn bật khi chạy `--config … --no-reid` | `--reid/--no-reid` thành **tri-state** (`default=None`): CLI nói rõ thì thắng, không nói mới lấy YAML. Kiểm bằng bảng 4 tổ hợp |
| P2 | `_rec_t0` rò khi `close_recorder` ⇒ file mới mở trong cùng phiên bắt đầu bằng hàng chục frame lặp | Xoá mốc khi đóng + test |
| P2 | `max(1, so_lan)` **che** ca "nhịp vẽ nhanh hơn fps khai báo" (file **dài** hơn thực) và ca đồng hồ lùi | `max(0, …)` + rebase + 2 test |
| P2 | "TỰ TÌM LẠI" là **lời hứa**; `--reid --reid-cue face` bám vật ⇒ kho mẫu rỗng, không bao giờ nhận lại (đo: 201 frame, `reid_score = -1` cả phiên) | Đổi thành "ĐANG TÌM LẠI" (việc đang làm, không phải kết quả) + test |
| P3 | `ve_o_net_dut`: `dai=0` ném `ValueError`, không clamp `x2/y2` | Guard + clamp + test biên (biên ảnh, ô 1×1, `dai=0`, bbox 10 000) |
| P3 | Màu vàng chép tay ở `live_tracking` | Dùng `_COLOR_NGHI` |
| P3 | `run_info` không ghi `record_fps`/`record_pace_realtime` ⇒ artifact không tự giải thích thời lượng | Đã ghi |
| P3 | `./run demoip` in 2 dòng re-ID **trước** dòng "re-ID TẮT" | Chỉ in khi `--reid` thật sự bật |
| P3 | `docs/demo-ngay-mai.md` Cảnh 3 vẫn dạy "HUD hiện ĐANG TÌM LẠI…" | Viết lại theo cơ chế **mới** (lan truyền liên tục), bản cũ giữ để đối chiếu |

**Reviewer cũng chỉ ra 5 test còn thiếu — đã thêm đủ** (`fps=15`, nhãn fps thấp hơn nhịp vẽ, đồng hồ
lùi, mở lại recorder, `ve_o_net_dut` ở biên/1px/`dai=0`).

**Còn nợ (ghi vào Next steps):**
- (a) Reviewer: "`run_tracking` (headless) **không có** `IdentityWatch`" ⇒ **artifact headless
  không bao giờ có `nghi_doi_tuong`**; đừng trích cổng nghi từ artifact headless.
- (b) Cần **một phiên `./run demoip` thật** sau commit này: so thời lượng mp4 với đồng hồ treo tường
  (≤ 5 %) và trích 1 frame `nghi_doi_tuong=1` để thấy viền vàng — hiện chỉ có unit test + diễn tập
  model giả. **Người dùng làm khi chạy demo thử.**
- (c) Test đang vá `src.visualizer.time.monotonic` **toàn cục** (đóng băng đồng hồ mọi thread). Hiện
  vô hại vì không có thread nào chạy; nếu sau này có, phải tiêm đồng hồ qua tham số.

**Cổng sau khi sửa:** `./run lint` sạch · `./run test` **1896 passed** (5 deselected) ·
`./run webtest` **99 passed** · `./run e2e` **PASS** · `./run democheck` 7 OK / 0 LỖI.
