# ADR-0002: Giữ laptop (CPU) làm demo live, bỏ ràng buộc real-time on-device, Colab cho việc nặng offline

## Bối cảnh
Prototype benchmark (`docs/research/05`) đo được SAM 2.1 tiny trên laptop sinh viên ≈ 0.2–0.7 FPS với
mọi backend (PyTorch/ONNX/INT8/OpenVINO) — không thể đạt real-time ≥ 10 FPS như ADR-0001 kỳ vọng.
Bốn đường đi đã trình GVHD (`docs/research/05` mục 5).

## Quyết định (GVHD chọn ngày 16-10-2026)
**Phương án 2** — giữ laptop làm môi trường duy nhất:
- Demo **live trên CPU** với FPS đo được như thực tế (~0.2 FPS), không cam kết ngưỡng ≥ 10 FPS on-device.
- Báo cáo trình bày **trung thực** số đo CPU + phân tích kiến trúc chứng minh hệ thống real-time-capable
  trên GPU; số FPS GPU tham chiếu lấy từ Colab (T4) trên video đã quay.
- **Colab GPU** đảm nhiệm mọi việc nặng **offline**: nén/export model, benchmark chất lượng, xử lý video
  minh họa. Laptop không chạy việc nặng ngoài demo live.
- (Tùy chọn, không gắn với yêu cầu) chế độ live-qua-Colab (~2–4 FPS) nếu cần demo mượt hơn — cần wifi ổn định.

## Hệ quả
- ADR-0001 **vẫn giữ** phần "backbone = SAM 2/SAMURAI + tự tối ưu"; phần "≥ 10 FPS trên máy này" **bị thay thế**.
- GLOSSARY.md: định nghĩa "Real-time (ngưỡng đồ án)" cập nhật theo quyết định này — ngưỡng on-device bỏ, thay bằng "báo cáo trung thực + chứng minh real-time-capable".
- Kế hoạch triển khai (spec/tickets) không còn cần các ticket "đạt ≥10 FPS"; giữ các ticket đánh giá/đo lường để trình bày độ trễ, FPS, IoU trung thực.