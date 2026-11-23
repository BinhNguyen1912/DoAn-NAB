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
   - **Trước buổi demo:** `./run democheck` — 9 mục, **không nạp model**, ≤ 120 s (checkpoint, clip,
     `web/dist` cũ, API, cổng, tệp phiên cũ, nguồn đọc được, **frame có đổi**, `git_rev`).
     `--full --bbox x,y,w,h` = diễn tập thật (có nạp model, tự dựng API) và kiểm `frames` tăng +
     `mask_fps > 0`. "OK" ở mục nguồn chỉ nghĩa *"đọc được frame lúc kiểm"*, **không** phải "bám đúng" —
     và `--full` **bắt buộc** `--bbox` vì hộp mặc định hay rơi vào nền (AGENTS §6, ca Colab 13-11).
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
- **Mọi `*_p05` công bố ra artifact đi qua MỘT ngưỡng: 30 mẫu** (`drift_samples.MIN_SAMPLES`, ghim
  bằng test bằng `live_tracking._STAT_MIN_SAMPLES`). Ngày 17-11 repo có ba ngưỡng (5 ở `score_miou`,
  20 ở `make_trajectory_media`, 30 ở `status.json`) ⇒ cùng đại lượng mà ba con số không so được với
  nhau. Nay `mIoU_p05`/`drift_iou_p05` đều `None` khi n < 30, kèm `mIoU_p05_n`/`drift_n` +
  `*_p05_nguong`; **`None` ở đây nghĩa là "chưa công bố", không phải "p05 = 0"**. Hệ quả phải nhớ:
  GT thật `binh1` chỉ 12 frame ⇒ `mIoU_p05 = None` (đọc cột `frames` thay vì p05), và artifact
  `data/miou_synthetic_2026-11-14_metrics.json` (5 frame, p05 0,9239) **sinh trước** đổi này ⇒ cấm
  trích p05 của nó. `p05` theo **cửa sổ** (`rolling_p05`/`flag_rate`/`low_p05_low_empty`) không bị
  ngưỡng này chi phối — "đủ mẫu" ở đó do chính cửa sổ quyết định.
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
- **`vos_every = 1` (đơn luồng) NAY CŨNG đo tuổi mask** (ticket #24, 17-11): nhánh inline
  (`_after_vos`) gọi `_note_mask_age(age = 0, vos_ms, pre_ms, queue_ms = 0, post_ms)` và ghi cả
  `pre_ms`/`post_ms` vào `status.json`; trước đó nó không ghi gì nên HUD im lặng ở đúng cấu hình đã
  dùng cho mIoU fixture. Đo trên máy này (`data/bang_cau_hinh_2026-11-17_every1_metrics.json`,
  `git_rev 3cc0248`, `git_dirty_code false`, `image_size 192`, 3 lần × 60 frame, clip `binh1.mp4`, ô
  chai `300,275,150,410`): **9,33 ± 0,55 FPS phát = nhịp mask** (không có LK lấp), `vos_ms 87,33 ± 4,52`,
  `pre_ms 10,96 ± 1,85`, `mask_age_p95 109,9 ± 9,32` (`age_n 60`). **`FPS phát` của dòng này KHÔNG so
  được với 29,8 của `vos_every ≥ 2`** (hai đường khác nhau), và tuổi mask ≈ `pre_ms + vos_ms + post_ms`
  **không phải** chỉ `vos_ms` — đúng lý do phải tách `mask_age_total_ms`. Đường đơn luồng **không** có
  `drift_iou` (không nội suy LK ⇒ không có cặp VOS ↔ nội suy); đừng "sửa" bằng cách gọi
  `_measure_drift` trong `_after_vos`. Mỗi frame PHÁT (kể cả frame `engine.start()`) ghi **một** mẫu
  ⇒ bảng 15-11 ghi `age_n 59` (60 frame) còn lần chạy lại ra `60` — chênh 1 mẫu là do mẫu của frame
  `start()`, không phải bug.
- **Hai định nghĩa tuổi mask, đừng trộn:** `mask_age_cu_ms` = age + `vos_ms` (**định nghĩa cũ**, số
  trước 14-11 dùng cái này: p95 271–273 ms), `mask_age_total_ms` = queue + pre + vos + post + age
  (**tuổi dữ liệu thật**, từ 14-11). p95 tính **theo từng mẫu** chứ không cộng `vos_ms` hiện tại cho
  cả cửa sổ. So sánh số cũ với số mới phải nêu định nghĩa, nếu không là so hai đại lượng khác nhau.
- **`POST /api/live/start` CHẶN tới khi model nạp xong** (`routes.py` → `live.start()` →
  `WorkerFrameSource.start()` → `_wait_first_frame()`): đo trên máy này **3,4–4,1 s** với checkpoint
  tiny (cache ấm). Đừng đặt timeout 5 s cho request đó — biên chỉ ~1 s, và `cv2`/torch cache lạnh hay
  checkpoint `small`/`base` sẽ vượt; hỏng timeout **không** có nghĩa server chưa dựng phiên (nó vẫn
  dựng sau lưng client ⇒ worker giữ webcam mà không ai gửi stop). `scripts/measure_live_relay.py`
  dùng `timeout=600`, `scripts/demo_preflight.py --full` dùng `max(30 s, --full-timeout)`.

- **Muốn nói "bám ĐÚNG" thì phải chấm mIoU mask vs GT** (`./run miou`, quy trình trong
  `docs/thuoc-do-bam-dung.md`): `drift_iou`/`stability` chỉ là độ tự nhất quán. Quy tắc chấm: GT rỗng
  ⇒ **không chấm**; model rỗng mà GT có vật ⇒ **0,0**; thiếu mask ⇒ *chưa chạy*, không phải bám sai;
  mIoU trên fixture tổng hợp là **cận trên**. Số "chọn cấu hình" lấy từ `./run bangcau`
  (`docs/bang-cau-hinh.md`, **3 lần/cấu hình có `±`**); so hai cấu hình thì dùng `./run ab` (chạy chèn
  kẽ, chênh lệch ≤ `max(std_a, std_b)` ⇒ viết **"không phân biệt được"**).

- **Ngưỡng nhiễu phải lấy THEO Ô CHỌN — số cũ chỉ đúng cho ô khuôn mặt.** Dòng
  "`drift_iou` ±0,004, `mask_age_p95` ±3 ms" (đo 08-11) là của ô phủ **khuôn mặt**. Đo lại trên artifact
  đã commit: ô **chai** (`data/lan2_chai_binh1_lan1..3_metrics.json`, 55 s) cho `drift_iou` 0,444–0,454
  (**±0,010** — gấp 2,5×) và `mask_age_p95` 215,4–221,4 (**±6 ms**); phiên ngắn 11 s
  (`data/chu_ky_chai_binh1_1vong_lan*_metrics.json`) cho **±0,019** và **±32 ms**. Dùng ±0,004 cho ô chai
  là gọi chênh lệch 0,005 thành "khác thật".
- **`measured_fps`/`display_fps` bão hoà ~29,3–29,9 ở MỌI `image_size`** (bảng 9 cấu hình:
  `data/bang_cau_hinh_2026-11-15_metrics.json`) vì LK lấp phần giữa ⇒ **không** dùng nó để chọn cấu hình;
  chọn theo `vos_fps` + `mask_age_p95` (`docs/bang-cau-hinh.md`). Riêng `mask_age_p95` (mean 3 lần, 15-11):
  192 → **390,2 ms** (every 2) / **373,6** (every 3) / **303,6** (every 6); 320 → **603,6** / **656,5** / **707,2**.
  **Nhưng đừng so số p95 giữa hai artifact**: cùng cấu hình 192/3 đo ngày 14-11 cho 315,8 ± 16,4, ngày 15-11
  cho 373,6 ± 97,9 và lần lặp 362,4 ± 59,5 (`data/bang_cau_hinh_2026-11-15_lan2_192va320_every3_metrics.json`)
  ⇒ chênh **~50–60 ms giữa hai phiên** (lớn hơn cả `±` của phiên 14-11). Chỉ so **trong cùng một lần chạy**
  (`./run ab` chèn kẽ), và độ tươi của mask **không** dùng để nói "cấu hình này tốt hơn" khi chênh < `±`:
  192/3 vs 192/6 ở lần đo 15-11 chênh 70 ms < `±` 97,9 ⇒ **không phân biệt được** (lần 14-11 lại xếp ngược
  chiều) — đúng kết luận "`vos_every` không phải nút điều khiển độ tươi của mask".

- **`--image-size` chỉ là YÊU CẦU; `status.json` từ 15-11 echo cả HIỆU LỰC.** `cau_hinh.image_size_yeu_cau`
  vs `cau_hinh.image_size_hieu_luc` (đọc từ `predictor.image_size`, tức giá trị model **thật sự** dùng).
  Đo trên máy này (checkpoint tiny, `git_rev 58bb629`): `--image-size 192` → hiệu lực **192**, `cau_hinh_lech []`;
  **không** truyền `--image-size` → yêu cầu `null`, hiệu lực **1024**, lệch `[]` (null = "không có gì để so").
  Ba trạng thái KHÔNG được lẫn: `image_size_kiem_duoc = false` / hiệu lực `None` = **CHƯA KIỂM ĐƯỢC**
  (worker bản cũ, predictor không khai báo) — **cấm** đọc `cau_hinh_lech == []` thành "đã khớp".
  `scripts/bang_cau_hinh._run_once` (dùng chung `./run bangcau` + `./run ab`) coi lần chạy có hiệu lực khác
  `--sizes`/`--image-size` **hoặc** hiệu lực `None` là **LỖI** (dòng "—", không có số). Đã diễn tập thật bằng
  cách cho `build_overrides` trả `[]`: 2/2 lần bị từ chối, `./run bangcau` thoát mã 1.
  Artifact từ **15-11** trở đi có `cau_hinh` (đo trên cây sạch: `bang_cau_hinh_2026-11-15_metrics.json`,
  `git_rev 96b0c3e`, `git_dirty_code=false`, 27/27 lần chạy có `image_size_hieu_luc` = `--sizes`).
  Riêng `bang_cau_hinh_2026-11-14` + `ab_192_vs_320_2026-11-14` sinh **trước** thay đổi ⇒ **không** có
  `cau_hinh`; đừng trích chúng như "bảng đã tự kiểm cấu hình".


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
- **Cổng "nghi đổi đối tượng" phải CÓ NHỚ, và `track_cos` KHÔNG phân biệt được vùng sai cùng tông.**
  Đo 21-11 (phiên `demoip_1121-121732`): cổng nhảy báo ĐÚNG ở f178 (bám sang **cửa/tường be cùng tông** với
  điện thoại be) nhưng sau cú nhảy chuyển động lại mượt ⇒ cổng **không báo lại**, hệ vẽ mask SAI **65
  frame**. Mask-cos của vùng sai = **0,752–0,989** (median 0,854) so với ca đúng **0,905** ⇒ **không tồn tại
  θ tách được** (0,75 bắt 0/65; 0,85 bắt 43 % nhưng **chặn oan 15 %** frame đúng) ⇒ **đừng làm "cổng cos"**,
  và **đừng trích** "θ bắt được ca máy lạnh" (số 0,51–0,72 của ca đó là **box-cos**, khác đại lượng).
  Nay `src/identity_guard.IdentityWatch` giữ trạng thái nghi (latch) tới khi bấm `r` (chọn lại) hoặc `c`
  (vẫn đúng) và `visualizer` **không vẽ** mask/ô khi nghi. Chi phí đo được: cổng báo **21 lần/2 973 frame
  (0,71 %)** trên 18 phiên; ẩn tới hết phiên mà không ai bấm gì = **34,7 %** frame, **5/18 phiên sạch không
  bao giờ bị ẩn** (`data/identity_latch_chi_phi_2026-11-21_metrics.json`). **Cả hai đường đều có** (web: `bam = "nghi_doi_tuong"` + `nghi_doi_tuong_n` trong `status.json`, nút
  "Vẫn đúng, tiếp tục" ⇒ `POST /api/live/confirm` ⇒ API ghi `confirm.json`, worker đọc rồi **tự xoá**;
  e2e trên Chrome thật kiểm banner + nút + endpoint).
- **Trước khi trích số FPS/latency: kiểm KHÔNG có worker live mồ côi.** Đóng tab web KHÔNG dừng worker
  (`/dev/shm/doan-live`); API chỉ reap khi mở phiên mới **cùng thư mục**, nên CLI không biết. Đo 21-11:
  một worker web bỏ quên ăn **461 % CPU** ⇒ `./run demoip` ra **1484 ms mean / 2821 ms p95** thay vì
  **158/199 ms** (chậm 9×) và cả phiên bị kết luận sai là "model chậm". Nay `tools/run_live.py` in WARN
  kèm pid + `kill -9 <pid>` trước khi mở phiên (`src/proc_pid.find_live_workers`). Kiểm nhanh:
  `ps -eo pid,pcpu,etime,cmd | grep live_worker` và `uptime`.
- **`image_size`: đo được XU HƯỚNG, nhưng CHƯA có ngưỡng nhiễu mIoU ⇒ chưa được tuyên bố "tốt hơn".**
  Đo 22-11 trên T4 (clip `binh2.mp4`, `vos_every=1`, 360 frame, ô chọn suy từ GT frame đầu
  `(334,319,158,568)`, mIoU `binh2_tay` n=8 frame có vật): **0,7644** @192 (99,5 ms/frame) →
  **0,8161** @320 (111,9) → **0,8338** @512 (129,1) → **0,8368** @1024 (**507,4** = 2 FPS).
  `192/320` và `512/1024` đo ở **hai lần chạy khác nhau** (artifact `data/gpu_sweep_...` chỉ còn
  512/1024 — xem bullet dưới), và **mỗi cấu hình mới đo n=1**.
  **Cấm kết luận "cấu hình này tốt hơn"**: repo CHƯA đo ngưỡng nhiễu cho **mIoU mask vs GT** trên clip
  này. Con số 0,022–0,034 từng bị trích cho việc đó là **`iou_mean` (hộp vs GT) trên `binh1`/`b1b`**
  (`docs/task/20-11-...`), **không** phải mIoU trên `binh2_tay`; còn ±0,019 là `drift_iou`. Theo quy
  tắc n=1 ở trên, cả ba so sánh (192→320, 320→512, 512→1024) **đều chưa kết luận được**; muốn tuyên
  bố thì chạy **3 lần/cấu hình** (`./run ab`-kiểu chèn kẽ) rồi mới có `±`.
  **Điều DUY NHẤT chắc chắn từ số này là GIÁ:** 1024 chậm **3,9×** (507 ms = 2 FPS) mà mIoU chỉ nhích
  +0,003 ⇒ **cấm đưa 1024 vào cấu hình nào**; 320→512 đắt thêm 15 %.
  mIoU @192 trên GPU **trùng khít** baseline CPU (0,7644) ⇒ thiết bị không đổi chất lượng phân đoạn
  (thời gian CPU @192 đo được ~100–107 ms/frame, KHÔNG phải "342 ms"). `ms/frame` ở đây GỒM cả nạp
  model ⇒ **cận trên**, không phải `vos_ms`. Cột `binh2_tay2` chỉ có **n=2** frame có vật ⇒ cấm trích
  0,81 của nó như số chắc. Mốc cho Cutie: **phải tự đo được ngưỡng nhiễu mIoU trước**, rồi mới đặt
  mốc (đừng lấy 0,856–0,868 — đó vẫn là số mượn).
- **Điểm prompt ÂM không phải "liều thuốc chung": trên clip mà lỗi là mask HỤT, nó làm HỤT THÊM.**
  Đo 22-11 (`scripts/ab_diem_am.py`, so cặp từng frame, điểm âm sinh từ HÌNH HỌC chứ không từ GT):
  trên `binh2` (lỗi đang là **hụt diện tích**) — điểm âm quanh ô ĐÚNG: 192 **+0,0016** (5/8 frame, CI95
  chứa 0 ⇒ không kết luận), 512 **−0,0010** (1/8); mô phỏng "chọn ô rộng tay" (ô nới 1,3×, điểm âm
  trong vành): 192 +0,0088 (2/8, CI95 chứa 0), **512 −0,0744 (2/8, CI95 [−0,2200, +0,0007])**.
  ⇒ **Chỉ dùng điểm âm khi mask TRÀN ra ngoài vật** (ca 21-11 bám sang cửa/tường cùng tông); gợi ý
  trên canvas đã ghi đúng câu đó. **Cấm** viết "điểm âm đã khắc phục bám nhầm" khi chưa có clip tái
  hiện ca 21-11 (repo **chưa có** clip đó). Đây là kết quả ÂM TÍNH có artifact:
  `data/ab_diem_am_2026-11-22_metrics.json`, `data/ab_diem_am_512_2026-11-22_metrics.json`.
- **Muốn so hai cấu hình thì so CẶP theo frame (`scripts/paired_miou.py`), đừng so hai giá trị trung
  bình.** So trung bình cần ngưỡng nhiễu mIoU — repo **CHƯA có**; mọi lần trích trước đây đều mượn của
  đại lượng khác (0,019 = `drift_iou`; 0,022–0,034 = `iou_mean` hộp-vs-GT trên `binh1`/`b1b`) nên
  **đều sai**. Cách đúng: chấm trên **cùng bộ frame** rồi lấy chênh lệch TỪNG frame (khử phương sai
  giữa frame), báo `n`, số frame cùng dấu, mean/median, CI95 bootstrap, sign test chính xác.
  Đo 22-11 (`binh2_tay`, 8 frame chung, hai artifact cùng `git_rev 316c6e8` trong `data/`):
  **192→320** 7/8 dương, mean **+0,0517**, CI95 **[+0,0249, +0,0842]**, sign p **0,070** ⇒ "có khả năng
  thật, CHƯA đạt ngưỡng tuyên bố" (sign test cần 8/8 mới p<0,05); **320→512** 6/8, +0,0176,
  CI [+0,0036, +0,0315], p 0,289 ⇒ **chưa kết luận**; **512→1024** 4/8, +0,0030, CI **[-0,0071,
  +0,0140] chứa 0**, p 1,000 ⇒ **không khác biệt** (bằng chứng ÂM TÍNH, mạnh hơn "chưa đo") mà chậm
  **3,9×** ⇒ **cấm 1024**. Cảnh báo: frame trong một clip KHÔNG độc lập ⇒ p chỉ là chỉ báo; 8 frame là
  rất ít, muốn chốt phải lặp 3 lần/cấu hình. Frame tệ nhất (`163`, 0,746–0,750) **không** tốt lên khi
  tăng `image_size` ⇒ lỗi còn lại không phải do độ phân giải.
- **Gộp artifact nhiều lần chạy: `payload["ket_qua"]` phải được gán SAU khi gộp, và mỗi DÒNG phải mang
  provenance riêng.** Bản đầu gán payload trước rồi gán lại `rows` ⇒ file ghi ra chỉ có cột của đợt
  cuối, còn bảng in ra thì đủ dòng; người đọc tưởng "cùng một lần chạy" và trích số từ một file
  KHÔNG chứa số đó (review độc lập 22-11 bắt đúng, artifact `gpu_sweep_binh2_2026-11-22` là bằng
  chứng: `lenh = --sizes 512,1024` mà log lại trích cả 192/320). Nay: `tao_payload()` chỉ nhận list
  ĐÃ gộp; gộp **từ chối** khi khác `clip`/`o_chon_xywh`/`frames_gt`/`vos_every`/`gt_dirs`/`git_rev`;
  mỗi dòng có `lenh_rieng` + `do_luc_rieng` để đọc đúng nguồn từng số, và file có `schema` (đổi cấu
  trúc `chi_tiet` thì tăng số, không trộn hai lược đồ). Vòng review thứ hai bắt thêm: dòng THÀNH CÔNG
  từng **không có `lenh`** (nên `lenh_rieng` rỗng đúng ở dòng có số), `--max-frames` + `--out` vẫn ghi
  đè được artifact công bố, và mã thoát bị dòng LỖI cũ trong file làm exit 1. Test:
  `tests/test_bench_gpu_binh2.py` (29 case).
- **Trên Colab: `--stop-after-frames` là BẮT BUỘC, và `--stream` phải dùng `Popen`.**
  `tools/live_worker.py` mặc định `loop_files=True` ⇒ thiếu `--stop-after-frames` thì nó **lặp file vô
  hạn**, người chạy thấy "chạy quài" và tưởng model chậm (gặp thật 22-11, 2 lần). Và
  `subprocess.run(stdout=PIPE)` **không stream** (gom hết rồi mới trả) ⇒ im lặng 30–90 s lúc nạp model,
  người chạy bấm Ctrl-C. `scripts/bench_gpu_binh2.py` nay tự đọc `CAP_PROP_FRAME_COUNT` và **NÉM nếu
  không đọc được hoặc ≤ 0** (trước đó `if dung_sau:` lặng lẽ bỏ cờ ⇒ lặp vô hạn trở lại), in log bằng
  `Popen` + luồng đọc riêng (`--timeout` mới thực sự cắt được tiến trình treo mà không in gì), và
  **kiểm `image_size_hieu_luc` == yêu cầu** (None = "chưa kiểm được" ⇒ dòng LỖI, không công bố).
- **`IdentityWatch` latch deadlock: Re-ID reacquire PHẢI reset cổng nghi và cập nhật `last_bbox`.**
  Đo 22-11 (phiên webcam thật `demoip_1122-195623`): chai nước chạm mép phải (`x2=639`) làm SAM 2
  giật ô về giữa ⇒ `IdentityWatch` bật cờ nghi (latch) và ẩn ô. Sau đó Re-ID nhận lại chai nước thành
  công 98% (`reid_score 0.98`, SAM 2 score 22.0) và bám mượt mà suốt 10 s — nhưng người dùng thấy MẤT
  DẤU VĨNH VIỄN vì: (a) `reacquired=1` không reset `watch` và không cập nhật `last_bbox`, (b) nhánh
  `if not switch: last_bbox = bbox` đóng băng `last_bbox` ở tọa độ cũ trước cú nhảy, biến mọi frame sau
  đó thành cú nhảy giả 400 px, khiến visualizer ẩn ô suốt cả phiên. Nay: `reacquired=1` hoặc bấm `c`
  tự động reset `watch` và cập nhật `last_bbox = result.bbox`; khi mất dấu (`mask.any() == False`),
  `last_bbox = (0, 0, 0, 0)` để khi vật xuất hiện lại không bị so với ô cũ từ nhiều giây trước.
- **Trần "mượt" của demo webcam là CÁI CAMERA (16,5 fps), không phải model.** Đo 21-11: relay `/info`
  = 16,53 fps; ảnh `/snapshot.jpg` đổi **16,0 lần/s**; hạ `--width 320 --height 240 --fps 30` vẫn **16,51
  fps** ⇒ giới hạn cảm biến, hạ độ phân giải **không** giúp. Model trên CPU: @192 **102 ms** (9,8 lần/s),
  @160 **75 ms**, @128 **58 ms** (17,3 lần/s) — chất lượng (fixture che, cận trên): mIoU nền 0,913/0,927/
  0,898 và mIoU khi che 50 % 0,861/0,826/0,781. ⇒ Muốn overlay tươi hơn thì hạ `image_size` (**160** là
  điểm cân bằng); muốn hình >16 fps thì phải **đổi nguồn** (điện thoại 30 fps qua `./run phone`, hoặc
  clip). **Đừng hứa GPU free làm mượt live** — Colab/Kaggle không thấy webcam laptop và không có URL
  công khai để relay đẩy ảnh vào; tunnel thêm 50–150 ms/frame.

- **Cổng "nghi đổi đối tượng" báo nghi thì phải kéo theo TÌM LẠI, không chỉ ẩn overlay.**
  Đo 23-11 (phiên `demoip_1123-092343`, remote máy lạnh be trơn): cổng báo đúng ở f264, tầng hiển thị
  ẩn ô/mask, **nhưng** `ReIdSession` vẫn `state = tracking` **48/312 bước (15,4 %)** trên **áo người**
  (score 1,2–4,5; `mask_area` med 43 512 px) ⇒ không vào nhánh mất-dấu ⇒ **Re-ID không được gọi lần
  nào** dù remote ở giữa khung; 47 bước cuối người dùng thấy "không có gì". Nay `IdentityWatch` →
  `ReIdSession.set_suspicious(True)` ⇒ bước kế tiếp **bỏ track + đi tìm lại** (giữ mẫu tham chiếu),
  cờ tự xoá khi nhận lại/`c`/`r`; phím `c` dùng `InferenceWorker.reanchor()` (GIỮ mẫu Re-ID).
  **Cấm** quay lại kiểu "ẩn là đủ". Cờ này cũng là đường **chống nhiễm bộ nhớ**: bước bị nghi không
  nạp mẫu vào `_obj_refs`/neo.
- **Hai cổng nhảy KHÔNG cùng thước đo — đừng thay cái này bằng cái kia.** Cổng hiển thị
  (`identity_guard.search_window_radius`) bị chặn trần **200 px** (0,25×đường chéo khung 640×480);
  cổng nội bộ `reid._is_suspicious_jump` cần **1,5 × đường chéo ô** (ô 127×269 ⇒ **446 px**). Cùng
  phiên 23-11: cổng hiển thị báo ở **204 px**, cổng nội bộ **không bao giờ** báo. Và cả hai đều **mù
  với trôi dần** (ô bò 60–150 px/bước sang máy lạnh/poster/áo) — muốn bắt phải có mô hình chuyển động
  (Kalman/LK), việc > 4 h ⇒ plan 3 ý kiến trước.
- **Phiên 23-11 chốt thêm 3 bằng chứng ÂM TÍNH cho "cổng tự phán quyết":** `ncc` nhận lại ĐÚNG
  0,686/0,687/**0,468** vs ứng viên SAI bị veto 0,472/0,528 (⇒ **cấm** nâng `ncc_min` 0,40→0,55);
  `mask_area` lớn nhất chỉ **2,0×** trung vị (⇒ cổng diện tích không cứu được) và `fill` med 0,77
  (bình thường); `track_cos` vùng sai 0,45–0,79 nằm trong dải ca đúng.

- **Veto mặt phải kiểm HÌNH HỌC, không chỉ "chồng lên ô mặt".** Đo 23-11 (phiên `demoip_1123-095901`):
  remote 103×267 (tỉ lệ w/h **0,39**) giữ ngay cạnh mặt (tỉ lệ 0,78) ⇒ **322 ứng viên bị veto** dù ncc
  0,56–0,71, hệ ngồi "TỰ TÌM LẠI" **160/254 bước (64 %)** trong khi remote **to rõ giữa khung** ở
  t≈16 s (`data/tmp_analyze_1123/b400.jpg`). Nay `_trung_mat` chỉ coi ứng viên là mặt khi **tỉ lệ w/h**
  0,6–1,7× và diện tích 0,4–6,0× của chính mặt đó — dây phân biệt là TỈ LỆ KHUNG, không phải diện tích.
- **Đừng so cosine giữa hai LOẠI mặt nạ khác nhau.** Khi tìm lại, `_match_object` chấm đặc trưng trên
  **ô chữ nhật** (không có mask thật) còn `_obj_refs` là đặc trưng của **mask SAM** ⇒ cosine bị hạ hệ
  thống (đo: đúng vật chỉ 0,68–0,73 < ngưỡng 0,75). Nay có thêm `_obj_refs_box` (mẫu chấm cùng cách) và
  `raw = max(mẫu-mask, mẫu-ô)`. **Chưa chốt** là đủ để vượt 0,75 — phải đo phiên mới; HUD in
  `khop X / can 0.75` là chỗ lấy số để chốt ngưỡng, đừng hạ ngưỡng bằng cảm tính.

- **ĐỪNG lưu "mẫu đặc trưng trên ô chữ nhật" để so với ứng viên khi tìm lại.** Thử 23-11 rồi phải
  REVERT: mẫu-ô gồm cả nền ⇒ `cos(tường, mẫu-ô)` = **0,779** (mẫu-MASK chỉ 0,457) ⇒ vượt ngưỡng 0,75
  và **nhận lại SAI vào tường/cửa** (phiên `demoip_1123-101110`: reacquired f118 cos **0,976** / ncc
  **0,484**, rồi bám tường ~100 bước; `mất dấu 1 %` — chỉ số ĐẸP mà bám sai, `nghi_doi_tuong` 0 dòng).
  Quy luật đọc số: **cos cao + ncc thấp = khớp đặc trưng nhưng không khớp pixel**. Muốn cứu ca "vật
  trong khung mà không nhận lại" thì phải **xác minh bằng mask thật** (re-prompt SAM rồi chấm
  mask-vs-mask), không phải đổi loại mặt nạ của mẫu.
- **Veto mặt: chặn theo HÌNH HỌC là đúng, nhưng nó KHÔNG phải thứ chữa "không nhận lại được".** Sau khi
  nới veto (chỉ chặn ô giống hình mặt), phiên `demoip_1123-101110` có `vetoed = 0` và vẫn bám sai —
  vì cổng chính là cosine. Đừng quy lỗi "không nhận lại" cho veto mà không nhìn `reid_score`/`ncc`.
- **CƠ CHẾ ĐÚNG ĐỂ "TỰ TÌM LẠI" LÀ KHÔNG ĐÓNG BĂNG LAN TRUYỀN — KHÔNG PHẢI RE-ID.** Đo 23-11
  (`data/ab_binh1_*`, `git_rev f065a98`, `git_dirty_code = false`, **3+3 lần chèn kẽ, cả 6 lần giống
  nhau tới 4 chữ số**), clip `data/binh1.mp4` @192, `bbox 300,275,150,410`, 333 frame, chấm
  `./run miou score --gt docs/gt/b1`: **A** (`--reid --reid-cue object --reid-obj-threshold 0.75
  --reid-obj-ncc-min 0.40`) → mIoU **0,4236**, `mất dấu 5/333`, mask NGOÀI GT **43,1 %** (tệ nhất
  **100 %**), f181/f211/f241 = **0,0016 / 0,0 / 0,0**; **C** (không `--reid`, `--lost-after-frames 999
  --lost-score-threshold -99`) → mIoU **0,7794**, `113/333`, ngoài GT **0,6 %**, f181/f211/f241 =
  **0,7994 / 0,8495 / 0,8435**. C **trùng khít** `data/miou_b1_2026-11-20_metrics.json` ⇒ artifact
  20-11 là **lan truyền liên tục**, KHÔNG phải re-ID (đừng trích nó làm "bằng chứng re-ID chạy được").
  ⇒ (a) re-ID **nhận lại SAI** trên clip này, mà HUD lại đẹp nhất từ trước tới giờ (`5/333`): đúng dạng
  "chỉ số đẹp, kết quả sai"; (b) nút thắt thật là **cổng đóng băng** `--lost-after-frames` (mặc định
  **2**): đóng băng thì pipeline **không gọi SAM 2 nữa** ⇒ model mất khả năng tự bám lại và mọi trách
  nhiệm dồn cho re-ID; (c) vì thế 9 commit sửa ngưỡng/mẫu/loại mặt nạ re-ID ngày 23-11 **không thể**
  cứu demo — chúng tối ưu sai cơ chế. Plan + 2 vòng phản biện:
  `docs/plan/23-11-2026-chon-co-che-tu-tim-lai.md`.
- **A/B trên FILE phải chạy thẳng `tools/run_live.py`, TUYỆT ĐỐI không qua `./run view`.** `./run view`
  = `--display --smooth --reid --image-size 384`; `--smooth` trên file dùng `LatestFrameSource` (chỉ giữ
  frame mới nhất) ⇒ **mất frame** và ra số vô nghĩa (lần đầu tôi đo được "mất dấu 36/40" trong khi
  chạy đúng chỉ mất 4/40). Muốn chấm mIoU cho phiên CLI thì dùng
  `--dump-mask-frames 0,30,... --dump-mask-dir <dir>` (thêm 23-11): tên file theo **số frame video**,
  mask RỖNG vẫn ghi, mask `None` thì không ghi file + cảnh báo, có `manifest.json` để `score_miou`
  đối chiếu. Trước 23-11 chỉ `tools/live_worker.py` (đường web) xuất được mask.
- **Telemetry tìm lại: `reid_score = -1` KHÔNG nói được gì; phải đọc `cand_n` + `cos_truoc_cong`.**
  `-1` xuất hiện ở cả ba ca khác nhau: không có ứng viên nào qua prefilter NCC (`cand_n = 0`), ứng viên
  có cos 0,70–0,74 bị ngưỡng chặn (`cand_n > 0`), và cả frame `tracking`. Phiên `095901`: 175/254 dòng
  `-1`, trong đó 170 dòng `ncc = -1` (bộ sinh rỗng) và 5 dòng `ncc` 0,33–0,40 (cổng NCC loại) — nếu
  chỉ đọc `-1` thì kết luận "bộ sinh rỗng" là **suy diễn**, không phải số. Từ 23-11 CSV có
  `cos_truoc_cong` (cos cao nhất chấm TRƯỚC mọi cổng) và `cand_n` (số ứng viên đã chấm); `verify_cos`
  ghi ở **cả** nhánh xác minh thất bại (ca cần soi nhất).
- **Re-ID "bịa mask" khi vật đã rời khung — đo được, 5/5 frame.** Cùng bộ dump với mIoU ở trên
  (`data/ab_binh1_*_lan1_masks/`, 23-11): tại các frame GT **rỗng** (121/151/272/302/332 — vật đã
  cất), nhánh **có re-ID** trả mask **33 199 / 37 574 / 6 385 / 34 696 / 52 056 px** (tường, áo,
  điều hoà), còn nhánh **lan truyền liên tục** trả **0 px ở cả 5 frame**. ⇒ Lý do tồn tại của cổng
  đóng băng ("chống SAM 2 tưởng tượng mask khi vật đã rời khung") **không đúng trên clip này**: thứ
  tưởng tượng mask là re-ID chứ không phải model. Muốn nói "re-ID có ích" thì phải có clip mà vật
  **thật sự rời khung rồi vào lại** + mIoU chứng minh, repo **chưa có** clip đó.
- **Cổng xác minh mask-vs-mask PASS trên vùng SAI — đo trực tiếp, đừng chỉnh ngưỡng cos.** Telemetry
  sau khi sửa (23-11, `data/ab_binh1_reid_lan1_2026-11-23_metrics.csv`, `git_rev 2fb1455`): pipeline
  nhận lại ở f116 (`reid_score` 0,841 · ncc 0,614), rồi `verify_cos` = **0,8707** (f117) và **0,8746**
  (f118) — **PASS** cả hai frame xác minh — mà lần nhận đó vẫn **SAI** (IoU mask vs GT tại f181 =
  **0,0016**). Trước đó f113/f114 có `cand_sinh_n = 14` (bộ sinh đưa ra 14 ô) mà `cand_n = 0` và
  `cand_ncc_loai = 0` ⇒ thủ phạm là **`_filter_by_radius`** (vùng tìm nở dần), **không** phải bộ sinh
  và **không** phải cổng NCC. Hai hệ quả: (a) `cand_n = 0` một mình KHÔNG nói "bộ sinh rỗng" — phải
  đọc kèm `cand_sinh_n`/`cand_ncc_loai`; (b) muốn nói "cổng xác minh chặn được vùng sai" thì phải có
  ca vùng sai mà cổng trả cos **thấp** — repo **chưa có** ca đó, các ca đã đo đều 0,75–0,99.
  Và `verify_cos` nằm ở các frame **SAU** frame nhận lại (`verify_frames = 2`), không phải frame nhận.
- **ĐÍNH CHÍNH 23-11 (sau khi đọc artifact bằng CSV, không bằng mắt) — 4 câu tự viết trước đó đều sai:**
  (a) **"SAM 2 gần như không bao giờ trả rỗng" CHỈ đúng cho `rawrakhung`** (0/652 — cảnh tĩnh có điều
  hoà trắng + poster nên lúc nào cũng có thứ để bám). Trên `binh1` **113/333** frame rỗng (`--no-reid`)
  và `be2` **81/444** ⇒ đừng khái quát từ một clip. Đáng chú ý: binh1 **có re-ID chỉ còn 5/333 frame
  rỗng** — re-ID **lấp** chỗ rỗng bằng mask bịa, nên "ít mất dấu" trên HUD là dấu hiệu **xấu**, không
  phải tốt.
  (b) **"re-ID chậm ~8 frame khi vật vào lại" SAI**: độ trễ **cấu trúc 1 frame** (`reid_reacquire_confirm=2`:
  f344 `state=reacquiring`, `reid_score 0,842` > ngưỡng 0,75, `cand_n=7`; f345 mới `reacquired=1`).
  Cái đo được chỉ là **4 frame GT sau khi vật về đều thấp hơn** (chênh 0,003–0,058).
  (c) **"cổng xác minh LOẠI đúng vật vừa vào" SAI** — không có `vetoed`, không phải veto; nguyên nhân là
  `confirm=2` ở (b). Ngược lại cổng đó **PASS một phantom**: f338 `reacquired=1` (28 181 px) → f340
  `verify_cos = 0,856` → f343 `lost`. ⇒ cổng mask-vs-mask vừa **bỏ sót** vùng sai vừa **chấp nhận** nó.
  (d) **"nhận bừa 1 lần ở f280" thiếu mức độ**: trên `be2` có **25 lần `reacquired=1`**, trong đó **23
  lần nằm trong cửa sổ vắng (253–337) và mỗi lần sống đúng 1 frame**, `mask_area` 257 → **22 202 px**,
  `score` **17,0–18,1** (cao nhất phiên — tức điểm tin cậy *khen* đúng cái sai), `track_cos = None`
  **25/25**. Đây là **mẫu hình**, không phải sự cố lẻ.
  (e) **`track_cos` KHÔNG có mẫu nào trên nhánh `--no-reid`** (`src/live_pipeline.py:237,454` gán cứng
  `None`) và **`None` ở 25/25 frame `_reacquire`** ⇒ mọi kết luận "cos tách được" đo trên nhánh re-ID
  (nhánh đã bị A/B bác), và cos **mù đúng chỗ** re-ID bịa mask. Muốn dùng cos làm cổng thì phải bịt
  hai lỗ này trước rồi **đo lại**.
  (f) **`score` không cùng thang giữa hai chế độ**: frame `engine.start()` cho **17–22**, frame
  `process()` cho **4–10** ⇒ **cấm** dùng một ngưỡng tuyệt đối chung (θ=4,0 cho FP 0,7 % trên clip này
  và **52,8 %** trên clip khác).
- **`--lost-after-frames` (cổng "đóng băng") KHÔNG có tác dụng gì khi KHÔNG bật re-ID** — cơ chế đóng băng
  nằm trong `ReIdSession`, không phải vòng lặp pipeline. Đo 23-11 (cùng clip/GT, @192, `git_dirty_code=false`):
  `binh1` không re-ID **0,7794** ở cả cổng đóng lẫn cổng mở. Bảng 2×2 đầy đủ: `binh1` — không re-ID **0,7794**,
  có re-ID **0,4236**, re-ID + cổng mở 0,7794; `clip_be2` — không re-ID **0,8754**, có re-ID 0,8577,
  re-ID + cổng mở **0,5668** (mask tràn ngoài GT 19,6 %). ⇒ **re-ID không thắng ô nào trong 4 ô**, và "muốn để
  model tự bám lại" = **tắt re-ID**, không phải chỉnh cờ. Từ 23-11 `./run demoip` mặc định `--no-reid`
  (bật lại bằng `--reid`); mặc định của `tools/run_live.py` KHÔNG đổi để artifact cũ tái lập được.
  Đường lui: tag `demo-ok-23-11` + nhánh `backup/demo-ok-23-11`.
- **Cổng "nghi đổi đối tượng" từng là CÔNG TẮC TẮT VĨNH VIỄN khi không có re-ID.** Đo phiên thật
  `demoip_1123-144505`: latch bật ở f144 rồi không có gì xoá (`reacquired_count=0`, `reselect_n=0`) ⇒
  **50/194 frame = 25,8 % phiên TRẮNG hoàn toàn** dù vật vẫn rõ trong khung (ảnh giây 20,5). Trước đó re-ID
  nhận lại thành công sẽ reset latch; tắt re-ID là mất luôn cơ chế đó. Nay "nghi" vẽ **ô NÉT ĐỨT vàng + nhãn
  NGHI** (`visualizer.ve_o_net_dut`), **không** tô mask/quỹ đạo, ở CẢ hai đường (`visualizer.render`,
  `live_tracking._annotate`); `no_evidence` (ô do LK suy diễn) vẫn ẩn sạch theo luật 21-11. Cấm quay lại
  "ẩn sạch khi nghi" mà không có cơ chế reset.
- **`--record` ghi 1 frame cho mỗi frame HIỂN THỊ ⇒ video NGẮN hơn thực gian**. Đo phiên `demoip_1123-144505`:
  suy luận thật **30,76 s** nhưng `_web.mp4` = **625 frame @30 fps = 20,83 s** (nhanh **1,48×**); diễn tập live
  (model 100 ms, hiển thị 20 fps, 6,08 s) cho **2,27 s** = thiếu **62,7 %**. Nay `Visualizer._write()` giữ nhịp
  theo đồng hồ thực (`int((now-t0)*fps)+1`, lặp frame đang vẽ, trần `_MAX_LAP_FRAMES=60` + **REBASE** khi vượt
  trần), và cờ `pace_realtime` **chỉ bật cho nguồn LIVE** (`tools/run_live._la_nguon_live`): nguồn file phải ghi
  1:1 đúng fps clip (clip 333 frame = 11 s, không phải 29 s). Đo lại sau khi sửa: **4,6 %** sai lệch.
  Cấm trích "quỹ đạo theo thời gian thực" từ một video ghi trước 23-11 mà không kiểm thời lượng.
- **HUD từng in "MẤT DẤU — TỰ TÌM LẠI" khi `--no-reid`** — hứa một việc hệ không làm được, và câu đó đi vào
  video nộp bài. Nay `visualizer.lost_banner_text(tu_tim_lai)` chọn câu theo khả năng THẬT, `reid_enabled` được
  set ở cả `smooth_display` và `live_pipeline`; mặc định `False` (không biết thì không hứa). Khi thêm đường
  vẽ mới: phải đi qua `lost_banner_text`, đừng viết chuỗi mới.
- **Số hiệu năng chỉ được trích theo TỈ LỆ, không trích ms tuyệt đối làm số công bố.** Đo 23-11 trên cùng
  một code, máy có `loadavg` 6,2–8,2 (agent khác chạy `pytest`/`npm`): file **201–223 ms**, relay **211–393 ms**;
  lúc máy rảnh (`loadavg` 1,5–4,3) cùng code cho **206/303 ms** và **293/321 ms** — tức **2–3× chậm hơn** số
  lưu trữ (87–103 ms) chỉ vì trạng thái máy. Vì thế `run_info.json` từ 23-11 ghi `loadavg_1m`/`cpu_count`/
  `live_workers_khac`; **thiếu `loadavg` thì con số không được vào báo cáo**. Cũng đừng trích
  "live chậm 1,8× so với file" — hai số đó lấy từ hai artifact khác ngày, `n = 1`, và hôm nay đo chèn kẽ
  **không tách được**.
- **`--smooth` (đường `./run demoip`) KHÔNG có LK** — `grep light_tracker src/smooth_display.py` = 0; LK chỉ
  ở `live_tracking` (đường web/worker). Câu trong mục này *"live 108 ms mà hình vẫn 30 FPS là nhờ luồng riêng
  + LK"* **chỉ đúng cho đường web**. Với CLI, overlay là kết quả VOS gần nhất vẽ lên frame mới, và nhịp vẽ thật
  là **20,3 tick/s** vì `smooth_display.py` ngủ `1/30 s` **sau** khi đã làm việc (16 + 33 ms) — chính là gốc
  của "video nén 1,48×" trước ngày 23-11. Đừng tối ưu LK cho demo CLI; đừng hứa 30 FPS cho CLI.
- **Vòng đọc nguồn cũ chạy hết tốc lực: relay ảnh JPEG 16 fps bị đọc 263–293 lần/s.** Đo 24-11 trên relay
  thật: `LatestFrameSource` đọc **263 lần/s** cho nguồn 16 fps ⇒ 18 lần giải mã JPEG vô ích mỗi khung,
  1,6 MB/s loopback, **0,36 lõi (8 % của 4,3 lõi)**. Nay có `max_fps` (nguồn live 30, nguồn file `None`) và
  ngủ theo **mốc đầu vòng**; đo lại: **60 lần/2 s = 30/s**. Nguồn **file** còn đọc **715 lần/s** (giải mã clip
  20 lần, ffmpeg mở 8 luồng tranh torch) — chưa sửa, cần quyết "skip hay block".
- **"Quỹ đạo 100 điểm" KHÔNG phải "quỹ đạo theo thời gian".** Cùng 100 điểm = **16 s** ở 6,3 bước/s nhưng
  **32 s** ở 3,1 bước/s ⇒ đại lượng đổi nghĩa theo tốc độ máy. Từ 24-11 có `--trajectory-seconds` (cắt theo
  mốc thời gian của từng điểm); `./run demoip` dùng **5 s**.
