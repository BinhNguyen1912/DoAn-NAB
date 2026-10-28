# Ngày 27-10-2026 — Research 3 hướng + implement re-ID VẬT THỂ (ticket 10)

> Phiên nối tiếp phiên 25-10 (log: `25-10-2026-research-tai-nhan-dien-mat-va-vat-the.md`).
> Hôm nay: dispatch scout research repo ngoài, rồi implement xong tầng re-ID vật thể.

## 🎯 Mục tiêu
- Research **các repo/dự án khác** về nhận diện 1 vật thể (3 scout song song).
- Implement **tái nhận diện VẬT THỂ** (ticket 10) để remote TV mất dấu rồi quay lại vẫn bám lại được —
  lỗi người dùng báo: *"focus được nhưng khi mất dấu đưa vào lại sẽ không nhận diện được"*.
- Giảm chi phí quét toàn khung khi mất dấu (trước đó đo 348 ô = 323 ms, không dùng được).

## 📥 Input
- Yêu cầu người dùng: *"đi research, các repo khác về phần nhận diện 1 vật thể… cử 2 3 con reviewer"*.
- Nguồn lý thuyết đã có từ phiên 25-10: `docs/research/06`.
- Repo hiện trạng: `ReIdSession` chỉ khớp **mặt** → vật không mặt thì `_refs` rỗng → LOST vĩnh viễn.

## 🔨 Công việc đã thực hiện

1. **Dispatch 3 scout song song** (task tool, mỗi con 1 file báo cáo riêng, không sửa code):
   - `07a` VOS memory & giữ danh tính (XMem/Cutie/DEVA/SAM2/SAMURAI) — **còn đang chạy** cuối phiên.
   - `07b` tracking dài hạn + tìm lại toàn cục → `docs/research/07b-repo-long-term-tracking-global-redetection.md` ✅
   - `07c` thư viện/model embedding chạy CPU → `docs/research/07c-repo-embedding-reid-library-cpu.md` ✅
   - Dặn scout dùng `curl --doh-url https://1.1.1.1/dns-query` (web tool pi hết quota + WSL DNS bị hijack).

2. **Verify lại claim của scout** (không tin báo cáo mù): fetch thẳng file LICENSE →
   `deep-person-reid` **MIT**, `fast-reid` **Apache-2.0**, `boxmot` **AGPL-3.0** (copyleft, không dùng làm
   dependency) — khớp 3/3 với báo cáo `07c`.

3. **Viết `src/appearance.py`** (mới, theo TDD — test trước):
   - `object_signature` = covariance 5×5 trên `[x_norm, y_norm, B, G, R]` + HSV hist 8×8, chuẩn hoá L2.
   - `signature_quality_ok` (cạnh ≥ 24 px, mask chiếm ≥ 50% ô), `mask_to_bbox`, `candidate_boxes`.
   - `prefilter_candidates` — **tầng 1 cascade**: NCC (`cv2.matchTemplate` TM_CCOEFF_NORMED) trên frame
     thu nhỏ 4×, mỗi tỉ lệ một suất riêng, trả top-K ô cho tầng chấm điểm đắt.

4. **Sửa `src/reid.py`**: thêm `cue="face"|"object"|"both"`, `_obj_refs`, `_obj_template`, nhánh LOST dùng
   cascade (`prefilter_candidates` → `object_signature` → `best_match`), hàm dùng chung `_reacquire`,
   thuộc tính `object_ref_count`. Mặc định `cue="face"` → **hành vi cũ không đổi**.

5. **Config**: `src/config.py` (6 key mới + `_INT_KEYS`), `configs/default.yaml` (mục mới có comment),
   `tools/run_live.py` (`--reid-cue`, `--reid-obj-threshold`; thiếu model mặt mà `cue=both` thì tự lùi về
   `object` thay vì chết).

6. **Test** (`tests/test_appearance.py` 25 test, `tests/test_reid.py` thêm 4 ca cue vật thể, có `FakeEngineMasks`
   riêng để không đụng fake cũ).

## 📤 Output / Kết quả

**Cổng kiểm tra (chạy thật):**
- `ruff check .` → **All checks passed**
- `pytest -m "not slow"` → **239 passed**

**Số đo trên laptop (i7-1195G7), frame 1280×720, vật 170×170:**

| Việc | Trước | Sau |
|---|---|---|
| Tìm lại khi mất dấu | quét lưới 379 ô → **845 ms** | cascade: NCC 4,6 ms + top-K → **23,8 ms** |
| → nhanh hơn | — | **~35×** |
| Chi phí mỗi frame TRACKING | — | `object_signature` **2,9 ms/vùng** |
| Bộ nhớ mẫu | — | 8 vector + 1 template ảnh cắt (RAM) |

**Chất lượng khớp của `object_signature` (đo trên fixture tổng hợp, ground truth biết trước):**

| Ca | Cosine |
|---|---|
| cùng vật, dịch nhẹ | **1,000** ✅ |
| cùng màu, không hoa văn | 0,581 ✅ |
| khác màu, cùng hoa văn | 0,327 ✅ |
| hai vật giống y hệt | 1,000 ❌ (đúng dự đoán — ca này chỉ cue thời gian giải) |

**File thay đổi:**
- `src/appearance.py` — **mới**: đặc trưng vật thể + cascade tìm lại.
- `src/reid.py` — thêm cue vật thể, `_reacquire`, `_match_object`, `object_ref_count`.
- `tests/test_appearance.py` — **mới**: 25 test (thuần numpy, không cần checkpoint).
- `tests/test_reid.py` — thêm `FakeEngineMasks` + 4 ca cue vật thể.
- `src/config.py`, `configs/default.yaml`, `tools/run_live.py` — 6 key cấu hình + 2 CLI flag.
- `docs/research/07b-*.md`, `docs/research/07c-*.md` — báo cáo scout (mới).
- `.scratch/camera-ai-realtime/issues/10-*.md` — ticket (claimed, 5/6 criteria).

## 🐞 Vấn đề gặp phải & cách xử lý

1. **NMS xuyên tỉ lệ giết mất ô đúng.** Ban đầu gộp ứng viên của 3 tỉ lệ rồi NMS chung → ô 30×30 (tỉ lệ 0,75)
   chồng lên ô 40×40 (tỉ lệ 1,0) và loại nó → ô nhận lại lệch 14 px. **Sửa:** mỗi tỉ lệ một suất riêng
   (`per_scale_k`), không NMS xuyên tỉ lệ — vì điểm NCC giữa các tỉ lệ **không so sánh được** (template đã resize).
2. **Ô cắt bên trong vật thắng cosine.** Ô 30×30 nằm trong vật 40×40 được 0,930 còn ô đúng cỡ chỉ 0,886 →
   chọn sai cỡ. **Sửa:** *size prior* mềm `sqrt(min(area,target)/max(area,target))` để **chọn** ô, nhưng
   ngưỡng chấp nhận vẫn xét **cosine thô** (không phạt vật đến gần/ra xa).
3. **Test đầu tiên khẳng định px tuyệt đối (≤6 px) → fail.** Đúng ra prefilter ở downscale 4 chỉ là bước đề
   xuất thô, sai số ±4 px/cạnh là **theo thiết kế** → đổi sang chuẩn **IoU ≥ 0,5** (cùng chuẩn đã dùng cho
   `candidate_boxes`), kèm comment giải thích.
4. **GitHub API hết rate limit** (60 req/giờ, 3 scout dùng hết) → verify license bằng cách fetch thẳng
   `raw.githubusercontent.com/<repo>/master/LICENSE` thay vì field API.
5. **Ngày hệ thống là 27-10, không phải 25-10** → log phiên trước giữ nguyên tên (đúng ngày viết);
   phiên này tạo log riêng ngày 27-10.
6. **Sai lầm tự phát hiện:** tiêu đề `07c` bị lẫn chữ "partner" → đã sửa.
7. **Không commit** gì trong phiên này (người dùng chưa yêu cầu). Working tree vẫn còn 3 file bẩn từ trước
   (`data/smooth_metrics.csv`, `data/smooth_summary.json`, `docs/DoAnCameraAI.docx`) — **không đụng**.

## 🧪 Bổ sung cuối phiên — chạy trên dữ liệu THẬT của người dùng

Hai clip người dùng quay (`data/binh1.mp4`, `data/binh2.mp4`) — **chưa clip nào tạo được sự kiện mất dấu**:

| Clip | Thông số | Bbox frame 0 (x,y,w,h) | Chạy | Kết quả |
|---|---|---|---|---|
| `binh1.mp4` | 333 frame, 720×1280, 30 fps, 11 s | `104,308,209,287` | 130 frame, cue=object | mean **761 ms**, FPS 1,31, **lost=0** |
| `binh2.mp4` | 360 frame, 720×1280, 30 fps, 12 s | `83,291,160,285` | 180 frame, cue=object | mean **742 ms**, FPS 1,35, **lost=0** |
| `binh2` cửa sổ f200–320 | cắt ra để bắt chỗ mặt biến mất f231–237 | `164,338,242,286` | 120 frame | mean **756 ms**, **lost=0** |

**Kết luận đo được:** YuNet không thấy mặt ở 2/120 mẫu (f231, f237) nhưng **SAM 2 vẫn bám** (mask không rỗng)
→ *mặt bị che/quay đi KHÔNG phải mất dấu*. Cả hai clip đều giữ người trong khung (tâm mặt x chỉ dao động
163–372 trên khung rộng 720) nên **nhánh re-ID không được gọi lần nào**.

**Mô phỏng mất dấu (chèn 20 frame đen vào `binh1`, bỏ 30 frame) — cơ chế chạy ĐÚNG:**

| Frame | Trạng thái | Điểm khớp |
|---|---|---|
| 0–59 | tracking | — |
| 60 | lost=1 (mask rỗng) | — |
| 61 | lost (đóng băng) | — |
| 62–79 | reacquiring | **0,444** (bị loại, < 0,6) |
| **80** | **reacquired** | **0,918** |
| 81+ | tracking | — |

Kiểm chứng bằng YuNet *chỉ để đối chiếu*: tâm ô nhận lại (78, 474) **nằm trong** mặt phát hiện được → bám đúng người.
Chi phí: đang bám **702 ms/frame**, lúc tìm lại **59 ms/frame** (nhanh ~12× vì không gọi SAM 2).

**Còn thiếu để chốt:** clip có **vật thật rời khỏi khung** ≥ 2–3 giây rồi vào lại chỗ khác — hiện chỉ có 1 ca mô phỏng,
chưa đủ để chốt ngưỡng `reid_obj_threshold` (0,6).

### Lệnh tắt mới thêm trong phiên này
`./run reid <video> <x,y,w,h> [--max-frames N]` — headless, ghi `data/reid_hud.mp4` + CSV + JSON
(kèm 1 test trong `tests/test_run_script.py`).

### Bổ sung 2 — sửa 4 lỗi sau khi người dùng test webcam (chai đen bị mất dấu)

| # | Lỗi | Bằng chứng | Cách sửa |
|---|---|---|---|
| A | Dòng log `./run demo` in **sai cue** (dùng `${REID_CUE}` thay vì đọc `--reid-cue`) | log in `cue=face` trong khi pipeline in `[re-ID] bật cue=object` | `scripts/demo_webcam.sh` đọc cờ từ chính dòng lệnh; kiểm chứng 2 chiều |
| B | `frame_idx` lùi trong CSV | `reset()`/`start()` zero hoá bộ đếm của session, và `start()` **không** đóng dấu → engine trả 0 | bỏ zero hoá, đóng dấu trong `start()`; verify 95 frame → **đơn điệu True** |
| C | Ô chọn quá nhỏ vẫn được nhận | đo thật: ô rác `42×60` → SAM 2 bám loạn rồi mất dấu | `MIN_BOX` 5 → **16** + in cảnh báo |
| D | Vật ĐEN: cosine không phân biệt (hai vật đen khác nhau = 1,000) | đo fixture §4.4 báo cáo 06 | thêm **cổng NCC** `reid_obj_ncc_min` (mặc định 0 = tắt) + cột `ncc` vào CSV (ghi cả frame bị loại) |

**Số đo verify trên `binh1_simloss.mp4` (95 frame, cổng NCC = 0,5):**
- `frame_idx` đơn điệu: **True** (0→94)
- nhận lại **1 lần** tại f80: cos=**0,918**, ncc=**0,858** → cổng 0,5 cho qua (đúng)
- lúc tìm: cos=0,444 + ncc ghi lại được → dùng để hiệu chuẩn

**Cảnh báo rút ra từ chính số thật:** ca nhận lại **đúng** có `ncc = 0,858` → nếu đặt cổng 0,95 như đề xuất từ fixture
thì sẽ **chặn nhầm**. Vì vậy mặc định vẫn TẮT; nếu bật thì dùng khoảng **0,5–0,6** và phải đo lại trên clip thật.

**Trạng thái kiểm tra:** `ruff check .` xanh · `pytest -m "not slow"` → **251 passed** · `./run charts` chạy OK.
Ticket 12 → **done** (4/4). Ticket 11 → 5/6 (còn hiệu chuẩn trên clip thật).

### Bổ sung 3 — lần chạy THẬT của người dùng SAU khi sửa (`./run demo --reid-cue object`, 213 frame)

| Chỉ số | Trước khi sửa | Sau khi sửa |
|---|---|---|
| frame mất dấu | 207/257 (**81%**) | 25/213 (**12%**) |
| lần nhận lại | **0** | **6** (f33, 94, 117, 122, 159, 212) |
| `frame_idx` đơn điệu | ❌ (f11..72 sau f180..186) | ✅ 0..212 |
| cột `ncc` trong CSV | ❌ | ✅ có giá trị |
| FPS | 3,03 | 2,74 (mean 366 ms) |

Điểm khớp của 6 lần nhận lại: cos 0,671–0,955 · ncc 0,646–0,992 → **cả 6 đều qua ngưỡng 0,6**.

**Cảnh báo trung thực:** các lần mất dấu đều chỉ **1–2 frame** (mất "nháy") → đây là nhận lại sau **rớt mask ngắn**,
**chưa phải** ca "vật rời khỏi khung vài giây". Quỹ đạo có **37 cú nhảy > 80 px** giữa 2 frame liên tiếp (tb 57 px/frame)
— ở 2,7 FPS thì việc tay di chuyển nhanh cũng gây nhảy lớn, nên **phải xem video HUD** (`data/webcam_smooth.mp4`)
để phân biệt "tay di chuyển nhanh" với "nhảy sang vật khác".

## 📌 Việc cần làm tiếp (Next steps)
- [x] Chờ scout `07a` (VOS memory) → **timeout 30 phút**, đã tự viết bù `docs/research/07a-repo-vos-memory-identity.md`.
- [ ] Quay **clip vật thật rời khỏi khung** (remote: đặt xuống bàn → nhấc ra khỏi khung 2–3 s → đặt lại chỗ khác).
- [ ] **Quay clip thật** (remote + vật cùng màu + 2 vật giống hệt) → hiệu chỉnh `reid_obj_threshold`
      (hiện 0,6 là số khởi điểm, chưa có dữ liệu thật).
- [ ] Viết **ADR-0004** (mở rộng re-ID từ khuôn mặt sang vật thể; ADR-0003 vẫn giữ cho phần mặt).
- [ ] Chạy `tools/run_live.py --reid --reid-cue object --source <clip thật>` để đo end-to-end (FPS, tỉ lệ nhận lại).
- [ ] Cân nhắc v2: **mạng embedding nhỏ tự train** (0,66 MB, 0,72 ms — xem `docs/research/07c` §6).
- [ ] Commit khi người dùng đồng ý (gồm code + 3 báo cáo research + ticket).

## 📚 Tài liệu tham khảo
- `docs/research/07b-repo-long-term-tracking-global-redetection.md` (SPLT skim cascade, TLD cascade,
  DaSiamRPN-LT hysteresis, KeepTrack, LTMU) — nguồn của thiết kế cascade 2 tầng.
- `docs/research/07c-repo-embedding-reid-library-cpu.md` (license, OSNet x0.25 = 0,2 M params,
  Deep SORT arXiv:1703.07402 dùng mạng 2,8 M params train triplet trên crop tự gãn — chuẩn ngành cho v2).
- `docs/research/06-nhan-dang-lai-mat-va-dac-trung-vat-the-tu-lam.md` — số đo 3 cue + quyết định kiến trúc.
- arXiv:2411.11922 (SAMURAI), arXiv:2207.07115 (XMem), arXiv:1708.00197 (VS-ReID).
- File LICENSE đã đọc trực tiếp: `KaiyangZhou/deep-person-reid` (MIT), `JDAI-CV/fast-reid` (Apache-2.0),
  `mikel-brostrom/boxmot` (AGPL-3.0).
