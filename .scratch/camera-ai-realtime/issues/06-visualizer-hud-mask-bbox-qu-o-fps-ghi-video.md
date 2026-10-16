# 6: Visualizer HUD: mask + bbox + quỹ đạo + FPS + ghi video

**What to build:** Overlay trình bày hoàn chỉnh cho demo bảo vệ: mask tô màu bán trong suốt, ô bao, đường quỹ đạo nối tâm đối tượng qua thời gian (deque giới hạn số điểm từ config), text HUD FPS + độ trễ ms/frame với nhãn tiếng Việt; ghi video mp4 bản đã overlay (bật/tắt qua config). Khớp yêu cầu 5 của thầy (hiển thị vị trí, vùng phân đoạn, quỹ đạo) và phần ghi minh chứng.

**Blocked by:** 05

**Status:** claimed

- [x] HUD đủ: mask tô màu + ô bao + đường quỹ đạo + FPS/latency; nhãn tiếng Việt hiển thị đúng font
- [x] Bật ghi video qua config → file mp4 đầu ra mở được, nội dung đúng luồng demo
- [x] Quỹ đạo vẽ theo tâm đối tượng, giới hạn số điểm (deque) không tràn bộ nhớ
