# ADR-0001: Dùng SAM 2/SAMURAI làm backbone và tự tối ưu cho real-time

## Bối cảnh
Đề tài yêu cầu webcam live + real-time trên laptop sinh viên (MSI Modern 14 B11MOU: i7-1195G7, Intel Iris Xe, không CUDA). Nghiên cứu (`docs/research/03-...`) cho thấy full SAM 2/SAMURAI chạy trên máy này **không đạt real-time** nếu dùng nguyên bản (~2–8 FPS kể cả tối ưu native). Các biến thể on-device của SAM 2 (EdgeTAM 22× nhanh, EfficientTAM ~10 FPS trên iPhone) có thể đạt real-time nhưng là **model có sẵn**.

## Quyết định
Giữ **SAM 2 / SAMURAI làm backbone gốc** và **tự tối ưu** để đạt real-time, coi phần tối ưu là **đóng góp sáng tạo** của đồ án (không dùng EdgeTAM/EfficientTAM sẵn). Tối ưu trên laptop cục bộ bằng ONNX Runtime / OpenVINO trên Intel Iris Xe (FP16 iGPU, INT8 encoder cho CPU), streaming qua `async_loading_frames`. Ngưỡng "real-time" chấp nhận = **≥ 10 FPS live** (mục tiêu 15–24).

## Lý do
- Đồ án cần đóng góp riêng, mang tính sáng tạo; dùng model on-device có sẵn sẽ bị nhận xét "chỉ dùng sẵn".
- SAMURAI cùng codebase SAM 2 → port/glue được logic Kalman + memory-bank selection, giữ trọn 3 trụ (Segmentation + Motion Memory + Temporal Propagation).
- Đề tài gốc cho phép "tham khảo SAM 2, SAMURAI hoặc XMem".

## Các lựa chọn đã xét
- **EdgeTAM** (on-device, 22× nhanh SAM 2, 16 FPS iPhone): bị loại vì "có sẵn", thiếu đóng góp riêng.
- **EfficientTAM** (~1.6× nhanh, 10 FPS iPhone): bị loại cùng lý do.
- **XMem** (VOS nhẹ): giữ làm **phương án dự phòng** nếu SAM 2 tối ưu vẫn < 10 FPS.
- **Hybrid laptop + Colab GPU cho inference live**: bị loại vì stream frame qua mạng phá real-time (latency round-trip). Colab chỉ dùng cho việc **offline** (export/quantize model, benchmark chất lượng trên dataset), không dùng cho demo live.

## Hậu quả & rủi ro
- **Rủi ro chính**: ≥ 10 FPS trên máy này **không đảm bảo** (nghiên cứu ước lượng ~2–8 FPS). Bắt buộc **prototype benchmark sớm** để đo FPS thực tế của SAM 2.1 tiny (PyTorch CPU / ONNX CPU / OpenVINO iGPU, độ phân giải 1024 vs 512) trước khi cam kết kiến trúc.
- **Menu tối ưu (đóng góp sáng tạo)**: (1) export ONNX/OpenVINO IR; (2) INT8 quantize image encoder (CPU); (3) giảm resolution 1024→512/640; (4) async frame loading + single-step propagate; (5) prune memory bank / skip-frame; (6) *tuỳ chọn* thay Hiera encoder bằng vanilla ViT nhẹ trong fork SAM 2 của mình (giữ memory module) — đóng góp chính nếu thời gian cho phép.
- **Phương án thoát**: nếu prototype < 10 FPS sau khi áp dụng menu tối ưu → xét XMem hoặc hạ ngưỡng/report trung thực.
- **Cloud offload**: chỉ cho task offline (export/quantize/benchmark chất lượng). Demo live phải chạy cục bộ trên laptop.