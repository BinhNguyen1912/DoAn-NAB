# Plan 24-11-2026 — Bám bắt **vật bất kỳ** (đường B): lộ trình có số

> Lập theo AGENTS §9.2: 3 agent độc lập (chất lượng & số đo · sản phẩm & bằng chứng · độ bền & hiệu
> năng) → 1 vòng phản biện chéo → chốt. Toàn bộ **số trong plan này do parent đo lại trên máy này**;
> chỗ nào là số của agent thì ghi rõ.

## 🎯 Câu hỏi cần quyết

Giảng viên/hội đồng sẽ đưa **một vật bất kỳ** (không phải vật đã chuẩn bị). Trong **~2 tuần**, với
**CPU không GPU rời**, làm gì để (a) hệ bám đúng hơn **đo được**, (b) buổi bảo vệ **không thể hỏng**
vì một câu nói sai, và (c) **không** đốt giờ vào hướng đã bị số đo bác?

Ràng buộc không được vi phạm: không đổi `configs/default.yaml` (artifact cũ phải tái lập); mọi tuyên bố
chất lượng phải là **mIoU mask-vs-GT người tô**; so sánh phải **theo cặp từng frame** + CI95 + `n`;
`n=1` và `mIoU_p05` khi `n<30` thì **không kết luận**.

---

## 🧭 Trạng thái đã đo (mốc xuất phát — không phải ý kiến)

| clip (GT người tô) | vật | mIoU @192 | mask ngoài GT | bịa mask khi vật vắng |
|---|---|---|---|---|
| `data/clip_be2.mp4` (`docs/gt/vat_be_vaolai`, 11 frame) | vật be, có tay che, ra/vào khung | **0,8625** (n=8) | 5,2 % | **0/3** frame (0 px) |
| `data/binh1.mp4` (`docs/gt/b1`, 12 frame) | chai có nhãn | **0,7794** (n=7) | ≤1,9 % | — |
| `data/clip_tran_nen.mp4` (`docs/gt/tran_nen`, 6 frame) | **túi/tờ giấy TRẮNG MỜ trên tường TRẮNG** | **0,6987** (n=5) | **17,4 %** (tệ nhất 36,9 % @f0) | **1/1** frame **3 713 px lên mặt người** |

**"Trần" của từng hướng (cận trên lý thuyết, parent tính lại từ mask đã dump):** nếu cắt *hoàn hảo*
phần tràn thì `tran_nen@192` = **0,8254 (+0,128)**, `tran_nen@320` = 0,8167 (+0,088), `be2` = 0,9132
(+0,048). ⇒ **phần lỗi lớn nhất là TRÀN RA NỀN**, không phải trôi; và trên `tran_nen` mIoU **tăng** theo
frame (f0 0,5324 → f400 0,7882) ⇒ **không có trôi dần** trên clip có GT.

---

## 🧭 Ba góc nhìn (vòng 1)

### A. Chất lượng & số đo
Lỗi chính là **frame 0 + tràn nền**, không phải bộ nhớ ⇒ đề xuất: GT+số cho ca cùng tông (cắt từ
`clip_dung`/`clip_sai` đã có), phân rã lỗi mask, **băng thử refiner biên offline** (chọn làm "1 việc"),
ma trận INIT (điểm âm/dương, seed mask @320), proxy "sắp sụp" chỉ bàn cổng nếu AUC ≥ 0,8.

### B. Sản phẩm & bằng chứng bảo vệ
Rủi ro P0 **không phải** con số thấp mà là **bằng chứng không mở được + tự mâu thuẫn**: `origin/main`
dừng 22-11, nhánh ahead **60 commit**; nhiều câu trong tài liệu nộp nói ngược artifact. Kịch bản
không hỏng = **nói trước hạn chế bằng số + 2 đường lui cơ học**, không hứa "bám mọi vật".

### C. Độ bền & hiệu năng
**Nhịp mask là bậc một** với **ô hiển thị** (IoU ô 0,8460 ở `vos_every 1` → 0,5815 ở 3, chênh −0,2645 >
nhiễu 0,0903 — *đây là IoU hộp, không phải mIoU*) ⇒ model chậm hơn không miễn phí. Ngân sách ≤ ~100 ms
(giữ nhịp) / tối đa ~240 ms. Đề xuất: quét checkpoint bằng mIoU, provenance, spike Cutie có kill criteria.

---

## ⚔️ Tranh chấp (vòng 2 — phản biện chéo) và **kết quả parent kiểm tay**

| Điểm tranh chấp | A nói | B nói | C nói | **Chốt của parent** |
|---|---|---|---|---|
| **"0,8460 → 0,5815" dùng làm gì** | nó là IoU **ô**, không phải mIoU | (không bàn) | nó là luật "nhịp là bậc một" | **C tự rút, A đúng**: đó là `IoU(ô hiển thị, hộp GT)`; `lk_ok_frac` chỉ 0,143 ⇒ phần lớn là **ô đóng băng**, không phải bộ nhớ kém. **Cấm** trích làm mIoU. |
| **Cần bao nhiêu frame GT** | 90 frame rải 6 clip × 12–15 | 59 frame (19+24+7+6+3) | 90 frame rải (không cho p05) | **C đúng, A sai**: `MIN_SAMPLES = 30` **trên một artifact** ⇒ rải 12–15/clip thì **p05 = None ở cả 6**. Bộ ≥30 duy nhất (`docs/gt/remote_trang`) là `synthetic_exact` ⇒ **cấm** dùng làm p05 "người tô". |
| **`docs/gt/binh1_silhouette` + `binh1_tay`** | (không bàn) | "khai 12 frame GT nhưng **không có** PNG" | "PNG **có** 12/12, chỉ sai tên ⇒ đổi `frames/frame_*` → `gt_*`" | **B đúng, C SAI — và đề xuất của C là NGUY HIỂM**: `frames/` là **ảnh gốc 720×1280** để người nhìn mà tô; `gt_*.png` = **0 file**; README của bộ GT ghi rõ "**Bạn cần tạo**". Đổi tên ảnh gốc thành GT = **tạo GT giả**. Việc đúng: đánh dấu `dung_duoc: false` + cảnh báo trong `./run miou`. |
| **Có nên spike Cutie** | chưa (không có hiện tượng để sửa) | (không bàn) | có, kill > 150 ms | **Chưa spike.** Điều kiện mở lại ghi trước: chỉ khi có clip GT chứng minh **trôi/ra-vào khung**; dùng `be2` (mốc 0,8625, hai frame tái xuất 0,8358/0,8117), **kill nếu median > 100 ms/frame**. |
| **"1 việc"** | băng thử refiner | bảng tuyên bố ↔ artifact | quét checkpoint | **Cả ba đều bị số bác hoặc bị hạ ưu tiên** — xem mục ✅. |

### 5 kết quả ÂM TÍNH parent tự đo trong phiên này (dùng để không ai đề xuất lại)

1. **Quét checkpoint @192 trên `clip_tran_nen`**: tiny **0,6987** · small 0,2570 (config SAMURAI) / 0,5258
   (config gốc) · base_plus 0,2716 / 0,2741. ⇒ **model to hơn TỆ HƠN 2,5×**, *không* phải do sai config;
   small/base_plus **mất vật hẳn** (mask 0 px từ giữa clip). Trục "dung lượng model" **đóng**.
2. **Refiner rẻ trên mask đã dump**: `opening 3×3/5×5 + CC to nhất` = **no-op** (0,6972/0,6970 vs
   0,6971; `be2` y hệt) ⇒ phần tràn là **dải liền** với vật, không phải mảnh rác (⇒ `convex hull` chỉ
   làm tràn **tăng**). `erode 1/2/3` = 0,6882/0,6731/0,6517 (**tệ dần**). `GrabCut` = 0,6885/0,8581
   (**tệ**), 43–85 ms/khung.
3. **Nâng `--mask-threshold` 1,0/2,0** = 0,6450/0,5321 (vật mờ có logit thấp ở **giữa** vật).
4. **`--reanchor-every 30`** = **0,3965**, tràn 53,9 % (neo bằng ô đã trôi = khoá cái sai).
5. **`image_size 320` vs 192**: so cặp 5 frame **+0,0282, CI95 [−0,0416, +0,1126] chứa 0, sign test
   p = 1,00** ⇒ **"không phân biệt được"**. Cái **chắc chắn** ở 320: bịa mask ở frame vật vắng
   3 713 → **0 px**, tràn 17,4 → 11,7 %, **giá 534 ms/frame**.

### Một phát hiện MỚI chưa được kiểm (agent A) — và cách nó bị nhiễm bẩn
Agent A tìm thấy trong mã SAM 2 **hai ngưỡng lệch nhau cho cùng một quyết định**:
`samurai/sam2/sam2/configs/samurai/sam2.1_hiera_t.yaml:126` → `min_obj_score_logits: -1`;
`sam2_base.py:398` zero-hoá mask theo `> -1`, nhưng `sam2_base.py:867` lại dùng `> 0` để gắn
`no_obj_embed_spatial` (config bật `no_obj_embed_spatial: true`). Dữ liệu `data/fac_A.csv` (tiny @192,
binh1, 333 frame) parent **kiểm lại đúng**: 113/113 frame mask rỗng có `score ≤ −1,086`; **15 frame có
mask 42–3 767 px** nằm trong dải `(−1, 0]`; frame có vật thật `score ≥ 0,582`. ⇒ có **khoảng trống
~0,58 logit** để đặt ngưỡng.

**Nhưng 3 lần chạy thử hôm nay ĐỀU NHIỄM BẨN ⇒ chưa được kết luận:** parent copy `sam2.1_hiera_t.yaml`
thành `_tmp_gate0/_tmp_gate100/_tmp_control` rồi trỏ `model_cfg` vào bản copy ⇒ **cả 3** cho
mIoU **0,2486** và tràn **70,3 %**, trong khi chạy lại config **gốc** cho **0,6987 y hệt lần đầu**
(mask từng frame trùng khít: 18 174 / 13 362 / 15 865 / 15 249 / 14 090 px). ⇒ **copy config làm đổi
hành vi** (f0/f45 còn giống, từ f222 lệch) ⇒ **cấm** A/B bằng cách copy file config; phải override qua
`build_overrides()` (`src/tracker_engine.py:35`, hiện chỉ có `++model.image_size`).

---

## ✅ Quyết định

**Chọn: lộ trình 5 việc, 9,5 h cho phần không điều kiện + 5 h phần điều kiện.** Thứ tự tuyệt đối
**P0 → P1 → P2 → (P3 có điều kiện)**. Ba việc đầu **không** đụng model, **không** cần GT mới.

| # | việc | giờ | nghiệm thu CÓ SỐ | đụng model/GT? |
|---|---|---|---|---|
| **P0-a** | **Đưa bằng chứng lên `main`**: tách 60 commit thành 3 PR nhỏ (code+tests+web · `data/miou_*`+`docs/gt/*` · docs+plan), PR có artifact **merge commit, không squash** | 2,5 | `git log --oneline origin/main..HEAD \| wc -l` = **0**; `git show origin/main:run \| grep -c -- "--no-reid"` ≥ 1; `origin/main` chứa `data/miou_be2_full_2026-11-24_metrics.json` + `docs/gt/tran_nen/index.json`; `./run provcheck` exit 0; CI xanh | không |
| **P0-b** | **Sửa các câu đã KIỂM là sai** + đưa số mới vào bảng tự kiểm: `README.md:8` ("0,2–0,3 FPS" → số thật 142 ms ≈ 7 FPS), `README.md:140` (`--reid` → `--no-reid`), `README.md:618` ("đã bật sẵn re-ID, bám lại đúng"), `AGENTS.md:141` ("demo 256" → **192**), `docs/doi-chieu-yeu-cau-gvhd.md` req 9 (✅ tái nhận diện → 🟡 + caveat đã có ở req 6), req 10 (**0,6464 = IoU(mask, hộp bao)**, thay bằng dòng mIoU silhouette); `scripts/so_lieu_bao_cao.py::REGISTRY` (**20 dòng**) thêm dòng cho: 0,8625 (n=8) · 0,7794 (n=7) · 0,6987 (n=5) · 0/3 bịa mask · **5 kết quả âm tính** trên; mỗi dòng **có `n`** và câu "**cấm trích thành**" | 2,0 | `./run lint` xanh; `grep -c "0,2–0,3 FPS\|đã bật sẵn re-ID\|image_size 256" README.md AGENTS.md` = **0**; `python scripts/so_lieu_bao_cao.py --check` xanh với **≥ 28 dòng**; test tamper: sửa 1 số ⇒ exit ≠ 0 | không |
| **P1** | **Chặn bẫy dữ liệu**: `docs/gt/binh1_silhouette` + `binh1_tay` khai 12 frame nhưng **0 file `gt_*.png`** ⇒ thêm `"dung_duoc": false` + lý do vào `index.json`, và `./run miou score` **cảnh báo rõ** thay vì chỉ "12 lỗi chặn"; **cấm** đổi tên `frames/*` thành `gt_*` | 0,5 | `./run miou score --gt docs/gt/binh1_silhouette --check-index` in **"bộ GT CHƯA TÔ"** + exit ≠ 0; 2 test mới; `git diff --stat` không có file `gt_*.png` mới nào ở 2 thư mục đó | không |
| **P2** | **Đo được cái đang mù**: (a) thêm cột tổng hợp `dien_tich_pred/gt` + `phu_thieu` vào `scripts/score_miou.py` (hiện chỉ có `mask_ngoai_gt`), (b) in bảng từng frame cho 3 clip GT, (c) **kiểm lại giả thuyết cổng vật-vắng** bằng **hydra override** (không copy config): `build_overrides()` thêm `++model.min_obj_score_logits=0` và `=−100` (chẩn đoán) | 2,0 | (a) artifact có 2 cột mới, 2 test; (b) mỗi frame có `mask_ngoai_gt` + `phu_thieu` + `iou`; (c) 3 run trên `binh1` (`fac_A` có 15 frame nghi): mục tiêu **bịa 15 → 0** *và* `zero_oan` (= frame GT có vật mà mask rỗng) **không tăng**; nếu `−100` cho thấy small/base+ thật sự phân đoạn tốt ⇒ **kết luận (1) phải sửa lại** (dung lượng *có* là nút thắt, chỉ bị cổng chặn) | (c) đụng model qua override, **không** copy config |
| **P3** *(điều kiện)* | **INIT hardening**: box · box + 4 điểm âm vành · +điểm dương lõi · seed mask @320 qua `add_new_mask`; chạy `tran_nen` + `be2`, `vos_every 1`, **3 lần** | 3,0 | `tran_nen`: mIoU **≥ 0,7487** (+0,05) với **CI95 cặp không chứa 0** *và* `mask_ngoai_gt ≤ 0,12` *và* `phu_thieu` không tăng > 0,02; `be2` **≥ 0,8525**; nếu âm tính ⇒ **ghi thành kết quả âm tính**, không đưa vào live | model (+3 frame GT nếu muốn sign test 8/8) |
| **P4** *(điều kiện)* | Spike **Cutie** trong worktree + env riêng, hệ sống ≤ 100 ms | 2,0 | **kill nếu median > 100 ms/frame** hoặc mIoU cặp không vượt tiny; clip `be2`, mốc 0,8625 + f344/f348 0,8358/0,8117 | model mới |

### Vì sao chọn (kèm số)
- **P0-a/P0-b trước mọi thứ**: mIoU 0,6987 hay 0,8625 đều **giải thích được**; một câu sai trong tài liệu
  nộp thì **không**. `origin/main` chậm **60 commit** ⇒ mọi số 23–24/11 **không mở được từ link**.
- **P2(c) là hướng rẻ còn sống duy nhất** sau 5 kết quả âm tính: nó nhắm đúng 15 frame **có mask nhưng
  score ∈ (−1, 0]** (42–3 767 px) trên `binh1`, khoảng trống ngưỡng ~0,58 logit, **không cần GT mới**,
  revert = bỏ 1 dòng override.
- **Không** chọn "băng thử refiner" (A) vì 3/5 ứng viên đã chết bằng số; **không** chọn "quét checkpoint"
  (C) vì đã âm tính; **không** chọn "90 frame GT rải" vì p05 cần ≥30/clip.

### Bác (để sau không mở lại)
| phương án | số bác |
|---|---|
| Đổi checkpoint / model to hơn | tiny 0,6987 vs small 0,2570 / base_plus 0,2716–0,2741 @192 |
| `image_size` 320 cho live | +0,0282 CI95 chứa 0, p=1,00; giá 534 ms (1,9 FPS) |
| Ngưỡng mask 1,0/2,0 | 0,6450 / 0,5321 |
| `--reanchor-every` | 0,3965 (tràn 53,9 %) |
| Bật lại re-ID | 0,4236 vs 0,7794; bịa mask 5/5 frame |
| Cổng diện tích / cổng cos / latch | 50,5–73,6 % frame NGHI, 91,5 % trong đó báo oan |
| Refiner `opening+CC`, `erode`, `GrabCut`, `convex hull` | no-op / tệ hơn / chắc chắn tăng tràn |
| Cắt mask theo ô LK | no-op (`mask_area/bbox_area` max 0,841) |
| Đổi tên `docs/gt/*/frames/*` thành `gt_*` | = **tạo GT giả** (12 ảnh gốc 720×1280) |
| A/B bằng cách **copy file config** | copy y nguyên cũng cho 0,2486 thay vì 0,6987 |

### Tiêu chí nghiệm thu toàn plan (có số)
- [ ] `origin/main` chứa code + artifact mà báo cáo trích (`git log origin/main..HEAD` = 0).
- [ ] 0 câu trong README/AGENTS/`doi-chieu-yeu-cau-gvhd` mâu thuẫn artifact (5 câu đã chỉ định).
- [ ] Bảng tự kiểm ≥ 28 dòng, mỗi dòng có `n`, có "cấm trích thành".
- [ ] Không có `gt_*.png` giả ở `binh1_silhouette`/`binh1_tay`.
- [ ] P2(c): bịa mask trên `binh1` **15 → 0** frame, `zero_oan` không tăng, mIoU cặp không giảm.
- [ ] Mọi tuyên bố chất lượng trong báo cáo dùng **mIoU mask-vs-GT** + `n`; `p05` chỉ khi `n ≥ 30`.

---

## 🗣️ Kịch bản bảo vệ (khi hội đồng đưa vật lạ) — chốt

**90 giây nói trước** (để mọi thứ sau là "xác nhận", không phải "phát hiện"):
> "Máy em không có GPU rời: model **142 ms/lần ở 192 px** ⇒ mask mới **7 lần/giây**; hình **20 FPS** là
> nhờ luồng hiển thị riêng. Video nộp dài **29,33 s** so với **29,5 s** thật (tỉ lệ **0,994**).
> Chất lượng em đo bằng **mask-vs-GT người tô**: **0,86** (vật be, n=8) · **0,78** (chai, n=7) ·
> **0,6987** (túi trắng mờ trên tường trắng, n=5). Ở ca gần giống nền, mask **tràn** — em đo được: nếu
> cắt hết tràn thì mIoU lên **0,8254**, nhưng phần còn lại là **giới hạn model**, không phải lỗi code.
> Em cũng đã thử **model to hơn**: **0,2716** — tệ hơn hẳn, nên vấn đề **không phải** model nhỏ."

**Khi thầy đưa vật bất kỳ:**
> "Nếu vật **cùng tông nền**, hệ sẽ trôi — em có số cho đúng ca đó (0,6987, tràn 17,4 %). Em bấm `r`
> chọn lại: đó là **tính năng chọn đối tượng** của đề cương, không phải che lỗi."

**Cấm nói**: "tự nhận lại 17/17" · "tự tìm lại khi vật ra khỏi khung" · "mask 30 FPS" · "bám được mọi
vật" · "320 tốt hơn 192" · "p05 = None nghĩa là 0".

---

## 📌 Việc tách ra ticket
- [ ] `POST /api/live/select` giữa phiên **no-op** (`routes.py:223` hứa nhưng `live_tracking.py:842` chỉ
  đọc `bbox.json` lúc chưa start) ⇒ hoặc làm thật (poll `select.json` như `confirm.json`) hoặc **gạch
  lời hứa**. 1,5 h — chưa chốt vì chưa có số.
- [ ] HUD CLI in cấu hình đang chạy (`src/visualizer.py` hiện `grep -c image_size` = 0).
- [ ] Đo **nhiễu GT** (tô lại 3 frame): mọi chênh mIoU nhỏ hơn `1 − IoU(GT,GT)` là **không kết luận được**.

## 📚 Tham chiếu
- `docs/task/24-11-2026-chot-plan-6-viec-va-cham-miou-tren-gt-nguoi-to.md` (mục 8 — số mới nhất).
- `docs/phan-tich-dung-sai-model-may-code.md`, `docs/thuoc-do-bam-dung.md`, `docs/demo-clip-va-o-chon.md`.
- `docs/plan/24-11-2026-chong-tran-nen-cung-tong-chot.md` (plan trước — các hướng đã bị bác).
- Artifact: `data/miou_be2_full_2026-11-24_metrics.json` · `data/miou_tran_nen_truoc_2026-11-24_metrics.json`
  · `data/miou_tran_nen_320_2026-11-24_metrics.json` · `data/miou_tran_nen_baseplus_2026-11-24_metrics.json`
  · `data/miou_tran_nen_small_2026-11-24_metrics.json` · `data/fac_A.csv` (333 frame, score vs mask_area).
