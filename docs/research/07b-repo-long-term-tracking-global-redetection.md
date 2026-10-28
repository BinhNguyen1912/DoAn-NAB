# 07b — Global search / tái phát hiện (re-detection) trong tracker bám dài hạn: cách các hệ nguồn mở làm cho nó RẺ

> Báo cáo research cho quyết định kiến trúc. Ngày: **27-10-2026**.
> Trạng thái: **đề xuất kỹ thuật, chưa chốt** — chọn phương án trong §5, ghi ADR mới trước khi triển khai.
> Mọi truy xuất nguồn trong phiên này dùng `curl --doh-url https://1.1.1.1/dns-query` vào
> `api.github.com`, `raw.githubusercontent.com`, `export.arxiv.org`, `codeload.github.com`
> (web tools pi đã hết hạn mức; `docs.opencv.org` bịCloudflare chặn).

---

## 1. Câu hỏi nghiên cứu

Đồ án mất dấu vật (quay lưng, ra khỏi frame) rồi **không bao giờ tìm lại được** — phần ReID hiện chỉ
khớp khuôn mặt (`src/reid.py:160`, xem `06-*.md` §2.2). Bước "quét toàn frame bằng lưới ô ứng viên"
tự làm đã đo **348 hộp ứng viên = 323 ms** trên laptop CPU (số liệu từ phiên trước, chưa đo lại —
xem §6). Câu hỏi: **các tracker dài hạn (long-term SOT) nguồn mở làm global search / re-detection
bằng thuật toán gì, và làm sao giữ nó rẻ?**

Hình dạng bài toán chuẩn trong các paper (định nghĩa dùng lại toàn báo cáo):

- **Tái phát hiện (re-detection)**: khi tracker mất dấu (target ra khỏi ảnh, bị che kín, bị nhầm),
  chạy một bộ tìm kiếm **trên toàn ảnh** (hoặc vùng phóng dần) để đề xuất hộp mới, rồi **xác minh**
  hộp đó là vật đang theo dõi (dựa template/mô hình ngoại hình đã lưu).
- **Chuyển local ↔ global**: quyết định frame nào cần quét rộng (switch rule) và khi nào chấp nhận
  trở lại (accept rule). Nếu thiếu chống dao động (hysteresis), tracker sẽ "nhảy" qua lại giữa
  trạng thái mất/tìm được.

---

## 2. VOT-LT protocol: "mất" và "tìm lại" được định nghĩa và chấm điểm thế nào

Đây là chuẩn benchmark dài hạn được hầu hết các tracker khía cạnh này đo lường (VOT2018LT/2019LT,
OxUvA, TLP). Truy xuất trực tiếp mã nguồn toolkit:

- Tracker mỗi frame **phải báo lại 2 thứ**: hộp dự đoán + **điểm presence (confidence ≥ 0)**;
  mất dấu = báo ô trống + điểm thấp. Cách tracker chuẩn gói giao tiếp trax:
  `visionml/pytracking` `pytracking/evaluation/vot.py:120-133` — `Report the tracking results to the
  client` → `self._trax.status(tregion, {"confidence": confidence})`
  ([raw](https://raw.githubusercontent.com/visionml/pytracking/master/pytracking/evaluation/vot.py) — **VERIFIED-in-source**).
- Toolkit chấm bằng đường cong **precision–recall theo ngưỡng confidence** (tên VOT gọi là đường
  cong TPR): với mỗi ngưỡng θ, lấy tập frame mà `confidence ≥ θ`, rồi
  `precision = mean(IoU trên tập đó)` và `recall = tổng IoU / số frame vật thực sự hiển thị`.
  Nguồn: `votchallenge/toolkit` (branch `master`) `vot/analysis/longterm.py:80-91`
  — `subset = confidence >= threshold; precision[i] = np.mean(overlaps[subset]);
  recall[i] = np.sum(overlaps[subset]) / n_visible`
  ([raw](https://raw.githubusercontent.com/votchallenge/toolkit/master/vot/analysis/longterm.py) — **VERIFIED-in-source**).
- Ngưỡng confidence được **quét liên tục** (sorted scores chia thành N ngưỡng, thêm −inf/+inf) để
  vẽ đường cong rồi suy ra thước đo tổng (F-score) — `longterm.py:20-45` (ngưỡng) — **VERIFIED-in-source**
  cho phần tạo ngưỡng + TPR; công thức tổng hợp F-score cuối **chưa đọc hết** (xem §6).

**Hệ quả cho đồ án:** "tìm lại được" không phải là trả về hộp đúng ngay, mà là **một máy 2 đầu ra
(hộp + điểm presence)**. Đồ án đã có sẵn cả hai: điểm SAM 2 mỗi frame (`obj_score`/`iou_score`),
và trạng thái `lost` (`src/config.py:52` `lost_after_frames: 2`). Bài toán còn thiếu duy nhất là
**bước tìm hộp khi presence thấp** — chủ đề phần còn lại của báo cáo.

---

## 3. Bảng so sánh các phương pháp

| # | Phương pháp | Năm | Cách tạo ứng viên | Ứng viên/frame | Quy tắc kích hoạt global | Chi phí tương đối (FPS) | Nguồn | Trạng thái kiểm chứng |
|---|---|---|---|---|---|---|---|---|
| 1 | **TLD** (Kalal TPAMI'12) — OpenTLD | 2011-12 | Dọn grid hình hộp phủ toàn ảnh, nhiều tỉ lệ (`TLD.h:107-108`); lọc **variance bằng ảnh integral** rồi **rừng fern** (10 cây); các ô qua fern → đặc trưng **NCC/NN** (cảnh sát conservative similarity) | Grid dày đặc (nghìn ô) → variance lọc phần lớn → **≤ 100 ô** còn đi qua NN (`TLD.cpp:447-449`) | Khi short-term tracker (median-flow/KLT) không có cụm tin cậy: `detected=false` → chỉ chạy detector frame đó | "Real-time" theo tuyên bố — **chưa kiểm chứng số FPS** | [arthurv/OpenTLD](https://github.com/arthurv/OpenTLD) `src/TLD.cpp:414-450` | **VERIFIED-in-source** (mã) — FPS only-claimed |
| 2 | **DaSiamRPN-LT** | 2018 | RPN + hồi quy bbox trong **vùng tìm kiếm nở dần: 255 → 767 px, mỗi frame mất dấu nở thêm một bậc** ("iterative growing search region", "one step iteration ... sufficient") | RPN anchors trong vùng tìm (theo kích thước vùng) | Bật failure khi max-score RPN **< 0.8**; thoát failure khi **> 0.95** | **110 FPS** long-term (GPU TITAN X) | Paper arXiv:1808.06048 (nguồn `.tex` lấy từ `export.arxiv.org/e-print/1808.06048`, §4.1) | **VERIFIED-in-source** (paper LaTeX); mã LT **không có** trên master `foolwood/DaSiamRPN` (chỉ short-term — đã duyệt cây master) |
| 3 | **GlobalTrack** (AAAI'20) | 2019 | **Quét instance toàn ảnh mỗi frame**: R-CNN hai tầng hướng bởi query (QG-RCNN) — template modulating, RPN full-frame + RoI Align + hộp hồi quy | Full-frame RPN (hàng trăm–nghìn RoI) | **Không có switch**: không motion model, không online update, không smoothing — mỗi frame là 1 lần tìm kiếm toàn ảnh độc lập | N/a (GPU; abstract không nêu FPS) | arXiv:1912.08531; [huanglianghua/GlobalTrack](https://github.com/huanglianghua/GlobalTrack) (README); wrapper dùng trong LTMU: `DiMP_LTMU/Global_Track/Global_tracker/global_track.py` | **VERIFIED-in-source** (wrapper + README + abstract) |
| 4 | **Siam R-CNN** (CVPR'20) | 2019 | **Full-image re-detection hai tầng**: RPN trên **toàn ảnh 1000 RoI** + RoI Align so khớp **template frame đầu**; thêm **tối đa 100 re-detection frame trước** làm RoI dự phòng; tracklet DP động | **1000 RPN proposals** (+≤100 trước đó); tăng 10 000 proposal nếu thiếu recall (chậm ~1 FPS) | Không switch — re-detection chạy **mọi frame**, tracklet DP hợp nhất lịch sử | **4.7 FPS** trên GPU V100 (ResNet-101) | Paper arXiv:1911.12836 (`.tex` từ e-print); code: [vision.rwth-aachen.de/page/siamrcnn](https://www.vision.rwth-aachen.de/page/siamrcnn) (không fetch được) | **VERIFIED** (paper .tex); mã only-claimed |
| 5 | **SPLT** "Skimming-Perusal" (ICCV'19) | 2019 | **Coarse-to-fine kiểu cascade rẻ nhất**: thu nhỏ toàn ảnh về dạng grid window 256×256, bước 128 (50% chồng), **≤ 500 ô** (subsample nếu dư) — "skim"; siamese 2 nhánh nhỏ chấm điểm batch-64 → **top-3 vị trí** → chạy RPN + verifier 128×128 quanh từng vị trí | **≤ 500 ô rẻ** + RPN top-3 × ver (đắt, chỉ trên 3 vùng) | Perusal: score của RPN `Object_thres_low = 0.3` → nếu dưới: **bật global (skim)** ngay frame đó; accept nếu RPN `Object_thres_high = 0.7` **và** verifier distance **< G_V_T = 0.8**; thử vị trí skim kế tiếp nếu chưa qua | "Real-time" theo abstract (chạy 4.8× nhanh hơn GlobalTrack/SiamRCNN theo paper) | [iiau-tracker/SPLT](https://github.com/iiau-tracker/SPLT) `RPN_Verifier_Skim_top3.py:35-40, 532-732`, `utils/tracking_utils.py:47-90`; arXiv:1909.01840 | **VERIFIED-in-source** (mã + abstract) |
| 6 | **KeepTrack** (ICCV'21) | 2021 | Không detector riêng: **ứng viên = cực đại cục bộ của response map DCF** (`find_local_maxima, ks=5, th=0.05`) — hàng chục, không phải nghìn; mỗi ứng viên có descriptor → **so khớp NN với ứng viên frame trước** (learned association, gắn ID distractor) | Cực đa cục bộ của score map (đặc trưng < ~50) | Flag tracker `not_found/uncertain`; khi not-found: **vùng tìm kiếm nở dần** theo bộ đếm (`search_area_rescaling`: dùng `min(counter,30)` scale gần nhất ≥ scale cuối trong lịch sử 60 frame, lấy trung bình) | N/a (GPU, không nêu FPS trong đoạn đọc) | [visionml/pytracking](https://github.com/visionml/pytracking) `pytracking/tracker/keep_track/keep_track.py:227-253, 437-441`, `pytracking/parameter/keep_track/default.py:45-47`; arXiv:2103.16556 | **VERIFIED-in-source** (mã + abstract) |
| 7 | **LTMU** (CVPR'20) | 2020 | Khi local lost → gọi **GlobalTrack (QG-RCNN) full-frame** lấy **top-10 hộp** → điểm lại bằng verifier online (`pymdnet`) | 10 hộp từ detector toàn ảnh + verifier | Local DiMP chạy trước; **md_score (LSTM meta-updater trên 3 cue: hình học/phân biệt/ngoại hình) > 0 & flag normal = found**; `md_score < 0 | flag not_found` → global; **accept chỉ khi lost ≥ 5 frame liên tiếp** (`self.count >= 5`) rồi reset đếm | N/a (DiMP50 local + GlobalTrack R-CNN — GPU; không FPS) | [Daikenan/LTMU](https://github.com/Daikenan/LTMU) `DiMP_LTMU/Dimp_LTMU.py:478-512`; arXiv:2004.00305 | **VERIFIED-in-source** (mã + abstract) |
| 8 | **ODTrack** (AAAI'24) | 2024 | **Không có module global search tách rời**: "online token propagation" — chuỗi token đậm đặc truyền frame-kế-frame, attention tự phục hồi khi vật trở lại | n/a (token, không phải hộp) | n/a — thiết kế "no explicit switch rule" | "Real-time" theo abstract | arXiv:2401.01686; [GXNU-ZhongLab/ODTrack](https://github.com/GXNU-ZhongLab/ODTrack) README | Paper verified; **cơ chế re-detect cụ thể only-claimed** |
| 9 | **AQATrack** (arXiv 2024) | 2024 | Autoregressive query + spatio-temporal transformer, query nở dần theo thời gian | n/a | n/a (chưa đọc thân paper — chỉ abstract) | n/a | arXiv:2403.10574 | **Claimed-only** (repo `Qixin-U/AQATrack` 404 — xem §6) |
| 10 | **MixFormerV2** (NeurIPS'23) | 2023 | One-stream transformer **không dense conv**, 4 prediction tokens; MixFormerV2-S "real-time CPU" | n/a | n/a (bài paper chỉ short-term theo README) | **165 FPS GPU** (README); real-time CPU là claim của README | arXiv:2305.15896; [MCG-NJU/MixFormerV2](https://github.com/MCG-NJU/MixFormerV2) | README verified; **bản "MixFormerV2-lt" KHÔNG TÌM THẤY** trong repo (§6) |

> Người viết chỉ tóm tắt **cơ chế**, không khuyến nghị dùng nguyên mô hình — với đồ án thì mọi dòng
> GPU-only (GlobalTrack, Siam R-CNN, ODTrack…) đều quá đắt; đáng học là **quy tắc switch + cách rẻ hóa
> ứng viên** (các hàng 1, 2, 5, 6, 7).

---

## 4. Ba chiến lược RẺ nhất có thể tự cài — bản phác thảo

### 4.1. SPLT skim: thu nhỏ frame → grid cửa sổ ≤ 500 → top-K → RPN/xác minh đắt (VERIFIED-in-source)

Đây là hình dạng cascade **rẻ nhất đã thấy** trong các tracker nguồn mở: toàn phần tìm kiếm toàn ảnh
chỉ tốn **1 lần forward mạng siamese nhỏ trên ≤ 500 cửa sổ thu nhỏ** (batch 64), rồi chỉ có
**top-3 vị trí** được chạy phần đắt (RPN + xác minh 128×128).

Máy trạng thái (dịch trực tiếp từ `RPN_Verifier_Skim_top3.py`):

1. **Local**: crop vùng tìm 300 px quanh hộp cuối → RPN → k ứng viên → lọc IoU>0.4 với hộp cũ →
   xác minh top ứng viên bằng khoảng cách euclidean vector đặc trưng template (ResNet50, 128×128):
   `dist_min < V_T (0.7)` = còn thấy → bình thường (splt.py:462).
2. **Cascading scale-local** (splt.py:541-556): nếu chưa qua → thử lại quanh tâm với scale **0.5×, 1×,
   2×** kích thước vật gốc.
3. **Global/skim** (splt.py:532-732): nếu **RPN score của ứng viên tốt nhất < Object_thres_low (0.3)**:
   - `gen_search_patch_Hao` (tracking_utils.py:47-90): `crop_sz = avg(w0,h0) × 2.4`; thu nhỏ ảnh nên
     mỗi cửa sổ 256×256; grid bước **128 px (50% overlap)**; nếu > 500 cửa sổ → subsample còn ≤ 500.
   - Siamese skim (branch_z × branch_search) chấm **toàn bộ cửa sổ batch 64**.
   - Lấy **top-3** (SEARCH_K=4 −1) → quanh từng vị trí chạy lại phần local (RPN 300 px + verifier 128×128).
   - Accept nếu RPN score > `Object_thres_high (0.7)` **và** verifier distance `< G_V_T (0.8)`;
     chưa qua → thử vị trí skim kế tiếp (splt.py:677).
4. **Không accept** → giữ hộp cũ, không vẽ hộp mới (splt.py:732).

Con số đã cài trong repo: `splt.py:35-40` (V_T=0.7, G_V_T=0.8, O_T_L=0.3, O_T_H=0.7, O_T_C=0.6),
`splt.py:263` (`self.SEARCH_K = 4 # k = search_k -1`).

**Repo/mã:** `github.com/iiau-tracker/SPLT` (master) — file chính
`RPN_Verifier_Skim_top3.py` + `utils/tracking_utils.py` (`gen_search_patch_Hao`).
**VERIFIED-in-source** (đã fetch raw và đọc từng dòng liên quan 27-10-2026).

### 4.2. DaSiamRPN-LT / KeepTrack: vùng tìm kiếm nở dần + ngưỡng trễ (hysteresis) — rẻ vì KHÔNG quét toàn ảnh (VERIFIED)

Hai hệ này dùng chung một ý đã thành công nhiều năm: khi lost, **mở rộng vùng tìm kiếm dần dần cho đến
khi phủ cả frame** — phần lớn các frame mất chỉ cần một chút rộng hơn vùng cũ, không cần full frame.

**DaSiamRPN-LT** (paper .tex §4.1, đã khớp từng con số):
- Ngưỡng bật failure: max RPN score < **0.8**; ngưỡng rời failure: **> 0.95** (trước khi bật/tắt phải
  vượt ngưỡng xa nhau → chống dao động).
- Vùng tìm kiếm: **255 px** (normal) → "**iteratively growing with a constant step**" tới **767 px**;
  paper khẳng định "**one step iteration of local-to-global is sufficient**" — thực tế các sequence
  chỉ cần 1 bậc nở.
- Rationale rẻ: vì RPN **hồi quy bbox**, không cần pyramid ảnh (không chạy lại template ở các scale
  template) → 110 FPS.

**KeepTrack** (`keep_track.py:227-238`, gọi khi flag == not_found):
- `target_not_found_counter += 1` mỗi frame mất.
- Dùng `min(counter, 30)` **scale** gần nhất **≥ scale tại lần mất** trong lịch sử 60 frame, lấy
  trung bình làm kích thước vùng tìm mới (giúp bắt được trường hợp vật xuất hiện lại **lớn hơn/nhỏ hơn**).
- Ứng viên toàn ảnh chỉ khi cần: cực đại cục bộ của response map (`th=0.05, ks=5`),
  `keep_track.py:437-441`; không detector thứ cấp.

**Repo/mã:**
- DaSiamRPN: paper (arXiv:1808.06048) — **VERIFIED-in-source cho văn bản**; mã LT không phát hành.
- KeepTrack: `visionml/pytracking` `pytracking/tracker/keep_track/` — **VERIFIED-in-source**.

### 4.3. TLD (OpenTLD): cascade lọc bằng integral image + chỉ 100 ô "đắt" cuối (VERIFIED-in-source)

Trick kinh điển đáng "mượn" cho đồ án: ứng viên đi qua **3 tầng lọc, tầng nào càng đắt càng ít ô**:

1. **Tầng 0 — variance filter (tính trên ảnh integral, O(1) mỗi ô)**: `getVar(...) >= var` (TLD.cpp:427);
   lọc ô quá phẳng/đơn điệu (không thể là vật có texture) — lọc được phần lớn grid.
2. **Tầng 1 — rừng fern**: 10 cây random-fern (feature = so sáng/tối 2 điểm) — chấm nhanh cả grid còn lại
   (TLD.cpp:429-439).
3. **Tầng 2 — NCC/NN conservative similarity** trên **tối đa 100 ô** tốt nhất (TLD.cpp:447-449).
4. Accept/re-accept: **cluster các ô cùng vượt ngưỡng** (`clusterConf`, TLD.cpp:248), hợp lệ nếu cụm
   cách hộp cũ (`bbOverlap < 0.5`) **và** confidence cụm > confidence của tracker (TLD.cpp:251) —
   cụm mới xa + tin cậy hơn mới được phép gắp vật về.

**Repo/mã:** `github.com/arthurv/OpenTLD` `src/TLD.cpp` — **VERIFIED-in-source**.

### 4.4. LTMU: xác nhận nhiều frame trước khi "thấy lại" (VERIFIED-in-source) — quy tắc chống dao động

`DiMP_LTMU/Dimp_LTMU.py:478-512`: khi local lost (`md_score < 0 | flag not_found`), mỗi frame vẫn chạy
GlobalTrack → **top-10 hộp** → verifier điểm lại → nếu có hộp qua ngưỡng vẫn **không accept ngay**:
chỉ sau `self.count >= 5` (frame lost liên tục) mới ghi nhận lại vị trí và reset đếm (`:498-508`).
Đây chính là **hysteresis**: "phải mất đủ lâu trước khi cho phép tìm lại" — tương đương
`lost_after_frames` của đồ án nhưng áp cho chiều ngược lại (thoát lost).

---

## 5. Áp dụng cho đồ án này: 323 ms/quét → mục tiêu < 50 ms

Điều kiện hiện trạng (repo):
- `src/appearance.py:111` `candidate_boxes(...)`: `DEFAULT_STRIDE_FRAC = 0.5`, `DEFAULT_SCALES = (0.75, 1.0, 1.5)`
  → với vật cỡ 170 px trên frame 720p, mỗi scale ~ lưới bước w/2 → **348 ô**, mỗi ô được chấm bằng
  descriptor đắt (HSV hist 8×8 + region-covariance, `src/appearance.py:57-107`) — tức **348×(cvtColor
  + calcHist + covariance)** ≈ 323 ms.
- Trạng thái `lost` sau 2 frame mask rỗng (`src/config.py:52`), state machine `tracking → lost →
  reacquiring` (`src/reid.py:160`).

Xếp hạng theo tỷ lệ lợi ích/công sức (1 = làm ngay):

| # | Biện pháp | Mượn từ | Công sức | Dự kiến giảm | Lý do |
|---|---|---|---|---|---|
| **1** | **Chia 2 tầng: prefilter rẻ trước, signature đắt sau (chỉ top-K)** | SPLT skim + TLD cascade | Nhỏ (1 hàm mới trong `src/appearance.py`, không đổi pipeline) | 348 descriptor → ~10-20 → **≈ 10-20 ms** | 95% chi phí là chấm signature cho TẤT CẢ 348 ô. Dùng `cv2.matchTemplate` (TM_CCOEFF_NORMED, ảnh xám) trên **frame đã thu nhỏ 4×** với template thu nhỏ → tìm cực đại cục bộ → **chỉ 10-20 ô** đi qua signature. matchTemplate FFT toàn frame 720p/4 ≈ vài ms |
| **2** | **Vùng tìm kiếm nở dần + hysteresis ngưỡng enter/exit** | DaSiamRPN-LT (0.8/0.95, 255→767) + KeepTrack rescaling | Nhỏ (đổi cách sinh lưới `candidate_boxes`: giới hạn vùng nở quanh vị trí cuối) | **Giảm số ô ~3-10×** ở phần lớn frame lost | Vật đi khỏi frame bằng di chuyển/biến dạng dần; chỉ sau ~10 frame lost mới cần toàn frame. Dùng bộ đếm lost → bán kính tìm kiếm = kích thước vật × (1 + 0.5×counter), nở tới ≥ 767×kích thước vật; giữ ngưỡng enter/exit **khác nhau** để chống dao động |
| **3** | **Chụp ngân sách cố định: xoay vòng lưới ứng viên qua các frame lost** (temporal amortization) | ý tưởng chung trong cascade (giống TLD "chỉ chấm phần lọc còn") | Nhỏ (offset lưới theo `frame_idx % m`) | Chi phí/lượng ứng viên mất một phần bằng nửa, không tăng latence frame hiện hành | Chấp nhận "nhìn vạn vật trong 8-10 frame lost thay vì một frame" — đúng nghĩa long-term, không phá FPS của luồng tracking |
| **4** | **Xác nhận nhiều frame trước khi thoát lost** (giống LTMU `count >= 5`, hoặc giảm còn 2-3 cho độ trễ thấp) | LTMU `DiMP_LTMU.py:498` | nhỏ | chống nhảy ngẫu nhiên — không giảm ms nhưng chống flapping | Hộp candidate phải vượt ngưỡng 2 frame liên tiếp gần nhau mới `reacquiring → tracking` |
| **5** | Tái dùng proposal: nếu không mất quá lâu, **hoãn cả việc tạo grid** và chỉ theo dõi 2-3 vị trí "đáng ngờ" (quán tính Kalman của SAMURAI + biên frame) | KeepTrack (dùng lại previous candidates), SAMURAI Kalman hiện có trong repo (`sam2/sam2/modeling/sam2_base.py`) | trung bình | bỏ hẳn cost quét ở ~70-80% frame lost | Vật thường xuyên quay lại gần vị trí dự đoán; full-frame scan giữ cho trường hợp counter cao |

**Phác thảo tầng 1 (giữ nguyên API)** — đủ chi tiết để cài tay:

```
# khi state == "lost":
gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)            # 1 lần
small  = cv2.resize(gray, dsize=(gray[1]//4, gray[0]//4))   # 180×320
tmpl   = crop 4× nhỏ hơn của template 64..96 px (đã lưu trong ReIdSession refs)
smaps  = []  # một map cho mỗi scale (0.75, 1.0, 1.5) — template resize trước khi match
for s in scales:
    t = cv2.resize(tmpl, None, fx=s/4, fy=s/4)
    smaps.append(cv2.matchTemplate(small, t, cv2.TM_CCOEFF_NORMED))
# cực đại cục bộ với ngưỡng thấp (giống KeepTrack th=0.05):
pts  = find_local_maxima(cat(smaps), ks=5, th=TH_LOW)       # ≤ 30 điểm
top  = sort_by_score(pts)[:20]
boxes = upscale_to_fullres(top)                             # chỉ 20 ô
best  = argmax signature_score(boxes)                        # descriptor đắt (hist+cov) CHỈ 20 ô
if best.score >= TH_ENTER:  # ngưỡng vào, ví dụ 0.55
    confirm_2_frame_lien_tiep_truoc_khi_trang_thai_tracking()
```

Chi phí dự kiến trên laptop CPU: `matchTemplate` 3 scale ≈ 3-10 ms; cực đại cục bộ + chấm
20 signature ≈ 5-15 ms → **tổng ~15-25 ms**, dưới mục tiêu 50 ms. Số liệu này là **ước lượng chưa đo**
— phải đo lại trên đúng script benchmark của phiên trước (xem §6).

---

## 6. Chưa kiểm chứng (rõ ràng)

1. **348 ô / 323 ms** — con số do phiên trước của parent đo; phiên này **không đo lại** (chỉ đọc
   lại `src/appearance.py:111-131` để xác nhận cách sinh 348 ô với `stride=0.5`, 3 scales).
   Phải đo lại bằng script đo thật trước khi đưa vào báo cáo cuối kỳ.
2. **MixFormerV2-lt**: parent nêu trong scope, nhưng **không tìm thấy biến thể long-term nào** trong
   repo `MCG-NJU/MixFormerV2` (duyệt README + cây `lib/` main, 27-10-2026); README chỉ nói LaSOT/TNL2k
   short-term.claim "long-term MixFormerV2" **bỏ qua hoặc xác nhận lại** trước khi trích.
3. **AQATrack**: chỉ có abstract (arXiv:2403.10574). Repo `Qixin-U/AQATrack` trả 404 (curl GitHub HTML
   27-10-2026); **cơ chế query nở dần để re-detect là claimed-only** từ abstract, chưa đọc thân paper.
4. **ODTrack**: cơ chế "token propagation tự phục hồi sau occlusion" lấy từ abstract arXiv:2401.01686 +
   README repo; **chưa đọc code re-detection cụ thể** trong repo.
5. **Siam R-CNN**: chưa lấy được mã (chỉ paper .tex); repo chính thức ở `vision.rwth-aachen.de` ngoài
   phạm vi fetch của phiên; nhánh `siamrcnn` không còn trên `visionml/pytracking` master.
6. **DaSiamRPN-LT mã nguồn**: master `foolwood/DaSiamRPN` chỉ có short-term; mọi con số 0.8/0.95/255/767
   lấy từ **văn bản paper** (ĐÃ kiểm chứng văn bản) nhưng chưa có mã gốc để đối chiếu; các
   reimplementation cộng đồng chưa soát.
7. **FPS của TLD/GlobalTrack/KeepTrack/LTMU**: không có trong các nguồn đã fetch/đọc → để trống/n-a,
   không trích.
8. **VOT-LT**: công thức precision/recall đã đọc trong `longterm.py:80-91`; nhưng việc tổng hợp
   multi-sequence cuối (F-score qua các threshold, cách "predict presence" bị ghép với bounding box
   ở phần aggregation) **chưa đọc hết** — cần mở rộng nếu đồ án định chấm lại theo VOT-LT.

## 7. Tài liệu tham khảo (mọi link fetch 27-10-2026)

- DaSiamRPN, ECCV 2018 — Zhu et al., [arXiv:1808.06048](https://arxiv.org/abs/1808.06048); mã short-term: [foolwood/DaSiamRPN](https://github.com/foolwood/DaSiamRPN).
- GlobalTrack, AAAI 2020 — Huang et al., [arXiv:1912.08531](https://arxiv.org/abs/1912.08531); mã: [huanglianghua/GlobalTrack](https://github.com/huanglianghua/GlobalTrack).
- Siam R-CNN, CVPR 2020 — Stühmer et al., [arXiv:1911.12836](https://arxiv.org/abs/1911.12836).
- SPLT, ICCV 2019 — Yan et al., [arXiv:1909.01840](https://arxiv.org/abs/1909.01840); mã: [iiau-tracker/SPLT](https://github.com/iiau-tracker/SPLT).
- KeepTrack, ICCV 2021 — Sokolov et al., [arXiv:2103.16556](https://arxiv.org/abs/2103.16556); mã: [visionml/pytracking](https://github.com/visionml/pytracking) (`pytracking/tracker/keep_track/`).
- LTMU, CVPR 2020 — Dai et al., [arXiv:2004.00305](https://arxiv.org/abs/2004.00305); mã: [Daikenan/LTMU](https://github.com/Daikenan/LTMU).
- ODTrack, AAAI 2024 — Zheng et al., [arXiv:2401.01686](https://arxiv.org/abs/2401.01686); mã: [GXNU-ZhongLab/ODTrack](https://github.com/GXNU-ZhongLab/ODTrack).
- AQATrack, arXiv 2024 — Qiu et al., [arXiv:2403.10574](https://arxiv.org/abs/2403.10574).
- MixFormerV2, NeurIPS 2023 — Cui et al., [arXiv:2305.15896](https://arxiv.org/abs/2305.15896); mã: [MCG-NJU/MixFormerV2](https://github.com/MCG-NJU/MixFormerV2).
- TLD, TPAMI 2012 — Kalal et al.; mã: [arthurv/OpenTLD](https://github.com/arthurv/OpenTLD).
- VOT toolkit (long-term measures) — [votchallenge/toolkit](https://github.com/votchallenge/toolkit) `vot/analysis/longterm.py`; giao tiếp tracker — [visionml/pytracking](https://github.com/visionml/pytracking) `pytracking/evaluation/vot.py`.
- Liên quan repo: `docs/research/06-nhan-dang-lai-mat-va-dac-trung-vat-the-tu-lam.md` (trạng thái ReID hiện tại), `src/appearance.py`, `src/reid.py`, `src/config.py`.