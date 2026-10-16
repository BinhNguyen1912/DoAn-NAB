# 1: Fixture giả lập + nền tảng pytest

**What to build:** Tạo bộ sinh ảnh giả lập bằng code: một ô vuông màu đặc di chuyển theo quỹ đạo tuyến tính biết trước trên nền màu — trả về cả chuỗi frame (numpy) và vị trí (bbox) đúng tại từng frame, kèm chế độ che khuất (chen cản/ẩn vài frame). Đây là nền "prefactor" để mọi ticket sau test được mà không commit dữ liệu nặng; setup pytest cho repo (thư mục tests chuẩn).

**Blocked by:** None (can start immediately)

**Status:** claimed

- [x] pytest chạy được, có ít nhất 1 test green demo cách dùng fixture
- [x] Fixture sinh chuỗi N frame (numpy) + trả về vị trí (bbox) đúng của ô vuông tại từng frame
- [x] Có chế độ che khuất (chen cản/ẩn ô vuông vài frame) cho test sau dùng
- [x] Chạy được trên CPU máy hiện tại, không cần model
