# Plan 14-11-2026 — Tối ưu bám sát trên MSI (máy demo), không mua phần cứng

> **File này là handoff context.** Phiên 14-11 bàn toàn bộ hướng "làm sao bám sát đúng đối tượng
> realtime trên MSI mà không train lại model", **chưa viết dòng code nào**. Ai (người hoặc agent)
> tiếp nhận việc này đọc file này TRƯỚC, rồi mới code.

## 🎯 Câu hỏi cần quyết

Làm sao để sản phẩm **bám sát đúng đối tượng, realtime, chạy hoàn toàn trên một thiết bị biên**
(MSI + webcam rời), **chi phí phần cứng ~0**, mà vẫn **chứng minh được là tốt hơn** trước hội đồng?

Ràng buộc không được vi phạm:
- Máy đích là **MSI Modern 14 B11MOU**: i7-1195G7 (Tiger Lake, có AVX-512 + AVX512-BF16), Iris Xe,
  16 GB, **không CUDA**, Windows + WSL2.
- **Mac mini M4 (máy công ty) chỉ để viết code + chạy làn test nhanh** — không phải máy demo, và
  **không được trích bất kỳ số ms/FPS nào đo trên Mac** (M4 dùng NEON, không có AVX-512 ⇒ cơ chế
  tăng tốc khác hẳn, số không chuyển được).
- GVHD yêu cầu "mọi thứ nằm trong camera" (biên) — đưa lên server bị chậm ⇒ **cấm** kiến trúc
  client-server cho inference.

## 🧾 Chốt với người dùng trong phiên này

| Việc | Quyết định | Lý do |
|---|---|---|
| ESP32-CAM làm thiết bị | ❌ **BỎ** | 240 MHz / 520 KB RAM + 4 MB PSRAM không nạp nổi checkpoint 156 MB. Nó chỉ là **mắt**, model vẫn chạy trên laptop ⇒ biến "biên" thành "client-server", lại đổi 30 FPS ổn định lấy 10–15 FPS WiFi chập chờn |
| Mua GPU / Jetson / Colab | ❌ **BỎ** | Colab **không truy cập được webcam USB** (ADR-0001 đã loại cloud cho live). Jetson 13–15 tr **chưa có số nào trong repo** |
| Train lại SAM 2 | ❌ **BỎ** | ADR-0001 chốt "không train lại"; không có GT mask nào trong `data/`; và lỗi bám đã đo được là do **code** (bbox `xywh`/`xyxy`) chứ không phải weights |
| Đổi backbone sang SAM 3.1 | ⏸ **HOÃN** | +~7 J&F và prompt bằng chữ, nhưng **mất SAMURAI motion memory** (dựng trên internals SAM 2 = mất 1 trong 3 trụ đề cương), realtime cần H100-class. Chỉ mở lại nếu 4 hướng dưới không đủ |
| Phần cứng demo | ✅ **Laptop MSI + webcam rời** | Về kiến trúc **đã là biên**. Chỉ nên mua **webcam 1080p30** (~1,5 tr) vì trần FPS hiện tại là webcam (16,6 FPS @640×480) |
| Thước đo "tốt hơn" | ✅ Cả 4, xếp hạng: **mIoU > tỉ lệ mất dấu > vos_fps/mask_age > nhìn bằng mắt** | mIoU là thước duy nhất chứng minh "phân đoạn tốt hơn"; "nhìn bằng mắt" chỉ dùng làm kiểm tra phụ |

## 📊 Baseline đã đo trên chính MSI (số phải dùng, không đoán lại)

**Profile từng tầng @`image_size 192`, tổng 127,7 ms** (`docs/task/08-11-2026-do-lai-do-phan-giai-va-kich-thuoc-model.md`):

| Tầng | ms | % |
|---|---|---|
| **image encoder** | **90,0** | **70 %** |
| memory_attention | 22,6 | 18 % |
| mask_decoder | 9,4 | 7 % |
| memory_encoder | 8,0 | 6 % |

⇒ **Hệ quả định hình toàn bộ plan:** cắt sạch 30 % phía sau chỉ được ~30 ms. Muốn giảm nhiều phải
tấn công **encoder** hoặc **giảm số lần gọi model**.

Các số nền khác (cùng máy):
- `192` ⇒ 97 ms/frame (10,3 FPS) khi đo 8 frame; **120 ms (8,35 FPS)** khi bật re-ID vật thể, 60 frame, mất dấu 0/60.
- Hybrid VOS+LK: **hiển thị 29,9 FPS**, **mask 8,6 lần/giây** — cấm claim "mask 30 FPS".
- LK optical flow **3,19 ms** dưới tải; MIL 51,05 ms; KCF/CSRT **đã bị bỏ khỏi OpenCV 5.0 pip**.
- Trần thật của máy này cho lớp AI: **~18–22 FPS** (thay encoder + nén memory @160) — `docs/research/08`.
- Webcam laptop: **16,6 FPS @640×480**, chỉ **10 FPS @720p**. Relay `/snapshot.jpg`: **2,6 ms/frame**.
- GPU tham chiếu (Colab T4, `image_size 512`): **49,6 ms = 20,15 FPS**.

## 🚫 Đã bị bác — có số, ĐỪNG đề xuất lại

| Thử | Số bác |
|---|---|
| INT8 ONNX cho encoder | **196 ms vs 166 ms** PyTorch @320 — INT8 **chậm hơn** |
| Dùng lại đặc trưng encoder K frame | K=2: 13,3 FPS nhưng IoU 0,966→**0,840**; K=4: IoU **0,667** |
| Checkpoint to hơn (small/base+/large) | @256: 184 → 241 / 585 / 754 ms = chậm **1,3× / 3,2× / 4,1×**, không cải thiện detect |
| Tracker nhẹ khác | MIL 51 ms; KCF/CSRT không còn trong OpenCV 5.0 pip |
| **EfficientTAM làm model chính** | SA-V J&F: Ti **70,7**, S **74,5** vs SAM 2.1 tiny **76,5** ⇒ **kém chính xác hơn**; mobile 261–1011 ms/frame @1024². **Chỉ mượn kỹ thuật, không đổi model** |
| `--reanchor-every` | Pipeline tự tắt khi bật re-ID (đã đo) |
| Hạ `num_maskmem` rồi **mặc định** bật | Không có số bác, nhưng memory dài hạn chính là thứ đề cương cần cho che khuất ⇒ phải đo, không được mặc định |

## 🔬 Sáu hướng còn lại — xếp theo lợi ích / rủi ro

| # | Hướng | Bằng chứng | Chi phí | Rủi ro |
|---|---|---|---|---|
| **1** | **bf16 trên CPU** (`torch.autocast("cpu", bfloat16)` bọc encoder) | Tiger Lake **có** AVX512-BF16. **Không có số công bố cho CPU client** (mọi blog IPEX là Xeon/AMX) ⇒ phải đo | **30 phút** | Rất thấp |
| **2** | Đo **`num_maskmem` 3 / 5 / 7** | Chưa có ablation công bố cho SAM 2 ⇒ phải đo | 15 phút | Cao về chất lượng |
| **3** | **Pooling 2×2 trên memory attention** (mượn từ EfficientTAM) | Đo trên **laptop CPU: 29,2 → 8,4 ms** khi keys 4096→1024. Áp vào `memory_attention` (22,6 ms) ⇒ ước ~7–9 ms | 2–3 ngày | Trung bình: relative error **0,05** khi memory "mượt" nhưng **0,753** khi memory thô |
| **4** | **Selective mask propagation** — gọi VOS theo *tín hiệu bất định* thay vì `vos_every=3` cố định | Holmberg, *preprint* 2026 (`arxiv.gg/abs/2606.13033`): "dispatch sang VOS chỉ trên cửa sổ mà tín hiệu bất định bắn", training-free, black-box. **Chưa bình duyệt**, không có số CPU | 3–5 ngày | Trung bình (phải tự chọn ngưỡng) |
| **5** | **RepViT encoder (EdgeTAM)** | **Đã đo trên MSI: 35,6 vs 90,0 ms @192 = nhanh 2,5×** (34,7/50,9 @160/256) | 3–5 ngày | **J&F 72,3 vs 76,8 = mất 4,5 điểm** |
| **6** | ROI-crop inference (encoder trên crop quanh vật) | Không tìm được tiền lệ cho SAM 2 | 3–5 ngày | **Cao** — memory bank lưu feature toàn khung, đổi hệ toạ độ dễ vỡ memory attention |

**Hướng #1–#2 làm được ngay, không rủi ro. #3–#4 là nơi có lợi ích thật. #5 là đánh đổi có kiểm
soát. #6 không nên làm trước.**

## ✅ Quyết định

- **Chọn:** thứ tự **1 → 2 → 3 → 4**, chỉ cân nhắc **5** nếu 1–4 không đủ, **không làm 6**.
- **Vì sao:** #1/#2 rẻ (45 phút tổng) và có thể cho không; #3 tiết kiệm ~14 ms (11 %) với kỹ thuật
  **đã có số đo trên laptop CPU**; #4 là hướng duy nhất **vừa nhanh hơn vừa chính xác hơn** đồng
  thời tạo **đóng góp thật** cho báo cáo (không phải "dùng lại paper").
- **Bác:** đổi model to hơn / INT8 / encoder-reuse / EfficientTAM-as-model / ESP32-CAM / Colab —
  xem hai bảng trên, mỗi cái có số hoặc lý do kiến trúc.
- **Tiêu chí nghiệm thu (có SỐ):**
  - [ ] `mIoU` mask vs **GT clip thật của MSI** ≥ baseline, chênh lệch **lặp lại qua 3 lần chạy**
  - [ ] `empty_runs` / `lost_streak` **giảm** so baseline, cùng clip + cùng cấu hình, 3 lần
  - [ ] `vos_fps` ≥ **11** (baseline 8,5) và `mask_age_p95` ≤ **200 ms** (baseline 210–250 ms)
  - [ ] Mọi artifact có `git_rev` + `git_dirty_code` + `lenh` + `do_luc`

## ⚠️ Việc PHẢI làm trước khi code #3/#4 (chưa làm)

1. **Dựng GT mask trên clip thật của MSI** (~10 clip ngắn × 100–200 frame, bootstrap bằng chính
   SAM 2 rồi sửa tay). **Hiện `data/` không có file GT mask nào** ⇒ chưa chứng minh được "tốt hơn".
2. **Chạy vòng 3 ý kiến độc lập + 1 vòng phản biện** theo AGENTS.md §9.2 trước khi code #3 và #4
   (đây là việc > 4 giờ và đổi kiến trúc đường live). Phiên 14-11 **chưa chạy vòng này** — plan này
   chỉ là tổng hợp 1 phiên, **không thay thế** bước §9.2.
3. **Baseline live trên webcam rời thật** — hiện mọi số live là của webcam laptop qua relay.

## 📌 Việc tách ra ticket

- [ ] **Lỗ hổng lớn nhất của đường live:** `src/live_tracking.py` **không có re-ID và không có
      re-anchor** (`rg reid|reanchor src/live_tracking.py tools/live_worker.py` → 0 kết quả), trong
      khi đường job `tools/run_live.py` có đủ. Vật bị che là mất, có thể bám sang vật khác.
      Đây là lỗi **người xem nhận ra ngay** ⇒ ưu tiên cao hơn cả #1–#2.
- [ ] `src/video_source.py:132-140` — `CameraVideoSource` chỉ ép `MJPG + 640×480` **khi Linux**.
      Trên Windows không set gì ⇒ OpenCV dễ rơi vào **YUY2** (tốn băng thông USB gấp đôi, thường
      5–10 FPS). **Chỉ sửa sau khi `probe_cam_fps.py` trên MSI chứng minh YUY2 chậm hơn MJPG.**
- [ ] `scripts/probe_cam_fps.py` hardcode `cv2.CAP_DSHOW` (Windows-only) — không chạy được trên Mac.
- [ ] OpenVINO iGPU: repo ghi "chỉ thấy device `CPU`", nhưng lần đo đó chạy trong **WSL** (WSL2
      thường không expose Iris Xe). Chưa thử trên **Windows native** — 2 lệnh để biết:
      `python -c "import openvino as ov; print(ov.Core().available_devices)"`. Nếu ra `['CPU','GPU']`
      mới mở lại hướng "encoder trên iGPU song song CPU".

## 📚 Tham chiếu

- `docs/task/08-11-2026-do-lai-do-phan-giai-va-kich-thuoc-model.md` — sweep checkpoint + độ phân giải + profile từng tầng.
- `docs/research/08-real-time-25fps-tren-cpu-igpu.md`, `09-kien-truc-hybrid-vos-cham-tracker-nhe-30fps.md`, `11-do-encoder-repvit-tren-cpu-va-tran-realtime.md`.
- `docs/task/08-11-2026-hybrid-vos-lk-live-30fps.md` — kiến trúc hybrid đang chạy.
- `docs/adr/0001-sam2-samurai-backbone-tu-toi-uu-realtime.md`, `0002-giu-laptop-cpu-demo-live-colab-cho-offline.md`.
- `AGENTS.md` §6 (bảng số đã đo), §9.1 (review độc lập), §9.2 (plan 3 ý kiến).
- Nguồn ngoài (chất lượng khác nhau, ghi rõ khi trích):
  - Selective Mask Propagation — Holmberg, **preprint** 2026, `arxiv.gg/abs/2606.13033` → *chưa bình duyệt*.
  - EfficientTAM — arXiv 2411.18933; số pooling 29,2→8,4 ms lấy từ **blog TT Lab** (`ttlab.hopto.org`), đo trên laptop CPU, tác giả tự ghi là "partial measurements".
  - SAM 2.1 tiny SA-V J&F **76,5** — bảng chính thức trong model card SAM 2.1.
