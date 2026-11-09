# 16: Phiên đang `error` rồi bấm Bật phát: status giữ `error` (kèm 409/role=alert) suốt lúc mở nguồn

**What to build:** `_stop_locked()` chỉ hạ `RUNNING → STOPPED`; nếu phiên trước đang `error`, `start()` giữ `state=error` trong khi mở nguồn (mode `track` nạp worker 20–240 s). Hệ quả: `/api/live/status` trả `error` + message "Đang mở …"; `/api/live/stream` trả 409 "Phiên live đã dừng vì lỗi: Đang mở …"; `LivePanel` hiện dòng `role="alert"` — người dùng thấy "lỗi" trong khi hệ thống đang nạp bình thường.

Có từ trước nhánh watchdog, không do review vòng 3 (finding P3-6, review vòng 4).

Cách sửa nhỏ nhất: khi công bố `_message = "Đang mở …"` cũng đặt `self._state = LiveState.STOPPED` nếu state hiện tại không phải `RUNNING`; hoặc thêm state `starting` (cần sửa `LiveState`, schema `Literal`, UI, test) nếu muốn UI nói đúng "đang nạp".

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Trong lúc mở nguồn sau một phiên `error`, `/api/live/status` KHÔNG trả `error` (test: nguồn giả có `start()` ngủ 0,3 s, phiên A cho give-up, `start()` B ở thread phụ, assert state != error)
- [ ] `/api/live/stream` không trả 409 "Phiên live đã dừng vì lỗi: Đang mở …" trong cùng cửa sổ đó
- [ ] UI không hiện `role="alert"` khi đang nạp phiên mới
- [ ] `./run test`, `./run webtest`, `./run e2e` xanh
