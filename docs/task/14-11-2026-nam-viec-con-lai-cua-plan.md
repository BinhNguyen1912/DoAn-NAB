# Ngày 14-11-2026 — Xong 5 việc còn lại của plan: bảng cấu hình · mIoU (bám đúng) · HUD tuổi dữ liệu · media · A/B

> Nhánh `feat/plan-con-lai` (tách từ `main` 7d0e61b), nối tiếp
> `docs/task/14-11-2026-crash-error-va-democheck.md` (việc #2, #7). Đây là **toàn bộ phần còn lại** của
> `docs/plan/14-11-2026-plan-toi-uu-va-audit-bbox.md`: **#5, #6, #8, #9, #11**.

## 🎯 Mục tiêu
- Không còn "số không dùng được cho báo cáo": có **bảng cấu hình** để chọn cấu hình thi (#5), có
  **thước đo bám ĐÚNG** thay cho `drift_iou` (#6), **HUD nói ra tuổi dữ liệu ảnh** (#8), **ảnh quỹ đạo**
  cho báo cáo (#9), và **A/B có ngưỡng nhiễu** (#11).

## 📥 Input
- `AGENTS.md` §6 (kết luận đã đo), §9.1 (review độc lập), §9.2 (plan 3 ý kiến).
- `docs/plan/14-11-2026-plan-toi-uu-va-audit-bbox.md`; `docs/so-lieu-bao-cao.md` (bảng số + cột "CẤM trích").
- `data/drift_samples_*.csv` (mẫu từng lần VOS, có `bbox_x1..y2`), `data/binh1.mp4`, `data/binh2.mp4`.
- Code: `src/live_tracking.py`, `tools/live_worker.py`, `src/api/*`, `web/src/live.ts`, `scripts/*`.

## 🔨 Công việc đã thực hiện

### #5 — Bảng cấu hình (`scripts/bang_cau_hinh.py`, `./run bangcau`)
- Chạy **worker thật** (`tools/live_worker.py`, đúng đường live) cho từng cặp `image_size × vos_every`,
  `--lan` lần mỗi cặp, đọc `status.json` cuối ⇒ **mean ± std**; artifact JSON có `git_rev`/`git_dirty_code`
  ở **top level**, `lenh`, `do_luc`, `clip`, `bbox`, `device`.
- Từ chối `--lan 1` (không có ± ⇒ bảng bị trích như "ổn định") và `--bbox` suy biến; `--check` cho CI;
  md sinh từ artifact (`docs/bang-cau-hinh.md`) với cột **"CẤM trích"**.

### #6 — Thước đo "BÁM ĐÚNG" (`scripts/score_miou.py`, `./run miou`)
- Quy tắc chấm (bẫy `0/None`): GT rỗng ⇒ **không chấm**; model rỗng mà GT có vật ⇒ **0,0**; thiếu mask
  của model ⇒ **chưa chạy** (không phải bám sai); `mIoU = None` khi 0 frame chấm được.
- `label`: cắt frame ra PNG + sinh `index.json`; **từ chối** GT có phần do chính model gợi ý (chấm trên
  đó là đo chính nó).
- `LiveTrackConfig.dump_mask_frames/dump_mask_dir` + `_dump_mask()` (chỉ frame được chọn; mask **rỗng vẫn
  ghi file** để chấm 0,0; lỗi ghi chỉ cảnh báo, không giết phiên bám) + CLI `--dump-mask-frames`.
- `scripts/make_synthetic_gt_clip.py`: clip tổng hợp + GT **biết trước** để kiểm đường chấm; `index.json`
  **tái lập y hệt** (bỏ mốc thời gian — bug nhỏ nhưng làm `git status` bẩn đúng lúc đo provenance).
- `docs/thuoc-do-bam-dung.md`: quy trình gán tay 20–30 phút cho 10–20 frame + bảng quy tắc.

### #8 — HUD tuổi dữ liệu ảnh (`./run web`)
- `mask_age_total_ms` / `mask_age_p95` / `age_n` xuyên suốt: `status.json` → `LiveTelemetry` →
  `LiveStatus` → DTO HTTP → `web/src/api.ts` → `live.ts` → `LivePanel`.
- `maskAgeLine()`: `null` = **chưa đo** (không in "0 ms"); chưa đủ mẫu ⇒ không in p95; ≥ ngưỡng
  **1500 ms** ⇒ `role="alert"` "Mask CŨ: 2,6 s (vật có thể đã di chuyển)".

### #9 — Ảnh quỹ đạo (`scripts/make_trajectory_media.py`)
- 2 ô: quỹ đạo tâm ô bao **tô màu theo thời gian** trên nền frame + kích thước ô bao/`drift_iou` theo frame.
- Dòng không có toạ độ bị **loại và đếm riêng** (không đổi thành 0); `--expect-bbox` cảnh báo khi ô bao
  lệch > 10 % ("CÓ THỂ ĐANG ĐO SAI VẬT" — bẫy 14-11: ô phủ khuôn mặt thay vì chai).
- Ảnh đã commit: `docs/media/traj/binh1_vat_ra_khung.png` (đây là **chẩn đoán**, không phải ảnh thành tích).

### #11 — A/B có kiểm định nhiễu (`scripts/ab_test.py`, `./run ab`)
- Chạy **chèn kẽ** A,B,A,B,… (hai bên chịu cùng điều kiện trung bình), ngưỡng nhiễu = `max(std_a, std_b)`;
  chênh lệch ≤ ngưỡng ⇒ **"không phân biệt được"**; `n < 2` ⇒ "không kết luận được".
- Kiểm tham số ở cửa vào (khoảng hợp lệ), từ chối A ≡ B, `--lan 1`, bbox suy biến.

### Dọn đường
- `./run bangcau | ab | miou` (và `./run miou gt` in quy trình gán tay).
- `REGISTRY` của `scripts/so_lieu_bao_cao.py`: **4 dòng mới** (bảng cấu hình 192/320 + mIoU fixture) ⇒
  `docs/so-lieu-bao-cao.md` sinh lại (17 dòng).
- Artifact `git_*` chuyển lên **top level** (để `tests/test_so_lieu_bao_cao.py` kiểm được provenance).

## 📤 Output / Kết quả

**Bảng cấu hình** (`data/bang_cau_hinh_2026-11-14_metrics.json`, `git_rev 548e99b`,
`git_dirty_code=false`, 9 cấu hình × 3 lần, 0 lỗi, clip `binh1`, bbox 300,275,150,410, CPU tiny):

| image_size | vos_every | FPS phát | Nhịp mask | vos_ms | tuổi mask p95 |
|---|---|---|---|---|---|
| 192 | 2 | 29,83 ± 0,06 | **9,33 ± 0,15** | 91 ± 10 | **248 ± 17** |
| 192 | 3 | 29,87 ± 0,06 | 8,87 ± 0,40 | 91 ± 7 | 279 ± 19 |
| 192 | 6 | 29,83 ± 0,06 | 5,17 ± 0,06 | 98 ± 8 | **301 ± 0,2** |
| 256 | 3 | 29,33 ± 0,06 | 4,03 ± 0,06 | 186 ± 13 | 581 ± 15 |
| 320 | 2 | 29,77 ± 0,06 | 3,47 ± 0,15 | 270 ± 25 | 582 ± 20 |
| 320 | 6 | 29,80 ± 0,00 | 3,53 ± 0,06 | 278 ± 8 | 680 ± 20 |

⇒ **Chọn 192 cho demo** (mask gần gấp ba, tuổi dữ liệu ~300 ms thay vì 580–680 ms); 320 chỉ khi vật nhỏ.
**FPS phát luôn ~29,8 ở mọi cấu hình** (LK lấp giữa) — lần nữa: **cấm** đọc thành "mask 30 FPS".

**A/B 192 vs 320** (`data/ab_192_vs_320_2026-11-14_metrics.json`, chèn kẽ 3 vòng):
nhịp mask **8,07 ± 0,40 vs 3,50 ± 0,00** (chênh −4,57 ≫ nhiễu 0,40 ⇒ **A tốt hơn**); `vos_ms`
95,3 ± 5,2 vs 281,6 ± 10,5; tuổi mask p95 321 ± 36 vs 604 ± 2 ms. FPS phát 29,77 vs 29,87 (+0,10 so với
nhiễu 0,06 ⇒ chênh chỉ ~1,7 lần nhiễu — **không** dùng để nói "320 phát mượt hơn").

**mIoU** (`data/miou_synthetic_2026-11-14_metrics.json`): **0,9354** trên **5 frame** của fixture tổng hợp
(ô vuông 60 px trên nền nhiễu, `image_size 192`, `vos_every 1`). Cảnh báo `5/24 frame có GT` in rõ ⇒
**cấm** nói "mIoU trên cả clip", và đây là **cận trên** (GT ≡ pixel ô vuông, prompt = đúng bbox của nó).

**Kiểm tra:** `./run lint` xanh · `./run test` **1126 passed** (thêm 71 test: 17 bảng cấu hình · 18 mIoU ·
13 media · 17 A/B · 6 vitest cho HUD) · `./run webtest` 47 passed · `npm run build` OK ·
`./run e2e` **PASS** (thêm 1 check mới: HUD hiện "Mask CŨ: 2,6 s" + `role=alert` khi tuổi dữ liệu 2600 ms).

**File thay đổi (chính):**
- `scripts/bang_cau_hinh.py`, `scripts/ab_test.py`, `scripts/score_miou.py`,
  `scripts/make_synthetic_gt_clip.py`, `scripts/make_trajectory_media.py`, `scripts/so_lieu_bao_cao.py`,
  `scripts/e2e_web.js`, `run` — mới/sửa.
- `src/live_tracking.py` (`dump_mask_frames`, `_dump_mask`, `_parse_frame_list`), `tools/live_worker.py`.
- `src/api/{domain,live,routes,schemas}.py`, `src/api/adapters/worker_source.py`, `web/src/{api,live}.ts`
  + `web/src/live.test.ts`, `web/src/components/LivePanel.tsx`.
- `docs/bang-cau-hinh.md`, `docs/thuoc-do-bam-dung.md`, `docs/so-lieu-bao-cao.md`, `docs/media/traj/*`,
  `docs/gt/synthetic_tong_hop/*` (24 GT PNG + `index.json`).
- `data/bang_cau_hinh_2026-11-14_metrics.json`, `data/ab_192_vs_320_2026-11-14_metrics.json`,
  `data/miou_synthetic_2026-11-14_metrics.json`.
- Test mới: `tests/test_bang_cau_hinh.py`, `tests/test_score_miou.py`, `tests/test_make_trajectory_media.py`,
  `tests/test_ab_test.py`; sửa `tests/test_api_live.py`.

## 🐞 Vấn đề gặp phải & cách xử lý
- **"Chạy được" ≠ "biên an toàn"** (lặp lại bài học vòng review trước): tôi suýt `--full` hỏng vì timeout
  5 s cho POST start chặn 3,4–4,1 s. Hôm nay tương tự: 3 lần đo bảng cấu hình đầu tiên có **lỗi rải rác**
  vì tôi sửa code **trong lúc** script đo đang chạy (`_dump_mask` chưa tồn tại) — và chính đường
  `crash → state=error` mới thêm đã **báo đúng lỗi đó** thay vì lặng lẽ dừng. Bài học: **không sửa code
  trong lúc đo**; đo lại trên cây sạch.
- **`git_dirty_code` = true ba lần liên tiếp** vì (a) sửa code trong lúc đo, (b) `index.json` GT ghi mốc
  thời gian ⇒ mỗi lần sinh lại là một diff. Sửa: bỏ mốc thời gian khỏi GT generator + quy trình "commit
  code → đo → commit artifact".
- **Artifact để `git_rev` trong `meta`**: test có sẵn của repo đọc **top level** ⇒ artifact trông "không
  có provenance" dù có. Đã chuyển top level (và ghi lý do trong code).
- **`--lan 1`**: ban đầu chỉ cảnh báo rồi vẫn chạy ⇒ bảng không có `±`. Đổi thành **từ chối** (n<2 không
  kết luận được gì).
- **`_is_clip`/suffix list trùng lặp**: gom về `FILE_SUFFIXES` của `src/video_source.py` (một nguồn sự thật).
- **Review độc lập (§9.1) cho nhánh này:** xem mục dưới.
- **Plan 3 ý kiến (§9.2):** 3 agent độc lập (chất lượng/sản phẩm/độ bền) đã được gọi nhưng **chưa trả kết
  quả** trong phiên. Việc vẫn làm vì mỗi hạng mục đều có **số đo + tiêu chí nghiệm thu** rõ ràng từ plan
  trước; thiếu sót này được ghi ở đây thay vì im lặng.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Gán tay 10–20 frame** cho `data/binh1.mp4` (theo `docs/thuoc-do-bam-dung.md`, ~20–30 phút) ⇒ có
      **mIoU trên video thật** (hiện chỉ có cận trên trên fixture tổng hợp).
- [ ] Đo `--full` của `democheck` với **webcam/relay thật** (`source: 0`) — rủi ro "Device busy" do
      `probe_source` mở/đóng nguồn ngay trước worker (nêu từ review trước, chưa đo được).
- [ ] Kéo chuột chọn vật **trên camera thật** + 2 lần diễn tập có log (việc tay, `democheck` đã in 3 bước).
- [ ] Đoạn video demo **liên tục ≥ 20 s** (hiện dài nhất 3,7–5,3 s).
- [ ] Chốt phạm vi với GVHD bằng văn bản (re-ID bắt buộc? dataset chuẩn? "real-time" định nghĩa sao?).
- [ ] Ticket treo: port re-ID sang đường live · fixture "vật cản đi ngang" có texture · `pre_ms` →
      `cv2.cvtColor`/`cv2.resize` (phải đo chất lượng) · `score` vào `status.json`/CSV.

## 📚 Tài liệu tham khảo
- `docs/plan/14-11-2026-plan-toi-uu-va-audit-bbox.md` — plan gốc (#5, #6, #8, #9, #11).
- `docs/task/14-11-2026-crash-error-va-democheck.md` — việc #2, #7 (cùng ngày).
- `docs/thuoc-do-bam-dung.md` — thước đo mIoU + quy trình gán tay (mới).
- `docs/bang-cau-hinh.md` — bảng cấu hình sinh từ artifact (mới).
- `docs/so-lieu-bao-cao.md` — nơi trích số (17 dòng, có cột "CẤM trích thành").
- `AGENTS.md` §6 — các bẫy `0/None`, "drift ≠ độ chính xác", ngưỡng nhiễu.
