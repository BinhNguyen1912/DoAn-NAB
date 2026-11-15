# 28: Đưa `cau_hinh_lech` (cấu hình yêu cầu ≠ hiệu lực) lên API live + HUD

**What to build:** Từ 15-11, worker ghi `cau_hinh` + `cau_hinh_lech` vào `status.json`, nhưng **không** đi qua API: `src/api/adapters/worker_source.py::telemetry()` chỉ đọc các khoá số đã biết, `LiveTelemetry`/`LiveStatusResponse` không có trường này, `web/src/api.ts` cũng không.

Hệ quả: nếu buổi demo chạy sai cấu hình (hydra override no-op ⇒ model chạy 1024 trong khi người dùng chọn 192), người ngồi xem UI **không biết**; cảnh báo chỉ nằm trong `worker.log`. Đây đúng loại "xanh giả" mà cả repo đang cố chặn — số trên HUD trông đúng nhưng gắn sai cấu hình.

Phạm vi tối thiểu: chỉ đưa **cờ** lệch (hoặc `image_size_hieu_luc`) lên `LiveTelemetry` → DTO → `web/src/api.ts` → `LivePanel` hiện dòng cảnh báo `role="alert"` khi lệch. Không đưa cả khối `cau_hinh` vào HUD (rối, và không ai đọc).

**Lưu ý:** worker bản cũ không có khoá này ⇒ adapter phải đọc kiểu "vắng mặt = chưa biết", **không** mặc định `[]` (rỗng = "đã kiểm và khớp") — cùng bẫy `None` vs `0` của AGENTS §6.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] `/api/live/status` trả thêm cờ lệch (vd `cau_hinh_lech: []` hoặc `image_size_hieu_luc`), có test API cho worker cũ (thiếu khoá ⇒ không lỗi)
- [x] HUD hiện cảnh báo `role="alert"` khi phiên có cấu hình lệch (không chỉ nằm trong `worker.log`)
- [x] Có test vitest cho nhãn cảnh báo + e2e kiểm `role=alert`
- [x] `docs/task`/log ghi rõ đây là hiển thị cho người vận hành, KHÔNG đổi kết luận số đo

## Answer (15-11)

Đã xong trên nhánh `feat/cau-hinh-lech-hud` (commit `10b8758`), log:
`docs/task/15-11-2026-cau-hinh-lech-len-hud.md`.

`/api/live/status` trả `cau_hinh_lech: list[str] | null` + `image_size_hieu_luc: int | null` với
**4 trạng thái phân biệt**: `null` = chưa biết (worker bản cũ / khoá null) · `[]` + có số độ phân
giải = đã kiểm và khớp · `[]` + `image_size_hieu_luc == null` = **chưa kiểm được** (predictor không
khai `image_size`) · có phần tử = lệch thật ⇒ HUD cảnh báo đỏ `role="alert"`.

Số kiểm: `./run lint` · `./run test` **1217 passed** · `./run webtest` **54** · `npm run build` ·
`./run e2e` **PASS** (3 check mới, gồm ca âm "khớp thì không hiện dòng nào").

Review độc lập: 0 P0/P1; đã sửa 3 P2 (khoá `null` ⇒ "khớp", thiếu test HTTP cho 2 mắt xích mới,
mô tả `[]` sai ở 4 chỗ) + 8 P3. Ghi lại 2 P3 chưa làm ở mục Next steps của log.
