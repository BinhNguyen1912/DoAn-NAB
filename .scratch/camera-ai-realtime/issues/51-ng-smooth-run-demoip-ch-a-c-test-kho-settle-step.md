# 51: Đường `--smooth` (./run demoip) chưa có test khoá settle_steps; `frame_shape_doi` chưa có test nào đo được

**What to build:** Review vòng 2 (P2-E + m8). Hai lỗ hổng test **còn sống** sau commit sửa P1:

1. `src/smooth_display.py:378-381` — đường `--smooth` = **`./run demoip` (đường demo chính)** không có test nào chứng minh `settle_steps` tới `IdentityWatch`. Hiện chỉ có: `TestCoCongNghiDiToiCong` (chạy `run_interactive`) và `TestCoCongNghiDuocTruyenTuRunLive` (kiểm **kwargs vào stub**). Đột biến `settle_steps=DEFAULT_SETTLE_STEPS` **vô điều kiện** ở `:379` ⇒ **mọi test vẫn xanh**, và hành vi 44 % frame ẩn quay lại trong im lặng.

2. `src/metrics_logger.py::frame_shape_doi` — trường này chỉ ĐO được nếu `note_frame_shape` được gọi mỗi frame (đã sửa ở 3 vòng lặp), nhưng **không có test** nào bắt đột biến "gọi chỉ ở frame đầu" (m8) ⇒ nếu ai revert, `run_info` lại công bố `frame_shape_doi: 0` = "đã kiểm, không đổi" trong khi chưa kiểm (đúng bẫy "0/None ≠ đã đo").

Dùng khung test có sẵn: `tests/test_smooth_display.py:955-1035`.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Test chạy `run_smooth_display` hai lần với `settle_steps=1` và `=8` trên cùng clip + engine nhảy ⇒ `summary.chua_xac_minh_n` của lần 1 LỚN HƠN lần 8 (nếu cờ không tới cổng thì hai lần bằng nhau)
- [ ] Đột biến `settle_steps=DEFAULT_SETTLE_STEPS` vô điều kiện ở `src/smooth_display.py:379` phải làm test ĐỎ
- [ ] Test `frame_shape_doi`: đưa 2 khung khác kích thước vào `MetricsLogger` qua một vòng lặp ⇒ `frame_shape_doi > 0` (đột biến 'chỉ gọi `note_frame_shape` ở frame đầu' phải ĐỎ)
- [ ] `./run test` xanh, thời gian thêm < 5 s
