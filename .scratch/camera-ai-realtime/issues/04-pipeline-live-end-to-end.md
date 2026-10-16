# 4: Pipeline live end-to-end

**What to build:** Lát cắt dọc đầu tiên — hệ thống "sống": một lệnh chạy nối VideoSource → TrackerEngine → overlay đơn giản (mask mờ + ô bao) lên cửa sổ OpenCV, cập nhật mỗi frame; in FPS/độ trễ trung thực ra console. Chọn đối tượng tạm bằng bbox mặc định từ config (phần chọn bằng chuột là ticket sau). Chạy được cả webcam lẫn video file.

**Blocked by:** 02, 03

**Status:** resolved

- [x] Một lệnh chạy pipeline: webcam live (hoặc video file demo) → cửa sổ hiện frame + mask bám theo đối tượng (bbox mặc định từ config / bbox file txt nếu có)
- [x] Độ trễ trung bình in ra console theo từng frame (trung thực, không claim real-time)
- [x] Thoát cửa sổ / Ctrl+C sạch, không crash, không để process zombie

## Answer

Hoàn thành: pipeline 1 lệnh nối VideoSource → TrackerEngine → overlay + summary mean/p95/FPS hiệu dụng; Ctrl+C sạch. Log docs/task/16-10-2026-implement-ticket-04-pipeline-live.md. Display/webcam chờ thủ công trên máy có GUI (WSL không màn hình).
