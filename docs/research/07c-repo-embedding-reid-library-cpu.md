# 07c — Thư viện/embedding tái nhận diện (Re-ID) chạy được trên laptop CPU

> Báo cáo research cho quyết định kiến trúc. Ngày: **27-10-2026**.
> Câu hỏi: có thư viện/model có sẵn nào làm được **"tái nhận diện một vật bất kỳ từ 1 ví dụ"** (ví dụ cái remote TV) trên **CPU laptop (i7-1195G7, 4c/8t, ~16 GB, không GPU)** — và nên tự làm tới đâu để GVHD nhìn thấy phần tự làm của sinh viên?
> Kèm theo: các repo open-source đã làm "chọn vật trong 1 frame → nhớ → nhận dạng lại sau đó".
> Tất cả license dưới đây được đọc **trực tiếp từ file LICENSE / field API của chính repo đó** (ngày fetch: 27-10-2026) — không tin mô tả thứ hai.
> Số liệu đo trên chính laptop này (mục §2, dòng "đo"): từ phiên benchmark trước (`docs/research/06-nhan-dang-lai-mat-va-dac-trung-vat-the-tu-lam.md`).

---

## 1. Câu hỏi nghiên cứu

1. Thư viện Re-ID (torchreid/deep-person-reid, fast-reid, BoxMOT, OSNet...) có **chạy nổi trên CPU** không, license thế nào, và bao nhiêu là "hộp đen" của người khác?
2. Backbone embedding tổng quát (MobileNetV3, EfficientNet-Lite, DINOv2, CLIP) dùng **frozen trên CPU** có khả thi không?
3. Có repo nào đã làm **instance re-ID cho vật bất kỳ** (không phải người) hay phải tự làm không?
4. Câu trả lời "chuẩn ngành" cho bài toán này có phải là **tự train một mini embedding net (50k–200k params, triplet loss, trên crop tự gãn từ tracking)** không?

---

## 2. Bảng so sánh chính

Đo trên chính laptop này (từ phiên benchmark trước): chữ ký handcrafted (covariance + HSV hist) = **1.4 ms/region**; MobileNetV3-small (ImageNet, frozen) = **3.8 ms/crop @96px**; ResNet18 = **9.6 ms/crop**; SAM 2.1 tiny image encoder ≈ **450 ms/frame** (đã trả 1 lần/frame trong pipeline, không tính thêm). Số "ngoại suy" là ước thô theo tỉ lệ FLOPs so với MobileNetV3-small@96px — **chưa đo thật**, xem §7.

| Tuỳ chọn | License (nguồn trích) | Params / kích thước | CPU latency (đo ⟶ ngoại suy/claimed) | Độ tự làm của sinh viên | Verdict cho đồ án |
|---|---|---|---|---|---|
| **Chữ ký handcrafted (cov + HSV)** — đang chạy | — (tự viết) | không weights | **1.4 ms/region (đo)** | 100% tự làm | ✅ **Giữ làm v1** — nhanh nhất, rủi ro 0 |
| **Tự train mini-net (OSNet x0.25-kích cỡ hoặc MobileNetV3-small† + projection head)**, triplet + softmax | — (tự train; weight tự sinh) | **0.2 M** (OSNet x0.25 = 0.17–0.2M) до ~0.3M | ngoại suy ≈ **25–35 ms @256×128** | **Cao**: kiến trúc + data tự gãn + loss + huấn luyện đều là của mình | ✅ **Đường v2 khuyến nghị** — xem §6 |
| **OSNet x1.0 pretrained (torchreid)** | MIT (`deep-person-reid` LICENSE: "MIT License / Copyright (c) 2018 KaiyangZhou") | **2.2 M params, 0.98 GFLOPs** @256×128 (MODEL_ZOO.md) | ngoại suy ≈ **hàng trăm ms**; pretrained trên Market1501 (người) | thấp → chỉ dùng được làm "model có sẵn" | ⚠️ Chỉ dùng làm baseline đối chiếu, không vào product |
| **OSNet x0.25 pretrained** | MIT (cùng repo) | **0.2 M, 0.08 GFLOPs** @256×128; Market1501 top-1 91.2 | ngoại suy ≈ **~30 ms** | thấp (pretrained) nhưng **có thể tự train lại cùng kiến trúc** trong torchreid | ⚠️ Fallback của §6 — dùng architecture, tự train weight |
| **FastReID (JDAI-CV)** | Apache-2.0 (`fast-reid` LICENSE: "Apache License Version 2.0") | model SOTA chủ yếu ResNet50-class (~23M+) | quá nặng cho CPU real-time; đẩy 2024-07, ít bảo trì | rất thấp (toolbox lớn, nhiều tầng trừu tượng detectron-style) | ❌ Loại: quá nặng + black-box |
| **BoxMOT (mikel-brostrom)** | **AGPL-3.0** (`boxmot` LICENSE: "GNU AFFERO GENERAL PUBLIC LICENSE Version 3") — copyleft | reid model pluggable; có CLI `train-reid`, `eval-reid`, `export` (onnx/openvino/tflite) | không đơ trực tiếp: nó wrap model khác | thấp; và **AGPL lây lan license** nếu import | ❌ Loại làm dependency chính (risk copyleft cho repo đồ án công khai); chỉ đọc để tham khảo kiến trúc |
| **ONNX Runtime (CPU EP)** | MIT (API `spdx_id: MIT`) | runtime (~vài chục MB wheel — chưa kiểm chứng chính xác) | không thêm chi phí tính toán đáng kể so với PyTorch cho net nhỏ | trung gian: thêm 1 lớp build/export | ⭕ Optional: chỉ thêm nếu v2 cần chạy nhanh hơn PyTorch CPU |
| **FAISS** | MIT (API `spdx_id: MIT`) | library ~ hàng trăm KB–MB, nhiều backend | thiết kế cho **10⁴–10⁹ vectors** (faiss README: "scale to billions of vectors") | — | ❌ Không cần: **≤64 vectors → numpy thuần** đủ và dễ debug |
| **NumPy prototype matching** | BSD-style (numpy `LICENSE.txt`: "Copyright (c) 2005-2025, NumPy Developers" — 3-clause BSD) | không weights | so sánh 64 vector 128-D ≈ vi-giây (không đáng kể) | cao (tự viết matching logic của mình) | ✅ Dùng chính |
| **MobileNetV3-small frozen (torchvision/timm)** | torchvision: BSD-3; timm: **Apache-2.0** (API `spdx_id: Apache-2.0`) — torchvision license chưa tự đọc file phiên bản này (§7) | **~2.5 M** (MV3-S small); @96px rất nhẹ | **3.8 ms/crop @96px (đo)** | trung bình: backbone đen (ImageNet frozen) nhưng **head tự train** | ⭕ Nền tốt cho v2 nếu muốn frozen backbone + tự train head |
| **ResNet18 frozen** | torchvision (BSD-3, chưa tự đọc — §7) | **11.7 M** | **9.6 ms/crop (đo)** | trung bình | ⭕ Hơi to so với cần — chỉ dùng nếu cần đặc trưng mạnh hơn |
| **EfficientNet-Lite** | Google blog (không fetch được nội dung — §7) | blog ghi Lite0 ~4.7 M / Lite4 ~13 M (chưa kiểm chứng được trực tiếp) | chưa đo | trung | ❌ Không đi tiếp: không thu được bằng chứng tốt hơn MobileNetV3-small đã đo |
| **DINOv2 ViT-S/14** | Apache-2.0 (`facebookresearch/dinov2` API) | **~21 M** (paper arXiv:2304.07193) — input chuẩn 518px | CPU: quá nặng chưa đo; patch 14 cần ảnh ≥ 224px | rất thấp | ❌ Loại cho real-time CPU (đầu vào lớn, ViT không tối ưu CPU không-GPU) |
| **CLIP ViT-B/32 (visual tower frozen)** | MIT (`openai/CLIP` API) | visual tower ~88 M (số phổ biến — chưa kiểm chứng trực tiếp, §7); tổng mô hình lớn hơn | CPU: hàng trăm ms/ảnh (chưa đo) | rất thấp | ❌ Loại: quá nặng + nhúng ngữ cảnh-ảnh, khó tự làm phần của mình |
| **SFace ONNX (đang dùng cho mặt)** | Apache-2.0 (OpenCV ecosystem) | 128-D embedding | đã chạy được trên CPU (phiên trước) | trung | ✅ Giữ cho mặt (đã có); đối chiếu mô hình cho vật |

*GFLOPs của OSNet lấy từ `deep-person-reid/docs/MODEL_ZOO.md` (raw, fetch 27-10-2026): `osnet_x1_0 | 2.2 | 0.98 | softmax | (256, 128)`, `osnet_x0_25 | 0.2 | 0.08 | softmax | (256, 128)`, Market1501 [94.2 / 82.6] r1/mAP cho x1.0; 91.2/75.0 cho x0.25.*

---

## 3. Chi tiết từng thư viện

### 3.1. torchreid / deep-person-reid — **MIT** ✅

- Repo: https://github.com/KaiyangZhou/deep-person-reid — 4 933★, push gần nhất 2026-01-09.
- License **đọc trực tiếp** từ `licenses`-root file `LICENSE` (raw.githubusercontent.../master/LICENSE): "MIT License / Copyright (c) 2018 Kaiyang Zhou" — ✅ an toàn cho repo công khai.
- `docs/MODEL_ZOO.md`: họ **OSNet** có 4 cỡ, x1_0→x0_25; **x0_25 = 0.2M params, 0.08 GFLOPs @256×128** — đúng khoảng "50k–200k params" mà đề bài hỏi.
- Paper gốc OSNet: *Omni-Scale Feature Learning for Person Re-Identification*, arXiv:1905.00953 (Chen, 2019) — xác nhận qua arXiv API.
- **Lưu ý PyPI**: package `torchreid` trên PyPI v0.2.5 là **fork cộng đồng** (`goksenin-uav/torchreid-pip`, pypi.org/pypi/torchreid/json — license field ghi MIT, home_page trỏ về fork đó), không phải chính chủ. Chính chủ cài qua `git clone` + `pip install -e .`. Ghi rõ trong README khi dùng.
- Đánh giá "tự làm": thư viện cho phép **define dataset/trainer của mình** — có thể giữ kiến trúc OSNet để train net nhỏ của đồ án; đó là mức "dùng khung, tự làm phần dữ liệu + train" — hợp lý.

### 3.2. FastReID — **Apache-2.0** ✅ license nhưng ❌ vì quá nặng

- Repo: https://github.com/JDAI-CV/fast-reid — 4 005★, push cuối 2024-07-30 (chậm dần).
- License đọc trực tiếp `LICENSE`: "Apache License Version 2.0".
- Tool hướng đến mô hình SOTA (bag-of-tricks ResNet50/IBN, ~23M+ params), nhiều tầng trừu tượng kiểu detectron2/MMAction — **chi phí học + runtime không hợp CPU laptop real-time**. Trích trong báo cáo để cho thấy "đã xem xét và loại vì X", không phải chưa biết.

### 3.3. BoxMOT — **AGPL-3.0** ❌ (copyleft)

- Repo: https://github.com/mikel-brostrom/boxmot — 8 316★, push 2026-10-27 (rất active). License badge trên README + file `LICENSE` (raw): **"GNU AFFERO GENERAL PUBLIC LICENSE Version 3, 19 November 2007"**.
- Đây là **copyleft mạnh**: import module reid của nó vào nguồn đóng/đồ án public buộc mở toàn bộ source đó dưới AGPL. Với đồ án muốn "nếu dùng thì mọi người tự làm được", rủi ro license này lớn hơn lợi ích.
- Nó có CLI `train-reid`, `eval-reid`, `compare-reid`, `export` (onnx/openvino/tflite) — tốt cho việc **tham khảo knowledge**: quy trình train/triết lý reid-tracker coupling. Đọc code, không import.
- (Lịch sử thay đổi license của repo chưa kiểm chứng được qua API phiên này — xem §7.)

### 3.4. ONNX Runtime — **MIT** ✅, cần thêm chỉ khi v2 cần tốc độ

- Repo https://github.com/microsoft/onnxruntime (API spdx_id: MIT), README: "cross-platform inference and training machine-learning accelerator". CPU Execution Provider là mặc định, không cần GPU.
- Cho net 0.1–0.3M params, PyTorch CPU thường đủ nhanh; thêm ONNX chỉ khi muốn tối ưu sau. Không khuyến nghị trong v1.

### 3.5. FAISS — **MIT** ✅ nhưng **không cần ở quy mô này**

- API spdx_id: MIT; README faiss: "scale to billions of vectors" (thiết kế cho 10⁴–10⁹).
- Với **≤64 prototype vector** (điều kiện đề bài), so sánh bằng **numpy thuần** (khoảng cách cosine trên ma trận 64×D) là vi-giây và dễ debug/giải thích. FAISS chỉ thêm rủi ro build (C++ extension) không đổi được chất lượng. SFace (128-D) cũng so bằng numpy là đủ.

---

## 4. Repo đã làm "chọn vật trong 1 frame → nhớ → nhận dạng lại"

Kết quả thật: **không tìm thấy repo ready-to-use nào làm đúng đề bài của đồ án này** (chọn 1 vật bất kỳ như remote TV và re-ID nó trên CPU). Cở sở lý thuyết có, nhưng ở dạng bài research:

| Nguồn | Bằng chứng | Làm được gì cho đồ án |
|---|---|---|
| Paul et al., *Generic Instance Search and Re-identification from One Example via Attributes and Categories* — **arXiv:1605.07104** (2016, xác nhận qua arXiv API) | Bài paper gốc về **instance search / re-id từ 1 ví dụ** cho vật bất kỳ (không bắt buộc người) | Cơ sở lý thuyết cho "chọn 1 crop → nhớ embedding → re-id sau đó"; không có code mới |
| TAO benchmark — *TAO: A Large-Scale Benchmark for Tracking Any Object* — **arXiv:2005.10356** (2020, xác nhận qua arXiv API) | Benchmark chuẩn cộng đồng cho **tracking any object** (không chỉ người) — kèm challenge re-id vật | Đối chiếu scope đồ án; chứng minh "any object" là bài toán mở, không có solution cài-sẵn |
| Siam R-CNN — *Siam R-CNN: Visual Tracking by Re-Detection* — **arXiv:1911.12836** (2019, xác nhận qua arXiv API) | Kỹ thuật **twice-matching + trajectory-tube + re-detection** chống mất dấu | Ý tưởng re-detect rồi so khớp lại với lịch sử — có thể vay logic, không vay code |
| Track-Anything — https://github.com/gaomingqi/Track-Anything (API license: **MIT**, 7 013★) | Tool tương tác SAM-based cho video **tracking/segmentation** — là *propagation*, không phải re-ID độc lập | Tham khảo UX "chọn vật bất kỳ", không dùng được phần re-ID |
| Fork của SAMURAI yangchris11/samurai (30 fork mới nhất, 27-10-2026) | Toàn bộ vẫn mô tả "Official repository ..." — duy nhất `sarunasbend/samurai-ukf` (thay KF) | **Chưa thấy fork nào thêm re-ID vật thể**. GitHub code search (cần token) chưa chạy được — xem §7 |
| SAMURAI gốc https://github.com/yangchris11/samurai — **Apache-2.0** (API spdx_id) | Không có re-ID appearance ngoài Kalman/memory-score | Đúng như phần đã phân tích ở `docs/research/01/02` — phần "nhận dạng lại" phải tự thêm |

Kết luận **thực tế tốt cho đồ án**: không có "giải pháp có sẵn" — nghĩa là phần tái nhận diện vật thể **thuộc vào phần tự làm của sinh viên**, không bị chiếu "dùng model có sẵn".

---

## 5. "Tự train mini embedding net" có phải chuẩn ngành không? — Có.

Chuỗi evidence trực tiếp:

1. **Deep SORT** — *Simple Online and Realtime Tracking with a Deep Association Metric*, **arXiv:1703.07402** (Wojke, Bewley, Poule, 2017 — xác nhận qua arXiv API). Trích nguyên văn từ bài (ar5iv, fetch 27-10-2026):
   - "In total, the network has **2,800,864 parameters** and one forward pass of 32 bounding boxes takes approximately **30 ms** on an Nvidia GeForce GTX 1050 mobile GPU."
   - Quy trình chính xác giống bài toán đồ án: **crop từ tracklet video, tự gãn theo ID tracking, train loss = cross-entropy + triplet, thu được một embedding để so-khớp sau này**. Đây chính là "tự gãn crop từ tracking" mà đề bài hỏi.
2. **FaceNet** — *FaceNet: A Unified Embedding for Face Recognition and Clustering*, **arXiv:1503.03832** (Schroff et al., 2015 — xác nhận qua arXiv API): nguồn gốc **triplet loss** với "semi-hard" mining — recipe loss cho embedding.
3. **Bag of Tricks and A Strong Baseline for Deep Person Re-identification** — **arXiv:1903.07071** (Luo et al., 2019 — xác nhận qua arXiv API): chuẩn hóa toàn bộ recipe train re-ID (loss, augmentation, BN-neck) — dùng được cho net nhỏ tự train với bất kỳ dataset re-ID nào.
4. **OSNet x0.25 (0.2M params)** trong `deep-person-reid/docs/MODEL_ZOO.md` chứng minh **đúng cỡ 50k–200k params là cỡ "tiny re-ID net" phổ biến, đã được train chéo dataset đạt top-1 91.2 Market1501** (pretrained người) — nghĩa là cỡ model này hợp lý, không phải "quá nhỏ để làm gì".
5. Thực tế đã đo trên chính laptop (phiên benchmark trước): **crop @96px MobileNetV3-small chỉ 3.8 ms** — nếu tự train head nhỏ thêm ~100–200k params thì chi phí thêm không đáng kể so với 450 ms/frame của SAM 2 encoder.

⇒ **Câu trả lời chuẩn ngành và rủi ro thấp nhất chính là Deep SORT-style: nhỏ + triplet + self-labelled crops từ tracking của chính pipeline.** Đây cũng là cách khiến GVHD thấy phần tự làm rõ ràng nhất.

---

## 6. Đường đi rủi ro thấp nhất

So sánh ba đường, nêu rõ trade-off:

### v1 — Giữ handcrafted (covariance + HSV), 1.4 ms/region (đo)
- ✅ Nhanh nhất, 100% tự làm, không weights, không license issue, dễ giải thích trong báo cáo.
- ❌ Yếu với vật cùng màu/cùng dáng (remote TV nhiều cái giống nhau trong phòng), không học được gì.
- **Nên: luôn giữ lại làm cue rẻ** (chạy 1.4 ms mọi region), kể cả khi v2 có.

### v2 — **Tự train mini embedding net (khuyến nghị)**
- **Kích thước mục tiêu: 0.1–0.3 M params** (cỡ OSNet x0.25 = 0.2M đã được chứng minh ở MODEL_ZOO.md); kiến trúc hoặc tự viết (backbone 96px + projection head) hoặc **mượn architecture OSNet x0.25 từ torchreid (MIT) nhưng train lại hoàn toàn với data của mình** — phần hộp đen giảm về "kiến trúc public, weight tự sinh".
- **Data: crop tự gãn từ chính pipeline** — mask SAM 2 khi tracking ổn định (kf_score/iou tốt) → crop → pseudo-label = ID của track đó; không cần dataset ngoài (Deep SORT: arXiv:1703.07402 làm đúng quy trình này).
- **Loss: softmax + triplet** (FaceNet: arXiv:1503.03832; recipe chuẩn: arXiv:1903.07071), train **offline (không cần real-time)** trên CPU laptop qua đêm là đủ với cỡ model này.
- **Trade-off được nêu tên:** tốn thêm ~1–2 tuần làm data-augmentation + tuning; chất lượng phụ thuộc chất lượng crop tự gãn (nếu mask SAM 2 trôi, nhãn giả cũng trôi → chống bằng cách chỉ lấy crop khi `stable_frames_threshold` đạt — cơ chế đã có sẵn trong SAMURAI mode).
- CPU latency ước ngoại suy ~25–35 ms/region (@256×128) — chỉ embed lại mỗi khi cần cập nhật prototype (không phải mỗi frame), phù hợp budget 450 ms/frame đã tiêu cho SAM 2 encoder.

### v3 — Dùng pretrained embedder (OSNet/CLIP/DINOv2 frozen)
- ✅ Không cần train, chạy nhanh nhất để có baseline số mAP.
- ❌ Điểm chết nghiêm trọng với đồ án: **đề bài là vật bất kỳ (remote TV), còn các model này pretrained trên người (Market1501/DukeMTMC) hoặc object classification ImageNet/CLIP** — đều rơi về "hộp đen của người khác" mà GVHD không chấp nhận, và phần pretrained người không có ý nghĩa cho remote.
- Verdict: chỉ dùng OSNet pretrained làm **baseline đối chiếu offline** trong báo cáo ("tự train của mình so với model public"), không đưa vào runtime chính.

### Khuyến nghị cuối
1. **v1 hiện tại giữ nguyên** (handcrafted 1.4 ms) — không phải đập đi.
2. **Bắt đầu v2 ngay**: architecture nhỏ + triplet/softmax + crop tự gãn từ SAM 2. Dùng torchreid (MIT) chỉ là khung trainer/architecture; khẳng định trong báo cáo: *"weight của embedding net do đồ án tự train trên crop tự gãn từ pipeline của chính mình"*.
3. **Không dùng BoxMOT (AGPL-3.0)** làm dependency; không cần FAISS (numpy đủ với ≤64 vector); không thêm ONNX Runtime nếu PyTorch CPU đủ nhanh.
4. Nếu hết thời gian: fallback là **MobileNetV3-small frozen + projection head tự train ~100k params** (backbone đã đo 3.8 ms, chỉ thêm head).

---

## 7. Chưa kiểm chứng (minh bạch)

- **CPU latency của OSNet / DINOv2 / CLIP / EfficientNet-Lite: chưa có số đo thực.** Các con số ngoại suy §2 là **ước lượng thô theo tỉ lệ GFLOPs** so với MobileNetV3-small@96px đã đo 3.8 ms; cần benchmark 1 vòng 100 crop trên chính máy trước khi ghi vào báo cáo chính thức.
- **PyPI `torchreid` v0.2.5 là fork cộng đồng** (`goksenin-uav/torchreid-pip`) — không phải chính chủ KaiyangZhou. License field PyPI ghi MIT nhưng đó là fork, không phải bản chính chủ; nếu dùng PyPI, đọc lại `LICENSE` trong wheel.
- **Lịch sử thay license của BoxMOT**: API GitHub bị rate-limit phiên này, không xác nhận được khi nào repo chuyển sang AGPL-3.0; chỉ xác nhận **trạng thái hiện tại = AGPL-3.0** (file LICENSE raw).
- **GitHub code search** (tìm fork SAMURAI/SAM 2 có re-ID) chưa chạy được — cần token xác thực. Đã liệt kê 30 fork mới nhất bằng API thường, thấy duy nhất `samurai-ukf` (thay KF). Không khẳng định "không tồn tại fork re-ID", chỉ là "không tìm thấy trong bộ này".
- **huggingface.co web UI bị chặn; chỉ truy cập được `huggingface.co/api/models/openai/clip-vit-base-patch32`** (model card API). Số params visual tower CLIP ~88 M là **số phổ biến, chưa đọc trực tiếp từ nguồn chính chủ**.
- **EfficientNet-Lite**: Google AI blog không fetch được nội dung (2 URL đều chặn/rỗng). Số params Lite ~4.7 M/13 M chỉ là tài liệu nhớ, không dùng làm cơ sở kết luận trong §2.
- **License torchvision** (ResNet18/MobileNetV3) và **OpenCV YuNet/SFace weight license** chưa tự đọc lần này; BSD-3/Apache-2.0 là nhận biết chung — cần 1 lần trích nguyên văn file LICENSE nếu đưa vào bảng phụ lụp license của báo cáo.
- **FAISS/numpy**: chỉ xác nhận license; chưa benchmark numpy match 64×128-D trên máy này (dự kiến vi-giây, nhưng chưa có số đo).

---

## 8. Tài liệu tham khảo (nguồn truy cập 27-10-2026)

- torchreid/deep-person-reid: https://github.com/KaiyangZhou/deep-person-reid — LICENSE (MIT), docs/MODEL_ZOO.md (OSNet params/GFLOPs).
- FastReID: https://github.com/JDAI-CV/fast-reid — LICENSE (Apache-2.0).
- BoxMOT: https://github.com/mikel-brostrom/boxmot — LICENSE (AGPL-3.0), README (CLI train-reid/export onnx).
- ONNX Runtime: https://github.com/microsoft/onnxruntime.
- FAISS: https://github.com/facebookresearch/faiss — README (scale billions).
- DINOv2: https://github.com/facebookresearch/dinov2 + arXiv:2304.07193.
- CLIP: https://github.com/openai/CLIP + HF API model card clip-vit-base-patch32.
- timm: https://huggingface.co/pytorch-image-models (API spdx_id Apache-2.0).
- OSNet paper: arXiv:1905.00953.
- MobileNetV3 paper: arXiv:1905.02244.
- Deep SORT (2.8M-param embedding, self-labelled tracklet crops, CE+triplet): arXiv:1703.07402 (trích nguyên văn qua ar5iv).
- FaceNet (triplet loss): arXiv:1503.03832.
- Bag of Tricks Person Re-ID: arXiv:1903.07071.
- Instance re-ID từ 1 ví dụ: arXiv:1605.07104.
- TAO benchmark: arXiv:2005.10356.
- Siam R-CNN (re-detection): arXiv:1911.12836.
- Track-Anything: https://github.com/gaomingqi/Track-Anything (MIT).
- SAMURAI (baseline hiện có): https://github.com/yangchris11/samurai (Apache-2.0) — đã phân tích ở `docs/research/01-phan-tich-repo-samurai.md`.
- Số liệu đo trên chính máy: `docs/research/06-nhan-dang-lai-mat-va-dac-trung-vat-the-tu-lam.md` (§1, §4).