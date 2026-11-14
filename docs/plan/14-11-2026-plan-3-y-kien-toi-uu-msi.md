# Plan 14-11-2026 — Làm gì tiếp trên MSI (plan 3 ý kiến §9.2, có audit bbox)

> Plan này trả lời câu "**bây giờ nên làm những gì**" sau khi đọc handoff
> `docs/plan/14-11-2026-toi-uu-bam-sat-tren-msi.md`. Plan handoff đó bàn *tối ưu ms*; plan này
> quyết định *thứ tự thi hành* bằng 3 góc nhìn độc lập + 1 vòng phản biện (AGENTS.md §9.2).
> **Chưa có dòng code nào được viết trong phiên lập plan này** — file này là quyết định để phiên sau code.

## 🎯 Câu hỏi cần quyết
- Trong ~2 tuần còn lại, trên **đúng máy demo MSI Modern 14 B11MOU** (i7-1195G7, Iris Xe, 16 GB,
  không CUDA, WSL2, `/proc/cpuinfo` **không** có `avx512_bf16`/`amx_bf16`), nên làm **việc nào trước**
  để sản phẩm "bám bắt đối tượng realtime" **vừa chạy được lúc bảo vệ, vừa có số bảo vệ được** —
  mà không train lại model, không mua phần cứng, không cloud?
- Ràng buộc: mọi số trích ra phải có `git_rev` + `git_dirty_code == false` + `lenh` + `do_luc`;
  so sánh A/B phải chạy **xen kẽ trong một phiên** (ngưỡng nhiễu: `drift_iou` ±0,004,
  `vos_fps` ±1,2 %, `mask_age_p95` ±3 ms, chênh **giữa phiên** đo được tới **16 %**).

## 🔎 Bằng chứng mới — audit bbox (chính phiên này, tự kiểm bằng ảnh frame 0)

**Các ô chọn đang dùng cho mọi số live KHÔNG nằm trên vật.** Ảnh kiểm (đã commit) ở `docs/media/bbox/`:

| Clip | Kích thước thật | bbox đang dùng (mặc định của 3 script) | Ô thực chất phủ | Ô đúng |
|---|---|---|---|---|
| `data/binh1.mp4` | **720×1280**, 333 frame | `104,308,209,287` | ❌ **KHUÔN MẶT người** (chai nằm ngoài hộp, bên phải) | `300,275,150,410` |
| `data/binh2.mp4` | **720×1280**, 360 frame | `200,400,300,500` | ❌ **2 chai + 2 bàn tay** (cắt mất nắp chai trắng) | `330,330,150,360` |

- Đo bằng `cv2.VideoCapture` trên chính `data/*.mp4` (14-11): `binh1` = `1280×720`, `binh2` = `1280×720`.
  Nhưng `docs/task/08-11-2026-do-lai-do-phan-giai-va-kich-thuoc-model.md:10` ghi
  *"bbox `104,308,209,287` (vật thể, **640×480**)"* → **sai cả nhãn vật lẫn độ phân giải**.
- `104,308,209,287` là **mặc định** của `scripts/profile_stages.py:69`,
  `scripts/benchmark_light_trackers.py:92`, `scripts/measure_watchdog.py:327` ⇒ số mới rơi vào lỗi cũ.
- **21 artifact** trong `data/*.json` chứa bbox này (gồm 3 lần baseline 13-11
  `live_web_relay_2026-11-13_1256|1257|1258`, `drift_samples_binh1_*`, `drift_samples_tinh_binh1_*`).
- Hệ quả (không phải suy đoán, mà là điều kiện thí nghiệm): "khuôn mặt" là vật **to, tương phản cao,
  gần như đứng yên** ⇒ mọi chỉ số trên `binh1` (`drift_iou` 0,866–0,871, `vos_fps` 6,1–6,4,
  `mask_age_p95` 271–273,5 ms) là **cận trên lạc quan**, và `binh2` ("mất dấu 21,8 %", `p05 = 0,00`,
  `empty_runs = 26`) là **confound do ô chọn**, không đo thuật toán.
- ⇒ **Chưa có một số live nào trong repo đo đúng "bám cái chai".** Việc số 1 của plan là đóng lỗ này.

## 🧭 Ba góc nhìn (vòng 1 — độc lập, không biết nhau)

### A. Chất lượng & số đo
- Trước hết phải có **thước đo "bám đúng"**: hiện **0 file GT mask** trong `data/`; `drift_iou`/`stability`
  bị AGENTS §6 cấm dùng làm độ chính xác. Đề xuất **nhãn điểm thưa** (`recall_in` = điểm-trong vật được
  mask phủ, `precision_out` = điểm-ngoài bị phủ tràn, `bam_sai`) qua `scripts/label_points.py` +
  `scripts/eval_points.py`, GT thiếu ⇒ **từ chối chấm**, mask rỗng mà có điểm-trong ⇒ `recall = 0`.
- Sửa ô chọn trước khi dán nhãn (nếu không, 4 h dán nhãn đo cái hộp sai).
- Kèm: 3 clip kịch bản (che kín 2 s / ra–vào khung / 2 vật giống nhau), fixture có **vật cản đi ngang**
  (hiện `src/synthetic_video.py:83-90` tô vật cản bằng **màu nền** ⇒ model thấy "vật biến mất",
  không phải "vật bị che"), hiệu chuẩn `object_score_logits`.
- Chỉ chọn 1 việc: dựng thước đo điểm thưa (mở khoá mọi nghiệm thu khác).

### B. Sản phẩm & bằng chứng bảo vệ
- Repo **không có 1 file ảnh/video nào đã commit** (`git ls-files '*.png' '*.mp4'` = 0) ⇒ clone mới
  hay máy demo hỏng là **mất toàn bộ phần "nhìn thấy"**. Riêng `docs/media/` **không** bị `.gitignore`.
- Rủi ro sân khấu chưa ai kiểm: **kéo chuột chọn đối tượng trên web với camera thật chưa từng chạy**
  (e2e chỉ phủ clip tổng hợp 160×120) — mà đó là 30 giây đầu của buổi demo.
- Bài nói "mất dấu thì dừng chứ không bám sang vật khác" **sai với bản web**: `status_payload`
  không có `object_score`, đường live **không có re-ID/re-anchor** (grep = 0).
- Bằng chứng "camera thật" chỉ có **1 artifact, n=1**, và ô chọn nằm trên **vùng tối nền** cảnh tĩnh.
- Chỉ chọn 1 việc: diễn tập trọn kịch bản trên máy demo bằng **1 lệnh** + quay lại chính lần diễn tập.
- Phản đối mạnh: dành 2 tuần cuối cho 4 hướng tối ưu ms (mua ~0 độ tin hội đồng) và cho việc port re-ID
  vào live (1–3 ngày, đụng file nóng, có thể phá mốc 29,9 FPS HUD).

### C. Độ bền & hiệu năng
- Lỗi nguy hiểm nhất: **crash trông y như "thầy bấm dừng"** — `src/live_tracking.py:424-431` `finally`
  đặt `STATE_STOPPED` vì `self._error` chỉ được đặt bởi luồng VOS; `src/api/adapters/worker_source.py:190-198`
  ánh xạ `stopped` → `STOPPED` **bất kể mã thoát** ⇒ traceback chết tiến trình mà UI báo "worker đã kết
  thúc phiên". Đường vào thật: `engine.start()` với bbox xấu (`:401`, chạy **inline** sau khi API đã
  `running`), `_source.read()` ném, `.open()` nằm **ngoài** `try` (`:379`).
- `mask_age`/`vos_ms` **không** gồm `_to_input_tensor` (`src/tracker_engine.py:185` trước `t0` ở `:188`)
  ⇒ mọi `vos_ms` trong `data/` thấp hơn thực ~5,65 ms; `mask_age_p95` cộng **một** `vos_ms` hiện tại
  cho mọi mẫu lịch sử.
- Không cần hạ tầng mới: `measure_live_relay.py:369-404` **đã** có provenance; `repeatability.py`
  có sẵn nhưng **0 caller** ⇒ thiếu **kỷ luật chạy xen kẽ**, không thiếu công cụ.
- Chỉ chọn 1 việc: biến mọi ngoại lệ vòng lặp chính thành `state=error`.

## ⚔️ Tranh chấp (vòng 2 — phản biện chéo)

| Điểm tranh chấp | A nói | B nói | C nói | Chốt |
|---|---|---|---|---|
| Việc đầu tiên | dựng thước đo điểm thưa (4 h) | `./run democheck` + diễn tập (5–7 h) | crash ⇒ `error` (2,5 h) | **Audit bbox trước tất cả (1 h)** — cả 3 đều bỏ sót; phản biện vòng 2 phát hiện ô `binh1` nằm trên **mặt** ⇒ dán nhãn/diễn tập/crash đều đứng sau nó |
| Có làm `bf16` (hướng #1 của handoff) | KHÔNG (không có `avx512_bf16`, chỉ còn emulation; không có GT để phát hiện hỏng) | KHÔNG (không mua được độ tin) | KHÔNG (rủi ro ngang INT8, đã đo **chậm hơn** 196 vs 166 ms) | **Bác** — giữ làm "kill-test 20 phút" tuỳ chọn, chỉ nhận nếu encoder giảm > 10 % **và** không hồi quy |
| Đổi nhịp mask (`--vos-hz` theo thời gian) | không nhắc | không nhắc | đề xuất (3,5 h) rồi **tự bác**: every=2 → 7,5/s < every=3 → 8,65/s; quan hệ **không đơn điệu** | **Bác** — thay bằng **đo chu kỳ** (`pre/post/idle/cycle`) 1 h, chỉ mở lại nếu `idle_ms` chứng minh có frame bị bỏ |
| `mask_age_p95 ≤ 200 ms` (tiêu chí handoff) | không nhắc | sàn ≈ 2 × `vos_ms` ⇒ bất khả thi ở 192 | age ≈ `vos_ms + 1/vos_fps + pre` ≈ 272 ms (khớp 271–273,5 đo được) | **Đổi tiêu chí, không đổi số**: chỉ khả thi nếu hạ `image_size` 160 (104,9 ms) mà chất lượng nằm trong nhiễu; ngược lại **công bố 250–270 ms** |
| `num_maskmem` / `image_size` sweep | 2 việc riêng (3 h) | không nhắc | gộp 1 chủ, chỉ đo (5 h) | **Gộp thành 1 bảng quyết định** (3 h) trên fixture che khuất + 3 lần live/mức `image_size`, phải có ngưỡng nhiễu in kèm |
| `object_score` lên HUD | hiệu chuẩn AUC ≥ 0,8 rồi thành cờ | thêm vào HUD (6–8 h) | thêm dữ liệu 20 phút, AUC sau | **Chỉ thêm `score` vào `status.json`/CSV (20 phút); KHÔNG hiện lên HUD** — ca "bám nhầm nền" đã ghi `score +19,40` (rất tự tin và sai); badge dùng `lost_streak`/`empty_frac_window` đã có |
| Relay `--fourcc MJPG` + `measured_fps ≥ 25` | không nhắc | đề xuất (2–3 h) | **đã đo 13-11: MJPG = YUY2 = 16,6 FPS**, và `measured_fps` đang 29,9 khi camera chỉ 16,6 ⇒ tiêu chí **luôn xanh** | **Bác** (nghiệm thu giả) — nếu cần số camera thật thì đo **khung mới/giây tại consumer** (md5), ~30 phút |
| Harness A/B riêng (4 h) | không nhắc | thay bằng checklist | đề xuất rồi **tự thu xuống 1,5 h** | **1,5 h** — thêm `--label`, kết luận "khác biệt / không phân biệt được", cấm trộn số hai ngày trong một bảng |
| GT mask dày 10 clip × 100–200 frame | không đề xuất (quá đắt) | bác (20–40 h) | không nhắc | **Bác** — thay bằng 5–10 frame nhãn tay trên clip đúng bbox (tuỳ chọn 2–4 h) |
| Port re-ID vào đường live | không nhắc | bác (rủi ro phá mốc realtime) | không nhắc | **Bác trong 2 tuần này**; phải **nói trước** với hội đồng: cơ chế có ở đường CLI, đường web chưa nối |

## ✅ Quyết định

- **Chọn:** thứ tự **1 → 7** dưới đây (core **≈ 18 h**), phần "tuỳ chọn" chỉ làm khi còn giờ:

| # | Việc | Giờ | Nghiệm thu CÓ SỐ |
|---|---|---|---|
| 1 | **Audit bbox + vô hiệu hoá số cũ**: ảnh kiểm vào `docs/media/bbox/`; sửa `docs/task/08-11…:10` (720×1280, "ô phủ khuôn mặt"); đánh dấu **21 artifact** + đổi default bbox của `profile_stages.py`/`benchmark_light_trackers.py`/`measure_watchdog.py` | 1 | 4 ảnh trong `git ls-files docs/media/bbox`; `grep -rn "104,308" scripts/` = 0; mỗi artifact cũ có cờ `CANH_BAO_bbox_mat` trong log |
| 2 | **Crash ⇒ `error`**: `health()` coi `code != 0` là ERROR bất kể `state`; ngoại lệ vòng lặp chính ⇒ `state=error` + message; `_rewind()` chỉ cho nguồn file | 1,5 | 4 test mới (đỏ trước – xanh sau): `_DeadProc(1)`+`stopped` ⇒ `ERROR`+`(mã 1)`; `engine.start` ném ⇒ `status.json.state == "error"`; webcam `read()`=None ⇒ **không** mở lại thiết bị; kill -9 worker ⇒ banner lỗi ≤ 1 s (baseline 116–117 ms) |
| 3 | **Baseline LẠI với ô đúng** (`binh1` `300,275,150,410`; `binh2` `330,330,150,360`), @192, `vos_every 3`, 55 s, **3 lần xen kẽ**, kèm 1 lần ô cũ làm mốc | 2 | 7 artifact `git_dirty_code=false`; bảng `vos_fps`/`mask_age_p95`/`empty_runs`/`drift_iou` kèm `drift_n`; câu kết luận 1 trong 2 dạng ("ô cũ làm số lạc quan" / "không đổi ⇒ nguyên nhân khác") |
| 4 | **Đo chu kỳ VOS**: thêm `pre_ms`/`post_ms`/`idle_ms`/`cycle_ms`; `mask_age_p95` theo **từng mẫu**; `vos_ms` gồm cả `_to_input_tensor` | 1 | giải thích **≥ 95 %** của chu kỳ (156 ms) với `vos_ms` 124 ms; có cờ `idle_ms` ⇒ quyết định đóng/mở hướng cadence |
| 5 | **Bảng quyết định cấu hình**: `image_size` {160,192,256} × `num_maskmem` {3,5,7} trên fixture che khuất (mIoU) + 3 lần live/mức `image_size`; cần sửa `build_overrides()` (`src/tracker_engine.py:35`, hiện chỉ `image_size`) | 3 | bảng có `spread`; chênh < ngưỡng nhiễu phải ghi **"không phân biệt được"**; chốt mặc định cho demo kèm mức `mask_age_p95` tương ứng |
| 6 | **Thước đo "bám đúng" (lite)**: `scripts/eval_points.py` (hàm thuần + test) + **1 clip × 12 khung × 8 điểm-trong + 4 điểm-ngoài**, nhãn dán **1 lần**, chấm trên output chạy 3 lần | 2 | `recall_in`/`precision_out` + **Wilson CI theo khung**; GT thiếu ⇒ **từ chối chấm**; mask rỗng + có điểm-trong ⇒ `0,0` (không được "không đo được"); điểm phải nằm trong **mask**, không phải bbox |
| 7 | **`./run democheck`** (không nạp model, 9 mục ≤ 120 s) + **2 lần diễn tập có log**, gồm **kéo chuột trên camera thật** (relay + MJPG), lưu `bbox_check.jpg` | 2,5 | PASS 9/9 trên máy sạch (`rm -rf /dev/shm/doan-*`); FAIL đúng 1 ca cố ý (tắt relay); 2 log diễn tập có giờ + ảnh HUD; thời gian bật→có mask ≤ 120 s |
| 8 | **HUD + `status.json`**: hiện `mask_age_p95` + `empty_frac_window` + badge **MẤT DẤU**; payload tự khai `image_size`/`vos_every`/`fps nguồn`; thêm `score` (chỉ để log) | 2 | `./run webtest` + `npm run build` + `./run e2e` xanh; `status.json` có 7 khoá mới; badge hiện khi `empty_frac_window > 0`; phiên 30 s không hồi quy (`drift_iou` ±0,004, `display_fps` ±0,3 %) |
| 9 | **Media vào git**: video demo 20–30 s ≤ 5 MB + 3 hình + **JSON provenance cạnh mỗi file** (`git_rev`/`git_dirty_code`/`lệnh`) | 1,5 | `git ls-files docs/media` ≥ 8 file; mỗi media có `.json` cùng `git_rev`; `ffprobe` = h264/yuv420p |
| 10 | **`docs/so-lieu-bao-cao.md` SINH từ artifact** (script đọc `data/*_metrics.json` → bảng, cột "**cấm trích thành gì**", kèm `n`) | 1,5 | chạy lại script ⇒ diff rỗng; mọi dòng có đường dẫn artifact; bảng phủ mIoU fixture, `drift_iou`, `mask_age_p95`, `vos/MASK fps`, số T4, watchdog |
| 11 | **A/B có kỷ luật**: `--label` cho `measure_live_relay.py`, `repeatability.py` có caller thật, in "khác biệt / không phân biệt được" | 1,5 | test null-A/B (A vs A) ⇒ **"KHÔNG PHÂN BIỆT ĐƯỢC"**; 1 bảng chứng minh 8,65 vs 6,4 mask/s là khác bối cảnh, không so được |

- **Tuỳ chọn (chỉ khi còn giờ, theo thứ tự):** GT mask tay 5–10 frame ⇒ `mIoU` trên clip thật (2–4 h,
  phải ghi "n=mẫu nhỏ") · fixture vật cản **có màu riêng** rồi đo độ trễ nhận lại **theo số lần cập nhật
  VOS** (2 h) · `object_score` AUC (2 h, chỉ làm sau #6) · kill-test `bf16` (20 phút) ·
  `np.ascontiguousarray` → `cv2.cvtColor` (bit-identical, 1,47 ms — dưới ngưỡng nhiễu, gộp vào #4).
- **Vì sao thứ tự này:** #1 sửa **điều kiện thí nghiệm** (số hiện có đang đo cái mặt); #2 bảo hiểm buổi
  demo (crash im lặng là ca tệ nhất, 1,5 h, 0 ms chi phí); #3 tạo baseline **đúng** — mọi so sánh sau
  phải cùng ô; #4–#5 trả lời "có thể nhanh/tươi hơn không" **bằng số** trước khi đụng pipeline;
  #6 là thước đo duy nhất thay được mIoU; #7–#10 biến số thành bằng chứng nộp được.
- **Bác (để sau không mở lại):** `bf16` trên CPU (không có `avx512_bf16`) · relay `--fourcc MJPG` +
  `measured_fps ≥ 25` (đã đo âm 13-11; `measured_fps` 29,9 khi camera 16,6 ⇒ tiêu chí luôn xanh) ·
  tự đổi cadence theo thời gian (`--vos-hz`) · port re-ID vào live trong 2 tuần này · GT mask dày 10 clip ·
  hiện `object_score` lên HUD (score `+19,40` ở ca bám nhầm nền) · sweep `cv2.setNumThreads` (trần 2–3 ms,
  dưới ngưỡng nhiễu) · 4 hướng tối ưu của handoff 14-11 trong cửa sổ demo này (giữ làm hướng nghiên cứu,
  không phải việc thi hành) · INT8/checkpoint to hơn/encoder-reuse/RepViT/EdgeTAM/SAM 3.1 (đã có số bác).
- **Tiêu chí nghiệm thu cấp plan (có SỐ):**
  - [ ] 100 % số live trích trong báo cáo đến từ **ô chọn đã kiểm bằng ảnh** (không còn artifact nào dùng `104,308,209,287` mà không kèm cảnh báo)
  - [ ] `./run lint` + `./run test` xanh trước mỗi lần merge; `./run webtest` + `./run e2e` xanh nếu đụng `web/`
  - [ ] Mỗi kết luận A/B có **≥ 3 lần/cấu hình, chạy xen kẽ**, kèm `spread` và nhãn "khác biệt / không phân biệt được"
  - [ ] Không có tuyên bố "mask 30 FPS"; mask nêu bằng `vos_fps` + `mask_age_p95` đo được
  - [ ] Có **≥ 1** số "bám đúng" không phải `drift_iou`/`stability` (từ #6)

## 📌 Việc tách ra ticket
- [ ] Sửa default `--bbox` của 3 script + test khoá (sau #1)
- [ ] Đánh dấu 21 artifact cũ bằng cờ cảnh báo `bbox_mat` (script nhỏ, đọc `data/*.json`)
- [ ] `score` (`object_score_logits`) vào `status.json` + `CSV_HEADER` của `src/drift_samples.py` (20 phút, phần còn lại của #8)
- [ ] Port re-ID + re-anchor vào `src/live_tracking.py` (**không** làm trong 2 tuần demo; ghi rõ lý do trong báo cáo)
- [ ] Fixture "vật cản đi ngang" **có texture riêng** trong `src/synthetic_video.py:83-90`
- [ ] `_to_input_tensor`: `np.ascontiguousarray` → `cv2.cvtColor` (bit-identical, 1,47 ms/frame)
- [ ] Đo lại 3 lần trên **webcam rời thật** khi có thiết bị (hiện mọi số live là webcam laptop qua relay)

## 📚 Tham chiếu
- Handoff nguồn: `docs/plan/14-11-2026-toi-uu-bam-sat-tren-msi.md` (+ log `docs/task/14-11-2026-handoff-toi-uu-bam-sat-tren-msi.md`), nhánh `origin/docs/handoff-toi-uu-msi`.
- Số nền: `docs/task/08-11-2026-do-lai-do-phan-giai-va-kich-thuoc-model.md` (profile tầng @192), `docs/task/08-11-2026-hybrid-vos-lk-live-30fps.md`, `docs/task/13-11-2026-ticket-15-dang-mau-drift-ra-csv.md`, `data/live_web_relay_2026-11-13_1256|1257|1258_metrics.json`, `data/drift_2026-11-08_metrics.json`.
- Bằng chứng ô chọn sai: `docs/media/bbox/*.jpg` (4 ảnh, sinh bằng `cv2` trên frame 0 của `data/binh1.mp4`, `data/binh2.mp4`).
- Ràng buộc/kinh nghiệm: `AGENTS.md` §6 (số đã đo, bẫy "0,0 là chưa đo"), §9.1 (review độc lập), §9.2 (plan này).
- ADR: `docs/adr/0001-sam2-samurai-backbone-tu-toi-uu-realtime.md`, `0002-giu-laptop-cpu-demo-live-colab-cho-offline.md`, `0005-*` (api ports&adapters).
- Nguồn ngoài (độ tin cậy khác nhau — **chưa kiểm chứng được**, đừng trích như sự thật): EfficientTAM arXiv 2411.18933 + số pooling 2×2 từ blog TT Lab; "Selective Mask Propagation" với link `arxiv.gg` (**không phải** arxiv.org).
