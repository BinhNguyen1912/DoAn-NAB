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
2. Thực hiện code/thay đổi.
3. Chạy kiểm tra trước khi kết thúc bằng **lệnh tắt của repo** (`run` tự chọn đúng môi trường Python):
   - **Lint:** `./run lint` — CI chạy đúng lệnh `ruff check .`; phải xanh.
   - **Làn nhanh** (UI/logic/config — ~30s): `./run test` — CI chạy `pytest -m "not slow"`.
   - **Full suite** (cần checkpoint SAM 2): `./run testall` — chỉ khi đụng
     `tracker_engine`/model/CLI model hoặc trước commit cuối.
   - **Frontend:** `./run webtest` (vitest, hàm thuần) khi sửa `web/src/**`.
   - **E2E trình duyệt thật** (Chrome/Edge + Playwright, cần Windows): `./run e2e` — bắt buộc trước khi
     báo "xong" cho bất kỳ thay đổi nào ở UI/API (nó đã bắt được 3 bug thật ngày 08-11: canvas
     300×150, codec mp4v không phát được, và job báo `done` trước khi xuất H.264).
4. **Tạo/cập nhật file log trong `docs/task/` theo mục 2** (template: `docs/task/_template.md`) — bước BẮT BUỘC cuối mỗi phiên.
5. Tóm tắt lại cho người dùng: đã làm gì, file nào thay đổi, bước tiếp theo.

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
- **SAM 2 không tất định**: cùng seed, cùng video, hai lần chạy cho ô bao cuối khác nhau ⇒ chỉ so
  sánh chỉ số **trong cùng một lần chạy**.
- **Báo cáo và handoff kèm số từ CSV** (`mean`, `p95`, `mất dấu`, `reacquired`), không mô tả cảm tính.

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
