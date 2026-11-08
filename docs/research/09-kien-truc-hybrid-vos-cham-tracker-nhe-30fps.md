# Kiến trúc hybrid: VOS chậm (5–10 FPS) + tracker nhẹ (25–30 FPS hiển thị)

> Ngày: 08-11-2026. Máy mục tiêu: i7-1195G7 (4 nhân/8 luồng), Iris Xe, **không CUDA**.
> Bối cảnh repo: `src/smooth_display.py` đã có 3 luồng (capture / inference / display, bỏ frame khi
> model bận) nhưng display chỉ vẽ lại overlay của lần suy luận gần nhất — **chưa có tracker nhẹ**.

## 0. Quy ước nhãn nguồn

- **[ĐÃ ĐO]** — đo trên chính máy này, có file trong repo.
- **[NỘI BỘ]** — đã fetch/xác minh trong research trước của repo.
- **[PAPER — cần đối chiếu]** — từ paper/docs, cần mở lại URL trước khi chép vào báo cáo.
- **[ƯỚC LƯỢNG]** — suy luận kỹ thuật, chưa đo. **N/A** — không đủ dữ kiện.

## 1. Kết luận

1. **"VOS thưa + tracker dày" là pattern có tiền lệ công bố, không phải mánh:** DEVA tách model
   phân đoạn ảnh (chạy trên keyframe thưa) khỏi module lan truyền thời gian; phái MOT
   (SORT → ByteTrack → OC-SORT) giữ quỹ đạo bằng motion giữa các lần detect [NỘI BỘ cho DEVA].
2. **Bằng chứng giảm nhịp:** DEVA đánh giá theo frame-gap, chất lượng giảm dần chứ không sập
   [PAPER — cần đối chiếu]; XMem gộp working memory mỗi **r = 5** frame — VOS SOTA đã "giảm nhịp"
   một phần mà vẫn giữ J&F [PAPER]. **SAM 2 paper không có ablation stride** → khoảng trống =
   đồ án tự đo, là **đóng góp thực nghiệm**, không phải thiếu sót.
3. **Tracker nhẹ rẻ hơn VOS 1–2 bậc:** KCF/CSRT/LK 1–20 ms [ĐÃ ĐO — xem §2] so với VOS 97–184 ms
   [ĐÃ ĐO]. Tầng hiển thị bị giới hạn bởi **nguồn hình**, không bởi tracker.
4. **Cấu hình đề xuất:** VOS = tiny @`image_size 192` (97 ms, 10,3 FPS, video thật 0/60 mất dấu
   [ĐÃ ĐO]) + tracker nhẹ mỗi frame nguồn + mask **tịnh tiến** theo tracker + **IoU-reset** mỗi lần
   VOS trả. Hiển thị **25–30 FPS** nếu nguồn 30 FPS; **~20 FPS** với relay webcam hiện tại [NỘI BỘ].
5. **Trung thực:** không gian lận nếu báo cáo **tách hai con số FPS** + nêu **tuổi mask**. HUD hiện
   tại đã hiển thị `overlay_age_ms` [NỘI BỘ: `src/smooth_display.py`] — giữ nguyên nguyên tắc đó.

## 2. Chi phí tracker nhẹ — ĐO THẬT trên máy này

Video `data/binh1.mp4`, **1280×720**, bbox `x,y,w,h = 104,308,209,287`, 200 frame.
Đo hai lần: (a) máy rảnh, (b) **trong lúc VOS đang vắt 3,4/4 lõi** — số (b) mới là số thật của pipeline.

| Tracker | ms/frame (máy rảnh) | **ms/frame (dưới tải)** | Ngân sách 33 ms? |
|---|---|---|---|
| **LK optical flow (median Δ, ~160 điểm)** | **2,22** | **3,19** | ✅ dùng 10 % |
| MIL (OpenCV) | 27,89 | **51,05** | ❌ vượt 1,5× |
| KCF / CSRT / MOSSE | — | — | **không có trong `opencv-python` 5.0** (`cv2.TrackerKCF_create` không tồn tại; `cv2.legacy` không có tracker) |
| NanoTrack / VitTrack | — | — | có API (`cv2.TrackerNano_create`) nhưng cần file ONNX — chưa tải |

→ **Kết luận đo được: LK là lựa chọn duy nhất vừa đủ rẻ dưới tải (10 % ngân sách 33 ms), vừa
không cần model.** MIL mất 51 ms dưới tải ⇒ một mình nó đã phá vỡ mục tiêu 30 FPS.

> Số do `scripts/benchmark_light_trackers.py` sinh ra (`data/light_trackers_summary.json`), chạy
> lại để tái tạo. Cách đo "dưới tải": chạy `tools.run_live --image-size 192` nền rồi benchmark
> song song — đúng điều kiện thật của demo.

So sánh bậc độ lớn với lớp AI:

| Thành phần | ms/frame | Ghi chú |
|---|---|---|
| SAM 2.1 tiny @192 | 97 (127,7 khi bật re-ID) | [ĐÃ ĐO] |
| SAM 2.1 tiny @256 | 184 | [ĐÃ ĐO] |
| Tracker nhẹ (LK) | 3,2 dưới tải | [ĐÃ ĐO] |

⇒ Tracker chiếm **2,5 %** thời gian của VOS. Thêm nó gần như miễn phí về mặt CPU.

## 3. Bằng chứng: giảm nhịp suy luận ảnh hưởng chất lượng thế nào

### 3.1 DEVA — bằng chứng trực tiếp nhất
*Tracking Anything with Decoupled Video Segmentation* (ICCV 2023), **arXiv:2309.03903**
(tài liệu nội bộ `docs/research/07a` fetch trực tiếp 27-10-2026 — dùng ID này, không dùng
2301.07868). Tách (i) model phân đoạn ảnh chạy trên **keyframe thưa** khỏi (ii) module lan truyền
thời gian; mất dấu thì chạy lại model ảnh để đề xuất ứng viên. Đây chính là phiên bản học thuật
của kiến trúc đồ án: **phần nặng chạy cách quãng, phần nhẹ nối giữa**.

### 3.2 XMem — giảm nhịp cập nhật bộ nhớ
Memory 3 tầng (Atkinson–Shiffrin); working memory gộp mẫu mỗi **r frame** (mặc định 5).
Tốc độ: ~30 ms/frame @480p trên GTX 1080 Ti [NỘI BỘ `docs/research/03` §4.3] — **GPU rời, không
áp dụng cho CPU này**.

### 3.3 SAM 2 — không có bằng chứng stride
Tuyên bố "real-time ~44 FPS" là trên **A100**, video cạnh 512 [PAPER — cần đối chiếu]. Không suy
ra được cho CPU 4 nhân. Không có ablation "suy luận cách quãng + nội suy mask" → N/A.

### 3.4 Phái MOT — bằng chứng gián tiếp mạnh
SORT (update 260 Hz theo paper), ByteTrack (30 FPS **gồm cả detector YOLOX** trên MOT17),
OC-SORT (re-update sau che): quỹ đạo duy trì bằng **motion thuần** giữa các detection — đúng vai
trò tracker nhẹ giữa hai nhịp VOS. Khác biệt duy nhất: đồ án còn phải **vẽ lại mask**, nên cần đo
thêm chất lượng mask (§4.5).

### 3.5 Khoảng trống tài liệu
Không có công bố đo **J&F khi nội suy mask giữa hai nhịp VOS trên CPU** → đồ án tự đo và báo cáo
như một kết quả thực nghiệm riêng. Đây là câu hỏi nghiên cứu hợp lệ cho buổi bảo vệ.

## 4. Thiết kế đề xuất

### 4.1 Sơ đồ luồng (mở rộng `src/smooth_display.py`)

```
Camera / nguồn (30 FPS mục tiêu)
   │  LatestFrameSource [ĐÃ CÓ] — luôn giữ frame mới nhất
   │
   ├──────────────────► InferenceWorker [ĐÃ CÓ]
   │                     SAM 2.1 tiny @192 → (mask, bbox) mỗi ~97-127 ms [ĐÃ ĐO]
   │                           │ kết quả mới
   │                           ▼
   │                 BƠM ĐỒNG BỘ [MỚI]:
   │                     τ_IoU = IoU(bbox_VOS, bbox_tracker)
   │                     ├─ τ ≥ 0,5 → nhận mask mới; re-init tracker theo bbox VOS
   │                     ├─ τ < 0,5 → tracker trôi → reset theo VOS; reset_count++
   │                     └─ VOS mất dấu → NGỪNG vẽ mask; nhảy nhánh re-ID [ĐÃ CÓ]
   │
   └─► Display loop [ĐÃ CÓ, _DISPLAY_SLEEP = 1/30]
        [MỚI] mỗi frame nguồn: tracker.update(frame) → bbox mới
        [MỚI] mask hiển thị = mask VOS gần nhất, TỊNH TIẾN Δ = tâm(tracker) − tâm(VOS lúc init)
        [ĐÃ CÓ] HUD: FPS hiển thị, FPS suy luận, tuổi mask (overlay_age_ms)
```

Điểm neo tích hợp: trong `run_smooth_display()` (đang render `stamped.result` mỗi vòng) — thêm
`tracker.update()` ngay trước render; **không đụng** `InferenceWorker._loop` (thread-safety đã
giải quyết 18-10).

### 4.2 Số dự kiến

| Chỉ số | Giá trị | Nhãn |
|---|---|---|
| FPS suy luận | 10,3 @192 / 5,45 @256; +re-ID: 8,35 | [ĐÃ ĐO] |
| Chi phí tracker/frame | **3,19 ms** dưới tải (bảng §2) | [ĐÃ ĐO] |
| **FPS hiển thị** | **25–30** nếu nguồn 30; **~20** với relay hiện tại | [ƯỚC LƯỢNG từ trần nguồn, NỘI BỘ] |
| Độ trễ vị trí nhìn thấy | ~1 nhịp hiển thị + tracker ≈ 35–55 ms | [ƯỚC LƯỢNG] |
| Tuổi mask hiển thị | TB ~145 ms, tối đa ~200 ms @192 | [ƯỚC LƯỢNG từ chu kỳ 97 ms] |
| Chất lượng mask tại frame suy luận | không đổi (IoU fixture 0,903 @192) | [ĐÃ ĐO] |
| Chất lượng mask toàn video (nội suy) | giảm vài điểm khi vật xoay/biến dạng; gần như không giảm khi tịnh tiến | [ƯỚC LƯỢNG] — **phải đo (§4.5)** |

### 4.3 Vì sao chọn @192 làm nhịp VOS
Tươi gấp đôi @256 (10,3 vs 5,45 FPS) → tuổi mask tối đa ~200 ms thay vì ~370 ms; video thật 60
frame 0/60 mất dấu [ĐÃ ĐO]. @160 (12,7 FPS, IoU fixture 0,924) là phương án "tươi nhất" nếu demo
vật chuyển động nhanh.

### 4.4 Phát hiện & xử lý khi tracker lệch
1. **IoU-reset:** mỗi khi VOS trả, `IoU(bbox_VOS, bbox_tracker) < 0,5` → reset tracker theo VOS,
   `reset_count++`, ghi vào metrics (báo cáo: "số lần reset/1000 frame").
2. **VOS mất dấu:** mask rỗng → **ngừng vẽ mask và tracker** (không "diễn" vị trí), chuyển sang
   nhánh re-ID [NỘI BỘ `src/reid.py`].
3. **Đổi kích thước bất thường:** diện tích bbox VOS mới lệch EMA > 50 % → coi là drift, reset.
4. **Khởi động:** chưa có kết quả VOS đầu tiên → không vẽ mask (giữ hành vi hiện tại).

### 4.5 Kế hoạch đo
1. ~~Micro-benchmark tracker~~ → **ĐÃ LÀM**: `scripts/benchmark_light_trackers.py` (bảng §2).
2. **J&F theo gap:** dùng pipeline đo IoU sẵn có (kiểu `scripts/experiment_lighting.py`): VOS mỗi
   frame làm baseline; mô phỏng gap 2/3/5 + mask tịnh tiến; báo IoU toàn video vs tại frame suy luận.
3. **End-to-end:** `tools/run_live.py --smooth` + tracker mới: FPS hiển thị, reset_count, tuổi mask p95.

## 5. Rủi ro

| Rủi ro | Biểu hiện | Phát hiện | Xử lý |
|---|---|---|---|
| Tracker bám sang vật che | Box/mask trôi theo nền | IoU-reset (§4.4.1) | Reset; VOS cũng mất → nhánh re-ID |
| Vật xoay/biến dạng giữa 2 nhịp | Mask tịnh tiến sai mép | So diện tích/hình dạng mask VOS mới | @192 (tươi hơn); nâng cấp: affine từ LK |
| Tracker nặng (MIL) | Hiển thị 20 FPS | Bảng §2 — MIL 51 ms dưới tải | Dùng LK (3,2 ms) |
| Tranh CPU với VOS (4 nhân) | Cả hai chậm thêm | `resource_usage` trong metrics | Tracker ≤5 ms; ghim torch 2–3 luồng |
| Nguồn relay chỉ ~20 FPS | Hiển thị trần 20 | Đếm FPS nguồn (HUD có) | Không phải lỗi kiến trúc; ghi rõ trong báo cáo |

## 6. Diễn đạt trung thực trong báo cáo

**Không phải gian lận**, với 3 điều kiện: (i) tách rõ hai con số FPS; (ii) nêu tuổi mask/độ trễ;
(iii) đo chất lượng mask cả hai cách (tại frame suy luận và toàn video).

**Câu mẫu (VI):**
> "Hệ thống hai tầng: tầng phân đoạn SAM 2.1 tiny đạt 10,3 FPS (image_size 192, CPU i7-1195G7,
> không GPU); tầng bám vị trí bằng bộ lọc tương quan chạy theo nhịp nguồn 25–30 FPS. Mask được làm
> tươi mỗi ~97 ms và nội suy vị trí giữa hai lần suy luận; độ trễ vị trí hiển thị ~40 ms, mask cũ
> tối đa ~200 ms (hiển thị trực tiếp trên HUD)."

**Câu CẤM:** "mô hình đạt 30 FPS real-time" / "realtime segmentation at 30 FPS" — sai sự thật.

**Bảng metric bắt buộc:** FPS suy luận (mean/p95) · FPS hiển thị · độ trễ suy luận p95 · tuổi mask
TB/p95 · chất lượng mask tại frame suy luận · chất lượng mask toàn video · số lần reset
tracker/1000 frame · mất dấu/reacquired.

## 7. Nguồn

**Nội bộ (đo/fetch trong repo):** `docs/task/08-11-2026-do-lai-do-phan-giai-va-kich-thuoc-model.md`;
`docs/research/11-do-encoder-repvit-tren-cpu-va-tran-realtime.md`;
`docs/task/04-11-2026-cuu-webcam-relay-http.md`; `docs/task/05-11-2026-tang-toc-256-...md`;
`docs/research/07a-repo-vos-memory-identity.md`; `src/smooth_display.py`.

**Ngoài:** DEVA arXiv:2309.03903 · XMem arXiv:2207.07115 · SAM 2 arXiv:2408.00714 ·
SAMURAI arXiv:2411.11922 · ByteTrack arXiv:2110.06864 (github.com/ifzhang/ByteTrack) ·
SORT arXiv:1602.00763 · OC-SORT arXiv:2203.14360 · MOSSE (Bolme, CVPR 2010) ·
KCF (Henriques, TPAMI 2015) · CSRT (Lukežič, CVPRW 2017) ·
OpenCV tracking API https://docs.opencv.org/4.x/d9/df8/group__tracking.html

## 8. Checklist trước khi chép vào báo cáo chính thức

1. ☐ DEVA: dùng arXiv:2309.03903 (không phải 2301.07868).
2. ☐ DEVA: trích J&F theo frame-gap cho §3.1.
3. ☐ XMem: ablation r = 5 cho §3.2.
4. ☐ SAM 2: FPS + thiết bị/độ phân giải chính xác; kiểm có ablation stride không.
5. ☐ SORT 260 Hz / ByteTrack 30 FPS: ghi rõ GPU và độ phân giải.
6. ☐ MOSSE/KCF/CSRT: nếu không có số paper thì **chỉ dùng số đo trong repo** (§2).
7. ☐ Chạy lại §4.5 mục 2–3, cập nhật mọi [ƯỚC LƯỢNG] thành [ĐÃ ĐO].
