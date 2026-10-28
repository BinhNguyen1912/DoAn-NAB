# 06 — Nhận dạng lại đối tượng: kết hợp cue khuôn mặt + đặc trưng vật thể, tự triển khai trên laptop CPU

> Báo cáo research cho quyết định kiến trúc. Ngày: **25-10-2026**.
> Trạng thái: **đề xuất, chưa chốt** — chờ GVHD/người dùng quyết định (xem §9).
> Mọi số liệu trong §4 do chính đồ án đo trên laptop (Intel CPU, không GPU rời), script: `docs/research/../` ngoài repo (xem §4.0).

---

## 1. Câu hỏi nghiên cứu

GVHD **không cho dùng phần tái nhận diện khuôn mặt** (YuNet + SFace — ADR-0003 / ticket 09).
Yêu cầu thay thế của người dùng:

1. Chọn **một vật bất kỳ** (ví dụ cái remote), hệ thống vẫn **"nhớ"** đúng vật đó.
2. Muốn **vừa mặt vừa đặc trưng vật thể** (không bỏ hẳn ý tưởng đa cue).
3. Phải **nhẹ máy** (CPU laptop, không GPU rời).
4. Phải **mang tính tự làm** — không chỉ gọi model có sẵn.
5. GVHD nói "dùng thẳng trên đó của nó" — tức dùng cơ chế sẵn có của **SAMURAI**.

---

## 2. Trạng thái THẬT của repo (kiểm chứng bằng file:dòng)

### 2.1 Đính chính quan trọng

Trong phiên làm việc trước, agent từng kết luận *"repo chưa dùng Kalman/motion-aware memory của
SAMURAI"*. **Kết luận đó SAI** (đã grep sai tên file). Sự thật:

| Hạng mục | Bằng chứng |
|---|---|
| Repo dùng **config SAMURAI** | `configs/default.yaml:` `model_cfg: configs/samurai/sam2.1_hiera_t.yaml` |
| SAMURAI mode **BẬT** | `samurai/sam2/sam2/configs/samurai/sam2.1_hiera_t.yaml`: `samurai_mode: true` |
| Trọng số + ngưỡng Kalman | cùng file: `kf_score_weight: 0.25`, `memory_bank_iou_threshold: 0.5`, `memory_bank_obj_score_threshold: 0.0`, `memory_bank_kf_score_threshold: 0.0`, `stable_frames_threshold: 15`, `stable_ious_threshold: 0.3` |
| Kalman filter chạy trong model | `samurai/sam2/sam2/modeling/sam2_base.py:20` (import), `:201-202` (`self.kf = KalmanFilter()`), `:669` (đọc `kf_score` khi chọn memory) |
| Chọn memory theo 3 ngưỡng | `sam2_base.py` nhánh `if self.samurai_mode:` trong `_prepare_memory_conditioned_features` — lọc frame vào memory theo `iou_score > 0.5 AND obj_score > 0.0 AND kf_score > 0.0` |
| Kalman API | `samurai/sam2/sam2/utils/kalman_filter.py`: `initiate/predict/project/update/gating_distance/compute_iou/xyxy_to_xyah` |
| Repo build predictor thẳng (không wrapper riêng) | `src/tracker_engine.py:38` (MODEL_CFG), `:116` (`build_sam2_video_predictor`), `:121` (hydra overrides) |

**Hệ quả:** trụ cột *Motion Memory* của đề cương **đã có trong luồng chạy**; muốn "tự làm" phần này thì
phải **port/tối ưu/thay thế chính sách chọn memory** (GLOSSARY.md cũng đã ghi định hướng này:
*"Motion-Aware Memory … phần đồ án sẽ tự port/tối ưu trên backbone SAM 2"*).

### 2.2 Phần tái nhận diện đang có (sẽ bị ảnh hưởng)

- `src/reid.py:159` `class ReIdSession` — máy trạng thái `tracking → lost → reacquiring → tracking`;
  `:162` tham số `threshold / lost_after_frames / ref_max / min_face_px / min_score`;
  `:173` `self._refs = deque(maxlen=...)` — **chỉ trong RAM**, không ghi đĩa; `:187` `reset()` xoá sạch.
- `configs/default.yaml`: `reid_enabled: true`, `reid_threshold: 0.363`, `reid_min_face_px: 40`,
  `reid_min_detect_score: 0.8`, `reid_ref_max: 8`.
- ADR-0003 + ticket 09 (`.scratch/camera-ai-realtime/issues/09-*.md`) là nơi ghi quyết định này.

→ Nếu bỏ/đổi mặt, **phải có ADR mới thay ADR-0003** và sửa lại các mục số liệu liên quan.

---

## 3. Nguồn gốc (đã fetch trực tiếp trong phiên, ngày 25-10-2026)

| Nguồn | Dùng để quyết định điều gì |
|---|---|
| SAMURAI — *Adapting Segment Anything Model for Zero-Shot Visual Tracking with Motion-Aware Memory*, arXiv:2411.11922 (Yang et al., 2024). https://arxiv.org/abs/2411.11922 | Xác nhận "motion-aware memory selection + motion cue" là cơ chế chống trôi/mất dấu **không cần train**. Cơ sở cho câu "dùng thẳng của SAMURAI". |
| XMem — *Long-Term VOS with an Atkinson-Shiffrin Memory Model*, arXiv:2207.07115 (Cheng & Schwing, ECCV 2022). https://arxiv.org/abs/2207.07115 | Kiến trúc **nhiều tầng memory + consolidation (memory potentiation)**: cơ sở cho "ngân hàng prototype + hợp nhất định kỳ" chống nổ bộ nhớ và giảm suy giảm theo thời gian. |
| VS-ReID — *Video Object Segmentation with Re-identification*, arXiv:1708.00197 (Li et al., 2017). https://arxiv.org/abs/1708.00197 | Tiền lệ học thuật đúng hình dạng bài toán: **module lan truyền mask + module ReID lặp lại với nhau** để chống mất dấu/dịch chuyển lớn. |
| *Identity-Conditioned Score Fusion for Open-Set Person Re-Identification*, arXiv:2610.07366 (Yao et al., 2026). https://arxiv.org/abs/2610.07366 | **Fusion điểm số nhiều cue (mặt/dáng/thân) KHÔNG cần train**, trọng số theo *danh tính* + giữ được hiệu chuẩn (calibration). Đây là nguồn sát nhất với yêu cầu "vừa mặt vừa đặc trưng vật thể, tự làm". |
| *A Comprehensive Overview of Biometric Fusion*, arXiv:1902.02919 (Singh, Singh, Ross, 2019). https://arxiv.org/abs/1902.02919 | Khung phân loại fusion: **fuse cái gì – khi nào – thế nào**; vai trò của **chất lượng (quality)** và chuẩn hoá trước khi hợp nhất. |
| *Query Adaptive Late Fusion for Image Retrieval*, arXiv:1810.13103 (Wang, Zheng, Wang, 2018). https://arxiv.org/abs/1810.13103 | Late fusion ở mức điểm, thích ứng theo truy vấn: một cue có thể vô dụng với vật này nhưng tốt với vật khác → cần trọng số theo truy vấn. |
| OSNet — *Omni-Scale Feature Learning for Person Re-Identification*, arXiv:1905.00953 (Zhou et al., ICCV 2019). https://arxiv.org/abs/1905.00953 | Phương án "embedding học sẵn nhưng rất nhẹ" nếu sau này muốn nâng cấp từ descriptor tay. |
| DaSiamRPN — *Distractor-aware Siamese Networks*, arXiv:1808.06048 (Zhu et al., ECCV 2018). https://arxiv.org/abs/1808.06048 | Cơ chế **distractor-aware + tìm lại toàn cục (local-to-global)** cho tracking dài hạn — tham chiếu cho bước "global search" khi mất dấu. |
| *Person Re-identification for Real-world Surveillance Systems*, arXiv:1607.05975 (Khan & Bremond, 2016). https://arxiv.org/abs/1607.05975 | Mô hình đặc trưng ngoại hình **không cần học có giám sát** — tiền lệ hợp lệ học thuật cho descriptor tay. |
| *One-pass Person Re-identification by Sketch Online Discriminant Analysis*, arXiv:1711.03368 (Li et al., 2017). https://arxiv.org/abs/1711.03368 | Cập nhật mô hình **trực tuyến, không lưu toàn bộ dữ liệu đã qua** — đúng ràng buộc RAM/streaming của đồ án. |

**Nguồn lý thuyết chưa fetch được trong phiên này** (web tool hết hạn mức tuần, và `docs.opencv.org`
chặn curl bằng Cloudflare): Tuzel et al., *Region Covariance: A Fast Descriptor* (ECCV 2006);
Ojala et al., LBP (TPAMI 2002); Jégou et al., VLAD (CVPR 2010); Dalal & Triggs, HOG (CVPR 2005).
Các descriptor này được dùng ở §4/§5 với tư cách **kỹ thuật đã cài đặt và tự đo**, không phải trích dẫn
đã kiểm chứng. Cần bổ sung trích dẫn chuẩn khi viết báo cáo cuối.

---

## 4. Đo trên chính máy đồ án

### 4.0 Cách đo (tái lập được)

- Fixture tổng hợp tự sinh 640×480, **ground truth biết trước**: vật đích = ô vuông cam **có sọc trắng**;
  vật gây nhiễu đặt chỗ khác với 3 biến thể (khác màu / cùng màu khác texture / **giống y hệt**).
- Descriptor tay: HSV-hist (`cv2.calcHist`), HSV-hist lưới 2×2, covariance 5×5 trên `[x, y, B, G, R]`.
- Đặc trưng lấy từ model: **encoder SAM 2.1 tiny đã nạp sẵn trong pipeline**, masked average pooling
  trên `backbone_fpn` (level 0 + 2 level kế), có biến thể lưới 1×1 và 2×2.
- Đo độ trễ trên frame **1280×720** (đúng độ phân giải nguồn thật), trung bình 10–50 lần.
- Môi trường: `~/miniconda3/envs/samurai`, Python 3.11, `opencv 5.0.0`, `torch 2.14.1+cpu`.

### 4.1 Độ trễ từng cue (ms/frame, 1280×720)

| Cue | ms | Nguồn |
|---|---|---|
| YuNet detect (toàn frame) | **27,49** | có sẵn (`src/reid.py`) |
| SFace feature (112×112) | **8,29** | có sẵn |
| HSV hist (1 vùng) | 1,10 | tự viết |
| HSV hist lưới 2×2 | 0,20 | tự viết |
| Covariance 5×5 | 1,07 | tự viết |
| ORB 300 keypoint + descriptor | 2,36 | tự viết |
| Masked average pooling (trên feature map **đã có sẵn**) | **0,04** | **miễn phí** |
| *(tham chiếu)* encoder SAM 2 @512 | ~450 | đã trả trong pipeline (~733 ms/frame toàn pipeline @512) |

**Kết luận độ trễ:** toàn bộ tầng tái nhận diện mới (mặt + descriptor vật thể) tốn **~38 ms/frame**,
tức **~5%** của pipeline CPU hiện tại (~733 ms/frame @512). Nút thắt vẫn là backbone, không phải
tầng nhận dạng. Cue lấy từ encoder **gần như miễn phí** vì encoder đã phải chạy cho việc bám bắt.

### 4.2 Khả năng phân biệt (cosine so với vật đích; **cao = khó tách**)

| Cue | cùng vật, dịch nhẹ (positive — càng cao càng tốt) | cùng màu, **không** texture | cùng màu, texture khác | **giống y hệt** | khác màu |
|---|---|---|---|---|---|
| HSV hist | 1,000 | 0,786 ❌ | 0,866 ❌ | **1,000** ❌ | 0,382 ✅ |
| HSV hist lưới 2×2 | 1,000 | 0,786 ❌ | 0,866 ❌ | **1,000** ❌ | 0,382 ✅ |
| Covariance 5×5 | 1,000 | 0,061 ✅ | 0,997 ❌ | **1,000** ❌ | 0,166 ✅ |
| Feature encoder (grid 1×1) | 0,950 | 0,589 ✅ | 0,602 ✅ | **0,975** ❌ | 0,914 ⚠️ |
| Feature encoder (grid 2×2) | 0,916 | 0,592 ✅ | 0,606 ✅ | **0,964** ❌ | 0,910 ⚠️ |

### 4.3 Ba kết luận từ số đo

1. **Không có cue nào đủ một mình.** Mỗi cue mạnh ở một kiểu khác nhau và mù ở kiểu khác:
   - Màu (HSV hist): tách tốt khi **khác màu** (0,382) nhưng **yếu** khi cùng màu (0,79–0,87).
   - Covariance: tách rất mạnh khi **cấu trúc texture khác** (0,061) nhưng mù khi texture khác kiểu
     "có cấu trúc" (0,997) — vì nó mô tả thống kê bậc hai không đủ để phân biệt hai hình có sọc với chấm.
   - Feature encoder (miễn phí): tách tốt texture (0,59–0,61) nhưng **gần như mù màu** (0,914 so với
     positive 0,950) — vì SAM 2 học cho *phân đoạn*, không học cho *nhận dạng*.
2. **Ca "giống y hệt" không thể giải bằng ngoại hình.** Mọi cue đều ≈ 1,000, thậm chí **cao hơn
   positive thật (0,946–0,950)** → nếu chỉ dựa vào ngoại hình, hệ thống sẽ bám nhầm. Ca này **chỉ**
   giải được bằng **cue thời gian**: liên tục quỹ đạo (Kalman) + memory gắn với *thể hiện* (instance)
   đang bám — đúng thứ SAMURAI đã có trong repo (§2.1).
3. **Vì (1) và (2), giá trị "tự làm" nằm ở tầng hợp nhất + hiệu chuẩn ngưỡng, không nằm ở việc
   viết thêm một descriptor.** Đây là điểm trả lời được câu hỏi của hội đồng "phần nào là của em?".

### 4.4 Vật ĐEN / ít texture — giới hạn thật (đo 27-10-2026)

Đo trên fixture tự sinh (vật đen đặc trên nền sáng, mô phỏng chai đen):

| Ca | Cosine (cov+HSV, đang dùng) | NCC (`TM_CCOEFF_NORMED`) |
|---|---|---|
| cùng vật, dịch nhẹ | 1,000 | **1,000** |
| **vật đen KHÁC** (khác cỡ) | **1,000** ❌ | 0,897 ⚠️ |
| vật đen khác **có nhãn trắng** | 0,766 ⚠️ | **0,394** ✅ |
| vật đen vs vật xám | 0,986 ❌ | 0,000 (khối gradient) |

**Nguyên nhân vật lý:** vật đặc một màu → histogram HSV dồn 1 bin, covariance gần như phẳng, gradient chỉ có ở viền
→ vector đặc trưng gần như **hằng số**, mất khả năng phân biệt. Đây là **cùng một loại giới hạn** với ca
"hai vật giống y hệt" ở §4.2: **ngoại hình không thể giải**, phải dựa vào **hình dạng (NCC)** và **cue thời gian**.

→ Việc tiếp theo: ticket 11 (dùng NCC làm cổng quyết định + ghi NCC vào metrics để hiệu chuẩn trên clip thật).

---

## 5. Kiến trúc đề xuất (phần "tự làm" là tầng 1–3)

```
frame ──► [T0] Bám + Motion Memory (SAM 2 config SAMURAI — ĐÃ CÓ)
              │  mask, bbox, score, kf_score, best_iou_score
              ├─► [T1] Object Signature  (TỰ LÀM — không train, ~1,3 ms)
              │      covariance 5×5 + HSV hist + encoder pooled feature
              │      └─► Prototype Bank (deque + hợp nhất định kỳ, học từ XMem)
              ├─► [T2] Face Cue (MODULE RIÊNG, bật/tắt — YuNet + SFace, ~36 ms)
              │      └─► quality gate: cạnh mặt, độ nét, điểm detect, tỉ lệ che
              └─► [T3] Fusion + Hiệu chuẩn  (TỰ LÀM — phần đóng góp chính)
                     chuẩn hoá từng cue theo impostor set (z/t-norm)
                     + trọng số theo chất lượng & độ tin của cue
                     └─► [T4] State machine: tracking → lost → SEARCH → verify → re-anchor
```

### T1 — Object Signature (không train, ~1,3 ms)
- Vector = `[covariance 5×5 đã chuẩn hoá, HSV hist, encoder pooled feature]`, L2-normalize từng khối
  rồi weight theo khối. Lý do chọn đúng ba khối này: **chúng bù trừ đúng chỗ yếu của nhau** (§4.2).
- **Prototype bank**: giữ tối đa N mẫu (mặc định 8 như `reid_ref_max` hiện tại), thêm mẫu chỉ khi
  đạt cổng chất lượng (mask đủ lớn, score cao, vật không bị che nhiều).
- **Hợp nhất định kỳ (consolidation)**: gộp cụm mẫu gần nhau thành prototype trung bình — học từ
  XMem (`2207.07115`) để chống nổ bộ nhớ và giảm suy giảm theo thời gian; kết hợp cập nhật
  trực tuyến không lưu toàn bộ dữ liệu (`1711.03368`).

### T2 — Face cue là **module tuỳ chọn**, không phải xương sống
- Giữ nguyên `src/reid.py` (đã có test) nhưng đặt sau cờ cấu hình, mặc định **TẮT** để không vi phạm
  yêu cầu GVHD; bật khi demo cần "vừa mặt vừa vật" hoặc khi GVHD đổi ý.
- Điều kiện dùng: **chỉ khi** vật đang bám là người **và** có mặt đủ chất lượng trong bbox.

### T3 — Fusion + hiệu chuẩn (đóng góp chính, không train)
- Mỗi cue trả về **điểm tương đồng**, KHÔNG phải quyết định. Quyết định ở một chỗ duy nhất.
- **Chuẩn hoá điểm** trước khi hợp nhất (biometric fusion, `1902.02919`): với mỗi cue, lấy phân bố
  điểm với "impostor set" (các vùng nền/vật khác trong khung) → z-score/t-norm → tránh việc ngưỡng
  của cue này bị lệch do ánh sáng/camera.
- **Trọng số theo chất lượng**: cỡ vật, tỉ lệ che, độ nét, điểm `object_score_logits` và `kf_score`
  mà SAMURAI đã trả về → cue kém tin (mặt nhỏ, vật bị che) bị giảm quyền biểu quyết.
- **Hợp nhất** theo hướng likelihood ratio (nhân xác suất sau khi chuẩn hoá) hoặc trung bình có
  trọng số trong logit — chọn cái nào thì phải **đo cả hai** trên dữ liệu của đồ án.
- **Hiệu chuẩn ngưỡng**: dùng chính clip thật của đồ án để chọn ngưỡng theo **tỉ lệ nhận nhầm mục
  tiêu cho phép**, thay vì chép ngưỡng 0,363 của tài liệu OpenCV (đây là criteria còn treo của
  ticket 09 — ADR-0003 đã ghi số đo 0,199–0,723 cùng một người).

### T4 — Chỉ được quyết định "mất dấu" dựa trên nhiều nguồn
Trạng thái `lost` hiện nay chỉ dựa vào *mask rỗng 2 frame liên tiếp* (`lost_after_frames: 2`). Đề xuất
bổ sung điều kiện: mask rỗng **và** điểm object giảm **và** không có ứng viên nào vượt ngưỡng →
giảm báo động giả khi vật bị che một phần.

---

## 6. Phân công cue theo tình huống (dùng để trả lời hội đồng)

| Tình huống | Cue quyết định | Cue bị vô hiệu |
|---|---|---|
| Vật bị che khuất một phần | Memory + Kalman (T0) | ngoại hình giảm trọng số |
| Vật bị che hoàn toàn, ngắn (< ngưỡng lost) | Kalman dự đoán + memory | — |
| Mất dấu hẳn, vật quay lại **cùng vị trí cũ** | Memory (temporal) | — |
| Mất dấu hẳn, vật quay lại **chỗ khác** | Object Signature (T1) + fusion | Kalman (đã sai) |
| Có **vật giống hệt** trong khung | **Kalman/memory — ngoại hình bất lực** (§4.2) | mọi cue ngoại hình |
| Người quay mặt đi / mặt nhỏ | Object Signature (T1) | mặt (quality gate tắt) |
| Người có mặt rõ | mặt + Object Signature (fusion) | — |
| Vật cùng màu, khác texture | encoder feature + covariance | màu |
| Vật khác màu, cùng hình dạng | màu | encoder (gần mù màu) |

---

## 7. Kế hoạch thực nghiệm (khi có dữ liệu thật)

**Dữ liệu cần quay (người dùng quay, ~10 phút):**
1. 1 vật có texture + 1 vật cùng màu khác texture (ví dụ 2 cái remote khác hãng).
2. 2 vật **giống hệt nhau** đặt xa nhau (để kiểm tra ca §4.2 — kỳ vọng: chỉ cue thời gian đúng).
3. 1 người: đi qua đi lại, bị che toàn bộ 1–2 giây, quay lại.
4. 2 người mặc giống nhau (để đo tỉ lệ nhận nhầm).
5. Các clip này cũng phục vụ **hiệu chuẩn ngưỡng** cho ADR/ticket 09.

**Bảng ablation đề xuất (mỗi dòng một cấu hình, cùng dữ liệu):**

| # | Cấu hình | Đo gì |
|---|---|---|
| A0 | Bám thuần (không re-ID) | mốc nền |
| A1 | + Object Signature (covariance only) | đóng góp của từng khối |
| A2 | + HSV hist | |
| A3 | + encoder pooled (miễn phí) | |
| A4 | A1+A2+A3, hợp nhất trung bình | fusion có lợi không |
| A5 | A4 + chuẩn hoá z/t-norm | chuẩn hoá có lợi không |
| A6 | A5 + trọng số theo chất lượng | |
| A7 | A6 + face cue (module bật) | **"vừa mặt vừa vật" hơn gì** |
| A8 | A6 nhưng policy chọn memory tự sửa (port lại T0) | phần "tự làm" ở tầng bám |

**Chỉ số báo cáo:** tỉ lệ nhận lại đúng / nhận nhầm (đếm thủ công), thời gian tới lúc bám lại (frame),
IoU mask sau che, độ trễ mỗi frame (ms), FPS. Ghi vào `data/` + `docs/task/` như các lần trước.

---

## 8. Rủi ro

| Rủi ro | Mức | Xử lý |
|---|---|---|
| GVHD tiếp tục cấm cả cue mặt → T2 phải bỏ | cao | Thiết kế đã tách T2 ra sau cờ; T1+T3+T4 vẫn là đóng góp |
| "Tự làm" bị coi là chỉ ghép thư viện | trung bình | Nhấn vào T3 (chuẩn hoá + trọng số + hiệu chuẩn bằng số đo riêng) và A8 |
| Vật thể không có texture/màu đặc trưng (cốc trắng) | trung bình | Khi đó T0 (thời gian) gánh chính; T1 chỉ để khôi phục sau khi mất dấu hoàn toàn |
| Thêm cue làm tăng nguy cơ báo nhầm | trung bình | Yêu cầu mọi ngưỡng phải hiệu chuẩn; đo A4–A7 thay vì tin vào trực giác |

---

## 9. Việc cần người dùng/GVHD quyết định

1. **Cue mặt giữ hay bỏ?** Đề xuất: giữ dưới dạng module tuỳ chọn, mặc định tắt.
2. **Phần nào được tính là "của em"?** Đề xuất: tầng fusion + hiệu chuẩn + prototype bank + policy memory
   tự sửa (A8) — còn SAM 2/SAMURAI chỉ là backbone.
3. **Có đổi `reid_enabled` thành `false` trong `configs/default.yaml`** và viết ADR mới thay ADR-0003 không?
4. **Ai quay dữ liệu** ở §7 (máy đồ án không có sẵn clip người/vật thật).

---

## 10. Những gì báo cáo này CHƯA kiểm chứng

- Các ca §4.2 là **fixture tổng hợp** (màu/texture có kiểm soát), **không phải** ảnh thật — chưa có
  kết luận nào về độ chính xác trên người/vật thật.
- Khả năng phân biệt của encoder SAM 2 mới đo bằng **cosine masked-pooling thô**; chưa thử các cách
  gộp tốt hơn (attention pooling, multi-level có trọng số, whitening/PCA).
- Chưa đo ảnh hưởng của tầng mới lên **FPS end-to-end** (mới đo chi phí từng cue riêng lẻ).
- Chưa kiểm chứng trích dẫn cho covariance/LBP/VLAD/HOG (§3).
