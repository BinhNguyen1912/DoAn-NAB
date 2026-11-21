# 3: Cơ chế xác thực tái bắt đối tượng sau khi mất dấu

**What to build:** Kiểm tra hình học đối tượng (tỷ lệ w/h, diện tích) và prompt đối chiếu khi tái bắt đối tượng sau khi bị che khuất hoặc rời khung hình, tránh nhận nhầm vào mảng tường sáng.

**Blocked by:** 01, 02

**Status:** resolved

- [x] Lưu trữ lịch sử hình học đối tượng: diện tích trung bình (area) và tỷ lệ khung hình (aspect ratio) của các frame ổn định trước đó
- [x] Khi tái bắt đối tượng, ứng viên phải thỏa mãn ngưỡng sai lệch diện tích và aspect ratio so với lịch sử trước khi được chấp nhận
- [x] Tích hợp cơ chế re-prompt lại điểm dương/âm nếu ứng viên vượt qua vòng lọc hình học
- [x] Test tự động: vật thể ra khỏi khung rồi quay lại được nhận diện đúng; mảng tường hoặc đối tượng khác bị loại bỏ

## Answer

Đã hoàn thành cơ chế xác thực tái bắt đối tượng: GeometricProfile lưu trữ diện tích & aspect ratio (w/h) trung bình; kiểm tra tính tương thích hình học của ứng viên để loại bỏ mảng tường/công tắc cùng tông màu nhưng khác tỉ lệ; tự động sinh điểm prompt tương phản khi tái bắt để SAM 2 khởi động lại sạch sẽ; 1735 test xanh 100%.
