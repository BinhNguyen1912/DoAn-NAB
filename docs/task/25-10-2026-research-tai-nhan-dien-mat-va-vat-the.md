# Ngày 25-10-2026 — Research tái nhận diện (mặt + đặc trưng vật thể) & xử lý sự cố mạng/DNS

> Log theo `AGENTS.md` mục 2. Phiên bắt đầu bằng việc khôi phục nhiệm vụ bị mất context
> (do người dùng đổi model giữa phiên), sau đó research và gỡ sự cố mạng.

## 🎯 Mục tiêu
- Khôi phục lại **nhiệm vụ đã giao ở phiên trước** (bị mất do `/mmodel` restart).
- Research: làm sao **vừa dùng khuôn mặt vừa dùng đặc trưng vật thể** để tái nhận diện một vật bất kỳ,
  **không cần train nặng**, chạy nhẹ trên laptop CPU, và **mang tính tự làm**.
- Gỡ lỗi `Connection error` / `Retry failed after 3 attempts` mà pi liên tục báo trong phiên.

## 📥 Input
- Nhiệm vụ người dùng (nguyên văn, phiên `2026-10-25T05:09`): *"thầy tao không cho dùng phần đó [YuNet+SFace].
  Bây giờ tôi muốn dơ 1 vật ví dụ như remote thì sao. Vẫn phải nhớ nó. Có phần nào mình sẽ train tương tự
  không, nhưng không trên mấy để cho nó nhẹ máy tôi lại. À ổng còn nói là dùng thẳng trên đó của nó. ý là samurai"*
- Yêu cầu bổ sung hôm nay: *"vừa mặt vừa đặc trưng vật thể… phải mang tính tự làm, đi research liên tục"*.
- Repo `D:\DOAN-NAB`; checkpoint `sam2.1_hiera_tiny.pt`; model mặt `models/face/*.onnx`; `data/input.mp4`.
- Môi trường: `~/miniconda3/envs/samurai` (Python 3.11, opencv 5.0.0, torch 2.14.1+cpu).

## 🔨 Công việc đã thực hiện

1. **Khôi phục context nhiệm vụ.** Web/`recall` không có nhiệm vụ (session mới), nên đọc trực tiếp file
   session JSONL trong `C:\Users\MSI\.pi\agent\sessions\--D--DOAN-NAB--\` → tìm ra 2 phiên `2026-10-25T04-45-46`
   và `05-10-18` có nhiệm vụ, và phát hiện **2 lượt trả lời cuối của model bị RỖNG** (context_edit, không có
   nội dung) → nhiệm vụ chưa từng được trả lời.

2. **Đính chính một kết luận SAI của phiên trước.** Kiểm tra lại code trên đĩa: repo **ĐÃ** chạy
   motion-aware memory + Kalman của SAMURAI:
   - `samurai/sam2/sam2/configs/samurai/sam2.1_hiera_t.yaml`: `samurai_mode: true`, `kf_score_weight: 0.25`,
     `memory_bank_iou_threshold: 0.5`, `memory_bank_obj_score_threshold: 0.0`, `memory_bank_kf_score_threshold: 0.0`,
     `stable_frames_threshold: 15`, `stable_ious_threshold: 0.3`.
   - `samurai/sam2/sam2/modeling/sam2_base.py:20` (import Kalman), `:201-202` (`self.kf = KalmanFilter()`),
     `:669` (đọc `kf_score`), nhánh `if self.samurai_mode:` lọc frame vào memory bank theo 3 ngưỡng.
   - `samurai/sam2/sam2/utils/kalman_filter.py` (initiate/predict/project/update/gating_distance/compute_iou).
   - `src/tracker_engine.py:38` (MODEL_CFG), `:116` (`build_sam2_video_predictor`), `:121` (hydra overrides).

3. **Research (nguồn gốc, fetch trực tiếp bằng `curl`).** Web tool của pi hết hạn mức tuần (HTTP 429) nên
   tự dựng công cụ `curl` + DuckDuckGo HTML + arXiv API. Thu được 10 nguồn có thể trích dẫn, nổi bật:
   SAMURAI `2411.11922`, XMem `2207.07115`, VS-ReID `1708.00197`,
   **Identity-Conditioned Score Fusion cho open-set ReID `2610.07366`** (fusion mặt/dáng/thân không cần train),
   Biometric Fusion overview `1902.02919`, Query Adaptive Late Fusion `1810.13103`, OSNet `1905.00953`,
   DaSiamRPN `1808.06048`, no-training appearance `1607.05975`, online update `1711.03368`.

4. **Đo trên chính máy** (script ngoài repo, `/mnt/d/_tmp_research/measure_cues.py`, `addendum.py`):
   - **Độ trễ** trên frame 1280×720: YuNet detect 27,49 ms; SFace feature 8,29 ms; HSV hist 1,10 ms;
     HSV hist lưới 2×2 0,20 ms; covariance 5×5 1,07 ms; ORB 300kp 2,36 ms;
     **masked average pooling trên feature map có sẵn: 0,04 ms (miễn phí)**; encoder @512 ~450 ms.
   - **Khả năng phân biệt** trên fixture tự sinh có ground truth (vật đích = ô cam có sọc trắng):
     - HSV hist: positive 1,000; cùng màu không texture 0,786; cùng màu texture khác 0,866; khác màu 0,382.
     - Covariance 5×5: positive 1,000; cùng màu không texture **0,061**; texture khác 0,997; khác màu 0,166.
     - Feature encoder (free): positive 0,950; cùng màu không texture 0,589; texture khác 0,602; khác màu **0,914**.
     - **Ca "giống y hệt"**: HSV 1,000 / covariance 1,000 / encoder 0,975 → **mọi cue ngoại hình đều bất lực**
       (thậm chí cao hơn positive thật 0,946).

5. **Viết báo cáo research** `docs/research/06-nhan-dang-lai-mat-va-dac-trung-vat-the-tu-lam.md`:
   câu hỏi nghiên cứu, trạng thái thật của repo, bảng nguồn, 3 bảng số đo, kiến trúc 4 tầng đề xuất
   (T0 bám+memory đã có / T1 Object Signature + prototype bank / T2 face cue tuỳ chọn /
   T3 fusion + hiệu chuẩn ngưỡng — phần "tự làm" / T4 state machine), bảng phân công cue theo tình huống,
   kế hoạch ablation A0–A8, rủi ro, và mục "chưa kiểm chứng".

6. **Gỡ sự cố mạng** (`Connection error` liên tục của pi) — xem mục Vấn đề bên dưới.

## 📤 Output / Kết quả
- **Báo cáo research hoàn chỉnh** với 3 bảng số đo thật trên máy và 10 nguồn có thể trích dẫn.
- **Kết luận thiết kế có bằng chứng:** (a) không cue nào đủ một mình → phải fusion;
  (b) ca "vật giống hệt" chỉ **cue thời gian** (Kalman/motion memory) giải được;
  (c) phần "tự làm" nên đặt ở **tầng hợp nhất + chuẩn hoá + hiệu chuẩn ngưỡng**, không nằm ở descriptor.
- **Sự cố mạng đã FIX:** DNS bị giả mạo trên Wi-Fi → bật Cloudflare WARP mode `doh`; kiểm chứng
  **10/10 mẫu trả đúng IP + HTTP 200** (trước đó 13/25 mẫu sai IP và 25/25 request fail).
- **Phát hiện độc lập:** tài khoản `ollama-cloud` (user `thangnhtm`) **hết quota tuần** → API trả HTTP 429.
- File thay đổi / tạo mới:
  - `docs/research/06-nhan-dang-lai-mat-va-dac-trung-vat-the-tu-lam.md` — báo cáo research (mới).
  - `docs/task/25-10-2026-research-tai-nhan-dien-mat-va-vat-the.md` — log này (mới).
  - *(ngoài repo, tạm)* `/mnt/d/_tmp_research/{wq.py, measure_cues.py, addendum.py, nettest.ps1, live.ps1}`.

## 🐞 Vấn đề gặp phải & cách xử lý

### 1. Mất context nhiệm vụ sau khi đổi model
- **Triệu chứng:** người dùng hỏi "biết nhiệm vụ vừa giao là gì không", nhưng session mới hoàn toàn rỗng.
- **Xử lý:** đọc trực tiếp file session JSONL cũ trên đĩa thay vì `recall` (recall scope `active` không thấy
  session khác). Phát hiện thêm: 2 lượt trả lời cuối ở phiên cũ bị rỗng → nhiệm vụ chưa từng được đáp.

### 2. Web tool hết hạn mức
- **Triệu chứng:** `HTTP 429 … you (thangnhtm) have reached your weekly usage limit` cho cả search và fetch.
- **Xử lý:** tự dựng công cụ `curl` + DuckDuckGo HTML + arXiv API (`/mnt/d/_tmp_research/wq.py`).
  Một số trang (docs.opencv.org) bị Cloudflare chặn curl → ghi rõ trong báo cáo là **chưa kiểm chứng**.

### 3. `Connection error` / `Retry failed after 3 attempts` (pi) — nguyên nhân là DNS bị giả mạo
- **Chẩn đoán (số liệu thật):**
  - DNS thường (UDP/53) trả `ollama.com` → `147.45.69.3` (IP rác) trong **13/25 mẫu**; IP đó trả cert tự ký
    `subject=CN=localhost, issuer=CN=ospanel` → TLS fail.
  - Ép IP đúng (`--resolve …:34.36.133.15`) → **HTTP/2 200** ⇒ mạng tới server tốt, lỗi ở DNS.
  - DoH qua `1.1.1.1` → đúng IP, **HTTP 200** ⇒ xác nhận đường DNS thường bị can thiệp.
  - `ipconfig /flushdns` **không cứu** (8/8 vẫn fail) vì nguồn giả mạo vẫn sống.
  - Loại trừ: không có proxy trong registry/env; `Cloudflare WARP` đang **Disconnected — Manual Disconnection**
    (nên WARP không phải thủ phạm).
- **Cách sửa đã áp dụng:** `warp-cli --accept-tos mode doh` + `connect` (chế độ **chỉ mã hoá DNS**, không tunnel).
  - Sau khi bật: DNS = `127.0.2.2/127.0.2.3` → **10/10 đúng IP, HTTP 200** → hết `Connection error`.
- **Tư vấn kèm:** KHÔNG gỡ WARP (nó là thuốc, không phải bệnh). Bền vững hơn: bật DoH cho Wi-Fi trong
  Windows (Settings → Wi-Fi → DNS → Manual → `1.1.1.1`, Encrypted only) hoặc cấu hình DoH ở router.

### 4. Lỗi riêng, KHÔNG phải mạng: hết quota
- Gọi API thật qua DoH: **HTTP 429** — `you (thangnhtm) have reached your weekly usage limit`.
- **Xử lý:** dùng provider khác trong pi (`/model` → `opencode-go`, đang HTTP 200) hoặc nạp credit / chờ reset tuần.
  Session hiện tại đang chạy `opencode-go / deepseek-v4-flash`.

### 5. Cảnh báo nhỏ (chưa xử lý)
- `wsl: Failed to start the systemd user session for 'msi'` xuất hiện ở mọi lệnh — không ảnh hưởng kết quả đo,
  nhưng nên dọn nếu muốn log sạch.
- `data/smooth_metrics.csv`, `data/smooth_summary.json` (lần chạy 264 frame) và `docs/DoAnCameraAI.docx`
  **vẫn đang bẩn trong working tree** — người dùng chưa chọn A/B/C nên phiên này **không đụng vào**.
- Báo cáo mới viết **chưa chạy `ruff`/`pytest`** vì chỉ thêm 2 file markdown (không đụng code) —
  cổng kiểm tra sẽ chạy ở phiên implement đầu tiên.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Người dùng/GVHD chốt 4 câu hỏi ở §9 báo cáo: (1) giữ hay bỏ cue mặt, (2) phần nào tính là "của em",
      (3) có viết ADR mới thay ADR-0003 + đặt `reid_enabled: false` không, (4) ai quay dữ liệu thật.
- [ ] Quay 5 loại clip ở §7 (đặc biệt: **2 vật giống hệt** và **2 người mặc giống nhau**).
- [ ] Hiệu chuẩn ngưỡng cho ticket 09 bằng clip thật (thay số 0,363 chép từ tài liệu OpenCV).
- [ ] Chốt hướng code: nếu làm thì đi `tdd` cho T1 (Object Signature) trước, rồi T3 (fusion + hiệu chuẩn),
      cuối phiên chạy `pytest -m "not slow"` + `ruff check .` rồi ghi log mới.
- [ ] Dọn working tree (chọn A/B/C cho 3 file đang bẩn).

## 📚 Tài liệu tham khảo
- SAMURAI: https://arxiv.org/abs/2411.11922 · XMem: https://arxiv.org/abs/2207.07115
- VS-ReID: https://arxiv.org/abs/1708.00197 · Fusion open-set ReID: https://arxiv.org/abs/2610.07366
- Biometric fusion overview: https://arxiv.org/abs/1902.02919 · Query adaptive late fusion: https://arxiv.org/abs/1810.13103
- OSNet: https://arxiv.org/abs/1905.00953 · DaSiamRPN: https://arxiv.org/abs/1808.06048
- Không giám sát: https://arxiv.org/abs/1607.05975 · Cập nhật trực tuyến: https://arxiv.org/abs/1711.03368
- Nội bộ: `docs/adr/0003-tai-nhan-dien-khuon-mat-yunet-sface.md`, `docs/samurai-setup.md`, `GLOSSARY.md`,
  `.scratch/camera-ai-realtime/issues/09-*.md`, `src/reid.py`, `src/tracker_engine.py`
