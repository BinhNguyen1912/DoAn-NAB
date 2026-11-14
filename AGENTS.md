# AGENTS.md — Hướng dẫn cho AI Agent làm việc trong repo này

> File này là **quy ước bắt buộc** cho mọi AI agent (và contributor) khi làm việc trong repo `DoAn-NAB`.
> Đọc kỹ trước khi thực hiện bất kỳ thay đổi nào.

---

## 1. Tổng quan dự án

- **Tên đề tài:** Xây dựng hệ thống Camera AI bám bắt đối tượng theo thời gian thực.
- **Nội dung cốt lõi:** Nhận diện, phân đoạn và bám bắt đối tượng trong video real-time dựa trên:
  - **Image Segmentation** (phân đoạn ảnh)
  - **Motion Memory** (bộ nhớ chuyển động)
  - **Temporal Propagation** (lan truyền theo thời gian)
- **Yêu cầu sản phẩm cuối kỳ:**
  1. Thu nhận & xử lý video trực tiếp (Camera USB/IP).
  2. Cho phép người dùng **lựa chọn đối tượng** cần bám bắt.
  3. Phân đoạn & theo dõi đối tượng dựa trên **Segmentation Mask**.
  4. Tích hợp **Motion Memory** + **Temporal Propagation** (chịu được che khuất/biến dạng).
  5. Hiển thị vị trí, vùng phân đoạn, **quỹ đạo di chuyển** theo thời gian thực.
  6. Đánh giá hiệu năng: **FPS, độ trễ, chất lượng phân đoạn, độ ổn định bám bắt**.
- **Định hướng kỹ thuật:** Tham khảo các mô hình VOS như **SAM 2**, **SAMURAI**, **XMem**; stack chính **Python + OpenCV**.
- Tài liệu đề tài gốc: `docs/DoAnCameraAI.docx`.

---

## 2. ⚠️ QUY TẮC BẮT BUỘC: Ghi log công việc hằng ngày

**Sau MỖI phiên làm việc có thay đổi code/tài liệu, agent PHẢI tạo file log** để sinh viên dùng viết báo cáo sau này.

### 2.1. Vị trí & đặt tên

- Thư mục: `docs/task/`
- Đặt tên file: `DD-MM-YYYY-ten-cong-viec.md`
  - Ví dụ: `16-10-2026-setup-repo-va-video-capture.md`
  - Tên công việc: tiếng Việt không dấu hoặc tiếng Anh, nối bằng gạch ngang, viết thường.
- Nếu trong ngày có nhiều việc riêng biệt → có thể tạo nhiều file, hoặc 1 file tổng hợp cho cả ngày (ưu tiên 1 file/ngày nếu các việc liên quan nhau).

### 2.2. Template bắt buộc

Mỗi file log PHẢI theo đúng cấu trúc trong **`docs/task/_template.md`** (đọc file đó rồi copy làm khuôn — 7 mục: Mục tiêu, Input, Công việc đã thực hiện, Output/Kết quả, Vấn đề & cách xử lý, Next steps, Tài liệu tham khảo).

### 2.3. Nguyên tắc ghi log

- Ghi **trung thực, đủ chi tiết** để sau này chép vào báo cáo (mục "Quá trình thực hiện").
- Luôn ghi rõ **Input → Xử lý → Output**.
- Có số liệu đo lường (FPS, latency, mIoU...) thì PHẢI ghi kèm.
- Không xóa/sửa log ngày cũ trừ khi được yêu cầu.

---

## 3. Cấu trúc thư mục repo

```
DOAN-NAB/
├── AGENTS.md              # File này — quy ước cho agent
├── CODING_STANDARDS.md    # Chuẩn code chi tiết (đọc khi review)
├── README.md              # Giới thiệu dự án + cài đặt từ clone mới
├── docs/
│   ├── DoAnCameraAI.docx  # Đề cương đề tài gốc
│   ├── adr/               # Quyết định kiến trúc (0001…0005)
│   ├── agents/            # Cấu hình skill (issue-tracker, triage-labels, domain)
│   ├── plan/              # 📁 Plan việc lớn: 3 ý kiến + tranh luận + quyết định + _template.md
│   ├── samurai-setup.md   # Cơ chế hydra/checkpoint upstream (navigation)
│   └── task/              # 📁 Log công việc theo ngày (BẮT BUỘC) + _template.md
├── src/                   # Source code chính của hệ thống
│   ├── api/               # Backend FastAPI theo ports & adapters (ADR-0005) → chạy VPS
│   │   ├── domain.py      # JobState/Job/JobStatus + quy tắc + lỗi miền (không I/O)
│   │   ├── ports.py       # Protocol: JobStore / PipelineRunner / VideoProbe
│   │   ├── service.py     # JobService — use case, chỉ phụ thuộc port
│   │   ├── adapters/      # FileSystemJobStore, SubprocessPipelineRunner, Cv2VideoProbe
│   │   ├── routes.py      # HTTP mỏng: parse → service → DTO
│   │   └── main.py        # create_app() = composition root
│   ├── worker/            # command (dựng lệnh) · artifacts (đọc kết quả) · process (subprocess)
│   └── *.py               # Pipeline lõi: tracker_engine, live_pipeline, reid, metrics_logger...
├── web/                   # Frontend React + Vite: api.ts · hooks/ · components/ · App.tsx
├── tools/                 # CLI chạy (run_live.py), benchmark, demo
├── tests/                 # pytest (fixture synthetic, không commit dữ liệu nặng)
├── configs/               # Cấu hình (default.yaml — checkpoint/nguồn/ghi/metrics)
├── data/                  # Dữ liệu test (video mẫu...) — KHÔNG commit file nặng
├── models/                # Model weights / link tải model
├── requirements.txt       # Dependencies Python
├── ruff.toml              # Rule lint đã ghim tại repo
├── pytest.ini             # Marker slow + --timeout=120
└── .github/workflows/     # CI: ruff + pytest làn nhanh
```

> Khi tạo module mới, đặt đúng thư mục theo cấu trúc trên; nếu cần thư mục mới, cập nhật lại mục này trong `AGENTS.md`.

---

## 4. Quy ước code

- **Ngôn ngữ:** Python 3.10+.
- Chuẩn chi tiết (ngôn ngữ comment, UI phải test headless được, quy tắc test): **`CODING_STANDARDS.md`** — đọc khi review và khi thêm module mới.
- Kiểm tra cơ học bằng `ruff` (`ruff.toml`) — import/biến thừa, tên chưa định nghĩa — không tự sửa tay khi `ruff check .` báo được.
- Không commit model weights/video nặng — `.gitignore` đã chặn.

---

## 5. Quy trình làm việc của agent trong mỗi phiên

1. Đọc yêu cầu từ người dùng + xem lại `docs/task/` gần nhất để nắm tiến độ. **Với việc liên quan
   hiệu năng / webcam / re-ID: đọc thêm AGENTS.md mục 6 trước khi sửa** (đó là các kết luận đã đo,
   tránh làm lại việc đã bị bác bỏ).
2. Thực hiện code/thay đổi. Việc lớn (> ~4 giờ, đổi kiến trúc/model/thuật toán) phải lập plan theo
   **mục 9.2** (3 ý kiến tranh luận) trước khi code.
3. **Review độc lập trước khi merge** theo **mục 9.1** (agent khác, không phải agent vừa code).
4. Chạy kiểm tra trước khi kết thúc bằng **lệnh tắt của repo** (`run` tự chọn đúng môi trường Python):
   - **Lint:** `./run lint` — CI chạy đúng lệnh `ruff check .`; phải xanh.
   - **Làn nhanh** (UI/logic/config — ~30s): `./run test` — CI chạy `pytest -m "not slow"`.
   - **Full suite** (cần checkpoint SAM 2): `./run testall` — chỉ khi đụng
     `tracker_engine`/model/CLI model hoặc trước commit cuối.
   - **Frontend:** `./run webtest` (vitest, hàm thuần) khi sửa `web/src/**`.
   - **E2E trình duyệt thật** (Chrome/Edge + Playwright, cần Windows): `./run e2e` — bắt buộc trước khi
     báo "xong" cho bất kỳ thay đổi nào ở UI/API (nó đã bắt được 3 bug thật ngày 08-11: canvas
     300×150, codec mp4v không phát được, và job báo `done` trước khi xuất H.264).
5. **Tạo/cập nhật file log trong `docs/task/` theo mục 2** (template: `docs/task/_template.md`) — bước BẮT BUỘC cuối mỗi phiên. Log phải ghi cả **kết quả review độc lập** (mục 9.1) và **quyết định plan** (mục 9.2).
6. Tóm tắt lại cho người dùng: đã làm gì, file nào thay đổi, bước tiếp theo.

---

## 6. Kinh nghiệm đã đo — đọc trước khi sửa (để không mò lại từ đầu)

Mỗi dòng là một kết luận **đã đo trên máy này**. Đọc mục này trước khi (a) đề xuất tối ưu/đổi
model, (b) sửa `src/reid.py`, (c) hứa một con số FPS trong báo cáo.

- **Đo trước, hứa sau.** Đề xuất tối ưu/đổi model phải kèm số đo trên chính máy này *trước* khi
  đưa ra phương án nhiều ngày. Ngày 05-11 hai đề xuất đã bị số đo bác bỏ: ONNX INT8 cho encoder
  chậm hơn PyTorch ở `image_size 320` (196 vs 166 ms), và `--reanchor-every` bị pipeline tự tắt
  khi bật re-ID. Bảng số: `docs/task/05-11-2026-tang-toc-256-toi-uu-hud-va-nguon-snapshot.md`.
- **Máy này không có GPU rời** (chỉ Iris Xe; `torch` bản CPU; OpenVINO chỉ thấy device `CPU`).
  Trần pipeline SAM 2.1 tiny @256 là **~175 ms/frame (5,7 FPS)** và model chiếm 168/175 ms ⇒ tối ưu
  code quanh đó chỉ còn ~20 ms. Số GPU (Colab T4 49,6 ms = 20,15 FPS):
  `docs/task/22-10-2026-colab-gpu-so-lieu-va-fix.md`.
- **Demo trên CPU dùng `image_size 256`** (155 ms ⇒ ~6,5 FPS); 320 chỉ khi cần chi tiết vật nhỏ.
  Bảng đo: `docs/research/03-kha-nang-real-time-tren-laptop-cpu-igpu.md`.
- **Đo nguồn live ở đúng nhịp tiêu thụ.** Benchmark đọc liên tục từ webcam/relay cho số sai:
  30 ms "decode" MJPEG thực chất là *chờ* relay phát 20 fps; trong pipeline chỉ chênh ~5 ms.
- **Webcam WSL: `Device busy (exported)` là cờ kẹt ở DRIVER usbipd-win**, không phải WSL.
  `wsl --shutdown`, reboot, unbind/bind, restart service đều đã thử và không khỏi ⇒ đi đường relay:
  `./run relay` rồi `./run demoip` (pipeline đọc `/snapshot.jpg`). Chi tiết:
  `docs/task/04-11-2026-cuu-webcam-relay-http.md` +
  `docs/task/05-11-2026-webcam-usbipd-ket-o-driver-khong-phai-wsl.md`.
- **Re-ID: vật chạm mép khung vẫn phải học được mẫu** (case "vật ra/vào khung" của đề cương).
  `_collect_reference()` cắt dải mép (`clip_mask_border`, 4 px) rồi nhận mẫu khi phần thấy ≥
  `EDGE_MIN_AREA_FRAC` (0,35) diện tích EMA; dải rác sát mép vẫn bị chặn. `HINT_CHAM_MEP` chỉ in
  khi **không lưu được mẫu nào**. Chi tiết:
  `docs/task/05-11-2026-tang-toc-256-toi-uu-hud-va-nguon-snapshot.md` (mục "Bổ sung 14:00").
- **Live: model 108 ms (@192) mà hình vẫn 30 FPS là nhờ LUỒNG RIÊNG + LK** (`src/light_tracker.py`,
  `_VosWorker` trong `src/live_tracking.py`). Đo thật: đơn luồng **18 FPS**, tách luồng **29,8 FPS**
  (`vos_every=3`, VOS 8,5 lần/giây). Đừng "tối ưu" bằng cách tăng `vos_every` — hình đã chạm trần
  30 FPS, chỉ mask cũ đi. **Mask vẫn ~8,5 FPS**, cấm claim 30 FPS cho mask.
  Chi tiết: `docs/task/08-11-2026-hybrid-vos-lk-live-30fps.md`.
- **Ô chọn trên live: `(x,y,w,h)` ≠ `(x1,y1,x2,y2)`.** `bbox.json` (UI/API) dùng `(x,y,w,h)`, SAM 2
  nhận `(x1,y1,x2,y2)` ⇒ phải qua `xywh_to_xyxy()` trước `engine.start()`. Bug này đã làm **toàn bộ
  số Phase 4c đo bằng ô chọn sai** (hộp cao âm, ô bao trôi). Số đúng (đo lại 08-11): 8,8 FPS
  (`vos_every=1`) → **29,9 FPS** (`vos_every=3`, mask 8,6 lần/giây).
- **Chống nhấp nháy mask mặc định TẮT**: đo 3 clip, `holds = 0` trên 2 clip, và trên `binh2` IoU
  hiển thị không cao hơn (0,681 vs 0,706) ⇒ bật là thêm trễ vô ích. Chỉ bật `--mask-smoothing 0.5`
  khi có clip bị che thật sự chứng minh được lợi ích.
- **Watchdog live phải đọc `frame.jpg` chứ không phải `status.json`.** Worker chết ⇒ API từng báo
  `running` mãi (đo 09-11, `kill -9` worker thật): nay `error` sau **116–117 ms** + message nêu mã
  thoát, luồng MJPEG đóng sau **95–110 ms** (`data/watchdog_2026-11-09_metrics.json`, 3 lần,
  `git_rev = 013e0a7`).
  **Ngưỡng "frame đứng" là `max(15 s, 4 × vos_ms)`, trần 120 s — đừng hạ về 2 s**: nhịp ghi frame hợp
  lệ có thể ~4 s/frame (`image_size 1024`, `vos_every=1`) và `engine.start()` chạy inline ⇒ ngưỡng
  2 s giết phiên khoẻ (review độc lập 09-11 bắt đúng). Ca `kill -9` **không** dùng ngưỡng đó (bắt
  bằng `proc.poll()`) nên vẫn ~0,1 s; ca **sống mà treo** mất **~15 s** — cấm trích "0,1 s" cho ca treo.
  Nhưng lúc `waiting_selection` worker **không** ghi `status.json` (`live_tracking.py:342-348`) ⇒ nếu
  lấy `ts` trong đó làm heartbeat thì phiên khoẻ sẽ bị giết oan khi người dùng chờ chọn ô.
  `status.json` **không có** field `ts`; đừng thêm rồi dùng nó làm heartbeat.
- **Watchdog mode `raw` (webcam/relay) chậm hơn hẳn mode `track` — đừng trộn hai số.** Không có
  `proc.poll()` để hỏi, chỉ biết qua "không có frame" ⇒ `OpenCvFrameSource` chờ **3 s** (`STALE_S`)
  **và ≥ 3 lần đọc trượt liên tiếp** (`MISS_MIN`) mới kết luận. **Dung sai "một lần trượt" là bắt
  buộc, đừng bỏ**: read-timeout của `HttpVideoSource`/`RtspVideoSource` là 5 s > `STALE_S`, nên nếu
  kết luận ngay ở lần trượt đầu thì một cú chập mạng giết phiên khoẻ (review độc lập vòng 2, P1).
  Ân hạn frame đầu là `WARMUP_S` 10 s. Đo 09-11 trên relay ảnh JPEG localhost: **3,75–3,76 s** để
  `error`, luồng MJPEG đóng cùng lúc (`data/watchdog_raw_2026-11-09_metrics.json`, 3 lần,
  `git_rev = 013e0a7`) — **chưa đo trên webcam/RTSP thật**. Với nguồn có read-timeout 5 s
  (`HttpVideoSource`/`RtspVideoSource`), `MISS_MIN = 3` khiến ca "mất mạng hẳn" mất thêm ~15 s
  (3 × 5 s) — đó là **giá phải trả** để không giết phiên khoẻ khi mạng chập; đừng trích "raw báo lỗi
  sau ~3 s" cho mọi kiểu mất mạng.
  Với `HttpSnapshotSource` (relay): nguồn giữ frame cuối `max_misses=20` lần rồi mới trả None ⇒ đồng
  hồ 3 s chỉ bắt đầu **sau** đó; mạng "black-hole" (mỗi lần hỏng chờ hết timeout 5 s) có thể làm ảnh
  đứng hàng phút trước khi báo lỗi. Đừng nói "raw phát hiện trong 3 s" cho mọi kiểu mất mạng.
- **`read()` treo vô hạn thì watchdog không cứu được**: `health()` chạy **cùng thread** với `read()`
  (`live.py`) nên không có nhịp kiểm nào trong lúc `read()` block (V4L2/RTSP không có read-timeout).
  Chỉ ca `read()` trả None, **ném** lỗi, hoặc nguồn tự khai `health()` là được xử lý (nay không làm
  chết thread đọc). Mọi nguồn mà `read_jpeg()` ném liên tiếp quá `_READ_ERROR_GIVE_UP_S` (5 s) thì
  service tự chuyển `error` + đóng nguồn (log lần đầu + mỗi 100 lần). Bộ đếm này **phải reset trong
  `start()`**: để rò qua phiên thì lần lỗi đầu tiên của phiên mới thấy `stuck_s` hàng chục giây ⇒
  giết phiên khoẻ (review độc lập vòng 3 bắt đúng).
- **"Không phát hiện được" là THẤT BẠI, không phải "đạt"**: `scripts/measure_watchdog.py` ghi
  `that_bai` riêng khỏi `vuot_nguong` và thoát mã 1 (`so_lan_khong_phat_hien`, `git_loi`); một lần
  chạy không có `error` trong **`WAIT_S` của mode** (worker 10 s, raw 15 s) từng bị ghi thành
  "0 lần vượt ngưỡng" — đúng bẫy "0/None ≠ đã đo". `--lan 0` cũng là thất bại (`n = 0`).
- **SAM 2 không tất định**: cùng seed, cùng video, hai lần chạy cho ô bao cuối khác nhau ⇒ chỉ so
  sánh chỉ số **trong cùng một lần chạy**.
- **Chất lượng phân đoạn phải là mIoU mask vs GT, không phải IoU hộp bao.** Số hiện có (fixture
  tổng hợp, image_size 320): mIoU **0,96** nền / **0,89** khi bị che 50 % / **None** khi che kín
  (GT rỗng, 6/6 lần mất dấu) — `data/occlusion_metrics_320_metrics.json`. **Đây là CẬN TRÊN**
  (GT ≡ pixel màu ô vuông trên ảnh tổng hợp, prompt là đúng bbox GT) — cấm trích như "mIoU trên
  video thật/DAVIS".
- **Metric IoU phải phân biệt "GT rỗng" với "model trả rỗng"**: GT rỗng ⇒ không chấm (NaN/None);
  model rỗng mà GT có vật ⇒ **0,0**. Gộp cả hai thành "không đo được" sẽ thổi phồng mIoU (một lần
  bám sai được ghi là không đo được). Bẫy `IoU(rỗng, rỗng) = 1,0` đã gặp 3 lần trong repo
  (`stability`, `mIoU`, và một test).
- **Artifact số đo phải có `git_rev` == commit code đang chạy, `git_dirty`, `lenh`, `do_luc`.**
  Số đo trên working tree bẩn thì không tái lập được (review 08-11 bắt đúng lỗi này).
  Artifact sinh bằng `scripts/measure_watchdog.py` có thêm **`git_dirty_code`** = bẩn **bỏ qua
  `data/`** — đo lại lần hai thì chính file artifact bị sửa nên `git_dirty` luôn `true` một cách vô
  nghĩa; tái lập được ⇔ **`git_dirty_code == false`**.
- **`stability` KHÔNG phải thước đo độ chính xác.** `drift_iou` cũng KHÔNG: nó là **độ tự nhất quán**
  của ô đang hiển thị so với lần VOS kế tiếp (VOS bám lệch hệ thống mà ổn định thì drift vẫn cao).
  Độ chính xác chỉ có **mIoU mask vs GT**. `stability` chỉ nói mask có nhấp nháy không.
- **Mọi so sánh A/B phải nêu ngưỡng nhiễu** (`scripts/repeatability.py`; đo 3 lần cùng cấu hình
  08-11/192): `drift_iou` ±0,004, `drift_iou_p05` ±0,057, `vos_fps` ±1,2 %, `measured_fps` ±0,3 %,
  `mask_age_p95` ±3 ms. Chênh lệch nhỏ hơn ⇒ viết **"không phân biệt được"**, không viết "tốt hơn".
  Ngưỡng chỉ đúng cho **cùng clip + cùng cấu hình**; `n < 2` (một lần chạy) thì không kết luận được gì.
- **`vos_every` KHÔNG phải nút điều khiển độ tươi của mask.** Ở 192, VOS chỉ chạy 7,5–8,7 lần/giây
  (`vos_ms` ≈ 130 ms) nên tuổi dữ liệu ảnh người xem thấy p95 ≈ **210–250 ms ở vos_every 2, 3 và 6**
  như nhau. Báo cáo phải nói "HUD 30 FPS, mask lấy từ model cũ ~0,2 s" — cấm viết "mask 30 FPS".
- **Hybrid chỉ giữ được ô bao trên một số clip**: binh1 drift 0,88–0,89 (p05 0,66–0,72), simloss 0,87
  (p05 0,64), **binh2 p05 = 0,00 (VOS trả mask rỗng 26 lần; `mask_drops`/`lost_streak` = 0 nên KHÔNG
  phải LK mất dấu)**. Cấm phát biểu "hybrid luôn bám được" — phải nêu clip + drift đo được.
  **ĐÍNH CHÍNH 14-11**: các số trên đo bằng ô **sai** — `binh1` `104,308,209,287` phủ **khuôn mặt**,
  `binh2` `200,400,300,500` phủ **2 chai + 2 tay**; và phần lớn "mask rỗng" là **vật đã rời khung**
  (`binh1` cất chai từ frame ~115). Ô + khung đúng: `docs/demo-clip-va-o-chon.md`.
- **Số "0,0" trong artifact là cạm bẫy**: `drift_iou`/`mask_age` nay trả **None + `drift_n`/`age_n`**
  khi chưa đo. Khi trích số, phải đọc kèm `*_n`; `n == 0` là **chưa đo**, không phải "đo được 0".
- **`measure_live_relay` báo `ket_qua = true` KHÔNG có nghĩa là bám đúng vật**: nó chỉ kiểm đường ống
  (running, có frame, có mask). Đo trên Colab T4 (13-11) với **bbox trỏ vào nền** cho `ket_qua = true`
  mà `drift_iou` 0,203–0,346 và `stability` 0,27–0,35 — tái lập trên CPU với đúng clip đó cũng ra
  0,118/0,389 (`data/repro_bbox_tro_nen_cpu_2026-11-13_metrics.json`) — cùng kết luận, **không** trùng
  giá trị: cả hai đều ≪ 0,86/0,88 trên `binh1` ⇒ đó là **lỗi chọn ô**, không phải "GPU bám tệ". Trước khi trích số chất lượng phải xem
  ảnh `bbox_check.jpg` (cell 8a của notebook) hoặc kiểm bbox nằm trên vật. Chi tiết:
  `docs/task/13-11-2026-colab-t4-lan-2-so-gpu-nhung-bbox-sai.md`.
- **Báo cáo và handoff kèm số từ CSV** (`mean`, `p95`, `mất dấu`, `reacquired`), không mô tả cảm tính.
- **Ngưỡng `drift_iou_p05 = 0,70` (đăng ký trước 08-11) KHÔNG dùng được làm cờ chẩn đoán**: đo 13-11
  bằng dãy mẫu từng dòng (`data/drift_samples_*.csv`, `scripts/analyze_drift_samples.py`), nó báo
  động **100 % cửa sổ** trên clip khoẻ binh1 ở cửa sổ ≥ 100 mẫu, 74–84 % ở 50, 45–47 % ở 20. Ngưỡng
  **0,30** thì 0 % báo oan trên binh1 và bắt 100 % trên binh2. Đối chứng cảnh tĩnh (frame lặp) cho
  `drift_iou` 0,9951 và p05 0,9884 (n = 364) ⇒ p05 thấp là lỗi bám/mất dấu thật, không phải lỗi đo.
  **Độ trễ phát hiện ≈ độ dài cửa sổ** (p05 chưa tồn tại trước khi đủ W mẫu): binh2 mất 15/45/95/195
  mẫu ở W = 20/50/100/200 (nhịp ~6,3 lần VOS/giây ⇒ W = 200 là ~30 s). Vì thế cờ chẩn đoán phải dùng
  cửa sổ ngắn, và **không** được hứa "phát hiện trong ~1 s". Chi tiết + số: log
  `docs/task/13-11-2026-ticket-15-dang-mau-drift-ra-csv.md`.
- **`source` của web là CHUỖI: `"0"` (webcam) không được để rơi vào nhánh file.** Hợp đồng HTTP
  khai `source: str` ("0 = webcam") nên `tools/run_live.py`/`tools/check_video_source.py` đã đổi
  chuỗi số → `int` từ trước, nhưng `open_video_source()` chỉ coi **int** là webcam ⇒ mode `raw`
  (`OpenCvFrameSource`) lẫn `track` (`live_worker`) nhận `"0"` đều báo
  "Không mở được video file: '0'" — người dùng báo 13-11 (tái hiện bằng `TestClient`: xem log): bấm
  "Bật phát" với ô nguồn mặc định là `0`. Nay
  factory tự đổi chuỗi chỉ-gồm-chữ-số → index webcam, **trừ khi** có file/thư mục thật trùng tên
  (`os.path.exists`). Tên số được hiểu theo **CWD của tiến trình** (API chạy theo CWD của uvicorn,
  worker chạy `cd REPO_ROOT`) ⇒ muốn trỏ file tên `0` thì ghi rõ `./0`. Khi thêm nguồn mới, kiểm cả
  hai đầu: HTTP (chuỗi) và CLI (int). Log:
  `docs/task/13-11-2026-live-webcam-nguon-0-tu-web.md`.
- **Relay webcam (`scripts/win_camera_relay.py`): `--fps` là TRẦN, đừng ngủ thêm một `interval` nữa.**
  Đo 13-11: webcam Windows cho ~16,6 FPS ở 640×480 (`scripts/probe_cam_fps.py`, 720p chỉ 10), nhưng
  relay chỉ phát **10,6** vì `sleep(interval)` không trừ thời gian `read()`+`imencode()` ⇒ chu kỳ =
  công việc + interval; sửa bằng mốc **đầu vòng** rồi mới ngủ phần còn lại. Với fake capture
  `read()` 40/80 ms + `--fps 20`: code cũ **11,0/7,6** FPS, code mới **20,0/12,5** FPS (không thể
  “đoán” bằng mắt trên webcam vì số giây thay đổi theo ánh sáng). `/info.fps` phải là **trung bình 1 s**,
  không phải một chu kỳ (một chu kỳ từng báo 21,3 FPS với `--fps 20`). Demo web: nguồn
  `http://<IP-Windows>:8090/snapshot.jpg` (ảnh JPEG rời 2,6 ms/frame), **không** dùng `/video` (MJPEG đắt hơn).

- **Dò nguồn (`GET /api/live/sources`) chỉ được chạy LÚC CÓ REQUEST, không bao giờ trong
  `create_app()`/import.** `src/api/main.py` có `app = create_app()` ở cấp module ⇒ dò ở đó là dò mỗi
  lần import (CI ubuntu không có webcam) và mỗi lần lưu file (`uvicorn --reload`). Đo 13-11: dò nguồn
  lần đầu **74 ms**, trong cache **3 ms** (TTL 5 s), `budget_ms = 1400` (webcam 0,6 s · HTTP 0,8 s).
  `live_busy` phải là **`RUNNING | LOADING`**: `LOADING` là worker `track` đang nạp model 20–240 s và
  **sẽ mở đúng thiết bị đó** — dò webcam lúc này là tranh thiết bị (ca "Device busy" ở trên).
  `available = true` chỉ có nghĩa *"thử được lúc `checked_at`"*, **không** phải "đang chạy": với
  `kind=file` nó chỉ là "file tồn tại, chưa mở thử" — UI phải in kèm bằng chứng (`check`) chứ không
  được in chữ "đã kiểm" trống rỗng. Và **cấm** dùng `fps` do relay tự khai (`/info`) làm FPS trên HUD:
  đo 13-11 relay khai 16,26 FPS trong khi nhịp đổi thật ~19,9/s ⇒ chỉ dùng `measured_fps`/`display_fps`
  của API/worker. Log + plan: `docs/task/13-11-2026-ui-moi-va-tu-dong-do-nguon.md`,
  `docs/plan/13-11-2026-ui-tu-dong-nguon.md`.

- **“Mất dấu” phải tách khỏi “vật đã rời khung” — ô chọn và khung frame phải kiểm bằng ẢNH.**
  Đo 14-11 (đường live, @192, `vos_every 3`, 55 s, 3 lần xen kẽ, `git_dirty_code=false`): ô chai
  `binh1 300,275,150,410` cho `empty` **36,0–36,7 % cả phiên nhưng 1,7–1,8 % khi chai trong khung**
  (hai đoạn `0:110` ∪ `165:262`; riêng đoạn `0:110` là 0,0 %); `binh2 330,330,150,360` cho 22–23 %
  nhưng **0,0 %** trong khung `0:160`. Ô **khuôn mặt**
  (`104,308,209,287`, mặc định cũ của `profile_stages.py`/`benchmark_light_trackers.py`/
  `measure_watchdog.py`) cho drift 0,881–0,884 và **0 % rỗng** — vì mặt luôn ở trong khung. ⇒ dùng
  `scripts/measure_live_relay.py --frame-window dau:cuoi` (artifact có `cua_so_frame.trong_khung` /
  `.ngoai_khung`), **cấm** trích tỉ lệ rỗng cả phiên như “model mất dấu”. Không cần train lại model:
  checkpoint `small` cho 31,1 % rỗng vs `tiny` 31,8 % mà chậm +18 %; `image_size` 256/320 làm
  `drift_iou` **giảm** (0,34–0,36/0,28–0,32) và chậm 1,8–2,5×; `vos_every` 1/2/3 như nhau. Chi tiết:
  `docs/task/14-11-2026-do-lai-bbox-dung-ket-luan-khong-can-train-lai.md`,
  `docs/demo-clip-va-o-chon.md`.

- **Chu kỳ VOS tách theo pha: nút thắt là model + tiền xử lý, KHÔNG phải "chờ frame".**
  Đo 14-11, **3 lần** (1 vòng `binh1`, @192, `vos_every 3`, `git_dirty_code=false`, artifact
  `data/chu_ky_chai_binh1_1vong_lan{1,2,3}_metrics.json`):
  `cycle_ms` **101,5–121,6** · `vos_ms` (model) **83,6–103,1** · `pre_ms` **11,6–13,1** ·
  `post_ms` **0,08–0,98** · `queue_ms` **2,1–75,9** · `idle_ms` **0,01–16,8**.
  ⇒ (a) **KHÔNG** được nói "queue ≈ 0 ⇒ frame không phải chờ": chạy **một** lần từng ra 0,33 ms nhưng
  n=3 cho 2,1–75,9 ms (mẫu cuối, phụ thuộc pha submit ↔ VOS) — n=1 ở đây kết luận sai, đúng cảnh báo
  "n < 2 không kết luận"; (b) kết luận đúng là `cycle ≈ vos_ms + pre_ms` ⇒ tăng tần suất gửi frame chỉ
  làm `queue` dài thêm, còn muốn nhanh hơn phải cắt **model** hoặc **tiền xử lý** (`pre_ms` 12–13 ms);
  (c) `vos_ms` **không gồm** `pre_ms` (đo riêng, `TrackingResult.pre_ms`, mặc định `None` = chưa đo).
- **Hai định nghĩa tuổi mask, đừng trộn:** `mask_age_cu_ms` = age + `vos_ms` (**định nghĩa cũ**, số
  trước 14-11 dùng cái này: p95 271–273 ms), `mask_age_total_ms` = queue + pre + vos + post + age
  (**tuổi dữ liệu thật**, từ 14-11). p95 tính **theo từng mẫu** chứ không cộng `vos_ms` hiện tại cho
  cả cửa sổ. So sánh số cũ với số mới phải nêu định nghĩa, nếu không là so hai đại lượng khác nhau.

## 7. Các repo/model tham khảo

- SAM 2: https://github.com/facebookresearch/sam2
- SAMURAI: https://github.com/yangchris11/samurai
- XMem: https://github.com/hkchengrex/XMem

Cài đặt/cơ chế hydra `model_cfg` của SAMURAI trong repo này: `docs/samurai-setup.md` (cài từ clone mới: `README.md` mục 1).

---

## 7b. Quy trình Git — 1 nhánh/nhiệm vụ, vào `main` qua PR

**Quy ước đầy đủ: `docs/quy-trinh-git.md`** (đọc trước khi bắt đầu phiên làm việc).

- **Không commit thẳng lên `main`.** Mỗi nhiệm vụ = 1 nhánh ngắn hạn (`feat/…`, `fix/…`, `docs/…`,
  `chore/…`) rẽ từ `origin/main`, rebase trước khi push, mở **PR** để người phụ trách review + merge.
- **Hạn chế conflict:** không sửa cùng lúc các file "nóng" (`run`, `AGENTS.md`, `README.md`,
  `requirements.txt`, `tests/conftest.py`, `web/package-lock.json`); thêm mục mới vào **cuối** file;
  logic mới đặt trong **module mới** thay vì nhồi vào file lớn; **không reformat** file không liên quan;
  PR < ~400 dòng diff.
- **Tag:** chỉ tag mốc "demo chạy được", tối đa **2 tag sống** (CLI + web). Tag cũ bị thay thế thì xoá.
- **Nhánh nháp:** tối đa một nhánh `demoip`; mỗi lần làm việc phải rebase lên `origin/main`,
  không merge ngược `main` vào nháp.

## 8. Agent skills

### Issue tracker

Issues/spec/tickets lưu cục bộ dạng markdown trong `.scratch/<feature>/`. Xem `docs/agents/issue-tracker.md`.

### Triage labels

Dùng 5 nhãn mặc định: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Xem `docs/agents/triage-labels.md`.

### Domain docs

Single-context: một `GLOSSARY.md` + `docs/adr/` ở root. Xem `docs/agents/domain.md`.

---

## 9. Hai quy trình BẮT BUỘC: review độc lập & plan 3 ý kiến

> Hai bước này là **điều kiện hoàn thành**, không phải "nên làm". Thiếu bước nào thì việc đó coi như
> chưa xong — kể cả khi test đã xanh.

### 9.1. Review độc lập sau mỗi vấn đề (trước khi merge)

**Khi nào:** mọi thay đổi chạm code/docs, ngay sau khi `./run lint` + `./run test` xanh và **trước**
khi mở/merge PR. Không review thì không merge (kể cả khi tự merge).

**Ai review:** một agent **độc lập** với agent đã viết code — dùng tool `task` với `agent_type:
reviewer` (không có `reviewer` thì `general` với prompt "chỉ đọc, không sửa"). Cấm tự review bằng
chính phiên đã code rồi coi là đã review.

**Prompt review phải có:** `parent_context` (kiến trúc, ADR liên quan, số đo đã có, trạng thái
lint/test) + `proposed_changes` (danh sách thay đổi kèm tiêu chí nghiệm thu) + phạm vi (commit/PR).
Yêu cầu đầu ra: bảng `[P0 chặn merge | P1 sửa sớm | P2 nên sửa | P3 góp ý] · file:line · bằng chứng ·
cách sửa + test nên thêm`, và **được phép nói "đã kiểm, không phải lỗi"**.

**Xử lý kết quả:**
- **P0**: sửa ngay trong cùng PR, thêm test bắt hồi quy, chạy lại review phần vừa sửa.
- **P1**: sửa ngay nếu ≤ 1 giờ, không thì tạo ticket (`.scratch/<feature>/`) và ghi vào log.
- **P2/P3**: tạo ticket hoặc ghi vào mục "Next steps" của log — **không im lặng bỏ qua**.
- Ghi vào log ngày: ai review, phát hiện gì, đã sửa gì, còn nợ gì (kèm id ticket).

### 9.2. Lập plan bằng 3 ý kiến tranh luận (trước khi làm việc lớn)

**Khi nào:** việc ước lượng > ~4 giờ, hoặc đổi kiến trúc / model / thuật toán / hợp đồng API;
hoặc khi hai phương án đều "có lý" và chọn sai sẽ tốn ≥ 1 ngày.

**Cách làm (2 vòng, không gộp):**
1. **Vòng 1 — độc lập:** gọi **3 agent song song**, mỗi agent một **góc nhìn khác nhau** và **không**
   biết đề xuất của nhau. Ba góc nhìn mặc định:
   - **Chất lượng & số đo** (tracking có thật sự tốt hơn? đo bằng gì?),
   - **Sản phẩm & bằng chứng bảo vệ** (demo/báo cáo/hội đồng cần gì?),
   - **Độ bền & hiệu năng** (race condition, tái lập số đo, test bắt hồi quy).
   Mỗi agent phải trả: bảng `[việc | mục tiêu đo được | cách làm (file/hàm) | nghiệm thu CÓ SỐ | giờ |
   rủi ro]`, **việc KHÔNG nên làm**, và "nếu chỉ chọn 1 việc".
2. **Vòng 2 — phản biện:** gửi cho **cả 3** agent bản tóm tắt của cả 3 đề xuất, yêu cầu: chỉ ra chỗ
   sai/thiếu của hai người kia, chỗ nào mình đổi ý, và **1 phương án hợp nhất**. Đây là bước tạo ra
   tranh luận thật — không được bỏ để tiết kiệm thời gian.
3. **Chốt:** người cha (agent chính) quyết định, nêu rõ **vì sao chọn**, **vì sao bác** phương án
   còn lại (kèm số đo nếu có), và **tiêu chí nghiệm thu có số**.
4. **Lưu:** `docs/plan/DD-MM-YYYY-<slug>.md` theo `docs/plan/_template.md`, gồm cả **điểm tranh chấp**
   và **phương án bị bác kèm lý do** — để sau này không mở lại việc đã bác.

### 9.3. Nếu tool agent báo lỗi

- `Declared subagent skill(s) not found: <tên>` ⇒ frontmatter của agent (trong
  `~/.pi/agent/npm/node_modules/@heyhuynhgiabuu/pi-task/agents/*.md`) khai báo skill **không tồn tại
  trên máy này**. Sửa mapping sang skill đang có (`code-review`, `codebase-design`, `tdd`,
  `verification-before-completion`, `memory`…) hoặc tạm dùng `agent_type: general` với prompt
  "chỉ đọc". **Không được bỏ qua bước review/plan vì lỗi tool.**
- Lỗi backend (`Failed to create herdr execution pane…`) ⇒ thử lại hoặc đổi `agent_type`; ghi lại
  vào log nếu lặp lại nhiều lần.

### 9.4. Checklist kết thúc phiên (đủ mới được báo "xong")

- [ ] `./run lint` xanh
- [ ] `./run test` xanh (và `./run webtest` + `npm run build` + `./run e2e` nếu đụng `web/`)
- [ ] Review độc lập đã chạy (mục 9.1), P0 = 0, P1 có chủ
- [ ] CI GitHub xanh trước khi merge
- [ ] Log `docs/task/…` có kết quả review + quyết định plan
- [ ] Số liệu trong log/README lấy từ file CSV/status.json thật, ghi rõ môi trường đo
