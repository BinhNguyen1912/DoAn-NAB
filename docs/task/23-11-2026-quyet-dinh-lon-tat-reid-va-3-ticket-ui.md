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
