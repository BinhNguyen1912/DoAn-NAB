# 3: Cơ chế xác thực tái bắt đối tượng sau khi mất dấu

**What to build:** Kiểm tra hình học đối tượng (tỷ lệ w/h, diện tích) và prompt đối chiếu khi tái bắt đối tượng sau khi bị che khuất hoặc rời khung hình, tránh nhận nhầm vào mảng tường sáng.

**Blocked by:** 01, 02

**Status:** ready-for-agent

- [ ] Lưu trữ lịch sử hình học đối tượng: diện tích trung bình (area) và tỷ lệ khung hình (aspect ratio) của các frame ổn định trước đó
- [ ] Khi tái bắt đối tượng, ứng viên phải thỏa mãn ngưỡng sai lệch diện tích và aspect ratio so với lịch sử trước khi được chấp nhận
- [ ] Tích hợp cơ chế re-prompt lại điểm dương/âm nếu ứng viên vượt qua vòng lọc hình học
- [ ] Test tự động: vật thể ra khỏi khung rồi quay lại được nhận diện đúng; mảng tường hoặc đối tượng khác bị loại bỏ
