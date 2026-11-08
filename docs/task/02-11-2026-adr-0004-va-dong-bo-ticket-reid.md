# Ngày 02-11-2026 — Trả lời "đã tới bước áp dụng model chưa" + viết ADR-0004 + đồng bộ ticket/doc

> Phiên nối tiếp 01-11 (hiệu chỉnh ngưỡng re-ID trên 2 clip thật → `ncc_min = 0,35`).
> Hôm nay: **quét lại toàn bộ source** để trả lời câu hỏi "cần làm gì tiếp, đã tới lúc áp dụng model
> chưa", rồi làm nốt phần tài liệu đang treo (ADR-0004) và đồng bộ ticket/README.

## 🎯 Mục tiêu
- Quét source + ticket + log để xác định **việc còn thiếu** (không đoán theo trí nhớ).
- Trả lời dứt điểm: **model đã được áp dụng vào hệ thống chưa, ở mức nào**.
- Viết **ADR-0004** (mở rộng tái nhận diện từ khuôn mặt sang vật thể) — việc đã nằm trong
  "Next steps" của log 27-10 mà chưa làm.
- Đồng bộ trạng thái **ticket 09 / 11** theo bằng chứng thật (không tự nhận "done" khi còn thiếu số đo).

## 📥 Input
- Yêu cầu người dùng: *"quét source cần làm thì tiếp, tới thời điểm áp dụng model chưa"*.
- Repo hiện trạng: 99 commit, cây làm việc sạch, commit cuối `7f5b2a3` (01-11).
- Nguồn số liệu dùng để viết ADR: `docs/research/06`, `docs/research/07b/07c`, log `27-10-2026`,
  `data/reid_2clip_calib.json`, commit `9c65c6b` (kết quả hiệu chỉnh), `.scratch/.../issues/10,11,13`.

## 🔨 Công việc đã thực hiện

1. **Quét source (đọc, không sửa):**
   - `src/` 13 module; `tools/` 6 CLI; `tests/` 25 file; `configs/default.yaml`; `.scratch/.../issues/` 13 ticket.
   - Grep `TODO|FIXME|NotImplemented|placeholder` → **không có việc treo trong code** (chỉ 1 `NotImplementedError`
     của lớp cơ sở `VideoSource.read` — đúng thiết kế, và 1 test tên "placeholder").
   - Đối chiếu 13 ticket: 1–8 `resolved`, 10/12/13 `done`, **9 `claimed`**, **11 `ready-for-agent`**.
   - Kiểm tra sự có mặt của model: `samurai/sam2/checkpoints/` có **4 checkpoint** (tiny 156 MB đang dùng),
     `models/face/` có **YuNet 232 KB + SFace 38,7 MB**.
   - Kết luận "đã áp dụng model chưa": **rồi, từ 16-10** — `src/tracker_engine.py` bọc SAM 2.1 tiny
     (config SAMURAI) ở chế độ streaming per-frame; SAMURAI giữ nguyên Kalman + memory bank;
     thêm 2 model ONNX cho re-ID khuôn mặt (ADR-0003); phần vật thể **cố ý không dùng model** (ADR-0004).
2. **Viết `docs/adr/0004-mo-rong-tai-nhan-dien-tu-khuon-mat-sang-vat-the.md`** (mới, ~100 dòng):
   bối cảnh (ADR-0003 chỉ phủ khuôn mặt, trái yêu cầu 2 của đề cương), 6 quyết định, lý do,
   **bảng bằng chứng đo** (845 ms → 23,8 ms; cosine 2 cặp vật; NCC 3 ca vật đen; hiệu chỉnh 2 clip thật;
   ca bám nhầm nền), 5 phương án đã cân nhắc (loại `boxmot` vì AGPL), hạn chế & rủi ro.
3. **Đồng bộ ticket theo bằng chứng (không tô hồng):**
   - Ticket 09: thêm ghi chú — 9/10 tiêu chí xong, tiêu chí "đo video 2 người" còn **thiếu clip**, không phải việc code.
   - Ticket 11: `ready-for-agent` → **`ready-for-human`**, ghi rõ 0,35 hiện có là số của clip **ly**
     (17 đúng + 1 sai), **chưa phải chai đen** → chờ người quay clip.
4. **Sửa doc trỏ ADR (3 chỗ) + sửa số liệu lỗi thời trong `docs/team-contribution.md`:**
   - `README.md` §8: danh sách ADR 0001/0002 → thêm 0003 + 0004.
   - `docs/team-contribution.md`: thêm **dòng 14** (đóng góp "tái nhận diện VẬT THỂ" — đặc trưng thủ công
     + cascade + 3 cổng chống kẹt + công cụ hiệu chỉnh); sửa dòng 11 "ADR-0001/0002, 8 ticket, 12 log"
     → **ADR-0001→0004, 13 ticket, 28 log**; dòng cuối §5 thêm 0003/0004.
   - `docs/giai-thich-do-an.md` §bảng tra: thêm `docs/adr/0003`, `docs/adr/0004`.

## 📤 Output / Kết quả

**Cổng kiểm tra (chạy thật cuối phiên):**
- `./run lint` → **All checks passed!**
- `./run test` → **305 passed, 4 deselected** (22,54 s)

**Trả lời câu hỏi "đã áp dụng model chưa" — có, 3 tầng model:**

| Tầng | Model | Trạng thái |
|---|---|---|
| Phân đoạn + lan truyền | SAM 2.1 **tiny** (`sam2.1_hiera_tiny.pt`, 156 MB) + config **SAMURAI** (Kalman + memory bank) | **Đang chạy** trong `src/tracker_engine.py`, streaming per-frame — đo ~0,2–0,3 FPS trên CPU (ADR-0002) |
| Tái nhận diện khuôn mặt | **YuNet** 232 KB + **SFace** 38,7 MB (ONNX, OpenCV) | **Đang chạy** khi `reid_cue=face` (mặc định) |
| Tái nhận diện vật thể | **Không dùng model** — covariance + HSV hist thủ công | **Đang chạy** khi `reid_cue=object/both`; 2,9 ms/vùng |

**Việc còn thiếu sau khi quét (xếp theo chặn/không chặn):**

| # | Việc | Chặn bởi |
|---|---|---|
| 1 | Đo re-ID **2 người** (cue=face): tỉ lệ nhận lại đúng/nhầm | cần người **quay clip** |
| 2 | Chốt `reid_obj_ncc_min` trên clip **chai đen** (đang tạm 0,35) | cần người **quay clip** |
| 3 | Quay clip "vật rời khung rồi vào lại", 2 vật cùng màu, 2 vật giống hệt | cần người **quay clip** |
| 4 | Video minh hoạ tốc độ GPU (chạy headless trên Colab) | cần Colab + quota |
| 5 | `docs/team-contribution.md` vẫn ghi "128/131 test, 25 commit" | **không chặn** — nên chốt bằng số tự sinh thay vì sửa tay từng lần |

**File thay đổi:**
- `docs/adr/0004-mo-rong-tai-nhan-dien-tu-khuon-mat-sang-vat-the.md` — **mới**: quyết định + bằng chứng đo.
- `.scratch/camera-ai-realtime/issues/09-*.md`, `11-*.md` — ghi chú trạng thái thật + đổi nhãn 11.
- `README.md`, `docs/team-contribution.md`, `docs/giai-thich-do-an.md` — trỏ ADR-0004, sửa số liệu lỗi thời.

## 🐞 Vấn đề gặp phải & cách xử lý

- **Không tìm thấy repo `https://github.com/MinhDuyDEV/litter`** (yêu cầu đầu phiên): `curl`/API GitHub trả
  **404** (repo **private**), nhưng `git ls-remote` **thành công** → tài khoản trên máy đã có quyền.
  Lệnh `git clone` bị **huỷ giữa đường** (chưa cài) → chưa đưa vào repo; nếu cần, phải chốt **clone vào đâu**
  (`samurai/` đang là tiền lệ: clone ngoài, **gitignored**, không vendor).
- **Số liệu trong doc dễ trôi**: `team-contribution.md` còn "128 test / 131 test / 25 commit" trong khi
  thực tế **305 test / 99 commit**. Đã sửa phần ADR/ticket/log, **chưa** sửa số test/commit vì sửa tay
  sẽ trôi lại ngay → đề xuất sinh số tự động (xem Next steps).
- **Cám dỗ "đóng ticket cho gọn"**: ticket 09/11 đều thiếu **số đo trên dữ liệu người dùng quay**.
  Giữ mở và ghi rõ chặn ở đâu — theo ADR-0002 (báo cáo trung thực), không tự nhận xong.

## 🧩 Bổ sung cùng phiên — đóng 3 lỗ hổng theo **12 yêu cầu chính thức của GVHD**

> Người dùng dán bảng "Yêu cầu thực hiện của sinh viên" (12 mục) và yêu cầu: *"bổ sung hết đi"*.
> Đối chiếu xong thì thấy **3 chỗ hồng** (không phải việc quay clip): mục **10** thiếu "mức sử dụng
> CPU/GPU", mục **11** thiếu "thay đổi ánh sáng", mục **12** thiếu bản đối chiếu yêu cầu ↔ bằng chứng.

### 🎯 Mục tiêu (phần bổ sung)
- Đo được **CPU / RAM / GPU** cho mục "Đánh giá hiệu năng" (yêu cầu 10).
- Có phép đo **ánh sáng thay đổi** (yêu cầu 11) — trước đó **0 test** về ánh sáng.
- Văn bản đối chiếu 12 yêu cầu ↔ file + số đo (yêu cầu 12, dùng làm phụ lục báo cáo).

### 🔨 Công việc đã thực hiện (phần bổ sung)
1. **`src/resource_usage.py` (mới)** — `ResourceSampler` lấy mẫu mỗi frame:
   CPU % / RAM (đọc `/proc/self/stat` + `/proc/self/status`), lùi về `getrusage` khi không có
   `/proc`, GPU qua `torch_gpu_probe` (chỉ báo bộ nhớ đã cấp — PyTorch không có API % nhân GPU).
   **Không thêm dependency**; thiếu nguồn đo thì trả `None` (không bịa 0 — ADR-0002).
2. **`src/metrics_logger.py`** — `MetricsLogger(sampler=...)`: `log()` lấy 1 mẫu, `summary()["resources"]`;
   tách `_summary_core()` để **không truyền sampler thì hành vi cũ không đổi** (15 test cũ vẫn xanh).
3. **`tools/run_live.py`** — tự tạo sampler khi có `--metrics-csv`, in `CPU … % | RAM … MB | GPU …` cuối phiên.
4. **`scripts/experiment_lighting.py` (mới)** — hàm thuần `apply_lighting` (ép float32 trước khi nhân để
   **không tràn số uint8**) + `run_sweep` (reset engine mỗi mức sáng) + CSV/JSON/biểu đồ.
5. **Test mới**: `tests/test_resource_usage.py` (**15**), `tests/test_experiment_lighting.py` (**17**, gồm 1 slow
   chạy SAMURAI thật). Tổng làn nhanh **305 → 336**, toàn bộ **305+3 → 341**.
6. **`run`** — thêm `./run light [khung]` + `./run occl [khung]`; `./run summary` in thêm CPU/RAM và
   **bỏ qua** file JSON không phải summary phiên đo (file thí nghiệm).
7. **`docs/doi-chieu-yeu-cau-gvhd.md` (mới)** — 12 dòng yêu cầu × (file bằng chứng + số đo + trạng thái),
   bảng số liệu dùng thẳng cho báo cáo, danh sách 4 việc còn thiếu, lệnh tái tạo số.
8. **README** — 2 mục mới ("Thí nghiệm đổi ánh sáng", "Mức sử dụng CPU/RAM/GPU") + link file đối chiếu;
   **`docs/cheatsheet-lenh.md`** — 2 lệnh mới + sửa số test lỗi thời ("140+ test" → 336/341).

### 📤 Output / Kết quả (phần bổ sung)

**Cổng kiểm tra (chạy thật):** `./run lint` → **All checks passed!** · `./run test` → **336 passed,
5 deselected** (20,8 s) · `./run testall` → **341 passed** (141,9 s, gồm 5 test cần checkpoint).

**Số đo mới 1 — tài nguyên (yêu cầu 10)** `data/res_1102_summary.json`, `binh1.mp4` 6 frame, `image_size 320`:

| Đại lượng | Số đo |
|---|---|
| Độ trễ | mean **240 ms**, p95 **312 ms** → **4,18 FPS** |
| CPU | **342,3 %** (1 lõi — như `top`) ≈ **42,8 %** máy 8 lõi; đỉnh **389,7 %** |
| RAM | **620,7 MB** trung bình, **632,3 MB** đỉnh |
| GPU | `null` (máy không có GPU NVIDIA) |
| Mẫu | 6 (= số frame, mỗi frame 1 mẫu) |

**Số đo mới 2 — đổi ánh sáng (yêu cầu 11)** `data/lighting_iou_320_summary.json`, 12 khung, `image_size 320`:

| gain | 1,00 | 0,60 | 0,35 | 0,20 | 0,10 |
|---|---|---|---|---|---|
| IoU TB | **0,974** | 0,974 | 0,969 | 0,964 | **0,942** |
| IoU thấp nhất | 0,952 | 0,967 | 0,952 | 0,937 | 0,921 |
| mất dấu | 0/12 | 0/12 | 0/12 | 0/12 | 0/12 |

→ Tối 90 % ánh sáng chỉ mất **0,032 IoU**, không mất dấu. **Trung thực:** fixture tương phản cao,
chưa phải cảnh thật (nhiễu màu, sáng cục bộ) → phải quay clip thật mới kết luận.

**File thay đổi (phần bổ sung):**
- `src/resource_usage.py` — **mới**: đo CPU/RAM/GPU không thêm dependency.
- `src/metrics_logger.py` — sampler tuỳ chọn → `summary["resources"]`.
- `tools/run_live.py` — in tài nguyên cuối phiên.
- `scripts/experiment_lighting.py` — **mới**: thí nghiệm ánh sáng.
- `tests/test_resource_usage.py`, `tests/test_experiment_lighting.py` — **mới**: 32 test.
- `run`, `docs/cheatsheet-lenh.md` — 2 lệnh mới (`light`, `occl`) + summary kèm tài nguyên.
- `docs/doi-chieu-yeu-cau-gvhd.md`, `README.md` — **mới/cập nhật**: đối chiếu 12 yêu cầu + số đo.
- `data/res_1102_summary.json`, `data/lighting_iou_320_summary.json` — bằng chứng đo (whitelist git).

### 🐞 Vấn đề gặp phải & cách xử lý (phần bổ sung)
- **Tràn số uint8** khi làm tối/sáng: `250 × 2 = 244` (quay vòng) → phải ép `float32` rồi `clip`.
  Đã khoá bằng test `test_khong_tran_so_khi_tang_sang` (nếu ai "tối ưu" bỏ `astype` sẽ đỏ ngay).
- **Fake engine trong test đếm frame không reset** → `IndexError` ở mức sáng thứ 2: lỗi ở **test**, không phải code;
  sửa bằng cách reset bộ đếm trong `reset()`. Đây đúng là kiểu lỗi mà `run_sweep` phải bắt được (quên reset engine).
- **File thí nghiệm lọt vào `./run summary`** (in `? frame | 0 ms`): lọc theo khoá `total_frames`.
- **`./run light 12`**: tham số đầu là số khung — phải phân biệt với cờ (`--frames`), cùng lớp lỗi đã gặp ở
  `./run fast --reid-cue` (27-10) nên tách nhánh `[ "${1#-}" = "$1" ]`.

## 🎥 Việc webcam (usbipd kẹt `Device busy (exported)`) — **đã chuyển sang log 04-11**

> Việc này xảy ra ở phiên **04-11-2026** (không phải hôm nay), nên ghi riêng để nhật ký đúng ngày:
> `docs/task/04-11-2026-cuu-webcam-relay-http.md`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Người dùng quay 3 clip: (a) 2 người, (b) chai đen, (c) 2 vật giống hệt → chạy
      `./run fast --reid --reid-cue face|object` rồi `scripts/calibrate_reid.py` để chốt ngưỡng.
- [ ] **Webcam qua USB/IP vẫn kẹt** — nếu muốn dùng lại đường đó: `usbipd unbind --busid 2-8`
      (Admin) → **reboot** → `usbipd bind` → `./run cam attach`. Trong lúc đó dùng `./run relay` /
      `./run demoip` (đã chạy được, đo 640×480 @21 fps).
- [ ] Tắt **auto-start của Zalo** (ZaloCall/ZaloCap tự chiếm camera sau mỗi lần khởi động).
- [ ] **Nhãn phân đoạn trên ảnh thật** để có mIoU thật (hiện chỉ có IoU bbox trên fixture).
- [ ] **Sơ đồ khối + bảng phần cứng** cho báo cáo (yêu cầu 3) và **ghép báo cáo theo mẫu trường** (yêu cầu 12).
- [ ] **Motion Memory tự xây** (yêu cầu 7) — chốt phạm vi với GVHD trước (chạm lõi backbone).
- [ ] Chốt repo `litter`: clone vào đâu, dùng làm gì (chưa cài trong phiên này).
- [ ] Sinh số liệu doc tự động (số test/commit/log) để `team-contribution.md` không trôi —
      nên đi qua `/to-spec` thay vì sửa tay.
- [ ] Chạy `/retro` cho chuỗi việc re-ID (25-10 → 02-11) trước khi chốt báo cáo.
- [ ] Commit khi người dùng đồng ý (ADR-0004 + 2 ticket + 3 doc + code đo tài nguyên + thí nghiệm ánh sáng).

## 📚 Tài liệu tham khảo
- `docs/adr/0003-tai-nhan-dien-khuon-mat-yunet-sface.md` — khuôn mẫu + số đo cosine mặt trên webcam.
- `docs/research/06-nhan-dang-lai-mat-va-dac-trung-vat-the-tu-lam.md` §4.2 — vì sao covariance + HSV bù trừ nhau.
- `docs/research/07b` (long-term tracking + global re-detection), `docs/research/07c` (embedding CPU, license).
- `docs/task/27-10-2026-reid-vat-the-va-research-repo-ngoai.md` — số đo cascade 845 ms → 23,8 ms.
- `data/reid_2clip_calib.json` — bằng chứng hiệu chỉnh 17 đúng + 1 sai → `ncc_min = 0,35`.
- `data/res_1102_summary.json` — bằng chứng CPU/RAM của phiên đo 02-11 (mục 10).
- `data/lighting_iou_320_summary.json` — bảng IoU theo mức sáng (mục 11).
- `psutil` CPU percent convention (1 lõi = 100 %) — cùng quy ước với `top`/`htop`.
- SAM 2: https://github.com/facebookresearch/sam2 · SAMURAI: https://github.com/yangchris11/samurai
