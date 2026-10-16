# 3: VideoSource (webcam / RTSP / file)

**What to build:** Module interface nguồn video thống nhất: trả frame kế tiếp + thuộc tính (FPS nguồn, kích thước). Ba adapter cùng interface: webcam tích hợp (theo index), camera rời/điện thoại qua RTSP URL, video file. File adapter có test tự động (dùng fixture); webcam/RTSP là lớp mỏng, kiểm chứng thủ công. Là seam thứ hai đã thống nhất với người dùng.

**Blocked by:** None (can start immediately)

**Status:** claimed

- [x] File adapter đọc đúng số frame/kích thước/dtype (test bằng fixture)
- [ ] Webcam adapter mở được camera laptop, trả frame (xác nhận thủ công)
- [x] RTSP adapter nhận URL; nguồn lỗi → báo lỗi rõ ràng thay vì treo
- [x] Một interface duy nhất — script demo chọn nguồn qua tham số
