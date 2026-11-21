# 1: Prompt negative và positive points khi chọn đối tượng

**What to build:** Cho phép chỉ định thêm điểm tâm (positive) và điểm nền sát mép (negative) bên cạnh bounding box để SAM 2 tách ranh giới vật thể đơn sắc/trắng trơn khỏi nền sáng ngay từ frame đầu tiên.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] TrackerEngine.start() nhận thêm tham số points và labels (1 cho positive, 0 cho negative) truyền vào add_new_points_or_box
- [x] API POST /api/live/select và cấu trúc bbox.json hỗ trợ danh sách points kèm labels (tùy chọn)
- [x] Visualizer hiển thị điểm positive (xanh lá) và negative (đỏ) lúc người dùng tương tác chọn ô
- [x] Test tự động fixture: vật thể trắng trên nền sáng phân tách ranh giới rõ ràng, không tràn mask ra ngoài nền

## Answer

Đã hoàn thành vertical slice hỗ trợ điểm prompt positive/negative: TrackerEngine truyền points/labels vào SAM 2 add_new_points_or_box; PromptSelector hỗ trợ click trái (positive) và click phải (negative) hiển thị xanh/đỏ; API hỗ trợ POST /api/live/select và LiveStartRequest kèm points; WorkerFrameSource ghi và live_tracking đọc points/labels qua PromptSelection; test tự động xanh 100%.
