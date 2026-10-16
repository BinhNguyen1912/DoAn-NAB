# 4: Pipeline live end-to-end

**What to build:** Lát cắt dọc đầu tiên — hệ thống "sống": một lệnh chạy nối VideoSource → TrackerEngine → overlay đơn giản (mask mờ + ô bao) lên cửa sổ OpenCV, cập nhật mỗi frame; in FPS/độ trễ trung thực ra console. Chọn đối tượng tạm bằng bbox mặc định từ config (phần chọn bằng chuột là ticket sau). Chạy được cả webcam lẫn video file.

**Blocked by:** 02, 03

**Status:** ready-for-agent

- [ ] Một lệnh chạy pipeline: webcam live (hoặc video file demo) → cửa sổ hiện frame + mask bám theo đối tượng (bbox mặc định từ config / bbox file txt nếu có)
- [ ] Độ trễ trung bình in ra console theo từng frame (trung thực, không claim real-time)
- [ ] Thoát cửa sổ / Ctrl+C sạch, không crash, không để process zombie
