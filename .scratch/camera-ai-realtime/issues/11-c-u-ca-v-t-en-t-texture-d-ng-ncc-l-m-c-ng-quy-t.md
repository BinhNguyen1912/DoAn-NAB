# 11: Cứu ca VẬT ĐEN / ít texture: dùng NCC làm cổng quyết định + ghi NCC vào metrics

**What to build:** Đo thật 27-10 trên fixture: với vật ĐEN đặc (chai đen), đặc trưng màu+covariance cho cosine **1,000 giữa hai vật khác nhau** (mất khả năng phân biệt). NCC thì tách được: cùng vật 1,000 / vật đen khác 0,897 / vật đen khác có nhãn trắng 0,394.

Việc:
- `src/appearance.py`: `prefilter_candidates(..., with_scores=False)` trả kèm điểm NCC.
- `src/reid.py`: `_match_object` dùng NCC (cổng `reid_obj_ncc_min` + trọng số) khi đặc trưng màu không đủ tin (độ bão hoà thấp / vector gần hằng).
- `src/metrics_logger.py`: thêm cột `ncc` để hiệu chuẩn bằng dữ liệu thật.
- `configs/default.yaml` + `src/config.py`: `reid_obj_ncc_min`, `reid_obj_ncc_weight`.

Không làm: đổi backbone, thêm model.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human

> **Ghi chú 02-11-2026:** 5/6 tiêu chí xong. Tiêu chí còn lại cần **clip THẬT có chai đen** —
> chỉ người dùng quay được, agent không tự tạo. Số hiện có (`data/reid_2clip_calib.json`,
> 17 ca đúng + 1 ca sai): cosine **không tách được** (sai 0,899 > đúng 0,770), NCC tách được
> (sai ≤ 0,279 < đúng ≥ 0,415) → tạm đặt `reid_obj_ncc_min = 0.35`. Đó là số của clip **ly**,
> chưa phải chai đen → giữ mở đến khi có clip chai đen.

- [x] `prefilter_candidates` trả kèm điểm NCC (tham số tuỳ chọn, không đổi hành vi mặc định)
- [x] `ReIdSession._match_object` dùng NCC như cổng/trọng số phụ khi vật ít texture-màu (đo: cùng vật NCC=1,000 vs vật đen khác NCC=0,897)
- [ ] Ngưỡng `reid_obj_ncc_min` hiệu chuẩn trên clip THẬT có chai đen (không dùng số synthetic)
      → tạm có 0,35 từ 2 clip thật (ly); **chờ clip chai đen** để chốt
- [x] Ghi `ncc` vào CSV metrics để hiệu chuẩn (thêm cột, không phá cột cũ)
- [x] Test: vật đen đặc khác hình dạng phải bị loại (cosine hiện tại cho 1,000 nên phải nhờ NCC)
- [x] `pytest -m "not slow"` + `ruff check .` xanh; ghi số đo vào log

## Comments

**21-11-2026 (nhánh `feat/nhan-lai-vat-live`):** cổng NCC do ticket này xây **chưa từng bật trên đường demo** — `src/config.py:68` và `configs/default.yaml` để `reid_obj_ncc_min = 0.0` (TẮT), và comment biện minh được viết **29-10**, tức **trước** bản hiệu chuẩn 01-11 của chính ticket này. Nay `run demoip`/`run fast` truyền `--reid-obj-ncc-min 0.35` + in `ncc_min=` trong dòng `[re-ID]` (không đổi `configs/default.yaml` để artifact cũ tái lập được).

Đo trên `binh2` 300 frame @192 (`data/reid_ab_p1_2026-11-21_{ncc0,sau-va}.csv`): bật 0,35 **không đổi gì** — cùng 4 lần nhận lại ở cùng frame (172/175/178/244), cùng dải `ncc` (−1,0…0,811), 288 frame `tracking` — vì mọi ứng viên được nhận đều đã ≥ 0,35. ⇒ Trên clip này cổng **không** phải yếu tố quyết định; giá trị của nó vẫn chỉ đến từ hiệu chuẩn có nhãn (ca sai ncc 0,279, **`n_bad = 1`**).

Tiêu chí còn lại của ticket **vẫn mở**: cần **clip THẬT có chai đen** để chốt ngưỡng (agent không tự quay được). Đừng đọc "đã bật 0,35" thành "đã hiệu chuẩn xong".
