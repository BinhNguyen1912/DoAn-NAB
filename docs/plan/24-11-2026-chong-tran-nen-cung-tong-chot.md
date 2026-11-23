# Plan 24-11-2026 — Sửa lỗi "mask tràn nền cùng tông": chặn / đo / hay chỉ ghi nhận?

> Plan theo AGENTS §9.2: 3 ý kiến **độc lập** (vòng 1) → **phản biện chéo** (vòng 2) → chốt.
> Ticket gốc: `#46` (mask tràn nền be cùng tông, 32 % frame phiên `demoip_1123-144505`).
> Bối cảnh: hôm 23-11 đã ship `#43` (HUD nói đúng), `#44` (video đúng thời lượng), `#45` (nghi ⇒ ô
> nét đứt), mục 10 `democheck` (kiểm thời lượng video) và bỏ re-ID khỏi demo (bảng 2×2).

## 🎯 Câu hỏi cần quyết

Trong **≤ 6 giờ** (1 người + agent, máy CPU-only 8 lõi, dùng chung), nên làm gì với lỗi "mask tràn
sang nền cùng tông" (**32 %** frame phiên thật, `mask_area` tới **6,7×** vật) — **thêm cổng chặn
mới**, **dựng dụng cụ đo rồi mới chặn**, hay **chỉ ghi nhận + dọn kịch bản demo**?

Ràng buộc không được vi phạm:
1. Không được làm buổi demo **xấu đi** (mỗi cổng "nghi" là latch: chỉ `r`/`c` mới xoá).
2. Mọi số công bố phải **tái lập được từ artifact đã commit** (có `git_rev`, `git_dirty_code`).
3. Không đổi model/checkpoint/`image_size` (đã có kết quả âm tính).

## 🧭 Ba góc nhìn (vòng 1 — độc lập, không biết nhau)

### A. Chất lượng & số đo

- **Phát hiện chính:** trên **2 clip CÓ GT**, mask **luôn NHỎ HƠN GT** (`dien_tich_pred/dien_tich_gt`
  0,56–1,02; `mask_ngoai_gt` 0,006) ⇒ **không thể** chứng minh "chống tràn tốt hơn" bằng 0,7794 /
  0,8754. Tiêu chí nghiệm thu hiện tại của `#46` là **bất khả**.
- Tín hiệu thay thế: **`bbox_area > 3,0 × EMA(α=0,03)`** báo ở **f96 (trễ 0,00 s)**, phủ **61/63**
  frame tràn, **0 báo oan** trên `binh1-nofreeze ×3` + `be2-nofreeze`; cổng nhảy tâm hiện tại báo
  **f144 (trễ 7,61 s)**, phủ 28/63. `score` **không dùng được** (52/63 frame tràn có `score > 0`).
- **"Cắt mask theo ô LK" là NO-OP**: `mask_area/bbox_area` max **0,841**, **0/181** frame > 1.
- Bác: `score` làm cổng · hạ k xuống 2,5 (báo oan 10 frame f203–210 của `binh1`, đúng đoạn tốt
  nhất, IoU 0,850) · connected-components làm giải pháp chính · lấy 2 clip GT làm tiêu chí.
- **Nếu chỉ 1 việc:** cổng diện tích ô; nếu ưu tiên là "chứng minh được fix tốt hơn" thì đổi sang
  **dựng dụng cụ đo** (clip có GT tràn).

### B. Sản phẩm & bằng chứng bảo vệ

- Video nộp bài là artifact tệ nhất: ~10 s mask phủ tường + tay, 15,5→20,8 s trắng, lại chạy nhanh
  1,48×. **#1 = #44+#45** (đã xong hôm 23-11).
- **#2 = quay raw → chạy pipeline trên chính clip đó → GT ≥ 30 frame → mIoU + p05** (vá `n=7`/`n=6`,
  chấp nhận số xấu hơn, **cấm chọn frame cho đẹp**).
- #3 kịch bản demo 1 trang + bảng "câu ĐƯỢC nói / CẤM nói" · #4 quỹ đạo cửa sổ 5 giây · #5 cổng
  `democheck` kiểm thời lượng (đã xong).
- Bác: sửa thuật toán tràn ngay (cần plan > 4 h, over-fit 1 phiên) · bật/hạ ngưỡng re-ID · "cổng
  cos" · hứa FPS GPU · trích `drift_iou`/`stability`/fixture như "bám đúng".

### C. Độ bền & hiệu năng

- Không có nút thắt ẩn: **model ≈ 85 % của 4,3 lõi**; đọc nguồn 0,36 lõi (8 %) — `LatestFrameSource`
  đọc **155 lần/s** trên relay 16 fps và **715 lần/s** trên nguồn file; vẽ + ghi mp4v 0,16 lõi (4 %).
- **Gốc của "video nén 1,48×"** là `smooth_display.py:528` ngủ nguyên 33,3 ms **sau** khi làm việc
  ⇒ **20,3 tick/s** (625 frame / 30,76 s khớp tuyệt đối).
- Đính chính: `--smooth` **KHÔNG có LK** (LK chỉ ở `live_tracking`, đường web) ⇒ câu AGENTS §6
  "hình 30 FPS nhờ LK" **chỉ đúng cho đường web**.
- Đề xuất: provenance (`wall_s`/`display_fps_mean`/`frames_written`/`video_s`/`loadavg_1m`) · chặn
  vòng đọc nguồn · tô mask theo ROI · nhịp phát theo deadline · `docs/hieu-nang-duong-live.md`.
- **Nếu chỉ 1 việc:** provenance — vì #44 vừa được sửa bằng tay đúng ở chỗ artifact không có số nào,
  và thiếu `loadavg` thì số sẽ bị viết thành "model chậm 4×".

## ⚔️ Tranh chấp (vòng 2 — phản biện chéo)

| Điểm tranh chấp | A nói | B nói | C nói | **Chốt** |
|---|---|---|---|---|
| **Có ship cổng diện tích không?** | Ship, 2,5 h | Bác: cần plan > 4 h + clip GT tràn trước | **Số cụ thể: nối cổng ⇒ `144505` có 98/194 = 50,5 % frame "NGHI"** (tràn bắt đầu f96) — gấp đôi 25,8 % hiện tại, **không thêm thông tin** | **KHÔNG ship.** Chỉ **đo offline** rồi đóng `#46` bằng số |
| **Số "9/36 phiên · ẩn 19,0 %" của A** | Là bằng chứng hiệu chuẩn | Không kiểm được | **Không có artifact nào trong `data/`**; `replay_gate_2026-11-23.json` là luật **score**, 32 phiên, `git_dirty_code = true`. Và "ẩn" là **luật cũ** — `#45` đã đổi sang nét đứt | **Không được trích** cho tới khi có artifact (việc 4 sinh ra nó) |
| **"0 báo oan" của A** | binh1 ×3 + be2 ×3 = 0 | (không nêu) | **Thiếu phép thử "vật tiến lại gần camera"**: EMA 5 s, diện tích ×4 trong < 1 s ⇒ báo oan khi hệ **ĐÚNG** | **Đúng, đây là lỗ.** Phải có take "approach" trước khi bàn bật cổng |
| **Clip GT: tự sinh hay quay thật?** | Tự sinh `make_flood_gt_clip.py` (1,5 h, +3 h nếu quay) | Quay raw (rẻ, thật) | Synthetic ⇒ mIoU là **cận trên** (cấm trích) và **không** kiểm được cơ chế tràn thật | **Quay thật** (0,5 h người dùng), kiêm cảnh "hạn chế" của báo cáo |
| **Video hiện tại tệ đến đâu?** | #45 chỉ phủ 5,3 s cuối; **5,1 s mask SAI** (f96→f143) vẫn còn | ~50 % video xấu | **B mô tả video của code CŨ**: sau #44 tổng là ≈ 30,8 s, sau #45 là nét đứt chứ không trắng | **Phải quay lại 1 phiên rồi mới nói** (việc 1) |
| **`wall_s` có cần không?** | (không nêu) | (không nêu) | **Có, là bug fix**: mục 10 `democheck` vừa merge dùng **proxy** `Σ frame × mean_latency`, bỏ model load + thời gian kéo lại ô ⇒ có thể **FAIL oan** trên video đúng | **Có** — và đã làm một phần hôm 23-11 (`ti_le_thoi_luong` tự khai) |
| **Chặn vòng đọc nguồn (8 % CPU)** | (không nêu) | Bán độ tươi, không mua FPS | Relay **155 lần/s** cho nguồn 16 fps; **file 715 lần/s** (giải mã clip 20 lần, ffmpeg mở 8 luồng tranh torch) | **Làm cho nguồn LIVE** (155 → ≤ 30/s). Nguồn file: để riêng (đổi ngữ nghĩa skip/block, cần quyết khác) |
| **Tô mask theo ROI (tiết 3,1 ms/tick)** | (không nêu) | (không nêu) | Đề xuất | **Bác**: fill mask/bbox 0,15–0,84 ⇒ có phần tràn **ngoài** ô; cắt theo ROI là **giấu đúng phần cần phơi ra**; 1,5 % của 4,3 lõi ⇒ không đáng |
| **Nhịp phát theo deadline (20,3 → 29 Hz)** | (không nêu) | (không nêu) | Đề xuất (kèm cảnh báo CPU tăng) | **Hoãn**: sau #44 thời lượng đã đúng; trần thật là **relay 16 fps** ⇒ chỉ là mượt mắt, CPU tăng |
| **Quỹ đạo 5 giây** | (không nêu) | 0,75 h | `--max-trajectory` **đã có**; 5 s = `round(5×vos_fps)` ⇒ **0,2 h**. Lý do thật: 100 điểm = **16 s** ở 6,3 bước/s nhưng **32 s** ở 3,1 bước/s ⇒ "quỹ đạo theo thời gian" đổi nghĩa theo tốc độ máy | **Làm** (0,4 h) |
| **"Live chậm 1,8× so với file"** | Có thể là thật | — | Đã tự đo: file **206/303 ms**, relay **293/321 ms** ⇒ **không tách được**; cả hai 2–3× chậm hơn số lưu trữ (87–103 ms) | **Bỏ việc đo lại**; **cấm trích 158 ms như số tuyệt đối** |

## ✅ Quyết định

- **Chọn:** **KHÔNG thêm cổng mới.** 6 h dồn vào: (1) có bằng chứng hiện trạng, (2) làm mọi số kiểm
  được, (3) cắt lãng phí CPU đo được, (4) **chẩn đoán** tràn (cột CSV, không phải cổng), (5) quỹ đạo
  theo thời gian, (6) dụng cụ đo tràn (chờ người tô), (7) ghi luật trích số, (8) review + log.

| # | Việc | Giờ | Nghiệm thu CÓ SỐ | Ai |
|---|---|---|---|---|
| 1 | Quay 1 phiên live 25–30 s + `./run democheck` + **xem video** + đếm `nghi_doi_tuong` | 0,4 | mục 10 xanh (`|lệch| ≤ 5 %`); video ≥ 25 s; % frame nghi là số (mốc cũ 25,8 %); ghi `loadavg` | **người dùng** |
| 2 | `wall_s` + `loadavg_1m`/`cpu_count` vào summary/run_info; mục 10 dùng số **tự khai** thay proxy | 1,0 | (a) `144505`: proxy 30,75 s vs `wall_s`; (b) ca kéo lại ô giữa phiên 10 s ⇒ proxy FAIL→PASS; (c) 2 test | đã làm 23-11, còn phần test ca (b) |
| 3 | Chặn vòng đọc nguồn LIVE (`LatestFrameSource`, mốc đầu vòng) | 0,5 | relay **155 → ≤ 30** lần/s; CPU luồng capture **0,36 → ≤ 0,10 lõi**; `mask_age_p95` **không đổi** (đo trước/sau) | agent |
| 4 | Ghi `bbox_area_ratio` + `nghi_ly_do` ra CSV/`status.json` — **chỉ để chẩn đoán** | 1,0 | tái lập **tràn bắt đầu f96** từ CSV; **công thức diện tích tham chiếu phải ghi trong cột** (median 3 920 px ⇒ 35 %; 5 776 px ⇒ 32 %) | agent |
| 5 | Quỹ đạo theo **thời gian** (5 s ⇒ `round(5×vos_fps)`, kẹp 16–64) | 0,4 | cùng 5 s: **32 điểm** ở 6,3 bước/s, **16 điểm** ở 3,1 bước/s; test hàm thuần | agent |
| 6 | **1 clip GT tràn**: quay raw (take B = vật be trên tường be) + take C ("approach") + chạy `--no-reid @192 --vos-every 1`; người dùng tô ≥ 10 frame | 0,6 máy + người | **kill criterion**: baseline phải có **≥ 10 %** frame `area_ratio > 2,5`; take C: **0 lần báo** cổng diện tích (nếu báo ⇒ đóng `#46` = "KHÔNG BẬT") | agent + người dùng |
| 7 | 1 dòng vào `docs/`: **cấm trích 158 ms như số tuyệt đối**; số hiệu năng phải kèm `loadavg` + `git_dirty_code` | 0,3 | — | agent |
| 8 | Review độc lập + log `docs/task/` | 0,8 | P0 = 0, P1 có chủ | agent |

- **Vì sao:** (a) cổng mới **làm demo xấu đi có số** — `144505` sẽ có **50,5 %** frame "NGHI" thay vì
  25,8 % (tràn bắt đầu f96), mỗi cổng là latch không tự hồi; (b) số hiệu chuẩn của A **không có
  artifact** và đo bằng **luật đã bị #45 thay**; (c) **chưa ai kiểm** ca "vật tiến lại gần camera" —
  đúng ca sẽ báo oan; (d) trong khi đó kịch bản demo đã tránh được lỗi: **0/96 frame tràn** ở đoạn vật
  trên rèm xám so với **63/85** khi vật lên tường be (tự kiểm lại từ CSV).
- **Bác (để sau không mở lại):**
  - Cổng diện tích nối vào latch — 50,5 % frame "NGHI", không thêm thông tin so với #45 đã merge.
  - `re-anchor(last_good_bbox)` — `last_good_bbox` trong cơn trôi **chính là** ô tràn (`bbox_area`
    4 655 → **29 110 px trong 1 bước**), và đường web **không có** `reanchor` (+1–1,5 h).
  - Bake-off 3 cách chữa — chưa có dụng cụ đo thì chỉ so cảm giác.
  - Clip **tổng hợp** tự sinh — mIoU là cận trên (cấm trích) và không tái hiện cơ chế tràn thật.
  - Tô mask theo ROI — giấu đúng phần tràn; 1,5 % CPU.
  - Nhịp phát theo deadline — sau #44 chỉ còn mượt mắt; trần thật 16 fps.
  - Đo lại "live 1,8× vs file" — file 206/303 vs relay 293/321 ms, không tách được.
  - Mọi thứ về re-ID / `image_size` / điểm prompt âm — đã có kết quả âm tính.
- **Điều kiện ĐỔI Ý (để plan không phải lời thề):** bật cổng diện tích **chỉ khi** có đủ 3 thứ —
  (i) artifact hiệu chuẩn trên ≥ 30 phiên (`git_dirty_code = false`), (ii) take C ("approach") cho
  **0 lần báo**, (iii) clip GT tràn cho thấy tràn giảm **≥ 30 %** frame mà mIoU **khộng giảm** trên
  `binh1`/`be2` (so cặp). Thiếu một điều ⇒ đóng `#46` = "không bật", kèm số.

## 📌 Việc tách ra ticket

- [ ] `#46` — đóng bằng số sau việc 6 (kể cả kết quả "KHÔNG BẬT").
- [ ] Nguồn **file** đọc 715 lần/s: cần quyết "skip hay block" cho `--smooth` + file (chưa làm).
- [ ] `run_tracking` (headless) **không có** `IdentityWatch` ⇒ artifact headless không có
  `nghi_doi_tuong`; nếu muốn quay video minh hoạ #45 thì phải dùng đường `--display`.
- [ ] Test đang vá `time.monotonic` **toàn cục** — nên tiêm đồng hồ qua tham số.

## 📚 Tham chiếu

- `docs/task/23-11-2026-quyet-dinh-lon-tat-reid-va-3-ticket-ui.md` (bảng 2×2 + 3 ticket + review).
- `.scratch/camera-ai-realtime/issues/43`, `44`, `45`, `46` (kèm các comment đính chính số).
- `docs/phan-tich-dung-sai-model-may-code.md` (mục 7), `docs/thuoc-do-bam-dung.md`,
  `docs/demo-clip-va-o-chon.md`, `AGENTS.md` §6.
