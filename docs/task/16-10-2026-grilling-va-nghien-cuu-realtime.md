# Ngày 16-10-2026 — Grilling thiết kế + nghiên cứu khả năng real-time + ghi ADR/GLOSSARY

## 🎯 Mục tiêu
- Phỏng vấn thiết kế (`/grill-with-docs`) để chốt kiến trúc hệ thống Camera AI real-time.
- Nghiên cứu khả năng chạy real-time trên laptop sinh viên (không GPU NVIDIA).
- Ghi lại quyết định kiến trúc (ADR) và thuật ngữ (GLOSSARY).

## 📥 Input
- Yêu cầu từ người dùng + ràng buộc từ GVHD: **webcam live bắt buộc + phải real-time**, mở rộng cam rời/cam điện thoại, làm trên laptop, phần nặng có thể đẩy lên mây.
- Phần cứng máy sinh viên (quét thực tế): MSI Modern 14 B11MOU, i7-1195G7 (4 nhân/8 luồng), 16GB RAM, **Intel Iris Xe (không CUDA)**.
- Đề cương gốc `docs/DoAnCameraAI.docx` (đọc trực tiếp).

## 🔨 Công việc đã thực hiện
1. Quét phần cứng laptop qua PowerShell (`Win32_VideoController`, `Win32_Processor`, `Win32_ComputerSystem`).
2. Đọc trực tiếp `docs/DoAnCameraAI.docx` (giải nén + parse XML) — đối chiếu 7 yêu cầu sản phẩm cuối kỳ + lịch trình 14 buổi.
3. Phỏng vấn 2 round (`/grilling`):
   - Round 1: phần cứng, FPS mục tiêu, nguồn đầu vào, UI, số object, ngôn ngữ.
   - Round 2: backbone, motion-memory, ngưỡng real-time, cổng prototype.
4. Nghiên cứu web (ollama web search/fetch) — đọc nhiều nguồn gốc:
   - AnnotateIt benchmark SAM 2.1 trên Intel Core Ultra 9 (iGPU): encoder ~2.19s/frame (Tiny) → không real-time.
   - SAMURAI issue #128: streaming webcam/RTSP khả thi qua `async_loading_frames`.
   - EfficientTAM (Meta, ICCV 2025): ~1.6× nhanh SAM 2, ~10 FPS iPhone.
   - EdgeTAM (Meta, on-device): 22× nhanh SAM 2, 16 FPS iPhone.
   - XMem (ECCV 2022): VOS nhẹ, phương án dự phòng.
   - OpenVINO + SAM2 trên Intel iGPU (blog note.com/todamah): convert IR, INT8 encoder.
5. Viết báo cáo nghiên cứu `docs/research/03-kha-nang-real-time-tren-laptop-cpu-igpu.md` (có trích nguồn).
6. Chốt quyết định với người dùng:
   - **Q7**: backbone = **SAM 2/SAMURAI gốc, tự tối ưu** (không dùng EdgeTAM/EfficientTAM sẵn — GVHD muốn đóng góp sáng tạo).
   - **Q8**: dùng SAM 2/SAMURAI + tự nâng cấp dần.
   - **Q9**: real-time = **≥ 10 FPS live** (mục tiêu 15–24).
   - **Q10**: dựng prototype benchmark đo FPS thực tế trước.
   - Q1–Q6: chạy hết trên laptop + ONNX/OpenVINO; nguồn webcam USB + RTSP + video file; UI OpenCV kéo chuột; single object; tiếng Việt cho comment/UI.
7. Ghi `docs/adr/0001-sam2-samurai-backbone-tu-toi-uu-realtime.md` (backbone + tối ưu + rủi ro + menu tối ưu + cloud-offload chỉ offline).
8. Tạo `GLOSSARY.md` (Image Segmentation, Motion Memory, Temporal Propagation, Motion-Aware Memory, Real-time ngưỡng, Backbone).

## 📤 Output / Kết quả
- Kiến trúc & ràng buộc đã chốt: SAM 2/SAMURAI + tự tối ưu real-time trên laptop Intel iGPU; ≥10 FPS live; streaming qua async frame loading; cloud chỉ cho task offline.
- Rủi ro chính được nhận diện: ≥10 FPS không đảm bảo → bắt buộc prototype benchmark sớm.
- File thay đổi:
  - `docs/research/03-kha-nang-real-time-tren-laptop-cpu-igpu.md` — báo cáo nghiên cứu (mới)
  - `docs/adr/0001-sam2-samurai-backbone-tu-toi-uu-realtime.md` — ADR quyết định backbone (mới)
  - `GLOSSARY.md` — glossary thuật ngữ đồ án (mới)
  - `docs/task/16-10-2026-grilling-va-nghien-cuu-realtime.md` — log này (mới)

## 🐞 Vấn đề gặp phải & cách xử lý
- Xung đột yêu cầu: "live camera" + "real-time" + "không GPU" trên cùng máy không đồng thời khả thi với SAM 2 nguyên bản → giải quyết bằng quyết định "tự tối ưu SAM 2" + nhận rủi ro + cổng prototype; cloud offload chỉ offline (vì stream frame qua mạng phá real-time).
- WSL không thấy `nvidia-smi`/`python` → quét phần cứng qua PowerShell.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Người dùng xác nhận "hiểu biết chung" trước khi qua bước tiếp.
- [ ] `/prototype`: benchmark SAM 2.1 tiny trên laptop (PyTorch CPU / ONNX CPU / OpenVINO iGPU, res 1024 vs 512) → đo FPS thực tế, trả lời "≥10 FPS có khả thi không".
- [ ] Sau khi prototype rõ → `/to-spec` → `/to-tickets` (ghi vào `.scratch/<feature>/`).

## 📚 Tài liệu tham khảo
- Xem mục 7 trong `docs/research/03-kha-nang-real-time-tren-laptop-cpu-igpu.md`.