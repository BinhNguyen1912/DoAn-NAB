# Ngày 16-10-2026 — Prototype benchmark SAM 2.1 tiny trên máy sinh viên

## 🎯 Mục tiêu
- Trả lời câu hỏi của ADR-0001 bằng số liệu đo thật (không lý thuyết): **SAM 2.1 tiny có đạt ≥ 10 FPS trên laptop không?**

## 📥 Input
- Env conda `samurai` của máy (Python 3.11, torch 2.14.1+cpu, sam2 import được, checkpoint tiny sẵn).
- 15 frame demo (`data/demo_input_frames`) + bbox con chó (`data/dog_bbox_frame0.txt`).
- Kế hoạch đo 4 backend: PyTorch CPU / ONNX CPU (+INT8) / OpenVINO GPU Iris Xe.

## 🔨 Công việc đã thực hiện
1. Cài `onnx`, `onnxruntime`, `openvino` vào env `samurai`.
2. Viết `tools/benchmark_sam2_realtime.py` — benchmark 4 phase (pipeline / encoder / onnx / openvino), có export model lưu `models/bench/`.
3. Sửa 2 lỗi trong lúc chạy:
   - Hydra search path là `pkg://sam2` → config name phải là `configs/samurai/sam2.1_hiera_t.yaml` (không phải `samurai/...`).
   - Thiếu gọi `main()` / import numpy rải rác trong script bản đầu.
4. Chạy đủ 4 phase, thu số liệu.
5. Viết báo cáo kết quả `docs/research/05-ket-qua-benchmark-prototype-sam2-tiny.md`.

## 📤 Output / Kết quả
**Đo được (số thật trên máy):**
- Pipeline video thật (PyTorch CPU): **~5.4s/frame ≈ 0.2 FPS** (chậm dần theo frame — thermal throttling).
- Encoder riêng @1024: PyTorch CPU 1.6–1.8s | ONNX fp32 1.70s | ONNX **INT8 1.38s** | OpenVINO CPU 1.61s → **~0.6–0.7 FPS mọi backend**.
- OpenVINO **không thấy GPU trong WSL** (chỉ `CPU`) → Iris Xe chưa đo được, phải chạy Python trên Windows.

**Kết luận:** SAM 2.1 tiny trên laptop này **không thể real-time ≥10 FPS** với mọi tối ưu runtime; khoảng cách 14–50×. Rủi ro ADR-0001 cảnh báo **hiện thực hóa**. Bộ ràng buộc (SAM2 + máy này + real-time + live) vô nghiệm theo dữ liệu → cần người dùng + GVHD chọn nhượng bộ 1 ràng buộc. Sửa ADR/ghi ADR-0002 **chờ quyết định**.

- File thay đổi:
  - `tools/benchmark_sam2_realtime.py` — script benchmark (mới)
  - `docs/research/05-ket-qua-benchmark-prototype-sam2-tiny.md` — báo cáo kết quả + các đường đi cho GVHD (mới)
  - `models/bench/sam2.1_tiny_encoder_fp32.onnx`, `..._int8.onnx`, `..._ir.xml` — model đã export (tái dùng được cho module đánh giá)

## 🐞 Vấn đề gặp phải & cách xử lý
- Giả định ban đầu "encoder là nút cổ chai, OpenVINO/INT8 sẽ nhanh 2–4×" **bị số liệu bác bỏ** — INT8 chỉ nhanh 19%, mọi runtime CPU gần như ngang nhau: bottleneck là CPU 4 nhân vật lý.
- Giả tưởng init_state precompute feature → phát hiện SAM 2 encode mỗi frame trong propagate.
- WSL không expose Intel iGPU cho OpenVINO → chưa đo được đường GPU (ước tính lạc quan ~2–3 FPS, vẫn < 10).

## 📌 Việc cần làm tiếp (Next steps)
- [x] Người dùng mang `docs/research/05` (mục 3 + 5) đi trao đổi GVHD — **GVHD chọn phương án 2**.
- [x] Ghi **ADR-0002**: giữ laptop CPU làm demo live, bỏ ngưỡng ≥10 FPS on-device, Colab cho việc nặng offline; GLOSSARY cập nhật định nghĩa Real-time.
- [ ] `/to-spec` → `/to-tickets` theo quyết định mới (tickets vào `.scratch/<feature>/`).

## 📚 Tài liệu tham khảo
- Kết quả chi tiết + nguồn: `docs/research/05-ket-qua-benchmark-prototype-sam2-tiny.md`.