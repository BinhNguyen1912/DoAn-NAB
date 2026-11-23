# Ngày 23-11-2026 — Phân tích phiên `demoip_1123-092343`: bám nhầm remote be trơn

## 🎯 Mục tiêu
- Trả lời đúng câu "bám vật nhầm" của người dùng trên **phiên webcam thật mới nhất**, bằng bằng chứng
  (CSV từng bước + ảnh trích từ video), KHÔNG bằng cảm tính.
- Xác định: (a) đoạn nào bám SAI, (b) vì sao cổng "nghi đổi đối tượng" không báo, (c) vì sao sau khi
  báo hệ vẫn KHÔNG tự cứu được.
- Chốt việc tiếp theo có số đo làm tiêu chí nghiệm thu.

## 📥 Input
- `data/demoip_1123-092343_web.mp4` — 38,9 s, 1 168 frame @30 fps (có overlay: ô đỏ = `bbox` từ mask,
  đường tím = quỹ đạo tâm, HUD = FPS/độ trễ/điểm tin cậy).
- `data/demoip_1123-092343_metrics.csv` — **312 bước VOS**, 16 cột (có `nghi_doi_tuong`, `track_cos`,
  `ncc`, `vetoed`, `mask_area`, `bbox_w/h`).
- `data/demoip_1123-092343_summary.json` + `_run_info.json` (`git_rev f784e0e`).
- Vật thể: **remote máy lạnh be/trắng trơn** cầm tay, nền là **tường be + máy lạnh be** — đúng ca
  "vật trơn cùng tông nền" mà người dùng hỏi từ đầu phiên.
- Code liên quan: `src/identity_guard.py` (`IdentityWatch`, `search_window_radius`),
  `src/smooth_display.py:290-326` (vòng lặp MƯỢT + cổng nghi), `src/reid.py:840-913` (nhận lại).

## 🔨 Công việc đã thực hiện
1. Đọc CSV: dựng lại quỹ đạo tâm, các cú nhảy > 60 px, danh sách frame mất dấu / nhận lại / bị veto.
2. Trích 12 + 12 frame (mỗi ~1,6 s) thành 2 ảnh lưới để nhìn toàn phiên; trích thêm frame lẻ ở
   t = 20 / 24 / 25 / 28 / 29 / 30,5 / 31,5 / 33,3 / 36,7 s.
3. Tính lại **đúng công thức cổng** (`search_window_radius`) trên từng bước để biết cổng báo mấy lần.
4. Đối chiếu "ô vẽ trên video" ↔ "ô trong CSV" để tách lỗi **hiển thị** khỏi lỗi **mô hình**.

## 📤 Output / Kết quả

### Số tổng (từ `summary.json`)
| | |
|---|---|
| bước VOS | **312** |
| độ trễ | mean **158 ms** · p95 **186 ms** → **6,3 FPS** (mask), HUD ~20–22 FPS (LK lấp) |
| mất dấu | **11 bước (3,5 %)** — f202-204, f216-217, f239, f244-248 |
| nhận lại (re-ID) | **3 lần** — f205 (ncc 0,686) · f218 (0,687) · f249 (0,468) |
| veto mặt/đầu | **3 ứng viên** (ncc 0,472–0,528) |
| CPU / RAM | 460 % (1 lõi) · đỉnh 648 MB |
| cổng "nghi đổi đối tượng" | **1 lần / 312 bước (0,3 %)** → ẩn overlay **48 bước = 15,4 %** phiên |

### Diễn biến (ảnh lưới + CSV)
| Giai đoạn | Ảnh trích | Trạng thái |
|---|---|---|
| ~0–20 s | lưới A (frame 0→583) | Ô **đúng trên remote** ở **12/12** mẫu. Quỹ đạo tím ngoằn ngoèo (người dùng vẫy vật), mask đôi khi tràn sang ổ điện/máy lạnh nhưng ô vẫn trên vật. |
| ~20–24 s | f631 (21 s) | Ô rơi xuống **poster/desk góc dưới-trái**, remote không nằm trong ô ⇒ **SAI** |
| ~24,3–25,9 s | f729, f778 | f729 đúng (hơi lệch), f778 ô lệch sang **tường phải** remote ⇒ **SAI** |
| ~27,5–30,8 s | f827, f875, f924 | Ô ở **poster** rồi phình thành **ô lớn 370×130 → trùm áo người** ⇒ **SAI nặng** (CSV: score 0,04–1,24; `bbox_w` lên **391 px = 61 % chiều rộng khung** ở f236) |
| ~31–32 s | f973 | Ô nhảy lên **tường/trần góc trái**, remote đang cầm giữa khung ⇒ cổng báo (f264, nhảy **204 px**) và **ẩn overlay từ đây** |
| ~32,4–38,9 s | f1022, f1071, f1120 | Overlay **ẩn**, HUD in `NGHI DOI TUONG — r: chon lai | c: van dung`; **remote vẫn nằm rõ trong khung** (cầm tay, giữa khung) nhưng hệ **không tìm lại** |

> Bản đồ bước↔giây là **xấp xỉ** (3,3–3,7 frame video cho 1 bước VOS; tỉ lệ trôi vì FPS hiển thị đổi
> 19,8–24). Mọi số theo **bước** lấy từ CSV, mọi mô tả ảnh lấy từ frame video — không trộn hai hệ.

### Ba nguyên nhân (đã kiểm bằng số, không suy đoán)
1. **Cổng nhảy gần như mù với vật to.** `search_window_radius` = `min(0,25×đường chéo, max(0,10×đường
   chéo, 1,5×max(w,h)))`; khung 640×480 ⇒ trần **200 px**, mà với ô 127×269 thì `1,5×size` = 403 px
   nên luôn bị cắt về 200 px. Cú nhảy **204 px** ở f264 vừa đủ vượt; các cú 60–154 px ở f229–f266
   **không** vượt. Chạy lại đúng công thức trên 312 bước: cổng báo **1 lần** (f264).
2. **Trôi dần không bị bắt.** Kiểu sai ở đây là ô **bò** sang máy lạnh/poster/áo (mỗi bước 60–150 px),
   không phải nhảy một phát. Cổng chỉ so ô với **ô bước trước** nên "bò" là hợp lệ.
3. **Cổng báo ⇒ chỉ ẨN, không TÌM LẠI** (đây là lỗi lớn nhất). Trong **48 bước** bị ẩn, CSV ghi
   `state = tracking` **cả 48 bước**, `reacquiring` = **0 bước**, score 1,21–4,46 (med 2,73),
   `mask_area` med **43 512 px** (vùng áo người). Nghĩa là: engine **vẫn đang bám sai**, nên theo thiết
   kế nó **không coi là mất dấu** ⇒ **Re-ID không được gọi lần nào** ⇒ không có cơ hội nhận lại remote
   dù remote ở ngay giữa khung. Người dùng chỉ còn cách bấm `r` và kéo lại ô (lần thử ở f310 bị từ chối:
   `[chọn] ô quá nhỏ`, `MIN_BOX = 16 px`).

### Kết luận phụ (quan trọng để KHÔNG làm sai hướng)
- **`ncc` không tách được ở phiên này**: nhận lại ĐÚNG = 0,686 / 0,687 / **0,468**; ứng viên SAI bị veto
  = 0,472 / 0,528 ⇒ **cấm nâng `ncc_min` 0,40 → 0,55** (sẽ chặn luôn ca đúng 0,468). Đây là bằng chứng
  ÂM TÍNH, ghi lại để lần sau không mở lại.
- **Diện tích & tỉ lệ lấp không tách được**: `mask_area` lớn nhất chỉ **2,0×** trung vị 60 bước đầu
  (43,8k vs 22,0k); `fill = area/(w×h)` med 0,77 — **không** bất thường so với các phiên tốt
  (0,70–0,87). ⇒ cổng diện tích/fill **không** cứu được ca này.
- **`track_cos` cũng không**: 0,45–0,79 ở vùng sai nằm trong dải ca đúng (đúng như kết luận 21-11).
- Fix deadlock 22-11 **có tác dụng**: không còn re-latch vô hạn; nhận lại ở f249 **được** xoá nghi và ô
  hiện lại (thấy rõ ở t≈31,5 s) — trước fix thì ô mất tới hết phiên.

## ⚠️ Vấn đề gặp phải & cách xử lý
- **`demoip_*.mp4` KHÔNG phải bản "raw"**: vẫn có overlay (dùng để soi ô/đường quỹ đạo), chỉ `_web.mp4`
  là bản H.264 phát được trên Chrome. Muốn ảnh sạch phải tự tắt overlay trong visualizer.
- Khớp bước↔frame bằng "ô đỏ trong ảnh" chỉ đúng 167/312 bước (phần sau lệch vì FPS hiển thị đổi) ⇒
  **không** dùng phép khớp này để tuyên bố "frame X bám sai", chỉ dùng để mô tả giai đoạn.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **P0 — "cổng nghi ⇒ ÉP TÌM LẠI"** (≈2 h, không đổi model): khi `watch.nghi` bật thì (a) ngừng
      propagate/ngừng tin `bbox` hiện tại, (b) đặt `ReIdSession` sang trạng thái tìm lại, (c) HUD
      `DANG TIM LAI`. Nhận lại được ⇒ unlatch (đã có từ 22-11). Không được ⇒ `MẤT DẤU — bấm r`.
      **Nghiệm thu có số trên chính phiên này**: 48 bước cuối phải là `reacquiring` (hoặc có lần nhận
      lại), KHÔNG còn 48 bước `tracking` trên vùng áo; và **mọi phiên cũ (18 phiên replay)** không được
      tăng số lần ẩn oan (hiện 21 lần/2 973 frame).
- [ ] **P1 — cổng nhảy theo chuyển động dự đoán (Kalman/LK)**, không theo trần 200 px: đây là việc >4 h
      ⇒ **phải lập plan 3 ý kiến (AGENTS §9.2)**. Tiêu chí: bắt được giai đoạn f229–f263 (ô bò sang
      máy lạnh/poster) mà **không** tăng báo oan trên `binh1` (hiện 0 %).
- [ ] **P2 — giảm đau cho người dùng**: khi latch, in rõ *"đang bám vùng SAI — bấm r rồi kéo ô"* + nhận
      cú kéo nhỏ (hoặc chấp nhận click để "xoá latch") thay vì im lặng reset về idle.
- [ ] Không làm: nâng `ncc_min`; thêm cổng diện tích/fill; thêm cổng cos (cả ba đều có bằng chứng âm).

## 📚 Tài liệu tham khảo
- `docs/task/22-11-2026-sua-deadlock-identity-watch-reacquire.md` (fix 22-11 + 4 bug)
- `AGENTS.md` §6: "cổng nghi đổi đối tượng phải CÓ NHỚ", "`track_cos` KHÔNG phân biệt được vùng sai"
- `src/identity_guard.py:26-70` (`search_window_radius`), `src/smooth_display.py:290-326`
- Ảnh phân tích: `data/tmp_analyze_1123/` (2 lưới + 20 frame lẻ) — **không commit** (`data/` bị chặn)

---

## 🔧 BỔ SUNG (cùng ngày) — SỬA P0: "cổng nghi ⇒ ÉP TÌM LẠI"

### Thay đổi
| File | Nội dung |
|---|---|
| `src/reid.py` | `ReIdSession.set_suspicious(bool)` + `suspicious` (property). Bước `step()` kế tiếp khi cờ bật: **bỏ track NGAY** (không chờ `lost_after_frames`) qua `_auto_recover()` — tức là reset engine, về `LOST`, **giữ** mẫu tham chiếu để tìm lại. Cờ tự xoá trong `start()`, `reset()`, và `_reacquire()` (nếu giữ, hệ quay vòng: nhận lại → bỏ → nhận lại). |
| `src/smooth_display.py` | `InferenceWorker.request_suspicious()` (main thread → luồng suy luận, chỉ khi giá trị **đổi**); `InferenceWorker.reanchor(bbox)` (neo lại engine nhưng **giữ** mẫu Re-ID — dùng cho phím `c`); vòng hiển thị: `_bao_nghi(watch.nghi)` sau mỗi bước; phím `c`/`r` đều `_bao_nghi(False)`; `c` gọi `reanchor(bbox_truoc_nghi)` (ô **đã lưu trước khi bỏ track**, vì sau đó `last_bbox` = rỗng). |
| `src/live_pipeline.py` | Cùng luật cho đường `run_interactive` (không `--smooth`): `reid_session.set_suspicious(...)`, `c` → `reid_session.start(frame, bbox_truoc_nghi)`. |
| Cả hai đường | In **một lần** khi cổng nghi bật mà **không** có Re-ID: "không tự tìm lại được; bấm r chọn lại" (trước đây im lặng). |

### Test (mới)
- `tests/test_reid.py::TestCoNghiTuTangHienThi` (5): bỏ track ngay trong bước kế tiếp · **không học thêm mẫu** (chống nhiễm `_obj_refs`) · bước sau vào nhánh tìm lại · nhận lại thì tự xoá cờ · `reset`/`start` xoá cờ.
- `tests/test_smooth_display.py::TestCongNghiEpBoTrackThatSu` — **end-to-end thật**: vòng hiển thị + `ReIdSession` thật + engine giả, cú nhảy **70 px** nằm trong cửa sổ **chỉ cổng hiển thị** bắt được (cổng nội bộ cần ≥ 85 px) ⇒ test chỉ xanh nhờ đường mới. **Đã diễn tập giết mutant**: tắt nhánh `if self._suspicious` trong `reid.py` ⇒ test đỏ đúng chỗ.
- `tests/test_smooth_display.py`: cổng nghi chuyển xuống session (worker → `set_suspicious`), `reanchor` **không** reset Re-ID, `c`/`r` xoá cờ.
- `tests/test_live_pipeline.py::TestCoNghiEpTimLaiInline` (2).
- Cập nhật test cũ `test_phim_c_giai_phong_deadlock_last_bbox` (đổi sang `worker.reanchor(bbox_truoc_nghi)`).

### Kết quả kiểm tra
- `./run lint`: **All checks passed**.
- `./run test`: **1810 passed**, 5 deselected (trước: 1799).
- **Chưa** chạy được phép đo "48 bước cuối thành tìm lại" trên chính phiên cũ: video `demoip_1123-092343.mp4` **có overlay cháy vào ảnh** ⇒ replay sẽ đưa ô đỏ vào cảnh, không phải dữ liệu sạch. Tiêu chí đó phải nghiệm thu bằng **phiên webcam mới** (`./run demoip`).

### Rủi ro còn lại (ghi để không tuyên bố quá)
- **Nhận lại SAI vẫn có thể xảy ra** (mẫu `_obj_refs` đã bị nhiễm trong giai đoạn trôi f229–f263, trước khi cổng báo): mỗi chu kỳ "bỏ track → nhận lại vùng sai → cổng báo lại" tốn ≥ 3 bước. Chưa đo tần suất; muốn chặn gốc phải **ngừng học mẫu khi track đang trôi** (cổng hình học/Kalman — P1, cần plan 3 ý kiến).
- Đường **web** (`src/live_tracking.py`) **không có Re-ID** ⇒ chỉ ẩn overlay + banner như cũ; muốn có tự phục hồi phải port re-ID sang worker (việc riêng).
