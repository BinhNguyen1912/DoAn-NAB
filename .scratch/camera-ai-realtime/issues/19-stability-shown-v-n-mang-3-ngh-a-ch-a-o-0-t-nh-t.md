# 19: `stability_shown` vẫn mang 3 nghĩa (chưa đo / màn hình trống / đo được 0)

**What to build:** `src/live_tracking.py`: `stability_shown: float = 0.0` là bản sao đúng lỗi mà
ticket 18 vừa sửa cho `stability`:

- chưa có mẫu nào ⇒ `0,0` (thực ra là **chưa đo**);
- mask hiển thị RỖNG (mất dấu) ⇒ cũng `0,0`;
- hai mask hiển thị rời nhau hoàn toàn ⇒ **đo được** `0,0`.

Không lộ ra người dùng (không đi qua `/api/live/status`, chỉ có trong `status.json` và trong
`data/*_metrics.json` đã công bố), nhưng người đọc artifact sẽ trích "ổn định 0 %" cho một phiên
chưa đo gì.

Cách sửa (giống ticket 18): `stability_shown: float | None = None` + `stability_shown_n: int`
(độ dài `_shown_iou_window`), `status_payload` thêm khoá, allowlist test `status.json` cập nhật.
Test: cửa sổ rỗng ⇒ `None`/0; mất dấu khi đã có mẫu ⇒ `0,0`/n>0.

**Blocked by:** None. **Status:** ready-for-agent

- [ ] Cửa sổ `_shown_iou_window` rỗng ⇒ `stability_shown is None`, `stability_shown_n == 0`
- [ ] Có mẫu rồi mới mất dấu ⇒ `stability_shown == 0.0`, `stability_shown_n > 0`
- [ ] `status.json` có `stability_shown_n`; allowlist test cập nhật
- [ ] `./run test` + `./run testall` xanh
