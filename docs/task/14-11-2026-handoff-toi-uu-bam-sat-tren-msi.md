# Ngày 14-11-2026 — Phiên bàn hướng tối ưu "bám sát" trên MSI (không code, chỉ chốt quyết định)

## 🎯 Mục tiêu
- Trả lời: muốn "bám sát đúng đối tượng realtime, mọi thứ trên camera, chi phí thấp" thì **cần làm
  gì** — có phải train lại model, đổi model, hay mua phần cứng — và **cái nào thực sự làm sản phẩm
  tốt hơn**.
- Chốt ràng buộc môi trường: **MSI là máy demo**, **Mac mini M4 chỉ để viết code** (phát hiện trong
  phiên: trước đó các trao đổi giả định làm trên máy đang mở repo).

## 📥 Input
- Yêu cầu người dùng (14-11): sản phẩm phải "như một camera", mọi thứ trong đó để đáp ứng nhánh
  biên; hỏi có cách "ăn gian" không; sau đó chốt: bỏ ESP32-CAM, dùng **webcam rời**, làm trên MSI.
- Ràng buộc phần cứng: MSI Modern 14 B11MOU (i7-1195G7, Iris Xe, 16 GB, không CUDA, Windows+WSL).
  Máy đang mở repo lúc bàn: **Mac mini M4 arm64, macOS 26.5.2** — không có `samurai/`, `models/`,
  `/dev/shm`, không có `python`/`ruff`/`pytest`, không có conda `samurai`.
- Tài liệu đọc trong phiên: `docs/adr/0001`, `0002`, `AGENTS.md` §6, `docs/task/08-11-2026-*`,
  `docs/research/08`, `09`, `11`, `configs/default.yaml`, `src/live_tracking.py`,
  `src/api/adapters/*`, `src/video_source.py`, `tools/live_worker.py`, `.github/workflows/checks`.

## 🔨 Công việc đã thực hiện
1. Khảo sát source: kiến trúc API ports&adapters (ADR-0005), 2 đường chạy (job upload vs live),
   luồng live (LiveStreamService → WorkerFrameSource → `tools/live_worker.py` → LiveTrackingSession
   với luồng VOS riêng + LK).
2. Kiểm bằng lệnh: đường live **không có** re-ID / re-anchor (`rg reid|reanchor src/live_tracking.py
   tools/live_worker.py` → 0); `data/` **không có** file GT mask nào; `CameraVideoSource` chỉ ép
   MJPG+640×480 khi Linux (`src/video_source.py:132-140`); `requirements.txt` **không** gồm torch
   (cài riêng, CI cài torch CPU).
3. Research ngoài (2 search + 1 fetch; agent `scout` **timeout 30 phút** nên tự tra):
   EfficientTAM (SA-V J&F Ti 70,7 / S 74,5 vs SAM 2.1 tiny 76,5), kỹ thuật pooling 2×2 memory
   attention (đo laptop CPU 29,2→8,4 ms; relative error 0,05 mượt / 0,753 thô), Selective Mask
   Propagation (Holmberg, preprint 2026, training-free), bf16/IPEX **không có số cho CPU client**.
4. Chốt bằng số (không suy đoán): 6 hướng còn lại + 6 hướng đã bác, và **thứ tự 1→2→3→4**.
5. Viết handoff: `docs/plan/14-11-2026-toi-uu-bam-sat-tren-msi.md` (quyết định + số + việc bác).

## 📤 Output / Kết quả
- **Không thay đổi code.** Không có số đo mới (phiên này chỉ đọc + research).
- Quyết định chốt:
  - **Không** train lại SAM 2, **không** mua GPU/Jetson/ESP32-CAM, **không** dùng Colab cho live.
  - Demo = **MSI + webcam rời**; chỉ nên mua **webcam 1080p30** (~1,5 tr) vì trần FPS là webcam
    (16,6 FPS @640×480 đo 13-11).
  - Tối ưu theo thứ tự: **bf16 (30 ph) → `num_maskmem` 3/5/7 (15 ph) → pooling 2×2 memory attention
    (2–3 ngày) → selective VOS propagation (3–5 ngày)**; RepViT encoder là đánh đổi cuối (−4,5 J&F).
  - Ưu tiên cao hơn cả 4 hướng trên: **port re-ID + re-anchor vào đường live** (lỗ hổng lớn nhất,
    người xem nhận ra ngay).
- File thay đổi:
  - `docs/plan/14-11-2026-toi-uu-bam-sat-tren-msi.md` — handoff: câu hỏi, baseline đã đo, hướng bị
    bác kèm số, 6 hướng còn lại, tiêu chí nghiệm thu, việc phải làm trước khi code.
  - `docs/task/14-11-2026-handoff-toi-uu-bam-sat-tren-msi.md` — log này.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Giả định sai về máy trong nửa đầu phiên**: đã đề xuất hướng "chạy Windows native để thấy Iris Xe"
  và "đo trên máy này" trong khi máy đang mở repo là Mac mini M4. Người dùng sửa lại: MSI mới là máy
  demo. Đã ghi ràng buộc này thành mục đầu tiên của plan để không lặp lại.
- **Không chạy được gì trên Mac mini**: không `python`/`ruff`/`pytest`, `./run` chết vì tìm conda
  `samurai`, không có `samurai/`+`models/` ⇒ **không dựng nổi TrackerEngine**. Chưa dựng venv (người
  dùng quyết định làm trên máy riêng).
- **Agent `scout` timeout cứng 30 phút** ⇒ tự chạy search/fetch. Ghi nhận để lần sau dùng `scout`
  cho brief ngắn hơn hoặc chấp nhận tự tra.
- **Số "SA-V J&F 76,5 vs 70,7/74,5"** lấy từ bảng model card + blog, khác nguồn nhau — đã ghi rõ
  nguồn và mức tin cậy trong plan, không trộn thành một bảng so sánh "chuẩn".

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Trên MSI**: `probe_cam_fps.py --camera 0/1` (đo trần FPS webcam rời) → quyết có sửa
      `CameraVideoSource` cho Windows hay không.
- [ ] **Trên MSI**: baseline `mode=track` @192, 3 lần, lưu `status.json` + `drift_samples.csv`.
- [ ] **Dựng GT mask trên clip thật của MSI** (~10 clip × 100–200 frame) — điều kiện bắt buộc để
      chứng minh "tốt hơn". Hiện `data/` không có GT nào.
- [ ] Chạy **plan 3 ý kiến §9.2** trước khi code pooling 2×2 / selective propagation.
- [ ] Ticket riêng: port re-ID + re-anchor vào `src/live_tracking.py`.
- [ ] Kiểm lại OpenVINO iGPU trên **Windows native** (2 lệnh) — nếu thấy `GPU` thì mở lại hướng
      encoder chạy trên iGPU song song CPU.

## 📚 Tài liệu tham khảo
- `docs/plan/14-11-2026-toi-uu-bam-sat-tren-msi.md` — handoff chính của phiên này.
- EfficientTAM: arXiv 2411.18933 · số pooling từ blog TT Lab (`ttlab.hopto.org/blog/vision-foundations-10-sam2-efficienttam`, tác giả ghi "partial measurements").
- Selective Mask Propagation: `arxiv.gg/abs/2606.13033` (**preprint**, chưa bình duyệt).
- SAM 2.1 model card — bảng SA-V J&F chính thức.
- `AGENTS.md` §2 (log), §6 (số đã đo), §9.2 (plan 3 ý kiến).
