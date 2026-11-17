# Ngày 17-11-2026 — Ticket #24: `vos_every = 1` (đơn luồng) cũng ghi tuổi mask

## 🎯 Mục tiêu
- Đóng ticket **#24**: `_note_mask_age` chỉ được gọi ở đường có **luồng VOS** (`vos_every > 1`) ⇒ ở
  cấu hình **đơn luồng** (`vos_every = 1`, đúng cấu hình đã dùng để đo mIoU fixture và các số
  "1 luồng 8,8 FPS") `mask_age_total_ms` luôn `None` ⇒ HUD không hiện tuổi mask, `bang_cau_hinh
  --every 1` ra `mask_age_p95 = None`.

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/24-…md`.
- Code: `src/live_tracking.py` (`_store_vos` = đường LK, `_after_vos` = đường inline + frame
  `engine.start()`, `_note_mask_age`), `src/tracker_engine.py` (`elapsed_ms` KHÔNG gồm `pre_ms`).
- Quy ước: `AGENTS.md` §6 (`None` ≠ 0, `pre_ms` nằm ngoài `vos_ms`), §9.1 (review độc lập).
- Cấu hình đo: `image_size 192`, `vos_every 1`, clip `data/binh1.mp4`, ô chai `300,275,150,410`
  (`docs/demo-clip-va-o-chon.md`).

## 🔨 Công việc đã thực hiện
1. **Ghi tuổi mask ở đường đơn luồng.** Trong `_after_vos`: đo `post_ms` quanh `_record_vos` +
   `_smooth`, ghi `_stats.post_ms` **và** `_stats.pre_ms` (lấy từ `result.pre_ms`), rồi gọi
   `_note_mask_age(age = 0, vos_ms = result.elapsed_ms, pre_ms = result.pre_ms, queue_ms = 0,
   post_ms)`. `age = 0` vì frame vừa được VOS xử lý **chính là** frame đang phát (không có frame
   chen giữa như đường LK).
2. **KHÔNG** gọi `_measure_drift` trong `_after_vos`: `vos_every = 1` không có nội suy LK nên không có
   cặp (VOS ↔ nội suy) để so — bịa một mẫu drift ở đây là làm sai `drift_iou`.
3. **Đo lại bảng cấu hình** trên cây sạch: `./run bangcau --sizes 192 --every 1 --lan 3 --frames 60`
   ⇒ `data/bang_cau_hinh_2026-11-17_every1_metrics.json` (`git_rev 3cc0248`,
   `git_dirty_code false`).
4. **Docs**: thêm 1 dòng vào `REGISTRY` của `scripts/so_lieu_bao_cao.py` (sinh `docs/so-lieu-bao-cao.md`
   + `--check` xanh) và 1 bullet `AGENTS.md` §6 với số + cảnh báo "FPS phát dòng đơn luồng không so
   được với 29,8 của `vos_every ≥ 2`", "tuổi mask = pre + vos + post, không phải chỉ vos".

## 📤 Output / Kết quả
- `vos_every = 1` nay có tuổi mask; `--every 1` **không còn** `mask_age_p95 = None`.
- Số đo (3 lần × 60 frame, cây sạch): **9,33 ± 0,55** FPS phát = nhịp mask · `vos_ms` **87,33 ± 4,52** ·
  `pre_ms` **10,96 ± 1,85** · `mask_age_p95` **109,9 ± 9,32** (`age_n 60`) ⇒ tuổi mask **lớn hơn**
  `vos_ms` ~22 ms và phần chênh đó nay **có cột giải thích** (`pre_ms` + `post_ms`).
  (Lần đo trước khi sửa review: 9,5 ± 0,5 / 82,1 / 105,53 — artifact bị thay thế, số mới là số dùng.)
- `./run lint` xanh · `./run test` **1304 passed**, 5 deselected.
- File thay đổi:
  - `src/live_tracking.py` — `_after_vos` (post/pre + `_note_mask_age`), `DINH_NGHIA_TUOI_MASK`, comment
    `post_ms`
  - `tests/test_live_tracking.py` — class `TestTuoiMaskDuongDonLuong`, `_Result` có `pre_ms`, test cũ
    `age_n` đổi kỳ vọng cho `every=1`
  - `tests/test_cau_hinh_hieu_luc.py` — ghim định nghĩa tuổi mask **đúng**
  - `data/bang_cau_hinh_2026-11-17_every1_metrics.json`, `docs/so-lieu-bao-cao.md`, `AGENTS.md`,
    `scripts/so_lieu_bao_cao.py`

## 🐞 Vấn đề gặp phải & cách xử lý
- **Test "vô răng" (review bắt):** vế `pre` của `mask_age_total_ms == 12,5 + (stats.pre_ms or 0.0) + post`
  luôn bằng 0 vì `_Result` của test không có `pre_ms` ⇒ truyền `pre_ms=0.0` (mất ~12 ms tuổi) vẫn xanh.
  Sửa: `_Result(pre_ms=7.0)` + assert cứng `12,5 + 7,0 + post` và `status["pre_ms"] == 7,0`.
- **Định nghĩa tự mâu thuẫn (P1 review):** `DINH_NGHIA_TUOI_MASK` vẫn ghi "vos_every=1 ⇒ age_n=0" và câu
  đó **đã nằm trong artifact của chính PR** (`age_n = 60`) — đúng loại "số không truy được về định
  nghĩa". Sửa chuỗi + sửa test `test_khai_dinh_nghia_tuoi_mask` (bản cũ chỉ kiểm chuỗi con `"age_n"`
  nên xanh với lý do sai).
- **File nguồn chứa literal `\u00ec`** (từ một lần sửa trước) ⇒ phép so khớp chuỗi trong script sửa
  không khớp; đã thay bằng chữ `thì` thật.

## ✅ Review độc lập (AGENTS §9.1)
- **Ai:** agent `reviewer` (chỉ đọc, phiên riêng), review `f753663..ce94809`.
- **Vòng 1: 0 P0, 1 P1, 3 P2, 5 P3.** P1 (định nghĩa tuổi mask sai) + P2 (`pre_ms` không được ghi,
  vế `pre` vô răng, docstring sai tên `_consume_vos`) **đã sửa trong commit `3cc0248`**; P3 đã sửa 1
  (test "age ≠ thời gian vòng lặp" nay dùng `elapsed_ms = 400`). P3 còn lại (thêm dòng `vos_every 1`
  vào bảng `docs/bang-cau-hinh.md` — file sinh tự động, phải sửa generator; thêm `git_rev`/clip/ô
  chọn vào chỗ công bố) ghi ở Next steps.
- Reviewer xác nhận **không** có double-sample (`age_n == frames`, `vos_every=1 ⇒ age_n == vos_runs`),
  không pha nào bị tính hai lần, và **web/API không hồi quy** (`live.ts` chỉ in khi `mask_age_total_ms`
  khác `null`; `maskAgeIsStale` ngưỡng 1500 ms không báo oan).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Thêm dòng `vos_every 1` vào **generator** của `docs/bang-cau-hinh.md` (hiện bảng chuẩn chỉ có
      `vos_every ≥ 2` ⇒ người đọc tưởng cấu hình đơn luồng chưa đo).
- [ ] Ticket **#26**: `_dump_mask` chạy trong cửa sổ `post_ms` (nhánh riêng, đang làm).
- [ ] Ticket **#22**, **#32**: xem log cùng ngày.
- [ ] Việc của người dùng: tô silhouette **≥ 30 frame** `binh1` để `mIoU_p05` có nghĩa.

## 📚 Tài liệu tham khảo
- `AGENTS.md` §6 (tuổi mask, `pre_ms` ngoài `vos_ms`, `None` ≠ 0), §9.1.
- `docs/so-lieu-bao-cao.md` (dòng "Tuổi dữ liệu ảnh p95 ở `vos_every 1`").
- `.scratch/rev24.md` (báo cáo review đầy đủ).
