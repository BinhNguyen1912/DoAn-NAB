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
