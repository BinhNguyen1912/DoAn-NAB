# 18: API chưa phân biệt `stability = 0` ("tệ nhất" / "vừa mất dấu") với "chưa đo"

**What to build:** `LiveTrackStats.stability: float = 0.0` không có encoding "chưa đo": giá trị `0`
xuất hiện cả khi (a) **chưa đo**, (b) **mask rỗng ⇒ đặt 0** (mất dấu, `src/live_tracking.py` nhánh
`if not raw.any()`), (c) **đo thật** mà hai mask liên tiếp rời nhau hoàn toàn. UI che lỗ hổng này
bằng `stability <= 0 ⇒ "nhấp nháy mask: chưa đo"` (`web/src/live.ts`), nhưng:
- người dùng **API** (`/api/live/status`, `status.json`) không phân biệt được ⇒ dễ trích "nhấp nháy
  0 %" cho một phiên vừa mất dấu;
- nhãn "chưa đo" **sai sự thật** đúng lúc mất dấu (chỗ duy nhất nói đúng là đoạn `mất dấu: …`).

Cách sửa (đề xuất): thêm `stability_n` (độ dài `_iou_window`) như `drift_n`, và đặt
`stability = None` khi cửa sổ rỗng — rồi cho đi qua adapter → schema (`float | None`) → `api.ts` →
`live.ts` (bỏ hẳn suy luận `<= 0`). Test: (1) phiên rỗng ⇒ `stability_n == 0`, `stability is None`;
(2) mất dấu ⇒ `stability_n > 0`, `stability == 0.0` (đo được số 0 thật); (3) `None` sống sót
end-to-end (mẫu: `test_drift_0_0_do_duoc_van_la_0_0`).

Phát hiện khi review độc lập nhánh `feat/chan-doan-chat-luong-bam` (note vòng 2 + P3 vòng 3).
Chưa gây lỗi hiện tại — chỉ là API không tự mô tả được.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Cửa sổ rỗng ⇒ `stability is None` + `stability_n == 0` (test `TestStabilityCoEncodingChuaDo`)
- [x] Mất dấu khi đã có mẫu ⇒ `stability == 0.0` + `stability_n > 0`
- [x] `None` sống sót worker → adapter → domain → route → JSON (`test_stability_none_va_0_0_khac_nhau`)
- [x] UI: `stability_n > 0` mới in số ⇒ `0,0` đo được in "nhấp nháy 100 %", `None` in "chưa đo" (3 test vitest)
- [x] `./run test` + `./run webtest` + `./run e2e` xanh

## Đã làm (10-11-2026)
- `src/live_tracking.py`: `stability: float | None` + `stability_n`; cửa sổ rỗng ⇒ `None`.
- adapter → `LiveTelemetry`/`LiveStatus` → schema (`float | None`) → `api.ts` → `live.ts`
  (`stability_n > 0` mới in số ⇒ `0,0` đo được in "nhấp nháy 100 %", không phải "chưa đo").
- Test: 3 test `live_tracking` (None/0,0/`n`), 1 test API (`None` ≠ `0,0` qua cả chuỗi), 3 test vitest.
