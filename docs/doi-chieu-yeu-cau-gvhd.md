# Đối chiếu 12 yêu cầu của GVHD ↔ hệ thống đã xây (bằng chứng + số đo)

> File này là **phụ lục báo cáo**: mỗi yêu cầu trong bảng "Yêu cầu thực hiện của sinh viên" (GVHD giao)
> được trả lời bằng *file cụ thể* + *số đo cụ thể*, không bằng lời khẳng định.
> Cập nhật lần cuối: **18-11-2026** (đính chính `drift_iou` theo ô chọn đúng) (thêm web/API, live hybrid 30 FPS HUD, drift, mIoU fixture,
> watchdog, H.264 — mỗi số trỏ đúng artifact). Chạy lại toàn bộ số trong file: xem mục "Cách tái tạo số liệu".
>
> Ký hiệu: ✅ xong có bằng chứng · 🟡 xong phần chính, còn thiếu số đo trên dữ liệu thật · ❌ thiếu

| # | Yêu cầu GVHD | Bằng chứng trong repo | Trạng thái |
|---|---|---|---|
| 1 | **Tiếp nhận đề tài**: mục tiêu, phạm vi, chức năng, kế hoạch | `docs/DoAnCameraAI.docx` (đề cương gốc) · `.scratch/camera-ai-realtime/spec.md` (27 user story + quyết định) · `docs/adr/0001`, `0002` · 13 ticket trong `.scratch/.../issues/` · log 16-10 (`to-spec`, `to-tickets`) | ✅ (USB/IP **trực tiếp** trong WSL còn kẹt driver `usbipd` — đường demo là relay HTTP, xem AGENTS §6) |
| 2 | **Nghiên cứu tổng quan** Camera AI + phương pháp phát hiện/phân đoạn/bám bắt | `docs/research/01…07c` (**10 báo cáo**, mỗi kết luận có nguồn đọc trực tiếp license/paper) · `docs/giai-thich-do-an.md` (từ điển thuật ngữ cho người mới) · `docs/research/02` (cơ sở lý thuyết SAM 2 + SAMURAI) | ✅ |
| 3 | **Thiết kế kiến trúc**: luồng xử lý video, thành phần AI, phần cứng camera, giao diện | `README.md` (sơ đồ 6 module) · `spec.md` §Implementation Decisions · `src/video_source.py` (4 nguồn) · `scripts/usbipd_helper.py` + `docs/cheatsheet-lenh.md` §usbipd (gắn webcam USB vào WSL) · `tools/find_phone_camera.py` (cam IP qua LAN) · **web 2 tầng**: `src/api/` (ports & adapters, ADR-0005) + `web/src/` (React) | 🟡 thiếu **sơ đồ khối + bảng phần cứng** vẽ cho báo cáo (hiện chỉ có ASCII) |
| 4 | **Thu nhận & xử lý video** (USB/IP) bằng Python + OpenCV, real-time | `src/video_source.py` (webcam index / RTSP / video file / **thư mục ảnh**) · `src/smooth_display.py` (thread đọc camera → hiển thị không nghẽn) · **camera THẬT qua relay HTTP Windows→WSL** (`scripts/cam_relay.sh`): đo 10-11 `state=running`, 681 frame đổi nội dung/25 s, HUD **30.1 FPS**, mask **6.6–8.4 lần/giây (cao nhất 8.4)** (`data/live_web_relay_2026-11-10_metrics.json`) · test: `test_video_source.py`, `test_frames_source.py`, `test_smooth_display.py`, `test_usbipd_helper.py`, `test_find_phone_camera.py` | ✅ (USB/IP **trực tiếp** trong WSL còn kẹt driver `usbipd` "Device busy" — đường demo là relay HTTP, xem AGENTS §6) |
| 5 | **Phân đoạn đối tượng** (Segmentation Mask) | `src/tracker_engine.py` bọc SAM 2.1 tiny (config SAMURAI) streaming per-frame, ticket 02 · đo **IoU 0,974** trên fixture (đáp án biết trước) · mask bool cùng kích thước frame, ô bao + điểm tin cậy mỗi frame · **mIoU mask vs GT** trên fixture tổng hợp: **0,956** (không che) / **0,892** (che 50 %) / `null` khi che kín (`data/occlusion_metrics_320_metrics.json` — **cận trên**, GT là hình giải tích) | 🟡 chất lượng trên **ảnh thật có nhãn** chưa đo (chưa có dữ liệu gán nhãn — ADR-0002 ghi đúng như vậy) |
| 6 | **Lựa chọn & bám bắt**: chọn đối tượng, vị trí, vùng phân đoạn, **duy trì định danh** | `src/prompt_selector.py` (kéo chuột chọn, `r` chọn lại — ticket 05) · `src/reid.py` máy trạng thái `tracking→lost→reacquiring` (ADR-0003) + cue vật thể (ADR-0004) · đo: 17/17 ca nhận lại đúng trong `data/reid_2clip_calib.json` · **chọn đối tượng trên WEB** (kéo chuột trong `LivePanel`) phủ bằng e2e Playwright (`./run e2e` PASS, kiểm đúng bbox gửi đi) | 🟡 thiếu **clip 2 người** để đo tỉ lệ nhận-lại-đúng/nhầm của cue mặt (ticket 09) |
| 7 | **Motion Memory**: lưu vị trí, đặc trưng, lịch sử chuyển động | Dùng **nguyên bản** memory bank + Kalman của SAMURAI (`docs/research/01`,`02`; ADR-0001) · phần tự viết quanh nó: `src/identity_guard.py` (phát hiện ô bao nhảy > 25 % đường chéo) + tự phục hồi trong `src/reid.py` (`_is_suspicious_jump` → reset engine, giữ ký ức vật) · độ trễ tăng theo bộ nhớ: đo 366 ms @213 frame (`data/smooth_summary.json`) | 🟡 **rủi ro khi bảo vệ**: chưa có "lịch sử chuyển động" do đồ án tự xây. Cần bàn GVHD nếu muốn tách thành module riêng (quỹ đạo + dự đoán vị trí) |
| 8 | **Temporal Propagation** + giữ bám khi che khuất/biến dạng | streaming per-frame (ticket 02) · `scripts/experiment_occlusion.py` che 0→100 % → đo IoU từng khung + số khung mất dấu · test `test_experiment_occlusion.py` | ✅ (trên fixture; cảnh thật: cần clip che khuất do người dùng quay) |
| 9 | **Tích hợp** 3 thành phần + xử lý **mất dấu** + **tái nhận diện** | `src/reid.py` 3 cổng chống "bám nhầm nền rồi kẹt" (ticket 13): `lost_score_threshold`, xác nhận 2 frame, kiểm chứng 2 frame · đo: ca bám nhầm nền (mask 782 px, score +19,40 giả) bị loại, khung 19 bám lại đúng với `reid=0,94` · ngưỡng hiệu chỉnh bằng 2 clip thật (`data/reid_2clip_calib.json`) | ✅ |
| 10 | **Tối ưu real-time** + đánh giá **FPS, độ trễ, CPU/GPU, độ chính xác** | **live hybrid VOS+LK** (worker riêng + Lucas–Kanade): HUD **30.1 FPS**, mask **6.6–8.4 lần/giây (cao nhất 8.4)**, tuổi dữ liệu ảnh p95 **210 ms** (clip `binh1`, `data/drift_2026-11-08_metrics.json`); **độ tự nhất quán ô bao** `drift_iou` **0,49–0,50** (binh1, **ô chai**, chỉ trong khung vật có mặt) và **0,726** (binh2, khung `0:160`, mask rỗng 0 %) — số cũ 0,885–0,889 / 0,528 đo bằng **ô khuôn mặt/ô sai**, xem đính chính dưới bảng; **độ chính xác** (tiêu chí này hỏi) = **mIoU mask vs GT**: **0,6464** (12 frame video thật, GT **hộp bao** — không phải phân đoạn) và **0,9354 / 0,892** (fixture tổng hợp = **cận trên**), `docs/so-lieu-bao-cao.md`; **watchdog**: worker chết ⇒ API `error` sau **116–117 ms** (`data/watchdog_2026-11-09_metrics.json`), nguồn camera mất frame ⇒ **3,75 s** (`data/watchdog_raw_2026-11-09_metrics.json`) · `src/metrics_logger.py` (CSV từng frame + summary mean/p95/FPS/tỉ lệ mất dấu) · **`src/resource_usage.py` (mới 02-11)**: CPU %, RAM, GPU (đo thật: **CPU 342 % ≈ 43 % máy 8 lõi, RAM đỉnh 632 MB**, không GPU — `data/res_1102_summary.json`) · tối ưu: `image_size` 1024→256 (`docs/research/03`,`05`), `--reanchor-every`, thread đọc camera | ✅ (GPU: chỉ có số trên Colab, xem `docs/colab-gpu.md`) |
| 11 | **Tích hợp, kiểm thử, hoàn thiện UI** + kiểm thử **chuyển động / che khuất / ánh sáng** | UI: `src/visualizer.py` (mask alpha + ô bao + quỹ đạo + HUD tiếng Việt + banner MẤT DẤU) · **UI web**: `web/src/components/LivePanel.tsx` (chọn ô, phát MJPEG, dòng "nhịp mask" nói rõ FPS phát ≠ nhịp mask) + `./run e2e` **PASS** trên Chrome/Edge thật (23 kiểm, gồm "trình duyệt GIẢI MÃ được video kết quả H.264") · **video demo xuất H.264** phát được trên web (`tools/run_live.py` + `src/worker/web_export.py`) · chuyển động: fixture ô vuông (`src/synthetic_video.py`) · che khuất: `experiment_occlusion` · **ánh sáng (mới 02-11)**: `scripts/experiment_lighting.py` → đo thật 5 mức sáng, **IoU 0,974 → 0,942**, 0/12 khung mất dấu (`data/lighting_iou_320_summary.json`) | ✅ (ánh sáng: fixture tổng hợp, độ tương phản cao — cần clip thật để kết luận về cảnh thật) |
| 12 | **Báo cáo: tổng quan + cơ sở lý thuyết** | `docs/tom-tat-do-an.md` (bản tóm tắt có số) · `docs/research/02` (lý thuyết SAM 2/SAMURAI), `docs/research/04` (giải thích cho người mới + dàn ý báo cáo) · `docs/adr/0001…0004` (quyết định + lý do) · `docs/team-contribution.md` (phần nào tự làm) · **44 file log** trong `docs/task/` (tính đến 09-11-2026) | 🟡 nội dung đủ, **chưa ghép thành file báo cáo theo mẫu của trường** |

## Số liệu dùng được ngay trong báo cáo

| Đại lượng (yêu cầu 10) | Số đo | Nguồn |
|---|---|---|
| FPS / độ trễ (CPU, `image_size` 1024 mặc định) | **0,20 FPS** (5047 ms/frame) | `data/gui_summary.json` |
| FPS / độ trễ (`image_size` 320, 6 frame, clip thật) | **4,18 FPS** (mean 240 ms, p95 312 ms) | `data/res_1102_summary.json` |
| FPS / độ trễ (`image_size` 256, webcam) | **4,6–5,4 FPS** (186–218 ms) | `data/fast_1101-*_summary.json` |
| FPS trên GPU Colab (T4) | **9,9 FPS** (101 ms) | `data/gpu_summary.json` |
| Mức sử dụng CPU | **342 % của 1 lõi ≈ 43 % máy 8 lõi** (đỉnh 390 %) | `data/res_1102_summary.json` → `resources` |
| Mức sử dụng RAM | **620,7 MB** trung bình, **632,3 MB** đỉnh | nt. |
| Mức sử dụng GPU | không có GPU NVIDIA trên máy demo (trường `gpu: null`) — số GPU: `docs/colab-gpu.md` | nt. |
| Độ chính xác bám bắt (IoU vs đáp án) | **0,974** (ánh sáng gốc), **0,942** (tối 90 %) | `data/lighting_iou_320_summary.json` |
| Độ ổn định: nhận lại đúng | **17/17** ca đúng được giữ, 1 ca sai bị cổng NCC 0,35 chặn | `data/reid_2clip_calib.json` |
| Chi phí tìm lại khi mất dấu | **845 ms → 23,8 ms** (cascade NCC, nhanh ~35×) | `docs/task/27-10-2026-*.md` |
| **Live hybrid**: FPS phát / nhịp mask / tuổi dữ liệu ảnh p95 | **29,9 FPS** / **8,6–8,7 lần/giây** / **210 ms** (clip `binh1`, `vos_every 3`, `image_size 192`) | `data/drift_2026-11-08_metrics.json` |
| **Độ tự nhất quán ô bao** (`drift_iou`) — **ô CHAI, chỉ trong khung vật có mặt** | `binh1` **0,49–0,50** (đo 4 lần) · `binh2` **0,726** (khung `0:160`, mask rỗng **0,0 %`) | `data/chu_ky_chai_binh1_1vong_lan{1,2,3}_metrics.json`, `data/sach_chai_binh1_1vong_metrics.json`, `data/sach_chai_binh2_1vong_metrics.json` (`git_dirty_code false`) — **KHÔNG phải độ chính xác** (AGENTS §6) |
| **mIoU mask vs GT** (fixture tổng hợp, cận trên) | **0,956** / **0,892** khi che 50 % / `null` khi che kín | `data/occlusion_metrics_320_metrics.json` |
| **Camera THẬT** (relay Windows→WSL): HUD FPS / mask / drift p05 | **30.1** / **6.6–8.4** lần/giây / **0.933** (`drift_n` 171), tuổi dữ liệu p95 **281.6 ms** (`age_n` 200) | `data/live_web_relay_2026-11-10_metrics.json` |
| **Watchdog** phát hiện nguồn chết | worker `kill -9`: **116–117 ms** (bắt bằng `proc.poll()`) · nguồn kiểu **`raw`** mất frame: **3,75 s** (relay ảnh JPEG **localhost**; **chưa đo trên webcam/RTSP thật** — `moi_truong` của artifact) | `data/watchdog_2026-11-09_metrics.json`, `data/watchdog_raw_2026-11-09_metrics.json` |
> ⚠ **`p95`/`mean` độ trễ trong bảng trên đo bằng code TRƯỚC 17-11** (ticket #32): artifact **không có**
> field `p95_latency_ms_n`/`mean_latency_ms_n`. Cỡ mẫu vẫn suy được: `n = total_frames − frozen_frames` ⇒
> **6** (`res_1102`) · **25** (`camtest`) · **52** (`demoip_1104-212328`) · **22** (`fast_1101-153223`) ·
> **15** (`gui`). Với `n = 6` thì `p95` gần **max** (res_1102: p95 312 ms, max 340,4, mẫu 225,2) — nên
> đọc là "p95 của 6 frame", **không** phải phân vị đáng tin.
> ⚠ **ĐÍNH CHÍNH 14-11 cho `drift_iou` (đọc trước khi trích)**: các số **0,887 / 0,873 / 0,528 (p05 0,000)**
> lưu hành trước đây đo bằng **ô KHUÔN MẶT** (`binh1`) và ô phủ **2 chai + 2 tay** (`binh2`) — không phải
> ô chai, nên **không** dùng để nói "bám chai tốt/xấu". Ô chai đúng (`docs/demo-clip-va-o-chon.md`):
> `binh1` `300,275,150,410` (khung `0:110` ∪ `165:262`), `binh2` `330,330,150,360` (khung `0:160`) ⇒
> `drift_iou` **0,49–0,50** (`binh1`) và **0,726** (`binh2`), `empty_frac` **trong khung** **1,6–3,3 %** và
> **0,0 %** — nguồn: `data/chu_ky_chai_binh1_1vong_lan{1,2,3}_metrics.json`,
> `data/sach_chai_binh1_1vong_metrics.json`, `data/sach_chai_binh2_1vong_metrics.json`
> (`git_dirty_code = false`; bộ đo 55 s cho số hơi khác: `binh1` 0,475–0,484 · `binh2` 0,702–0,721 —
> chênh giữa hai phiên, xem AGENTS §6). Còn **cả phiên** thì `binh1` rỗng **35,2 %** (`37/105` lần VOS) và
> `binh2` **19,1 %** (`22/115`) — vì chai **rời khung** ở những đoạn ngoài khung, **không phải** model mất
> dấu; đây là lý do phải có `--frame-window`.
> **Đuôi xấu phải nói ra**: ngay **trong** khung `binh1`, **7/60 mẫu (11,7 %) có `drift_iou = 0`** (frame
> 57/69/72/105/108/171/255) — ba mẫu đầu nằm **giữa** khung, ô bao trôi lên mép chai/ra ngoài
> (`94,0,247,435` · `239,0,375,439` · `340,0,478,443`) ⇒ **LK lệch khỏi vật thật**, không phải "chuyển
> tiếp lúc vật rời khung". Vì thế `p05` trong khung của `binh1` = **0,000** với `n = 60 ≥ 30` (ngưỡng 30
> mẫu **không** chặn) — **cấm** trích `p05` đó như "ổn định"; `binh2` trong khung có `p05 ≈ 0,275`. `drift_iou` vẫn chỉ là **tự nhất quán**, không phải độ chính xác — độ chính
> xác chỉ có mIoU mask vs GT.
> ⚠ **Provenance của các artifact trong bảng (rà 18-11)**: 14 file được trích, và **5 file không có
> `git_rev` truy được** — `data/res_1102_summary.json`, `data/gui_summary.json`,
> `data/lighting_iou_320_summary.json`, `data/smooth_summary.json`, `data/reid_2clip_calib.json` (sinh
> trước khi có quy ước provenance, **không có** trường `git_rev`), cộng `data/drift_2026-11-08_metrics.json`
> (trường `git_rev` là chuỗi 40 ký tự **gõ sai**, commit thật là `ee9f25672d72`) và
> `data/live_web_relay_2026-11-10_metrics.json` (rev chỉ còn ở object local — nhánh rebase trước khi push).
> ⇒ Số trong bảng **vẫn là số đo thật**, dùng được khi trích **kèm tên file**; nhưng **không** được nói
> "tái lập được từ `git_rev`" cho 7 file đó, và **cấm dẫn rev** của hai file cuối. Kiểm lại bằng
> `./run provcheck`.
> Từ 17-11: **`*_summary.json`** của `metrics_logger` có thêm `p95_latency_ms_n` (và `mean_latency_ms_n`);
> `p95` trả **`None`** khi `n = 0`, còn `mean` **vẫn** `0,0` (vì `effective_fps = 1000/mean` là hợp đồng
> cũ) — đọc kèm `_n`, `n == 0` = **chưa đo**, không phải "0 ms".


## Việc còn thiếu (nói thẳng, không giấu)

1. **Clip thật** cho 3 phép đo: 2 người (cue mặt), chai đen (chốt `reid_obj_ncc_min`), vật rời khung rồi vào lại.
   (Ảnh camera thật qua relay **đã có** — `data/live_web_relay_2026-11-10_metrics.json`; còn thiếu *clip*
   có vật bị che để đo drift khi che.)
   → Chỉ người dùng quay được; code đã sẵn sàng (`./run fast --reid-cue face|object`, `scripts/calibrate_reid.py`).
2. **Nhãn phân đoạn trên ảnh thật** để có mIoU thật (hiện chỉ có mIoU trên fixture + IoU bbox).
3. **Sơ đồ khối + bảng phần cứng** (yêu cầu 3) và **ghép báo cáo theo mẫu trường** (yêu cầu 12).
4. **Motion Memory tự xây** (yêu cầu 7) — cần chốt với GVHD phạm vi trước khi làm, vì chạm vào lõi backbone.

## Cách tái tạo số liệu

```bash
./run test                                   # 706 test làn nhanh (~58 s), không cần checkpoint
./run testall                                # 711 test trong checkout CHÍNH (có checkpoint SAM 2, ~180 s);
                                             # thiếu checkpoint ⇒ 5 test đó `skip` (706 passed, 5 skipped)
./run webtest && ./run e2e                   # 24 test vitest + e2e Playwright trên Chrome/Edge thật
python scripts/measure_live_relay.py --source "$(bash scripts/cam_relay.sh snapurl)" \
    --bbox 110,35,95,110 --image-size 192 --vos-every 3 --seconds 25   # bằng chứng camera THẬT
./run lint                                   # ruff check .
./run light 12                               # thí nghiệm ánh sáng → data/lighting_iou_320_summary.json + biểu đồ
./run occl 30                                # thí nghiệm che khuất
.venv/bin/python -m tools.run_live --source data/binh1.mp4 --max-frames 6 --image-size 320 \
    --metrics-csv data/res_1102_metrics.csv --metrics-summary data/res_1102_summary.json
./run summary                                # bảng mọi *_summary.json kèm CPU/RAM
```
