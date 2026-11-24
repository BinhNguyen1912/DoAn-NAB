# 24-11-2026 — "Vật rời khung rồi vào lại" KHÔNG phải "đổi đối tượng" (cổng nghi tự khoá phiên)

## 1. Mục tiêu

Người dùng báo (phiên `demoip_1124-193026`, 60 s):

> "nếu ra khung khoảng 10 s, khi đưa vào khung lại sẽ bị nghi, từ đó **không nhận diện lại nữa**"

Yêu cầu: vật rời khung rồi vào lại thì hệ **phải bám lại được**, không được kẹt ở trạng thái nghi.

## 2. Input

- `data/demoip_1124-193026_metrics.csv` (404 frame, `git_rev=14140ca`, mean 141 ms / p95 205 ms,
  `mất dấu 92/404 = 23 %`) + `data/demoip_1124-193026_web.mp4` (HUD).
- Code: `src/identity_guard.py` (`IdentityWatch`), `src/smooth_display.py` (đường `./run demoip`),
  `src/live_pipeline.py` (đường web), `scripts/eval_gate_rules.py`, `scripts/replay_latch_settle.py`.

## 3. Công việc đã thực hiện

### 3.1. Chẩn đoán bằng số (không đoán)

| đại lượng | số đo |
|---|---|
| frame `nghi_doi_tuong = 1` | **8** frame (f264–271) = 2,0 % |
| frame `chua_xac_minh` (ô nét đứt, không tô, không quỹ đạo) | **132** frame = **32,7 %** phiên |
| đoạn `mask_area = 0` dài | 6 đoạn 8–22 frame: `72–79`, `117–125`, **`158–179`**, **`248–262`**, `340–351`, `387–394` |
| frame bật cổng | **f264** — cách đoạn vắng `248–262` đúng **2 frame** |

Chuỗi thật ở cú báo:

- f248–262: **15 frame `mask_area = 0`** (vật ngoài khung).
- f263: model trả mask đầu tiên nhưng chỉ **559 px** — `bbox_area_ratio = 0,346` × tham chiếu ⇒ **mẩu rác**.
- f264: mask thật **24 100 px** ở vùng khác ⇒ cổng chấm "tâm nhảy 209 px" **giữa MẨU RÁC và VẬT** ⇒ báo nghi.
- f264 → hết phiên: latch không có đường xoá (re-ID TẮT) ⇒ **132 frame** chỉ còn ô nét đứt.

⇒ Lỗi **không phải ngưỡng**: cổng đang lấy **mẩu rác của lần dò lại** làm mốc so sánh. Ảnh
`m330` (cắt từ `_web.mp4`) xác nhận song song: sau cú báo ô bám sang **tường trống** (chai vẫn ở dưới,
nhoè) ⇒ vấn đề thứ hai (trôi dần) là **mù có từ trước**, không phải thứ sửa trong phiên này (§5).

### 3.2. Sửa: "vắng mặt" ≠ "đổi đối tượng" (một chỗ, cả 2 đường dùng chung)

`src/identity_guard.py`:

- `DEFAULT_LOST_RESET_STREAK = 3` — 3 bước **liên tiếp** không có mask ⇒ **vật đã rời khung**.
- `DEFAULT_REACQ_GRACE_STEPS = 2` — 2 bước đầu của phiên bám mới **miễn chấm nhảy** (mốc chưa đáng tin).
- `update(...)`: vắng ≥ 3 bước rồi có mask ⇒ `reset()` (về `ok`) + grace. Grace được kiểm **trước**
  phán quyết nhảy ⇒ bước 2 của phiên mới không lấy mẩu rác f263 làm mốc.
- `vua_bao` — cờ "bước này cổng **thật sự** kết luận đổi đối tượng". `_switch_warning` trước đây tự gọi
  `is_suspect_switch` **lần thứ hai** ⇒ sửa state machine mà console vẫn in WARN + banner (bắt được
  ngay trong lần chạy đầu). Nay cả `smooth_display` và `live_pipeline` chỉ in khi `watch.vua_bao`.

Vì sao ngưỡng **3**: 1–2 frame rỗng là **nhấp nháy** — 6/7 ca báo ĐÚNG của repo không có đoạn rỗng nào
trước đó, ca thứ 7 (`125109#137`) chỉ rỗng **1** frame ⇒ ngưỡng 3 **giữ nguyên 7/7** (đo ở §4).

### 3.3. Provenance: cờ THẬT + ghi vào `run_info`

Bài học P1 của review 24-11 (`run_info` ghi `settle_steps=8` trong khi **không** cờ nào đổi được nó)
được áp ngay, không lặp lại:

- `--lost-reset-streak N` (mặc định `3`, `0` = tái lập hành vi trước 24-11) trong `tools/run_live.py`.
- `_lost_reset_streak(args)`: `None` khi đường headless (không dựng cổng), `0` **không** bị nuốt thành
  mặc định, kẹp âm về 0.
- `run_info.json` có trường `lost_reset_streak` ⇒ phiên sau replay được, biết vì sao số khác.
- `src/smooth_display.run_smooth_display` + `src/live_pipeline.run_interactive` nhận và chuyển vào
  `IdentityWatch`.

### 3.4. Sửa kèm: banner phải TẮT khi latch tự xoá

`switch` (cờ banner "đổi đối tượng") trước đây gán `switch = watch.nghi or switch` — **sticky**. Latch
nay có thể được xoá **từ bên trong** `watch.update` (tái bám) mà không ai gán `switch = False` ⇒ banner
treo trên màn hình trong khi mask đã vẽ lại bình thường. Nay `switch = watch.nghi` (banner ⇔ latch).

### 3.5. Test (17 case mới, khoá đúng hành vi)

| file | class / case | số |
|---|---|---|
| `tests/test_identity_guard.py` | `TestTaiBamSauKhiVatRoiKhung` | 5 |
| | `TestBannerDiTheoTrangThaiLatch` | 1 |
| | `TestBienCuaNguongVang` (biên đúng 3; chuỗi thật `121732` f176–178) | 2 |
| | `TestBuocVosKhongPhaiFrameHienThi` | 3 |
| `tests/test_live_tracking.py` | `TestCongNghiAnMotBuocVOSKhongPhaiMoiFramePhat` (`_update_stats_locked` + `_result_threaded` với stub worker/interp — **không** phải engine SAM 2 thật) | 2 |
| `tests/test_run_live_helpers.py` | `TestLostResetStreak` | 3 |
| `tests/test_smooth_display.py` | `test_canh_bao_chi_in_khi_cong_that_su_cham` + assert hành vi chống-sticky trong `test_render_nhan_chua_xac_minh_sau_khi_bam_on_dinh` (2 case source-only, đã ghi rõ) | 1 |
| **tổng** | | **17** |

(Đã kiểm **mutant**: bỏ `and self._buoc_vos_moi` ⇒ `test_khong_phai_buoc_moi_thi_cong_khong_doi` ĐỎ.)

`TestTaiBamSauKhiVatRoiKhung` — vắng dài rồi vào lại **không báo**; hết grace thì **chấm lại như cũ**
(chống "sửa" bằng cách tắt cổng); vắng 1–2 frame **vẫn chấm**; tái bám **xoá latch**;
`lost_reset_streak=0` tái lập được hành vi trước 24-11.

### 3.6. REVIEW ĐỘC LẬP (mục 9.1) — bắt 1 P0 + 2 P1 + 3 P2, đã sửa

Reviewer (agent `reviewer`, chỉ đọc) kết luận **chưa merge được**. Các phát hiện và cách xử lý:

| mức | phát hiện | xử lý |
|---|---|---|
| **P0** | `switch = watch.nghi or switch` **sticky** ⇒ sau khi latch tự xoá (tái bám) HUD **vẫn ẩn mask tới hết phiên** + CSV ghi `nghi_doi_tuong = None` trong khi ảnh đang ẩn. Đúng triệu chứng người dùng báo, chỉ khác nguyên nhân | sửa ở `92dcfe5`: `switch = watch.nghi`; test source-level + test hành vi |
| **P1** | **Đường WEB đếm theo frame PHÁT, không theo bước VOS.** `live_tracking` gọi `_watch.update` mỗi vòng phát, `vos_every=3` ⇒ cùng một kết quả VOS lặp ~3,5 lần ⇒ `lost_reset_streak=3` co còn ~1 bước VOS (một VOS rỗng là reset ⇒ **mất** ca nhấp nháy `125109#137`) và `reacq_grace_steps=2` hết hạn **trước** bước VOS kế (⇒ đúng cú f263→f264 **vẫn** bị chấm trên web). Mọi số §4 là replay CLI nên **không** phát hiện được | `IdentityWatch.update(..., buoc_moi=)`; `live_tracking` chỉ đẩy cổng khi **seq VOS đổi** (`_watch_seq`). Test qua `_update_stats_locked` với stub: `TestCongNghiAnMotBuocVOSKhongPhaiMoiFramePhat` — đã kiểm **mutant** (bỏ điều kiện ⇒ test ĐỎ) |
| **P1** | Artifact ghi `git_rev=14140ca` + `git_dirty_code=true`, và cột "trước" **không** có artifact nào ⇒ trái luật tái lập | sinh lại **trên cây sạch ở `d2dc7e7`**: `git_dirty_code=false`; `--lost-reset` nhận **danh sách** ⇒ **một** artifact `replay_latch_tai_bam_...` chứa cả `vắng>=0` và `vắng>=3` cùng `git_rev` |
| **P2** | `_switch_warning` **tự chấm lại** với `max_jump_ratio` mặc định ⇒ `--max-jump-ratio < 0,25` thì cổng báo mà console **im lặng** | hàm chỉ còn **in**; phán quyết duy nhất ở `watch.vua_bao` |
| **P2** | Thiếu `reacq_grace_steps` trong provenance; `eval_gate_rules` thiếu `git_dirty` | đã thêm cả hai vào artifact |
| **P2** | Lỗ test: không test **biên đúng 3**, không test cờ đi tới `IdentityWatch` trên worker, test WARN chỉ so chuỗi source | thêm `TestBienCuaNguongVang`, `TestCongNghiAnMotBuocVOSKhongPhaiMoiFramePhat` (qua `_update_stats_locked`, stub worker), `TestLostResetStreak` |
| **P3** | Docstring ghi "140/404 = 34,7 % chưa xác minh" sai nhãn | sửa: **132 = 32,7 %** chưa xác minh + **8** frame `nghi` = 34,7 % *không tin cậy* |
| **P3** | Câu "ca 21-11 không bị ảnh hưởng vì vật **không** rời khung" **SAI**: phiên `1121-121732` có **2 frame rỗng liền** (f176–177) ngay trước cú báo f178 | sửa lại; **biên mỏng tới đâu**: ngưỡng **2** sẽ MẤT ca đúng đó, ngưỡng **3** giữ 7/7 — đã khoá bằng `TestBienCuaNguongVang` dùng đúng chuỗi f176–178 |

**Hệ quả phụ PHẢI nói kèm (đường web):** `settle_steps = 8` giờ đếm theo **bước VOS**, đúng như
AGENTS mô tả ("8 bước ≈ 1,3–1,8 s ở 4,5–6,3 bước/s"). Trước khi sửa, web đếm theo **frame phát** ⇒ 8
"bước" chỉ ≈ **0,27 s** (8/29,8). Nay một lần báo ẩn ≈ **0,94 s** (8/8,5) — dài hơn ~3,5 lần nhưng
**đúng ngữ nghĩa**, và đổi lại các lần báo OAN do tái bám biến mất. Đừng so số `frame_an` của phiên web
trước/sau mốc này mà không nói định nghĩa "bước" đã đổi.

Đã kiểm, **không** phải lỗi (reviewer xác nhận): thứ tự `_lost`/`_grace`/`reset()` trong `update()`;
`vua_bao` không làm mất cảnh báo ở cấu hình mặc định; mẫu số replay (26 phiên đo được / 17 phiên bị loại);
hai script lấy mặc định từ hằng số chung.

### 3.7. REVIEW VÒNG 2 — P1 CHƯA ĐÓNG: web **không nhìn thấy VOS rỗng thật**

Reviewer vòng 2 (`2910cd1f`) kết luận **chưa merge được**: sửa `buoc_moi` ở vòng 1 đúng phần "đếm",
nhưng trên đường web cổng **không bao giờ nhận được một bước VOS rỗng**, vì:

`tracker_engine._mask_to_bbox` trả bbox `(0,0,0,0)` khi mask rỗng (`tracker_engine.py:338-339`) →
`_bbox_hop_le((0,0,0,0))` = False (`live_tracking.py:584-596`) → `obs_bbox = None` → guard
`if obs_bbox is not None` làm `_watch.update` **không được gọi** ⇒ `_lost` không tăng ⇒
`lost_reset_streak`/`reacq_grace_steps` **không bao giờ chạy trên web** ⇒ đúng ca "vật rời khung rồi
vào lại" **vẫn bị báo nghi** ở đó. Đường CLI làm đúng từ trước (`last_bbox = (0,0,0,0)` khi mất dấu).

**Sửa:** gọi `_watch.update` **mỗi bước VOS**, kể cả khi `obs_bbox is None` (`cur = (0,0,0,0)`,
`co_mask = not raw_lost and obs_bbox is not None`), và **xoá mốc** `_last_good_bbox = (0,0,0,0)` khi
mất dấu (đối xứng `smooth_display.py` / `live_pipeline.py`). Test mới khoá đúng ca này:
`test_VOS_rong_THAT_phai_lam_tang_lost_va_reset_moc` (mask rỗng + bbox `(0,0,0,0)` như engine thật ⇒
3 bước = `_lost = 3`; vật hiện lại chỗ khác ⇒ **không** `nghi`, **không** `chua_xac_minh`).
Đã kiểm **mutant**: bọc lại `if obs_bbox is not None` ⇒ test **ĐỎ**.

Các mục còn lại của vòng 2 đã đóng:

| mức | phát hiện | xử lý |
|---|---|---|
| **P2** | Test P1 vòng 1 dùng `bbox=(10,10,30,30)` với mask rỗng — trạng thái engine **không bao giờ** sinh ra ⇒ test xanh dù web bỏ qua VOS rỗng | sửa thành `(0,0,0,0)` + assert `_lost == 3` |
| **P2** | **P0 chỉ khoá bằng chuỗi source**: revert về `switch = watch.nghi or switch` vẫn xanh | thêm assert hành vi: sau khi sang `chua_xac_minh` **không** còn `switch_warning=True`. Đã kiểm mutant: revert sticky ⇒ `test_render_nhan_chua_xac_minh_sau_khi_bam_on_dinh` **ĐỎ** |
| **P3** | `buoc_moi=False` có đổi `_vua_bao` (không phải no-op tuyệt đối) | ghi rõ hợp đồng trong docstring (`vua_bao` = cờ của **lần gọi này**); test assert `_lost/_grace/_settle/_trang_thai` không đổi |
| **P3** | log §5.2 vẫn ghi "ca 21-11 vật không rời khung" (**SAI**: f176–177 có 2 frame rỗng) | sửa, ghi rõ ngưỡng 2 sẽ mất ca đúng đó |
| **P3** | log ghi `2 017 passed`, "worker thật" (thực tế là stub) | cập nhật `2 026 passed` + nói rõ test dùng `_update_stats_locked` + stub, **không** phải engine SAM 2 |
| **P3** | `eval_gate_rules` docstring còn "1 ca đúng / 1 ca sai"; `replay` docstring ghi sai tên artifact; thiếu `lost_reset_streak_truoc: 0`; comment cũ "nghi ẩn y như no_evidence" | sửa hết |
| **P3** | Artifact ghi `git_rev` của commit **trước** HEAD | sinh lại ở commit code cuối; delta tới commit chứa artifact **chỉ là `data/`** ⇒ tiêu chí `git_dirty_code = false` |

## 4. Output / Kết quả

### 4.1. Phiên người dùng báo (404 frame) — replay bằng **chính** `IdentityWatch`

| | báo | ẩn mask | chưa xác minh |
|---|---|---|---|
| trước (`lost_reset_streak=0`) | 1 lần (f264) | 8 | **132 (32,7 %)** |
| **nay** (`=3`) | **0** | **0** | **0** |

### 4.2. Không mất ca báo đúng nào — `scripts/eval_gate_rules.py`

Nhóm chi phí **10 phiên / 1 509 frame** (danh sách đóng băng `data/eval_gate_config_list.json`):

| luật | báo | ẩn | chưa xác minh | **không tin cậy** | bắt ca ĐÚNG |
|---|---|---|---|---|---|
| `hien_tai_truoc_khi_tai_bam` (cũ) | 6 | 3,71 % | **11,33 %** | 15,04 % | **7/7** |
| **`hien_tai` (nay)** | 6 | 3,71 % | **4,24 %** | **7,95 %** | **7/7** |

### 4.3. Toàn bộ pool — `scripts/replay_latch_settle.py` (26 phiên ĐO ĐƯỢC / 5 180 frame, `settle=8`)
`data/replay_latch_tai_bam_2026-11-24_metrics.json` (`git_rev 05880ad`, `git_dirty_code=false`)

| | báo | ẩn | chưa xác minh |
|---|---|---|---|
| `--lost-reset 0` (cũ) | 25 | 4,77 % | **29,77 %** (1 542 frame) |
| **`--lost-reset 3` (nay)** | **24** | **4,31 %** | **16,20 %** (839 frame) |

⇒ **−45,6 %** frame "chưa xác minh"; riêng chi phí latch kiểu cũ (`settle=0`) giảm **34,54 % → 20,50 %**.

### 4.4. Kiểm tra

- `./run lint` xanh · `./run test` **2 027 passed** (5 deselected; lần chạy cuối, sau cả 3 vòng review).
- Artifact (sinh trên **cây sạch ở `05880ad`** = commit code cuối cùng, `git_dirty_code = false`;
  commit chứa artifact là commit **sau** đó và delta chỉ là `data/` ⇒ đúng tiêu chí tái lập của repo):
  `data/eval_gate_rules_2026-11-24_metrics.json` — chứa **cả hai cột** luật đang ship (`hien_tai`) và
  luật trước 24-11 (`hien_tai_truoc_khi_tai_bam`) trong cùng một `git_rev`;
  `data/replay_latch_tai_bam_2026-11-24_metrics.json` — `lost_reset_list = [0, 3]` +
  `reacq_grace_steps = 2`, tức **cột "trước" nằm trong cùng file** (khoá `"<settle>|<vắng>"`).
  `git_dirty = true` ở cả hai là do chính file artifact vừa ghi; tiêu chí tái lập của repo là
  **`git_dirty_code`** (bỏ qua `data/`).

## 5. Vấn đề & cách xử lý

1. **Không sửa bằng cách nới ngưỡng.** Bảng 4.2 xác nhận lại kết luận 24-11: mọi luật "giảm số lần báo"
   (`theo_dt` 3/7, `van_toc_lich_su` 6/7, `chi_khi_cham_*` 1–5/7) đều **mất ca đúng**. Thay đổi lần này
   không đụng ngưỡng px nào, chỉ đổi **điều kiện chấm**.
2. **Đánh đổi phải nói rõ:** sau khi vật rời khung rồi vào lại, hệ **tin** vùng mới (không còn dấu
   "chưa xác minh"). Ca "vật ra khung rồi một vật khác vào" thì không phân biệt được nếu không có re-ID
   — ranh giới đã biết, không phải bug mới. **Về ca 21-11** (`demoip_1121-121732`, bám sang cửa/tường be
   cùng tông): câu "vật không rời khung" là **SAI** — CSV có **2 frame rỗng liền** (`f176–177`,
   `lost=1`, `mask_area=0`) ngay trước cú báo đúng `f178`. Nó sống sót vì **2 < 3**, tức **ngưỡng 2 sẽ
   MẤT ca đúng đó** ⇒ đây là ca đúng **sát ngưỡng**, đã khoá bằng `TestBienCuaNguongVang`. Cùng nhóm
   với `125109#137` (vắng **1** frame).
3. **CÒN HỞ (không sửa trong phiên này): trôi dần.** Ảnh `m330` của chính phiên này cho thấy ô bám sang
   **tường** ~130 frame mà cổng **không** báo (đúng kết luận 23-11: cả hai cổng đều mù với trôi dần,
   biên quyết định chỉ 0,937→1,019 = 8 % ngưỡng). Muốn bắt phải có mô hình chuyển động/kiểm mask thật
   ⇒ việc > 4 h ⇒ **plan 3 ý kiến trước** (xem Tầng 2).

## 6. Next steps

- [ ] **Chạy lại `./run demoip`** với vật ra/vào khung ~10 s: kỳ vọng **0 WARN**, `chua_xac_minh_n = 0`,
      không còn ô nét đứt kéo dài. (Đây là bằng chứng live còn thiếu — số hiện có là replay trên CSV.)
- [ ] **Tầng 2 — Cutie / verified re-anchor**: trôi dần sang tường sau khi vật rời khung (§5.3) là thứ
      cần cơ chế mới, không phải ngưỡng. Trước khi tuyên bố "tốt hơn" phải đo **ngưỡng nhiễu mIoU**
      cho clip dùng để chấm.
- [ ] Người thứ 2 dán nhãn 7 ca để được TRÍCH "7/7" trong báo cáo (nợ từ plan 24-11).

## 7. Tài liệu tham khảo

- `docs/plan/24-11-2026-cong-nghi-bao-oan.md` (7/7 ca đúng, 7 luật bị bác, vì sao không nới ngưỡng)
- `docs/task/24-11-2026-cong-nghi-tu-ha-muc.md` (3 trạng thái `ok`/`nghi`/`chua_xac_minh`, settle 8)
- `docs/task/23-11-2026-phan-tich-phien-demoip-1123-bam-nham-remote.md` + `docs/plan/23-11-2026-chon-co-che-tu-tim-lai.md`
  (cổng mù với trôi dần; re-ID nhận lại sai)
- `src/identity_guard.py` · `scripts/eval_gate_rules.py` · `scripts/replay_latch_settle.py`
