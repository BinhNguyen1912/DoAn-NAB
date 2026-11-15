# 28: Đưa `cau_hinh_lech` (cấu hình yêu cầu ≠ hiệu lực) lên API live + HUD

**What to build:** Từ 15-11, worker ghi `cau_hinh` + `cau_hinh_lech` vào `status.json`, nhưng **không** đi qua API: `src/api/adapters/worker_source.py::telemetry()` chỉ đọc các khoá số đã biết, `LiveTelemetry`/`LiveStatusResponse` không có trường này, `web/src/api.ts` cũng không.

Hệ quả: nếu buổi demo chạy sai cấu hình (hydra override no-op ⇒ model chạy 1024 trong khi người dùng chọn 192), người ngồi xem UI **không biết**; cảnh báo chỉ nằm trong `worker.log`. Đây đúng loại "xanh giả" mà cả repo đang cố chặn — số trên HUD trông đúng nhưng gắn sai cấu hình.

Phạm vi tối thiểu: chỉ đưa **cờ** lệch (hoặc `image_size_hieu_luc`) lên `LiveTelemetry` → DTO → `web/src/api.ts` → `LivePanel` hiện dòng cảnh báo `role="alert"` khi lệch. Không đưa cả khối `cau_hinh` vào HUD (rối, và không ai đọc).

**Lưu ý:** worker bản cũ không có khoá này ⇒ adapter phải đọc kiểu "vắng mặt = chưa biết", **không** mặc định `[]` (rỗng = "đã kiểm và khớp") — cùng bẫy `None` vs `0` của AGENTS §6.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `/api/live/status` trả thêm cờ lệch (vd `cau_hinh_lech: []` hoặc `image_size_hieu_luc`), có test API cho worker cũ (thiếu khoá ⇒ không lỗi)
- [ ] HUD hiện cảnh báo `role="alert"` khi phiên có cấu hình lệch (không chỉ nằm trong `worker.log`)
- [ ] Có test vitest cho nhãn cảnh báo + e2e kiểm `role=alert`
- [ ] `docs/task`/log ghi rõ đây là hiển thị cho người vận hành, KHÔNG đổi kết luận số đo
