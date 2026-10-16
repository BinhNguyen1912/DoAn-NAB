# 8: Chế độ headless + config YAML + README

**What to build:** Đóng gói toàn bộ thành sản phẩm chạy được mọi nơi: lệnh chạy không UI — đọc video file, track toàn bộ, xuất mp4 kết quả + metrics CSV/summary; tham số hóa qua file YAML trong configs/ (checkpoint, model config, nguồn, bật/tắt ghi); README cài đặt tái tạo được từ clone mới (clone SAMURAI không vendor, conda env, tải checkpoint) + ghi nhận lệnh headless này dùng trên Colab GPU làm video minh họa (ADR-0002). Khớp stories 19–22 của spec.

**Blocked by:** 04, 07

**Status:** claimed

- [x] Một lệnh headless trên video file → ra mp4 kết quả + CSV + summary; chạy được môi trường không màn hình (server/Colab)
- [x] Đổi checkpoint/tham số qua file YAML trong configs/ không phải sửa code
- [x] README cài đặt từ clone mới (clone SAMURAI + conda env + tải checkpoint) đủ cho người khác tự làm; ghi rõ tham chiếu config SAMURAI
- [x] Tài liệu ghi nhận lệnh headless dùng cho Colab GPU theo ADR-0002
