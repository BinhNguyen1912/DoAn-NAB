# Ngày 21-11-2026 — Nhận lại vật trên đường live + demo bằng WEBCAM realtime (P1–P4)

## 🎯 Mục tiêu
1. Chốt plan cho câu hỏi lớn: **demo bằng webcam realtime** (không dùng video file) cần gì, sau khi ticket #41
   chứng minh đường live **không có** cơ chế nhận lại vật (ô VOS sai **trước** khi LK bước ở f162; vật vào lại
   thì bám vào **mặt người** ở f228).
2. Thực thi phần rẻ nhất–đắt nhất theo thứ tự đã chốt: vá bug P0 trong re-ID → bật cổng đã hiệu chuẩn →
   metric "vẽ ô khi không có vật" → lớp trung thực "không có bằng chứng thì không vẽ ô".

## 📥 Input
- Yêu cầu người dùng: *"pok làm đi, nhưng không demo bằng video, mà là bật cam realtime luôn"*.
- Ticket #41 (đã đóng): nguyên nhân bám sang vật khác là **base VOS**, không phải `max_mad`/`lk_scale`.
- `data/reid_2clip_calib.json` (hiệu chuẩn 01-11, 17 ca đúng + 1 ca sai có nhãn người).
- GT người tô có sẵn: `docs/gt/binh2_tay` (4 frame `gt_rong`), `docs/gt/b1` (5 frame `gt_rong`).
- Quy ước: `AGENTS.md` §6 (số đã đo), §9.2 (plan 3 ý kiến), §9.1 (review độc lập).

## 🔨 Công việc đã thực hiện

### 1. Plan 3 ý kiến + tranh chấp (AGENTS §9.2)
- `docs/plan/21-11-2026-nhan-lai-vat-tren-live-va-demo-webcam.md` — 3 góc nhìn độc lập (chất lượng & số đo /
  sản phẩm & bằng chứng / độ bền & hiệu năng), 1 vòng phản biện chéo, chốt 6 việc ~12 h, ghi rõ **phương án bị
  bác** kèm lý do (bọc `ReIdSession` nguyên khối, module mới `src/live_bam.py`, bộ GT webcam 7 h, nâng cosine
  lên 0,87/0,90, toggle runtime + event-log UI, đóng băng hiển thị, demo > 720p).
- Vòng phản biện tìm ra **bug P0 mà cả 3 đề xuất vòng 1 đều bỏ sót** (mục 2 dưới).

### 2. P1 — Vá P0: `_reacquire` không cập nhật `_last_bbox` (`src/reid.py`)
Cơ chế lỗi: `_reacquire` đặt `state=TRACKING` + `_verify_left` nhưng **không** cập nhật `_last_bbox`; tick sau
`_is_suspicious_jump` so với mốc **trước khi mất dấu** ⇒ vật vào lại ở chỗ khác bị coi là "nhảy bất thường"
⇒ `_auto_recover()` huỷ **ngay** lần nhận lại vừa xong: 2× `engine.start` (~210–280 ms) + 1 frame không có ô +
bỏ qua `verify_frames`. Bằng chứng thật: phiên `--reid --reid-cue object` trên `binh2` có **3 lần "reacquired"
liên tiếp f172/176/180** cho **một** lần vật vào lại.
Vá: cập nhật cả `_last_bbox` và `_last_center` (vùng tìm sau đó phải quanh chỗ vật **đang** ở).

Test hồi quy `tests/test_reid.py::TestCongChongNhayKhongTuHuyLanNhanLai`. **Ba cái bẫy đã tự sập khi viết test**
(ghi lại để lần sau không mất thời gian):
- đặt khoảng nhảy **đúng bằng** ngưỡng `1,5 ×` đường chéo thì **mutant sống** (cổng là `>` strict) ⇒ phải xa hơn
  hẳn (73,5 px vs ngưỡng 55,2 px);
- nền nhiễu ngẫu nhiên làm `_verify_ok` từ chối vì **lý do khác** (không phải cổng chống nhảy) ⇒ phải dán **cùng
  một texture** ở hai vị trí;
- bán kính tìm **nở dần** (`_filter_by_radius`: 0,75→1,75 lần cạnh vật trong 12 frame đầu) nên lúc mới mất dấu
  **không thể** nhảy 73 px ⇒ phải để `_lost_age` vượt `search_grow_frames`.
Kết quả mutant: **ĐỎ** khi xoá dòng vá, **XANH** khi có.

**A/B trên clip thật (đo lại cuối phiên, cùng clip `binh2`, 300 frame, @192, `--reid --reid-cue object`)** —
phải đo vì con số "3 lần liên tiếp" ở trên là **trước** khi vá:

| | n_reacq | frame reacquired | frame `lost` | frame `reacquiring` |
|---|---|---|---|---|
| TRƯỚC vá (`origin/main:src/reid.py`) | 5 | 172, 176, 180, 241, 245 | **16** | 10 |
| SAU vá | 4 | 172, 175, 178, 244 | **13** | 8 |

⇒ Vá có tác dụng thật nhưng **nhỏ** trên clip này (−3 frame mất dấu, −1 lần nhận lại). **ĐÍNH CHÍNH:** vẫn còn
**3 lần "reacquired" liên tiếp** (172/175/178) ⇒ hiện tượng đó **không** chỉ do cổng chống-nhảy; nó là **VOS trả
mask rỗng ở sát mép khung** (vật ra/vào khung) rồi mất dấu lại sau 3 frame ⇒ **nợ ticket**, không phải đã xong.
Artifact: `data/reid_ab_p1_2026-11-21_{truoc-va,sau-va}.csv`.

**Cổng NCC 0,35 trên clip này KHÔNG đổi gì** (`data/reid_ab_p1_2026-11-21_ncc0.csv` so với `sau-va`): cùng 4 lần
nhận lại ở cùng frame, cùng dải `ncc` (−1,0…0,811), 288 frame `tracking` — vì mọi ứng viên được nhận ở clip này đều
đã có ncc ≥ 0,35. Giá trị của cổng đến từ **hiệu chuẩn có nhãn** (ca sai 0,279), **không** phải từ clip này ⇒ phải
nói đúng như vậy trong báo cáo, không được trích "bật cổng 0,35 nên bám tốt hơn".

### 3. P2 — Bật cổng NCC đã hiệu chuẩn trên đường demo
`run demoip` + `run fast` truyền `--reid-obj-ncc-min 0.35`; `tools/run_live.py` in `ncc_min=` trong dòng `[re-ID]`.
Vì sao 0,35: `data/reid_2clip_calib.json` — 17 ca **đúng** có ncc **0,415–0,741**, ca **sai** có ncc **0,279**
⇒ NCC **tách được**, còn cosine **thì không** (ca sai 0,899 **>** ca đúng thấp nhất 0,770). Comment tắt cổng trong
`src/config.py` viết **29-10 — trước bản hiệu chuẩn 3 ngày**. **Không** đổi `configs/default.yaml` (để artifact cũ
tái lập được); cờ người dùng đứng sau nên vẫn đè được.

### 4. P3 — `ty_le_o_ma`: metric phạt "vẽ ô khi KHÔNG có vật" (`scripts/ab_o_hien_thi_vs_gt.py`)
Mọi chỉ số cũ (`iou_mean`, `drift_iou`, `stability`) chỉ chấm trên frame **có vật** ⇒ hệ "luôn trả lời" không bị
phạt. `hop_tu_gt` **bỏ** `gt_rong` (đúng, vì không có IoU để chấm) nhưng **không ai dùng** tập đó ⇒ thêm
`gt_rong_cua()`, `ty_le_o_ma()` (hàm thuần), `cham(..., gt_rong=)`; không truyền ⇒ `None` (chưa đo, **không phải 0**).
Artifact `schema` 6 → 7.

### 5. P4 — Lớp trung thực: `bam` = "có bằng chứng về vật"
`LiveStatusResponse.state` chỉ có `stopped/loading/running/error` ⇒ panel in "Trạng thái: running" đúng lúc hệ
**không có bằng chứng nào**. Thêm khoá riêng `bam` (`tracking` | `no_evidence` | `None`), **không** nhồi giá trị
mới vào `state`. Ô/mask/quỹ đạo **không vẽ** khi `no_evidence`; chữ ASCII `KHONG CO BANG CHUNG (<lý do>)` khắc lên
**chính ảnh**; `--dump-shown-csv` thêm **cột 12 `bam`** để tiêu chí "0 frame có ô khi no_evidence" **kiểm được trên
artifact**; `shown` trong CSV cũng ghi "không có ô" khi đã ẩn. Chuỗi đầy đủ: `status_payload` → adapter
`worker_source` → `LiveTelemetry`/`LiveStatus` → `LiveStatusResponse` → `web/src/api.ts` → `bamLine()` (5 test vitest)
→ `LivePanel` (`data-testid="bam-no-evidence"`, `role="alert"`).

## 📤 Output / Kết quả

### Số đo (máy này, CPU; artifact trong commit message + `data/o_ma_binh2_2026-11-21_metrics.json`)
| Đo | Số | Ghi chú |
|---|---|---|
| `bam_no_evidence_n` (`binh2`, 400 frame, @192, `vos_every 3`) | **72** frame | dải **175–340**, đúng đoạn vật ra khỏi khung |
| Frame **có ô** trong 72 frame `no_evidence` | **0** | tiêu chí nghiệm thu P4 ✓ |
| Frame có ô (toàn phiên) | 320/400 | `empty_runs = 25`, `vos_runs = 107` |
| `ty_le_o_ma` (4 frame `gt_rong`) | `n_gt_rong = 4`, `n_co_o_tren_rong = **1**` (lần đo trước khi có `bam`) | `ty_le_n = 4 < 30` ⇒ **chỉ báo ĐẾM** |
| Sau khi có `bam`: frame `gt_rong` 294, 326 | **không còn ô** ✓ | 196 và **359 vẫn có ô** ⇒ `ty_le_o_ma` **không** về 0 |
| `run demoip` dòng khởi động | `ncc_min=0.35` | đúng như thiết kế mong đợi |
| `binh2`, 30 frame @192 có `--reid-obj-ncc-min 0.35` | mean **118 ms**, p95 **147 ms** | khớp trần CPU đã biết |
| `./run democheck --source data/binh2.mp4` | **8 OK · 1 cảnh báo · 0 LỖI** | cảnh báo = API chưa chạy (bình thường) |

### Kiểm tra tự động
- `./run lint` = **All checks passed**
- `./run test` = **1607 passed**, 5 deselected
- `./run webtest` = **77 passed** (5 test mới cho `bamLine`)
- `npm run build` = OK (163,94 kB)

### File thay đổi
- `docs/plan/21-11-2026-nhan-lai-vat-tren-live-va-demo-webcam.md` — plan 3 ý kiến + tranh chấp + quyết định
- `src/reid.py` — vá P0 (`_last_bbox`/`_last_center` trong `_reacquire`)
- `run` — `demoip`/`fast` bật `--reid-obj-ncc-min 0.35`
- `tools/run_live.py` — in `ncc_min` trong dòng `[re-ID]`
- `src/live_tracking.py` — `bam` + `_cap_nhat_bang_chung` + ẩn ô/mask/quỹ đạo + HUD + cột 12 CSV + 3 khoá status
- `src/api/{domain,adapters/worker_source,schemas,routes}.py` — `bam`/`bam_ly_do`/`bam_no_evidence_n`
- `web/src/{api.ts,live.ts,components/LivePanel.tsx}` — `bamLine()` + dòng cảnh báo `role="alert"`
- `scripts/ab_o_hien_thi_vs_gt.py` — `gt_rong_cua`, `ty_le_o_ma`, `schema` 7
- `tests/{test_reid,test_live_tracking,test_api_live,test_ab_o_hien_thi_vs_gt}.py`, `web/src/live.test.ts`

## 🐞 Vấn đề gặp phải & cách xử lý
1. **Luật "mất bằng chứng" đầu tiên SAI và đo được là sai**: coi `lk_ok = False` là mất bằng chứng ⇒ báo oan
   **296/400 frame (74 %)** vì khi LK từ chối, `_result_threaded` trả `base_result` = ô VOS **THẬT** của frame VOS
   gần nhất (vẫn là quan sát, chỉ **cũ**). Nếu ship thì ô tắt gần hết buổi demo trong khi ô đang đúng. Luật cuối:
   chỉ **mask rỗng** (model không thấy vật **và** mask nội suy cũng rỗng) mới là mất bằng chứng, cần **2 frame
   liên tiếp** (`_BAM_NO_EVIDENCE_FRAMES`, cùng tinh thần dung sai `MISS_MIN` của watchdog). Độ cũ đã có số riêng
   (`mask_age_total_ms`) nên **không** nhân đôi bằng cách ẩn ô.
2. **`--frames` mặc định 300 < 360 frame clip `binh2`** ⇒ 2/4 frame `gt_rong` (326, 359) chưa từng chạy tới và bị
   ghi là `thieu_frame_rong`. Không phải "không vẽ ô" — phải chạy `--frames 400`. (Nếu đọc `ty_le_o_ma` mà bỏ cột
   `thieu_frame_rong` thì kết luận sẽ sai.)
3. Test test allowlist `status.json` **bắt đúng** 3 khoá mới chưa khai báo; test `test_start_status_frame_stop`
   cũng bắt đúng bộ khoá — đó là thiết kế tốt, không phải trở ngại.
4. Một lần chạy worker 400 frame **treo ở 55 frame** rồi hết timeout; chạy lại cùng lệnh xong trong **17 s** ⇒
   không tái lập được, ghi lại để nếu lặp thì điều tra (có thể tranh CPU với pytest/build cùng lúc).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **P5 (chưa làm, ~3–6 h)**: port tìm lại vào `_VosWorker` để **web** cũng có beat "mất dấu → nhận lại".
      Hiện beat đó chỉ diễn được trên `./run demoip` (webcam realtime qua relay, cùng engine, có chọn ô bằng chuột).
      Khi làm: `start` phải là **job xếp hàng** trong luồng VOS, `search` ≤ 60 ms mỗi **2** chu kỳ VOS, **không**
      tính tick tìm lại vào `vos_runs/vos_ms`, và **fail-open** (lỗi ⇒ quay về `process`, không bao giờ `state=error`).
- [ ] **Ticket nợ #1**: "bám sang vật khác **khi VẪN** tracking" (f162→f163 của `binh2`) — không việc nào trong
      12 h hôm nay sửa được; `auto_recover` chỉ bắt nhảy > 1,5 × đường chéo (f162→163 nhảy ≈ 229 px < ngưỡng
      520 px). **Phải ghi vào báo cáo là chưa sửa.** Frame `gt_rong` 196 và 359 vẫn có ô ⇒ `ty_le_o_ma` > 0.
- [ ] **Ticket nợ #2**: hiệu chuẩn `ncc_min` với **≥ 3 ca sai** (hôm nay `n_bad = 1`) trên clip có chai đen.
- [ ] **Ticket nợ #3**: `refs_n = 0` khi ô chọn dính mép — hiện chỉ in ra stdout (`reid.py`), **chưa** lên web.
- [ ] Diễn tập webcam thật 3 lần + quay màn hình + `./run democheck --full --bbox` (P6) — **chưa làm** vì cần
      webcam Windows qua relay trên máy người dùng.

## 📚 Tài liệu tham khảo
- `docs/plan/21-11-2026-nhan-lai-vat-tren-live-va-demo-webcam.md` (plan + tranh chấp + phương án bị bác)
- `docs/task/21-11-2026-ticket-41-vi-sao-binh2-bam-sang-vat-khac.md` (nguyên nhân gốc: base VOS)
- `data/reid_2clip_calib.json` (hiệu chuẩn 01-11: cosine không tách được, NCC tách được ⇒ 0,35)
- `docs/thuoc-do-bam-dung.md` (GT rỗng ⇒ không chấm; model rỗng mà GT có vật ⇒ 0,0)
- `AGENTS.md` §6 (bẫy `0/None ≠ đã đo`, "mask 30 FPS" là sai, watchdog, SAM 2 không tất định)
