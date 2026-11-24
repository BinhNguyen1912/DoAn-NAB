# Plan 24-11-2026 — Cổng "nghi đổi đối tượng" báo oan khi vật đi nhanh

## 🎯 Câu hỏi cần quyết
Người dùng báo: **"vật trắng trơn (remote) di chuyển nhanh quá thì bị nghi đổi đối tượng"**.
Hỏi: trong ~2 tuần trước bảo vệ, **có nên sửa thuật toán cổng** `src/identity_guard.is_suspect_switch`
(ngưỡng nhảy = `min(max(0,10·đường_chéo, 1,5·max(w,h)), 0,25·đường_chéo)` = **200 px** ở 640×480),
hay chỉ **giảm thiệt hại**? Ràng buộc: máy không GPU, `./run demoip` là đường demo chính, mọi số phải
đo được trên artifact đã commit, **không được bỏ ca báo đúng nào**.

## 🧭 Ba góc nhìn (vòng 1 — độc lập, không biết nhau)

### A. Chất lượng & số đo
Đo lại từ đầu: **17 lần cổng báo / 14 phiên**, `IoU(ô trước, ô sau) = 0` ở **26/27** cú nhảy ⇒ hình học
không tách được. Phát hiện **trần 200 px bị chạm 80,2 % số bước** ⇒ "ngưỡng theo kích thước vật" thoái
hoá thành **hằng 200 px**. Đề xuất: (1) **mua nhãn 23 lần báo** với luật viết trước (`SAI ⇔ vật trong
ô mới ∧ fill ≥ 0,5`); (2) lọc phiên theo config + ghi `frame_shape`; (3) đo `σ_jump`; (4) **đổi biến
quyết định sang trọng tâm mask**; (5) đổi chữ banner; (6) **bác cả A/B/C/D kỹ thuật**.

### B. Sản phẩm & bằng chứng bảo vệ
Chi phí thật lớn hơn "8 frame ẩn": phiên `144057` chỉ **22,4 %** frame bình thường, **60,3 %** ở
`chua_xac_minh` (**không tô mask, không quỹ đạo** ⇒ mất **yêu cầu 5 của đề cương**). **Take sạch là
khả thi**: `110536` = 200 frame, `nghi = 0`. Đề xuất: (1) **diễn tập + khoá kịch bản + video dự
phòng** (2,5 h, 0 code); (2) **vẽ quỹ đạo mảnh ở `chua_xac_minh`**; (3) bảng nhãn + ảnh; (4) cờ
`--max-jump-ratio`/`--settle-steps` làm **van xả demo**; (5) Caps Lock; (6) **không port LK**.

### C. Độ bền & hiệu năng
Dựng lại `IdentityWatch` từ CSV khớp **tuyệt đối** cột `nghi_doi_tuong` ⇒ replay là dụng cụ tin được.
Phát hiện **`chua_xac_minh` không có đường tự xoá** ⇒ **đuôi** (frame sau lần báo cuối) là chi phí
thật: `144057` = **77,6 %** phiên. Bác LK vì: trần nuốt số hạng LK ở **79,7 %** frame; `residual =
jump·(1 − P/dt)` làm phán quyết **thành hàm của fps hiển thị** (biên ca đúng chỉ 11,7 px); LK từ chối
**6/7** frame đúng lúc cần (bão hoà chuyển động lớn); và **race** `(dx, None)` giết phiên. Đề xuất:
(1) **đóng băng replay thành test**; (2) `max_jump_ratio` vào `run_info`; (3) chỉ số **đuôi**; (4) kiểm
ảnh vài cú nhảy; (5) tuỳ chọn nâng trần 0,25→0,30.

## 🔬 Đo trong lúc tranh luận (đã commit, cây sạch `243e146`)
**Kết luận lật 2 lần** — bản cuối cùng dựa trên **đọc video HUD** (`_web.mp4`) của 3 phiên có sự kiện:

> **6/6 lần cổng báo trên nhóm đóng băng là ĐÚNG.** Cái được gọi là *"vật đi nhanh nên bị nghi"* thực
> ra là **vùng bám đã rời VẬT ĐÃ CHỌN**: `144057` chọn **thìa gỗ** (`prompt_bbox=[397,79,491,462]`),
> người dùng rút thìa gỗ xuống rồi đưa **thìa nhựa trắng** vào ⇒ SAM 2 bám **thìa nhựa** ⇒ danh tính
> **đã đổi**. `141352` cùng kịch bản. `144226` báo khi **tay người khác** đi vào khung.

| luật | báo | không tin cậy | **đuôi** | **bắt ca ĐÚNG** |
|---|---|---|---|---|
| **hiện tại** | 6 | 15,04 % | 9,68 % | ✅ **7/7** |
| `theo_dt` | 4 | 14,84 % | 10,54 % | ❌ **3/7** (mất 4) |
| `van_toc_lich_su` | 9 | **26,57 %** | 18,56 % | ❌ 6/7 (thêm 3 báo, mất 1) |
| `theo_dt_va_dien_tich` | 3 | 14,84 % | 11,20 % | ❌ **2/7** (mất 5) |
| `chi_khi_cham_600` | 1 | 0,20 % | 0 % | ❌ 1/7 |
| `chi_khi_cham_900` | 2 | 4,04 % | 3,31 % | ❌ 3/7 |
| `chi_khi_cham_1200` | 3 | 4,04 % | 2,45 % | ❌ 4/7 |
| `chi_khi_cham_1500` | 4 | 13,32 % | 11,20 % | ❌ 5/7 |

Nguồn: `data/eval_gate_rules_2026-11-24_metrics.json` (`git_rev 243e146`, `git_dirty_code=false`),
nhóm **10 phiên ĐÓNG BĂNG / 1 509 frame** (`data/eval_gate_config_list.json`).

**Số quyết định (chất lượng/đo):** biên `|Δtâm| / bán kính` — bước **KHÔNG báo** cao nhất **0,937**,
bước **báo** thấp nhất **1,019** ⇒ **khoảng trống chỉ 8 % của ngưỡng**. Và cổng **mù với dịch chuyển
127–172 px** (141352 f7/f12/f16/f17 — mask tô đặc trên tóc/mặt mà không cảnh báo) ⇒ **lỗi là RECALL,
không phải precision**. Mọi đề xuất nới ngưỡng đi **sai chiều**.

## ⚔️ Tranh chấp (vòng 2 — phản biện chéo)

| Điểm | Chất lượng & đo | Sản phẩm | Độ bền | **Chốt** |
|---|---|---|---|---|
| **D1** tự phục hồi `chua_xac_minh → ok` sau N bước | **KHÔNG** (không có bộ kiểm nào hoạt động: `track_cos` vùng sai 0,752–0,989 vs 0,905 đúng) | **KHÔNG**; điều kiện để mở lại: tiêu chí phải là **bằng chứng** (IoU mask vs mask đã xác nhận, τ đo trước) + đếm `auto_ok_n` + mặc định TẮT | **KHÔNG**: N=16 đổi **119 frame (6,66 %)** sang "tin cậy" mà không có bằng chứng, **97/119 nằm trong 144057** | **KHÔNG** — nhưng **ghi nhận** đuôi 8,17 % là chi phí thiết kế, không phải bug |
| **D2** vẽ quỹ đạo ở `chua_xac_minh` | (không đề xuất) | **RÚT LẠI đề xuất vòng 1**: ảnh `l9.6` cho thấy `chua_xac_minh` **có lúc chỉ vào tường**. Vẽ là "nói dối có timestamp". Trả yêu cầu 5 bằng `ok` + kịch bản bấm `c` | **KHÔNG**: đảo `visualizer.py:318-319` + xoá `test_visualizer.py:886`; `c` lại xoá quỹ đạo | **KHÔNG** |
| **D3** nâng trần 0,25→0,30 | **KHÔNG** (cửa sổ 231–255 px = 3,1 % đường chéo = 1 ca mỗi loại) | **KHÔNG**: **90,3 %** "cải thiện" đến từ 2 phiên **ngoài** nhóm đóng băng; **xoá `092343#264`** (ca AGENTS ghi là báo ĐÚNG); đuôi **146→159 (tệ hơn)** | **KHÔNG**: kwarg hiện tại đổi **4 thứ** cùng lúc (`ratio_factor` nhân luôn `1,5·size`); số 174/1152 chỉ tái lập với biến thể "cap-only" | **KHÔNG** |
| **D4** 1 việc trong 3 h | mua nhãn | **diễn tập + video dự phòng** | **diễn tập** | **diễn tập** (nhưng 3 h đủ cho *cả* test đóng băng + nhãn) |
| **LK (port sang `--smooth`)** | bác (2 lý do độc lập: sai thang thời gian; ngoài tầm LK) | bác | bác (5 lý do, có số) | **KHÔNG làm trước bảo vệ** |
| **Luật `chi_khi_cham`** | — | **không ship** | — | **KHÔNG ship**: chỉ giữ **3/7–4/7 ca đúng** ⇒ "giảm chi phí" bằng cách bỏ ca báo đúng |

## ✅ Quyết định

**Chọn: KHÔNG sửa thuật toán cổng trước bảo vệ. Làm 3 việc đo được.**

- **Vì sao:** cổng báo **đúng 7/7** ca đã kiểm, và **cả 7 luật thay thế đều làm MẤT ca đúng**
  (3/7 · 2/7 · 1/7 · 4/7 · 6/7). Không có "báo oan" nào để sửa; lỗi thật là **bỏ sót** (dịch chuyển
  127–172 px không báo; 8/38 lần vật hiện lại sau mất dấu cách > 200 px, gồm 248,9 px ở ca 21-11 —
  log-only, không sửa vì 2/8 ca đó là "vật ra khỏi khung rồi về").
- **Bác:**
  - `theo_dt` — bỏ ca báo đúng (0/1), vì ca OAN nhanh **hơn** ca ĐÚNG (1 763 vs 870 px/s).
  - `van_toc_lich_su` — **nhiều lần báo hơn** (9 vs 6) và chi phí 22,44 % (vs 12,70 %).
  - `theo_dt_va_dien_tich` — bỏ ca báo đúng (0/1).
  - port LK — xem bảng trên.
  - nâng trần 0,30 — đuôi tệ hơn + xoá 1 ca ĐÚNG đã ghi trong AGENTS.
  - vẽ quỹ đạo ở `chua_xac_minh` — ảnh chứng minh vùng đó có lúc SAI.
  - tự phục hồi `→ ok` — không có bằng chứng nào phân biệt được "đúng lại" với "vẫn sai".

- **Tiêu chí nghiệm thu (có SỐ):**
  - [x] `scripts/eval_gate_rules.py` chấm được ≥ 6 luật trên **cùng** `IdentityWatch`, mọi số cùng
        một mẫu số **10 phiên / 1 509 frame** đóng băng trong `data/eval_gate_config_list.json`.
  - [x] Artifact `data/eval_gate_rules_2026-11-24_metrics.json` có `git_rev`, `git_dirty_code=false`,
        `lenh`, `do_luc`, chỉ số **đuôi** và `phien_co_bao`.
  - [x] Nhãn **7 ca ĐÚNG / 0 SAI** (đọc video HUD; **1 người dán** ⇒ phải có người thứ 2 mới trích).
  - [x] `--settle-steps` / `--max-jump-ratio` là cờ **THẬT** trên **2 đường CLI** (interactive +
        smooth; đường web vẫn mặc định — ticket P2-1), `run_info` có `frame_shape` (**None ở đường
        headless** vì headless không dựng `IdentityWatch`) + `max_jump_ratio` + `frame_shape_doi`;
        Caps Lock không còn làm `c/r/q` im lặng. **13 test mới**; **7/8 đột biến bị bắt** (m8 = gọi `note_frame_shape` chỉ ở frame đầu còn sống ⇒ ticket #51).
  - [ ] **Đóng băng replay thành test**: 10 phiên ⇒ luật đang ship **sau 24-11 tối**
    `(fire=6, ẩn=56, chưa=64, đuôi=39)` — **KHÔNG** phải `(6, 56, 171, 146)`: bộ số đó là **trước**
    khi có luật "vật rời khung rồi vào lại ≠ đổi đối tượng" (`data/eval_gate_rules_2026-11-24_metrics.json`
    vẫn giữ cả hai cột: `hien_tai` vs `hien_tai_truoc_khi_tai_bam`). Khoá theo 171 là khoá sai luật + assert
        **"KHÔNG báo"** cho 4 ca mù (f7 169,1 · f12 172,0 · f16 127,1 · f17 149,2 px) để hành vi hiện
        tại không trôi; đổi `DEFAULT_MAX_JUMP_RATIO` → 0,30 thì test **phải đỏ**.
  - [ ] **Diễn tập 3 lần**: `nghi ≤ 5 %` frame, đuôi `chua_xac_minh ≤ 20` frame, `ti_le_thoi_luong ≥
        0,95` (baseline `110536` = 0,994, `nghi = 0/200`); 1 video dự phòng cùng kịch bản.
  - [ ] Báo cáo chỉ trích: **"6 lần báo / 1 787 frame (0,34 %), 3/11 phiên, đuôi 8,17 %"** + câu
        "cổng cảnh báo để người vận hành quyết, hệ **không tự sửa**". **Cấm** trích "0,71 %",
        "bắt 2/2", "17/17", "cổng bắt đúng ca 21-11".

## 📌 Việc tách ra ticket
- [ ] **Đóng băng replay thành test** (1,5 h) — `tests/test_eval_gate_frozen.py`, dùng danh sách
      đóng băng, `pytest.skip` khi thiếu `data/`.
- [ ] **Người thứ 2 dán nhãn 6 ca** (0,5 h) — điều kiện để TRÍCH số "7/7" trong báo cáo (hiện 1 người).
- [ ] **Giữ `prev` qua ≤ 2 frame mất dấu** — **kỳ vọng** làm ca `121732#178` báo lại được, nhưng
      **CHƯA ĐO ĐƯỢC trên ca đó**: `data/eval_gate_rules_*` cho phiên `121732` `fire = 0` với **mọi**
      luật (CSV không có cột `nghi_doi_tuong`, f178 là `reacquired=1` ⇒ replay đi nhánh `watch.reset()`)
      ⇒ muốn công bố phải dựng lại ca đó bằng replay có re-ID trước. Giá đã đo trên **nhóm phiên**:
      ẩn 56→104, chưa xác minh 171→326, đuôi 146→266 (≈ gấp đôi chi phí) ⇒ cần quyết riêng.
- [ ] **Log-only: đếm "hiện lại sau mất dấu cách > 200 px"** (0,25 h) — đo được **8/38** lần, gồm
      **248,9 px** (21-11 #178) và **303,8 px** (`110536#142`). Không đổi hành vi.
- [ ] **Sửa gốc: giảm mask tràn khi vật đi nhanh** (mask nở 2–4× ⇒ ô trôi ⇒ cổng báo). Đây là nguyên
      nhân thật; việc > 4 h ⇒ plan riêng.

## 📚 Tham chiếu
- Artifact: `data/eval_gate_rules_2026-11-24_metrics.json`, `data/eval_gate_config_list.json`
- Script: `scripts/eval_gate_rules.py`, `scripts/replay_latch_settle.py`
- Ảnh nhãn: `data/tmp_an/v2_*`, `data/tmp_an/v3_*`, `data/tmp_an/l9.6.jpg`, `data/tmp_an/l12.6.jpg`
- Log: `docs/task/23-11-2026-*.md`, `docs/task/24-11-2026-*.md`; AGENTS §6 (cổng nghi, `chua_xac_minh`)
- Ticket: `.scratch/camera-ai-realtime/issues/47-*.md`, `48-*.md`

## Bổ sung 24-11 (tối) — luật thứ 8 KHÔNG phải "nới ngưỡng": điều kiện CHẤM, không phải bán kính

Người dùng báo phiên `demoip_1124-193026`: vật rời khung rồi vào lại ⇒ bị nghi ⇒ kẹt tới hết phiên.
Nguyên nhân **không** nằm trong danh sách luật ở trên: cổng lấy **mẩu rác 559 px** (`bbox_area_ratio
0,346`) của lần dò lại đầu tiên làm **mốc so sánh**, rồi chấm cú nhảy sang vật thật 24 100 px.

⇒ Kết luận ở trên vẫn nguyên: **không nới ngưỡng px, không thêm luật hình học** (bảng `eval_gate_rules`
xác nhận lại 3/7 · 6/7 · 2/7 · 1–5/7). Thứ được thêm là **điều kiện chấm**: `lost_reset_streak = 3`
(vắng ≥ 3 bước = vật rời khung ⇒ phiên bám mới, `reset()` + miễn chấm 2 bước) — đo trên 10 phiên đóng
băng giữ **7/7** ca đúng và giảm chưa-xác-minh **11,33 % → 4,24 %**. Chi tiết:
`docs/task/24-11-2026-vat-roi-khung-khong-bi-nghi.md`. Nợ V0 (người thứ 2 dán nhãn) **vẫn còn**.
