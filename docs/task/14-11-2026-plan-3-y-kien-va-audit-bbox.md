# Ngày 14-11-2026 — Plan 3 ý kiến (§9.2) + audit ô chọn: phát hiện mọi số live đang đo KHUÔN MẶT

## 🎯 Mục tiêu
- Trả lời câu hỏi của người dùng: *"bây giờ nên làm những gì"* — sau khi đã đọc handoff
  `docs/plan/14-11-2026-toi-uu-bam-sat-tren-msi.md` (phiên 14-11 bàn 6 hướng tối ưu, chưa code).
- Bắt buộc theo AGENTS.md §9.2: việc > 4 giờ / đổi đường live ⇒ phải có **3 ý kiến độc lập + 1 vòng
  phản biện** rồi mới chốt. Handoff 14-11 tự ghi *"phiên này CHƯA chạy vòng §9.2"* ⇒ phiên này chạy.

## 📥 Input
- Nhánh `origin/docs/handoff-toi-uu-msi` (commit `8346def`, 2 file docs, chưa merge vào `main`).
- Máy: MSI Modern 14 B11MOU — i7-1195G7 (4 nhân/8 luồng), Iris Xe, 16 GB, không CUDA, WSL2.
  `/proc/cpuinfo`: có `avx512f/bw/dq/vl/vnni/vbmi/vbmi2/vp2intersect`, **KHÔNG** có `avx512_bf16`,
  **KHÔNG** có `amx_bf16` (xem "Vấn đề gặp phải").
- Dữ liệu: `data/binh1.mp4` (720×1280, 333 frame), `data/binh2.mp4` (720×1280, 360 frame),
  `data/binh1_simloss.mp4` (720×1280, 323 frame), 21 artifact JSON dùng bbox `104,308,209,287`.
- 3 agent `general` vòng 1 (chất lượng & số đo / sản phẩm & bằng chứng / độ bền & hiệu năng) +
  3 agent vòng 2 (phản biện chéo, mỗi agent nhận tóm tắt của cả 3 đề xuất).

## 🔨 Công việc đã thực hiện
1. **Kéo code**: `git fetch --all --prune` → `main` = `7c47db1`, **0 commit** sau `origin/main`;
   prune 10 nhánh đã merge; chỉ 1 nhánh mới chưa merge: `origin/docs/handoff-toi-uu-msi` (+1 commit).
2. **Đọc + đối chiếu handoff với code thật** (không tin văn bản): grep `reid|reanchor` trong
   `src/live_tracking.py` + `tools/live_worker.py` → **0**; `ls data/ | grep -iE 'gt|mask'` → không có
   GT mask nào (chỉ `lighting_iou_*` = IoU hộp bao); `src/video_source.py:132-140` (MJPG+640×480 chỉ khi
   Linux) và `scripts/probe_cam_fps.py:45` (hardcode `CAP_DSHOW`) đúng như handoff nói.
3. **Kiểm giả thuyết phần cứng của handoff** bằng `/proc/cpuinfo` → **`avx512_bf16` KHÔNG có**
   ⇒ câu "Tiger Lake có AVX512-BF16" trong handoff sai; hướng #1 chỉ còn đường bf16-emulation của oneDNN.
4. **Chạy vòng 1** (3 agent song song, độc lập). Kết quả gọn:
   - A (chất lượng): cần **thước đo "bám đúng"** trước (nhãn điểm thưa `recall_in`/`precision_out`/`bam_sai`),
     vì `data/` không có GT và `drift_iou`/`stability` bị cấm dùng làm độ chính xác.
   - B (sản phẩm): repo **0 file ảnh/video đã commit**; rủi ro sân khấu chưa ai kiểm là **kéo chuột trên
     camera thật** (e2e chỉ phủ clip tổng hợp 160×120); bài nói "mất dấu thì dừng" sai với bản web.
   - C (độ bền): lỗi nặng nhất là **crash trông y như "bấm dừng"** (`src/live_tracking.py:424-431` +
     `src/api/adapters/worker_source.py:190-198`); `vos_ms`/`mask_age` bỏ tiền xử lí 5,65 ms;
     baseline live 3 lần = `vos_ms` 124,0/118,0/125,7 · `vos_fps` 6,4/6,4/6,1 · `mask_age_p95` 271,0/271,0/273,5.
5. **Chạy vòng 2** (3 agent phản biện chéo). Các điểm bị bác/đổi ý:
   - **B bị bác**: `--fourcc MJPG` + `measured_fps ≥ 25` (MJPG = YUY2 = 16,6 FPS đã đo 13-11;
     `measured_fps` đang 29,9 khi camera chỉ 16,6 ⇒ tiêu chí **luôn xanh**); commit mp4 vào git (vi phạm
     AGENTS §4) ⇒ thay bằng ảnh + JSON provenance.
   - **C tự bác**: `--vos-hz` theo thời gian (every=2 → 7,5/s < every=3 → 8,65/s ⇒ quan hệ không đơn điệu);
     `mask_age` "thiếu `vos_ms`" (đã cộng rồi, `live_tracking.py:711`).
   - **A bị bác phần**: "chốt 1 đường đo `vos_fps`" (chỉ có **một** nguồn: `worker_source.py:148` đọc lại
     `status.json` của worker); sweep `image_size` riêng (trùng bảng đã có) ⇒ gộp vào bảng quyết định.
   - **Cả 3 đều bỏ sót** (phát hiện ở vòng 2, rồi tôi tự kiểm lại): **ô chọn `binh1` phủ KHUÔN MẶT**.
6. **Audit ô chọn (tự kiểm bằng ảnh, không tin agent)**: đọc frame 0 của `binh1`/`binh2` bằng
   `.venv/bin/python` + `cv2`, vẽ hộp cũ và hộp mới, xem ảnh bằng mắt:
   - `data/binh1.mp4` = **720×1280** (log 08-11 ghi "640×480" → sai), bbox `104,308,209,287`
     phủ **khuôn mặt**; chai nằm ngoài hộp; ô đúng cho chai: `300,275,150,410`.
   - `data/binh2.mp4` = 720×1280, bbox `200,400,300,500` phủ **2 chai + 2 bàn tay** (cắt mất nắp);
     ô đúng cho 1 chai: `330,330,150,360`.
   - Bbox `104,308,209,287` là **mặc định** của `scripts/profile_stages.py:69`,
     `scripts/benchmark_light_trackers.py:92`, `scripts/measure_watchdog.py:327`; **21 artifact** trong
     `data/*.json` chứa nó.
7. **Viết plan** `docs/plan/14-11-2026-plan-3-y-kien-toi-uu-msi.md` theo `docs/plan/_template.md`
   (câu hỏi, 3 góc nhìn, bảng tranh chấp, quyết định 11 việc ≈ 18 h, danh sách bác, tiêu chí nghiệm thu).

## 📤 Output / Kết quả
- **Không sửa code.** Không có số đo mới của model (chỉ audit ảnh + dữ kiện phần cứng).
- Thứ tự thi hành đã chốt (core ≈ 18 h):
  1. Audit bbox + vô hiệu hoá số cũ (1 h) — 4 ảnh kiểm trong `docs/media/bbox/`, sửa log 08-11,
     đổi default bbox 3 script, đánh dấu 21 artifact.
  2. Crash ⇒ `state=error` (1,5 h).
  3. Baseline **lại** đúng ô: `binh1 300,275,150,410` / `binh2 330,330,150,360`, 3 lần xen kẽ (2 h).
  4. Đo chu kỳ VOS `pre/post/idle/cycle` (1 h) — chốt hướng cadence bằng số, không bằng đoán.
  5. Bảng quyết định `image_size` {160,192,256} × `num_maskmem` {3,5,7} trên fixture che khuất (3 h).
  6. Thước đo "bám đúng" lite: nhãn điểm thưa + Wilson CI theo khung (2 h).
  7. `./run democheck` 9 mục + 2 lần diễn tập (gồm **kéo chuột trên camera thật**) (2,5 h).
  8. HUD `mask_age_p95` + badge MẤT DẤU + `status.json` khai cấu hình (2 h).
  9. Media + provenance vào `docs/media/` (1,5 h). 10. `docs/so-lieu-bao-cao.md` **sinh từ artifact** (1,5 h).
  11. Kỷ luật A/B xen kẽ + `repeatability.py` có caller (1,5 h).
- Bị bác (kèm lý do): `bf16` (không có `avx512_bf16`) · relay MJPG/`measured_fps ≥ 25` · `--vos-hz` ·
  port re-ID vào live trong 2 tuần demo · GT mask dày 10 clip · `object_score` lên HUD · sweep
  `cv2.setNumThreads` · 4 hướng tối ưu của handoff 14-11 trong cửa sổ này.
- File thay đổi:
  - `docs/plan/14-11-2026-plan-3-y-kien-toi-uu-msi.md` — plan §9.2 đầy đủ (quyết định + nghiệm thu có số).
  - `docs/media/bbox/binh1_bbox_cu_104-308-209-287.jpg`, `binh1_bbox_moi_300-275-150-410.jpg`,
    `binh2_bbox_cu_200-400-300-500.jpg`, `binh2_bbox_moi_330-330-150-360.jpg` — 4 ảnh bằng chứng ô chọn
    (frame 0, nén JPEG q72, ~34 KB/ảnh; `docs/media/` không bị `.gitignore`).
  - `docs/task/14-11-2026-plan-3-y-kien-va-audit-bbox.md` — log này.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Handoff 14-11 ghi sai một dữ kiện phần cứng.** Nó viết *"Tiger Lake **có** AVX-512 + AVX512-BF16"*
  và dùng đó làm lý do chọn hướng #1 (`torch.autocast("cpu", bfloat16)`). `/proc/cpuinfo` trên chính MSI:
  **không có** `avx512_bf16` lẫn `amx_bf16` (BF16 đến từ Cooper Lake/Sapphire Rapids, không có ở Tiger Lake
  client) ⇒ chỉ còn bf16-**emulation** của oneDNN, kỳ vọng thấp. Đã ghi vào plan (mục bác) — **không** sửa
  handoff cũ vì đó là log của phiên khác; plan mới nêu rõ chỗ sai.
- **Hai nguồn ngoài trong handoff không kiểm chứng được**: link *"Selective Mask Propagation"* là
  `arxiv.gg/abs/2606.13033` (**không phải** arxiv.org) → hạ độ tin cậy, ghi rõ trong plan là **chưa
  kiểm chứng, không được trích như sự thật**.
- **Phát hiện nặng nhất lại đến từ vòng phản biện, không phải vòng 1**: cả 3 agent vòng 1 đều dùng
  `drift_iou`/`empty_runs` của `binh1` mà không ai nhìn ảnh để biết ô đang phủ cái gì. Vòng 2 mở
  `data/binh2_frame0_grid.png` và nghi ngờ; tôi tự render lại thì mới biết `binh1` còn tệ hơn (ô trên
  **mặt người**). Bài học: **số liệu không tự bảo vệ mình — phải xem ảnh của ô chọn trước khi trích số.**
- **Không chạy được `./run lint`/`./run test` trong phiên này** vì không sửa code; khi code #1–#11 phải
  chạy đủ checklist AGENTS §9.4.
- Ghi nhận nhỏ: `git status` có mục lạ `D:/` (đã thấy từ đầu phiên, có trước phiên này); `rg` không có
  trong WSL ⇒ dùng `grep`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Người dùng chốt: merge plan vào `main` (nhánh `docs/plan-toi-uu-15-11` + PR), và có làm luôn #1 + #2 không.
- [ ] Làm #1 (audit bbox): đổi default bbox 3 script, sửa `docs/task/08-11-2026-do-lai-do-phan-giai-va-kich-thuoc-model.md:10`,
      đánh dấu 21 artifact cũ.
- [ ] Làm #2 (crash ⇒ `error`) + 4 test hồi quy; review độc lập §9.1 trước khi merge.
- [ ] Làm #3 (baseline lại đúng ô) rồi mới trích bất kỳ số live nào vào báo cáo.
- [ ] Tạo ticket cho 7 việc trong mục "Việc tách ra ticket" của plan (ưu tiên: sửa default bbox + cờ cảnh báo artifact).
- [ ] Xem lại toàn bộ câu chữ trong `docs/tom-tat-do-an.md` / `docs/doi-chieu-yeu-cau-gvhd.md` đang trích
      số live của binh1 (vì số đó đo trên khuôn mặt) — **chưa sửa trong phiên này**.

## 📚 Tài liệu tham khảo
- `docs/plan/14-11-2026-plan-3-y-kien-toi-uu-msi.md` — plan chốt của phiên này.
- `docs/plan/14-11-2026-toi-uu-bam-sat-tren-msi.md` (nhánh `origin/docs/handoff-toi-uu-msi`) — handoff nguồn.
- `AGENTS.md` §6 (bảng số đã đo + bẫy "0,0 là chưa đo"), §9.1 (review độc lập), §9.2 (plan 3 ý kiến), §9.4 (checklist).
- `docs/task/08-11-2026-do-lai-do-phan-giai-va-kich-thuoc-model.md` — profile tầng @192 (encoder 90,0/127,7 ms).
- `docs/task/13-11-2026-ticket-15-dang-mau-drift-ra-csv.md` — ngưỡng p05 bị bác; độ trễ phát hiện ≈ độ dài cửa sổ.
- `docs/task/13-11-2026-live-webcam-nguon-0-tu-web.md:149-153` — đo 4 tổ hợp webcam: MJPG = YUY2 = 16,6 FPS.
- Artifact: `data/live_web_relay_2026-11-13_1256|1257|1258_metrics.json`, `data/drift_2026-11-08_metrics.json`,
  `data/reid_2clip_calib.json` (18 mẫu, `bad=1` ⇒ ngưỡng NCC 0,35 chọn trên chính tập đó).
