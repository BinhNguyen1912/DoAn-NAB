# Ngày 08-11-2026 — Minh bạch nhịp mask trên UI + sửa bug ô chọn (x,y,w,h) vs (x1,y1,x2,y2)

## 🎯 Mục tiêu
- Phase 4d: người xem phải thấy **hai nhịp tách rời** (FPS phát vs nhịp mask mới) ngay trên UI.
- Đo xem "chống nhấp nháy mask" có thật sự đáng bật mặc định không (quy tắc: đo trước, hứa sau).
- Rà lại đường đi của ô chọn trên live từ UI → API → worker → model.

## 📥 Input
- Phase 4c (PR #4): live 30 FPS nhưng mask chỉ mới ~8,5 lần/giây, con số này mới nằm trong `status.json`.
- Next steps đã ghi trong `docs/task/08-11-2026-hybrid-vos-lk-live-30fps.md`.
- `data/binh1.mp4` (1280×720), `data/binh1_simloss.mp4`, `data/binh2.mp4` (720×1280).

## 🔨 Công việc đã thực hiện
1. **`src/mask_filter.py` (mới)** — `MaskSmoother` gồm hai cơ chế tách rời:
   - **hold**: mask mới teo dưới 40 % diện tích mask đang hiện ⇒ coi là model "chớp", giữ mask cũ
     (đã dịch theo ô bao), tối đa 2 lần liên tiếp; quá số đó là **mất dấu thật** ⇒ tắt;
   - **EMA**: `acc = α·mới + (1−α)·cũ`, hiển thị `acc ≥ 0,5`.
   Kèm `mask_iou()` để đo độ ổn định, và bộ đếm `holds` / `drops`.
2. **`src/live_tracking.py`** — `mask_smoothing` trong `LiveTrackConfig`; `_smooth()` áp dụng cho
   **cả hai đường** (đơn luồng và luồng VOS); số liệu mới trong `status.json`:
   `stability` (IoU của mask VOS thô), `stability_shown` (IoU của mask đã làm mượt),
   `mask_holds`, `mask_drops`.
3. **Xuyên tầng số liệu (đúng ports & adapters)**: port mới `LiveTelemetrySource` +
   `domain.LiveTelemetry` → `WorkerFrameSource.telemetry()` đọc `status.json` →
   `LiveStreamService.status()` (đọc **ngoài lock**, lỗi số liệu không làm sập API) →
   `LiveStatusResponse.{mask_fps, stability, latency_ms}` → `web/src/api.ts` → `LivePanel`.
   Nguồn không có số liệu chi tiết (webcam/file) ⇒ các trường bằng 0, UI tự ẩn dòng.
4. **UI** — `web/src/live.ts::maskRhythmLine()` (hàm thuần, test headless) → dòng
   "Mask mới: 8,6 lần/giây · độ ổn định: 96 % · độ trễ model: 108 ms".
5. **`mask_smoothing` xuyên tầng** như `vos_every` (API 0–1 → service → nhà máy nguồn → adapter →
   `--mask-smoothing`), **mặc định 1.0 = TẮT** (lý do ở mục Output).

## 📤 Output / Kết quả
- **Bug thật phát hiện & sửa: ô chọn trên live bị seed SAI.** `bbox.json`/API dùng `(x, y, w, h)`
  nhưng `TrackerEngine.start()` gọi `add_new_points_or_box(box=…)` của SAM 2 vốn nhận
  `(x1, y1, x2, y2)`. Trước đây `live_tracking.run()` truyền thẳng ⇒ hộp `(x, y, w, h)` bị hiểu thành
  `(x1, y1, x2, y2)`. Ví dụ chọn `104,308,209,287` → hộp thật `(104,308)-(209,287)` **cao âm** ⇒ mask
  seed sai, kéo theo cả phiên bám lệch (đúng là hiện tượng thấy ở các lần đo 09-11: ô bao trôi
  thành `[0,250,298,681]`). Đã đổi sang `xywh_to_xyxy()` + test hồi quy
  (`test_o_chon_xywh_duoc_doi_sang_xyxy_truoc_khi_start`). `tools/run_live.py` vốn đã đổi đúng —
  chỉ đường live qua `bbox.json` bị sót.
- **Đo "chống nhấp nháy" — kết luận: KHÔNG đáng bật mặc định.**

  | Clip | Làm mượt | FPS phát | Mask mới/giây | `stability` (thô) | `stability_shown` | holds/drops |
  |---|---|---|---|---|---|---|
  | binh1 | 1.0 (tắt) | 29,9 | 8,7 | 0,962 | 0,962 | 0/0 |
  | binh1 | 0.5 | 29,9 | 8,7 | 0,963 | — | 0/0 |
  | binh2 | 1.0 (tắt) | 30,0 | 8,6 | 0,706 | 0,706 | 0/0 |
  | binh2 | 0.5 | 29,9 | 8,2 | 0,682 | 0,681 | **8/2** |

  ⇒ Trên 2/3 clip bộ lọc **không kích hoạt lần nào** (`holds = 0`); trên binh2 nó kích hoạt nhưng
  **không làm IoU hiển thị cao hơn** (0,681 vs 0,706 — chênh lệch nằm trong dao động giữa hai lần
  chạy). Cơ chế vẫn giữ trong code (test đơn vị chứng minh nó chặn được "chớp" tổng hợp) nhưng
  **mặc định TẮT**, đúng quy tắc "đo trước, hứa sau".
- **Cảnh báo khi đọc số**: cùng seed `(200,400,300,500)` trên `binh2.mp4`, hai lần chạy cho ô bao
  cuối khác nhau (`[112,360,238,738]` vs `[127,302,232,556]`) ⇒ SAM 2 có yếu tố không tất định;
  **chỉ so sánh các chỉ số trong cùng một lần chạy**, đừng so chéo hai lần.
- File thay đổi:
  - `src/mask_filter.py` (mới) — `MaskSmoother` + `mask_iou`
  - `src/live_tracking.py` — `_smooth`, `stability`/`stability_shown`/`mask_holds`/`mask_drops`, sửa bbox
  - `src/api/{ports,domain,schemas,routes,live}.py`, `src/api/adapters/worker_source.py`,
    `src/api/main.py`, `src/worker/command.py`, `tools/live_worker.py` — telemetry + `mask_smoothing`
  - `web/src/{api.ts,live.ts,live.test.ts,components/LivePanel.tsx}` — dòng "nhịp mask"
  - `tests/test_mask_filter.py` (mới), `tests/test_live_tracking.py`, `tests/test_api_live.py`, `tests/conftest.py`

## 🐞 Vấn đề gặp phải & cách xử lý
- **EMA một mình không dập được "chớp" 50 %**: α = 0,5 cho `acc` nhảy 1 → 0,5 → 0,75 → 0,375 ⇒ vẫn
  tắt mỗi hai lần. Xử lý: thêm cơ chế **hold** có giới hạn `max_hold` (giữ được 1 lần chớp, và
  vẫn tắt khi mất dấu thật).
- **`stability_shown` luôn 0,0**: `_smooth()` thoát sớm khi tắt làm mượt, mà đo độ êm hiển thị thì
  phải chạy cả khi tắt. Xử lý: tách phần đo ra ngoài nhánh "có/không làm mượt".
- **Đường hybrid không hề làm mượt** (phát hiện qua `holds = 0` ở mọi lần chạy): `_smooth()` chỉ
  được gọi trong `_after_vos()` (đường đơn luồng + frame `start()`), còn kết quả của luồng VOS đi
  qua `_store_vos()` — nơi **không** gọi `_smooth()`. Xử lý: gọi `_smooth()` ngay trong callback
  của luồng VOS (mask mới về là xử lý ngay), bỏ tham số `frame` không dùng.
- **Test cũ ghi sai hợp đồng**: `test_co_bbox_thi_bam_va_ghi_frame_overlay` có comment "SAM 2 dùng
  (x, y, w, h)" ⇒ chính nó khoá bug lại. Đã sửa kỳ vọng sang `(5,5,25,21)`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Tạo clip **bị che một phần** (vật đi qua cột) rồi đo `mask_holds`/`stability` — hiện chưa có
      dữ liệu để chứng minh tác dụng thật của bộ lọc.
- [ ] Đo lại toàn bộ bảng số sau khi sửa bug bbox (mọi số của Phase 4c đo bằng ô chọn SAI — cần
      chạy lại và cập nhật README/log Phase 4c).
- [ ] Đo trên Colab T4 để có bảng GPU (`scripts/colab_run_all.py`).
- [ ] Ghi `mask_fps` vào file metrics của job (hiện chỉ có ở live) để báo cáo có bảng thống nhất.

## 📚 Tài liệu tham khảo
- SAM 2 `SAM2ImagePredictor.add_new_points_or_box` (box dạng `[x0, y0, x1, y1]`):
  https://github.com/facebookresearch/sam2
- OpenCV `warpAffine` (dịch bộ tích luỹ mask): https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html
- Phase 4c: `docs/task/08-11-2026-hybrid-vos-lk-live-30fps.md`
