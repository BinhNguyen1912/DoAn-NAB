# Plan 21-11-2026 — Nhận lại vật trên đường LIVE + demo bằng WEBCAM REALTIME

> Plan theo AGENTS §9.2: 3 ý kiến độc lập (vòng 1) → 1 vòng phản biện chéo (vòng 2) → chốt.
> Bối cảnh: ticket #41 (`docs/task/21-11-2026-ticket-41-vi-sao-binh2-bam-sang-vat-khac.md`) chứng minh
> đường live **không có** cơ chế nhận lại vật: ô VOS sai **trước** khi LK bước (f162), vật vào lại thì
> bám vào **mặt người** (f228). Yêu cầu người dùng: **demo bằng webcam realtime, KHÔNG dùng video file**.

## 🎯 Câu hỏi cần quyết

Thêm cơ chế **nhận lại vật** (+ **không vẽ ô khi không có bằng chứng**) vào đường live để demo webcam
thật, trong **≤ 15 giờ**, mà **không** tái tạo lỗi "bám sang vật khác" và **không** làm hỏng các số đã
công bố. Ràng buộc: CPU only (Iris Xe); `max_mad`/`lk_scale` **không đổi** (#38/#40/PR #65 đã chốt);
webcam trong WSL phải đi qua relay (`./run relay` + `/snapshot.jpg`).

## 🧭 Ba góc nhìn (vòng 1 — độc lập)

### A. Chất lượng & số đo
V1 đo tách vật bằng `object_signature` (xong trong phiên) → **V2 bộ GT webcam** (5–6 h + 1,5 h tô) trước
khi làm tính năng → V3 cổng ô rác theo diện tích vs EMA → V4 giao thức live đếm sự kiện + nhãn mắt →
V5 **port `ReIdSession`** (20–24 h) → V6 hiệu chuẩn cổng thứ hai. Chọn 1: **V2**.

### B. Sản phẩm & bằng chứng bảo vệ
(1) nối `ReIdSession(cue=object)` **nguyên khối** vào `_VosWorker` + `reid` ra status/HUD/DTO (10–14 h) →
(2a) cổng ô rác EMA (2b) không vẽ ô khi `state != tracking` → (3) chống cờ chất lượng bắn oan →
(4) toggle runtime + checkbox (5–6 h) → (5) event log + 2 nút nhãn (5–6 h) → (6) preflight/diễn tập.
Tổng 33–39 h. "Rủi ro số 1 là chính repo (cờ đỏ), không phải model".

### C. Độ bền & hiệu năng
**KHÔNG bọc `ReIdSession`**; port logic sang `src/live_bam.py`; R1 hàng đợi lệnh `process|start` (1,5 h) →
R2 máy trạng thái `bam` + đóng băng model (2,5 h) → R3 tìm lại trong luồng VOS, ngân sách 60 ms (2 h) →
R4 một định nghĩa `shown` (1 h) → R5 nguồn không giết phiên (1,5 h) → R6 provenance + 12 test (2 h).
Tổng ~10,5 h, mặc định **OFF**.

## ⚔️ Tranh chấp (vòng 2 — phản biện chéo)

| Điểm tranh chấp | A nói | B nói | C nói | **Chốt** |
|---|---|---|---|---|
| Bọc `ReIdSession` nguyên khối? | port | **nguyên khối** | `ReIdSession` **không có** `.process` ⇒ `AttributeError` ⇒ `state=error` trong **0,12 s** | **Không bọc nguyên khối**; đường **CLI** (`./run demoip`) đã có sẵn re-ID và **đó là demo webcam chính thức**; port vào worker live là việc **sau**, dùng seam `_VosWorker.run` + adapter |
| `engine.start()` đắt? | — | "0,5–3 s, phải nói lấp" | ước 200–350 ms | **Đo được 105–139 ms ≈ 1× `vos_ms`** ⇒ dead time thật = **2 frame xác nhận ≈ 0,8–1,2 s**, không phải vài giây. C **rút R1 xuống 0,5 h** |
| Chi phí tìm lại | — | — | `search` **53 ms** (720p), worst-case **76 ms**; **1080p = 174 ms > `vos_ms` 162 ms** | Chỉ demo **≤ 720p**; in `search_ms_p95` ra `status.json`; **bỏ** `top_k=8` (cắt shortlist trước cổng danh tính) và **bỏ** `budget 60 ms` (p95 135 ms ⇒ tự bỏ đúng frame chậm) |
| Ưu tiên #1 | GT webcam (5–6 h) | cờ chất lượng | sửa cổng nhảy | **Metric trước, GT sau**: `ty_le_o_ma` tính được **hôm nay** trên 9 frame `gt_rong` có sẵn (binh2 4 + b1 5), ~2 h |
| Ngưỡng nhận lại | phải hiệu chuẩn lại | không nhắc | không nhắc | **Đã có hiệu chuẩn 2 phía trong repo**: `data/reid_2clip_calib.json` (01-11): cosine **không tách được** (sai 0,899 > đúng min 0,770), NCC tách được (sai 0,279 < đúng min 0,415) ⇒ **`ncc_min = 0,35`**; nhưng `DEFAULT_OBJ_NCC_MIN = 0.0` (**TẮT**) và comment biện minh viết **29-10 — trước** bản hiệu chuẩn 3 ngày |
| Ẩn ô khi nào | theo `state` | theo `state != tracking` | **diện tích** | **Cả hai sai**: `state` web chỉ có `stopped/loading/running/error`; đường hybrid vẫn bám bằng LK khi model mất dấu. Đúng: **"không có bằng chứng"** = `lk_ok=False` **hoặc** `lost_streak ≥ 2`, **hoặc** mask rỗng (trễ 2 frame), **cộng** cổng diện tích `max(300 px, 0,2×EMA)` chỉ để bắt ô teo |
| GT webcam (A-V2) | việc #1 | cắt | ngoài đường tới hạn | **Cắt**: 7 h, và **không** chứng nhận được buổi diễn (ánh sáng/vật khác). Thay bằng: sàng vật demo bằng `object_signature` (1,5 h) + quay màn hình |

### Phát hiện mới trong vòng phản biện (đắt hơn mọi việc trong 3 đề xuất)

**P0 — cổng "nhảy bất thường" tự huỷ lần nhận lại** (`src/reid.py:477-495` + `:516-530`): `_reacquire`
đặt `state=TRACKING` + `_verify_left` nhưng **không** cập nhật `_last_bbox`; tick sau `_is_suspicious_jump`
so với **mốc trước khi mất dấu** ⇒ vật vào lại ở chỗ khác > `1,5 ×` đường chéo ô ⇒ `_auto_recover()` ⇒
**làm lại từ đầu**: 2× `engine.start` (~210–280 ms) + 1 frame không có ô + **bỏ qua `verify_frames`**.
Khớp dữ liệu thật: phiên `--reid` có **3 lần "reacquired" liên tiếp f172/176/180** cho **một** lần vật
vào lại. Đây đúng là kịch bản demo ⇒ **sửa trước mọi thứ khác**.

**Đo được (phiên `tools/run_live.py --reid --reid-cue object`, `binh2`, 275 frame):** tracking mean
**162 ms**/p95 295 · lost mean **53 ms** · `engine.start` **105–139 ms** · `lost 16/275 (6%)` · 5 lần
`reacquired`. **`score`** (đường live **đang vứt**, 0 lần dùng dù `tracker_engine.py:57` có): khi lost
median **0,00**, **5/5 frame ≤ 0**; nhưng trong đoạn vật vắng, re-ID vẫn `tracking` với score **+5…+18**
(f180 **+18,45**) ⇒ **cổng `score` KHÔNG bắt được "bám sai vật khi vẫn tracking"** (f162→f163).

## ✅ Quyết định

- **Chọn:** 6 việc, **~12 h**, theo thứ tự **P1 → P2 → P3 → P4 → P5 → P6**:
  1. **P1 (1 h)** Vá P0: `_reacquire` cập nhật `_last_bbox` (+ `_collect_reference` đúng lúc) + test hồi quy
     bằng engine giả (đỏ khi bỏ dòng đó).
  2. **P2 (0,5 h)** Bật cổng NCC đã hiệu chuẩn **trên đường demo**: `run demoip`/`fast` truyền
     `--reid-obj-ncc-min 0.35` + in dòng `[re-ID] ncc_min=0.35` (**không** đổi `configs/default.yaml`).
  3. **P3 (2 h)** `ty_le_o_ma` trong `ab_o_hien_thi_vs_gt.py` (`hop_tu_gt` trả cả `gt_rong`) + proxy
     `o_ma_gia` trên CSV drift; `schema` 7; test.
  4. **P4 (4 h)** Lớp trung thực: `bam` (`tracking`/`no_evidence`), `refs_n`, `reacq_score` ra `status.json`
     + HUD ASCII + ẩn ô khi **không có bằng chứng** (trễ 2 frame); **không** đẩy mẫu drift ở frame
     `reacquired` vào cửa sổ sức khoẻ; giữ nguyên 4 giá trị `state`.
  5. **P5 (3 h)** Port tìm lại vào `_VosWorker` **sau** khi P2/P5-on-CLI đã diễn tập: `start` là job xếp
     hàng trong luồng VOS, `search` ≤ 60 ms mỗi **2** chu kỳ VOS, **không** tính tick tìm lại vào
     `vos_runs/vos_ms`, fail-open (lỗi ⇒ quay về `process`, không bao giờ `state=error`).
  6. **P6 (1,5 h)** Diễn tập webcam: `./run demoip` 3 lần + quay màn hình + `./run democheck --full --bbox`
     + commit artifact có `git_rev`/`git_dirty_code`.

- **Vì sao:**
  - P1 là **bug chặn demo** (tự huỷ lần nhận lại) và **1 dòng**; cả 3 đề xuất vòng 1 đều bỏ sót.
  - P2 dùng **hiệu chuẩn đã có trong repo 3 tuần** (`data/reid_2clip_calib.json`) thay vì tự hiệu chuẩn
    lại trên 1 clip (cosine 0,981/0,862 của phiên này là **cận trên lạc quan**: ADR-0004 trên 17 ca đúng
    cho thấy cosine **chồng lấn** 0,899 vs 0,770, và **nền** cũng đạt 0,835 ⇒ 0,60 nhận cả nền).
  - P3 biến "vẽ ô khi không có vật" thành **số** bằng GT **đã có**, không cần tô mới — đây là metric **duy
    nhất** phạt được kiểu "cổng luôn trả lời" (hôm nay `hop_tu_gt` **bỏ** `gt_rong` nên không ai bắt).
  - P4 là thứ hội đồng **nhìn thấy**: ô phải **biến mất** khi hệ thống không có bằng chứng, và HUD phải
    nói `TIM LAI 0,86` chứ không phải `VOS 0 ms`.
  - P5 mới đem re-ID lên **web**; nếu hết giờ thì **beat demo diễn trên `./run demoip`** — vẫn là webcam
    realtime, cùng engine, có cửa sổ chọn vật bằng chuột, và **được nói rõ** là web chưa có tìm lại.

- **Bác (để không mở lại):**
  - **Bọc `ReIdSession` nguyên khối**: nó **không có** `.process` ⇒ `AttributeError` ⇒ `state=error`
  trong **0,12 s** (watchdog đã đo 116–117 ms) ⇒ sân khấu chết, không cứu được bằng nút Dừng.
  - **Module mới `src/live_bam.py` chép logic**: nhân bản ≥ 10 hàm đã hiệu chuẩn (`_filter_by_radius`,
  `_confirm`, `_verify_ok`, `_reacquire`, `_match_object`, `_size_ema`, `_is_suspicious_jump`…) ⇒ hai bản
  lệch nhau, và mọi A/B offline sẵn có (`run_live.py --reid*`) **không còn dự báo** được hành vi live.
  - **Bộ GT webcam 7 h**: không chứng nhận được buổi diễn; `n = 12` ⇒ `p05 = None` theo luật repo.
  - **Nâng `obj_threshold` cosine lên 0,87/0,90**: mất 3–4/17 ca đúng mà **vẫn** lọt ca sai 0,899.
  - **Toggle re-ID runtime + checkbox + event-log UI** (11–12 h): không thêm bằng chứng nào; thay bằng
    cờ CLI + dòng log in ngưỡng.
  - **Đóng băng hiển thị khi `lost`**: đường hybrid vẫn bám bằng LK; hiện là "vẫn bám" chứ không phải
    "dừng" ⇒ phải ẩn ô theo **bằng chứng**, không theo `state`.
  - **Demo ở > 720p**: `search` 1080p = **174 ms > `vos_ms` 162 ms** ⇒ mask đứng hình đúng lúc cần nhất.

- **Tiêu chí nghiệm thu (có SỐ):**
  - [ ] P1: test engine giả "nhận lại cách 200 px, ô 40×40" ⇒ `engine.start` gọi **đúng 1 lần**,
    `state=tracking` **5 frame liền** (hiện tại: **2 lần start** + 1 frame mất ô); test **ĐỎ** khi xoá
    dòng `self._last_bbox = ...` trong `_reacquire`.
  - [ ] P2: `./run demoip` in `ncc_min=0.35`; `scripts/calibrate_reid.py` trên `data/reid_2clip_calib.json`
    vẫn **17/17 ca đúng được nhận**, **1/1 ca sai bị chặn**; ghi caveat **`n_bad = 1`**.
  - [ ] P3: artifact in `n_gt_rong = 9`, `n_co_o_tren_rong`, `ty_le_o_ma` **kèm n** (n = 9 ⇒ báo **đếm**,
    không báo %); proxy `o_ma_gia` có `n` + `empty_n`; `iou_mean` **không đổi** (test hồi quy);
    `schema` 7.
  - [ ] P4: trên `binh2` replay: **0 frame** có ô khi `bam = no_evidence`; `refs_n ≥ 1` sau khi chọn;
    **0** `drift_trend` trong 3 s sau một cụm `reacquired`; `state` vẫn 4 giá trị (test cũ xanh).
  - [ ] P5: `binh2` @192/`vos_every 3`, chèn kẽ ON/OFF **3 lần**: `measured_fps ≥ 28` khi lost;
    `cycle_ms` p95 ≤ 280; `n_reacq ≥ 3`; `start_ms` p95 ≤ 160; "vật vào lại → có ô" ≤ **1,4 s**;
    `vos_runs` **không** đổi khi có tick tìm lại (test).
  - [ ] P6: 3/3 lần diễn: `refs_n ≥ 1`, `n_reacq ≥ 1`, 0 nhận nhầm **nhìn thấy**; `./run democheck --full
    --bbox` thoát 0; artifact `git_dirty_code=false`.

## 📌 Việc tách ra ticket
- [ ] #41 (đã resolved) — nguyên nhân gốc f163/f228 là base VOS.
- [ ] **Ticket mới**: "bám sang vật khác khi VẪN tracking (f162→f163)" — **không** việc nào trong 12 h này
  sửa được; `auto_recover` hiện chỉ bắt nhảy > 1,5 × đường chéo (f162→163 nhảy ≈ 229 px < ngưỡng 520 px).
  Phải nói thẳng trong báo cáo là **chưa sửa**.
- [ ] **Ticket mới**: hiệu chuẩn `ncc_min` với **≥ 3 ca sai** (hôm nay `n_bad = 1`) trên clip có chai đen.
- [ ] **Ticket mới**: `refs_n = 0` khi ô chọn dính mép → hiện cảnh báo lên **web** (hiện chỉ in stdout).
