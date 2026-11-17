# 34: `test_reap_khong_cho_zombie_5_giay` đo thời gian tường — đổi sang assert `poll()` + ngưỡng theo số CPU

**What to build:** Nợ được nêu trong ticket #22 (đã đóng) nhưng **chưa có ticket follow-up** (review độc lập 17-11 bắt đúng: "nên tạo để không trôi").

Hiện test `tests/test_live_tracking.py::TestVeSinhWorkerCu::test_reap_khong_cho_zombie_5_giay` assert **thời gian tường** `elapsed < 3 s`. Trên máy bị chiếm CPU (đúng điều kiện của `./run testall`), một lần reap hợp lệ vẫn có thể vượt 3 s ⇒ test đỏ oan, cùng loại lỗi "đo thời gian tường" mà ticket #22 vừa xử lý ở test IoU.

Việc:
- Bỏ ngưỡng thời gian tuyệt đối; assert `proc.poll() is not None` (tiến trình đã được reap) trong một ngưỡng **rộng** (vd `5 s`, hoặc `max(5, 2 × số CPU)`), và **in** thời gian reap thật khi đỏ để lần sau có số.
- 5 lần liên tiếp xanh trên máy này khi có tải nền; ghi số đo vào log `docs/task/`.

**Status:** `ready-for-agent`

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `test_reap_khong_cho_zombie_5_giay` bỏ assert `elapsed < 3 s` (đo thời gian tường) → assert `proc.poll() is not None` (đã reap) trong ngưỡng rộng theo số CPU
- [ ] Test chạy được trên CI ubuntu (không có nhiều CPU, không có webcam/model) và không flaky khi máy tải: 5 lần liên tiếp xanh
- [ ] Ghi số đo (thời gian reap thật trên máy này) vào log `docs/task/`
