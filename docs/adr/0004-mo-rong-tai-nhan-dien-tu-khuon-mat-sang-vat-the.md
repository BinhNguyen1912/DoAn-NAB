# ADR-0004: Mở rộng tái nhận diện từ khuôn mặt sang VẬT THỂ (đặc trưng thủ công + cascade NCC)

## Bối cảnh

- ADR-0003 đã giải đúng bài toán "chọn mặt A → A rời khung → tự bám lại đúng A" **nhưng chỉ với
  khuôn mặt**: `ReIdSession` lưu embedding SFace 128-D, pha `REACQUIRING` chỉ detect mặt.
- Đề cương không giới hạn đối tượng là người: yêu cầu 2 là **"người dùng lựa chọn đối tượng cần bám bắt"**
  — remote TV, cái ly, chén, bút, chai… Lỗi người dùng báo (27-10): *"focus được nhưng khi mất dấu
  đưa vào lại sẽ không nhận diện được"* — xảy ra đúng với vật **không có mặt**.
- Nguyên nhân: vật không mặt ⇒ `embed_faces` không trả gì ⇒ tập tham chiếu `_refs` rỗng ⇒ LOST vĩnh viễn.
  Hệ thống "đóng băng" đúng như ADR-0003 nhưng **không bao giờ sống lại**.
- Hai hướng đã cân nhắc: (a) thêm mạng embedding học sâu, (b) tự xây đặc trưng + tìm lại hình học.
  Với ràng buộc ADR-0001/0002 (không train lại, chạy CPU trên laptop), chọn (b) và **không thêm model**.

## Quyết định

1. **Thêm "cue" (tín hiệu nhận dạng) là tham số**, không thay thế ADR-0003:
   `reid_cue ∈ {face, object, both}`, **mặc định `face`** ⇒ hành vi cũ **không đổi** (mọi test cũ xanh).
   Thiếu model mặt mà chọn `both` → tự lùi về `object` thay vì chết (CLI `tools/run_live.py`).
2. **Định danh vật thể = đặc trưng thủ công, không học** (`src/appearance.py`):
   - **covariance 5×5** trên `[x_norm, y_norm, B, G, R]` — bắt cấu trúc/hoa văn;
   - **histogram HSV 8×8** trong mask — bắt màu;
   - ghép 2 khối, chuẩn hoá L2, trọng số **0,5 / 0,5** (chưa có số đo biện minh cho lệch);
   - so khớp bằng **cosine**, lưu **deque 8 mẫu**, lấy **max** (cùng lý do ADR-0003: 1 mẫu là trượt).
   - Cổng chất lượng mẫu: **diện tích mask ≥ 600 px²** + cạnh ngắn ≥ 8 px + mask chiếm ≥ 50% ô.
     (Bản đầu đòi **cả 2 cạnh ≥ 24 px** → vật mảnh như bút 120×14 **không bao giờ** lưu được mẫu
     ⇒ re-ID chết ngay từ đầu. Đo thật 29-10.)
3. **Tìm lại bằng cascade 2 tầng** thay vì quét lưới rồi chấm descriptor toàn bộ:
   - tầng 1: **NCC** (`cv2.matchTemplate`, TM_CCOEFF_NORMED) trên frame **thu nhỏ 4×**, mỗi tỉ lệ
     (`0,75 / 1,0 / 1,5`) một suất riêng → **top-K = 20** ô;
   - tầng 2: chấm `object_signature` cho top-K (đắt) → chọn cosine lớn nhất.
   Lý do: đo 348 ô = **323 ms** một frame lost, không dùng được cho demo.
4. **Ngưỡng là tham số phải hiệu chỉnh, hai cổng tách vai**:
   - **cổng CHÍNH = cosine** (`reid_obj_threshold`, mặc định **0,60**, hiệu chỉnh trên clip thật);
   - **cổng PHỤ = NCC** (`reid_obj_ncc_min`), **mặc định TẮT (0,0)**. Bật khi vật **ít texture-màu**
     (chai đen): đo 27-10 hai vật đen **khác nhau** cho cosine **1,000** (mù hoàn toàn) nhưng NCC 0,897.
     Khi bật, khoảng dùng được là **0,35–0,6**; **0,70–0,75 là SAI** (đo thật: 6/17 ca đúng có NCC < 0,70).
5. **Chống "bám nhầm nền rồi kẹt vĩnh viễn"** (ticket 13) — 3 cổng bắt buộc, mặc định BẬT:
   - `lost_score_threshold` = 0,0: mask **không rỗng** nhưng score ≤ 0 **vẫn là mất dấu**
     (SAM 2 "tưởng tượng" mask: đo được 782 px với score **−4,98**);
   - `reid_reacquire_confirm` = 2: ứng viên phải khớp **cùng một chỗ 2 frame liên tiếp**;
   - `reid_verify_frames` = 2: sau khi bám lại phải kiểm chứng; mask mới không giống vật →
     `engine.reset()` + về LOST, **giữ** ký ức vật (mẫu tham chiếu không bị xoá).
6. **Ghi bằng chứng vào metrics**: thêm cột `ncc` (và `state`, `reid_score` từ ADR-0003) để hiệu chỉnh
   offline bằng `scripts/calibrate_reid.py` — ngưỡng phải có **nhà đo**, không đổi bằng tay.

## Lý do

- **Không thêm dependency, không train**: giữ nguyên triết lý ADR-0001 (đóng góp của đồ án là hệ thống
  + ngưỡng + đánh giá), và ADR-0002 (trung thực về hiệu năng CPU).
- **Bù trừ điểm yếu của nhau**: covariance mạnh ở "cùng màu khác hoa văn" (cosine 0,061), histogram mạnh
  ở "khác màu" (0,382) — đo tại `docs/research/06` §4.2, không phải suy đoán.
- **Nhẹ**: `object_signature` **2,9 ms/vùng**, bộ nhớ **8 vector + 1 template ảnh cắt**; không ảnh hưởng
  FPS lúc TRACKING (chỉ chấm 1 vùng/frame), chỉ đắt ở pha tìm lại.
- **Tách vai cổng cosine / NCC**: đã có dữ liệu thật bác bỏ việc dùng NCC làm cổng chính (chặn 6/17 ca đúng);
  NCC chỉ có nghĩa khi màu+hoa văn không phân biệt được (vật đen đặc).
- **Ba cổng chống kẹt** không thể bỏ: mỗi cổng sinh ra từ một ca thật đã quan sát, không phải phòng xa.

## Bằng chứng đo (máy hiện tại: i7-1195G7, CPU, frame 1280×720)

| Kiểm chứng | Số đo |
|---|---|
| Tìm lại khi mất dấu (quét lưới 379 ô) | **845 ms** → cascade: NCC 4,6 ms + top-20 → **23,8 ms** (**~35×**) |
| Chi phí `object_signature` mỗi vùng | **2,9 ms** |
| Cùng vật, dịch nhẹ (fixture) | cosine **1,000** ✅ |
| Cùng màu, **khác hoa văn** | **0,581** ✅ (tách được) |
| **Khác màu**, cùng hoa văn | **0,327** ✅ |
| Hai vật giống y hệt | **1,000** ❌ — đúng dự đoán, ca này chỉ **thời gian** giải được (không có cue nào tách nổi) |
| Vật đen đặc: cùng vật / vật đen khác / vật đen có nhãn trắng | NCC **1,000 / 0,897 / 0,394** (cosine cho 1,000 cả 3 ⇒ mù) |
| Hiệu chỉnh 2 clip thật (17 ca đúng + 1 ca sai) | cosine: sai cao nhất **0,899 >** đúng thấp nhất **0,770** ⇒ **KHÔNG tách được**; ncc: sai cao nhất **0,279 <** đúng thấp nhất **0,415** ⇒ tách được, điểm giữa **0,35** |
| Ca bám nhầm nền (ticket 13, fixture) | f12 mask 782 px, score **+19,40** (giả), reid 0,50 → bị 3 cổng loại; f19 bám lại đúng, reid **0,94** |

**Diễn giải quan trọng:**

- **cosine một mình không đủ** (ca sai 0,899 > ca đúng 0,770) ⇒ phải có cổng thứ hai, nhưng cổng thứ hai
  (NCC) **cũng không đủ một mình** (0,70 chặn 6/17 ca đúng) ⇒ **hai cổng phải tách vai**, đúng như Quyết định 4.
- Hai vật giống hệt nhau (cosine 1,000) là **giới hạn đã biết**, không phải bug: cần ràng buộc thời gian
  (vị trí/quỹ đạo) — ghi vào hạn chế của báo cáo, không hứa hơn.

## Các lựa chọn đã xét

| Phương án | Đánh giá |
|---|---|
| **A. Đặc trưng thủ công (covariance + HSV hist) + cascade NCC** | **Chọn.** 2,9 ms/vùng, không dep, không train, có số đo bù trừ rõ ràng. |
| **B. Mạng embedding học sâu có sẵn** (`deep-person-reid` MIT, `fast-reid` Apache-2.0) | Chính xác hơn cho "cùng loại vật khác cá thể", nhưng nặng hơn, cần onnxruntime/torch model mới. **Để v2** (xem `docs/research/07c`). |
| **C. `boxmot`** | **Loại**: **AGPL-3.0** (copyleft) — không dùng làm dependency cho đồ án. |
| **D. Chỉ template matching (NCC)** | Rất nhạy với tỉ lệ/ánh sáng, và NCC ca đúng đã đo chỉ 0,415 ⇒ làm cổng chính là tự bắn chân. **Loại** (giữ làm cổng phụ). |
| **E. Không mở rộng (dừng ở khuôn mặt)** | **Loại**: không đáp ứng yêu cầu 2 của đề cương (chọn *đối tượng* bất kỳ). |

## Hậu quả & rủi ro

- **Giới hạn đã biết**: hai vật giống hệt nhau → cosine 1,000, không phân biệt được (cần cue thời gian);
  vật **đen đặc/ít texture** phải bật cổng NCC; vật **quá nhỏ** (< 600 px² mask) không lưu được mẫu.
- **Ngưỡng phụ thuộc thiết bị** (camera/ánh sáng/khoảng cách): 0,60 cosine và 0,35 NCC là số **hiện có**,
  phải đo lại khi đổi phòng/camera; công cụ đo là `scripts/calibrate_reid.py` (không đổi tay).
- **Còn thiếu số liệu**: chưa có clip chai đen thật để chốt `reid_obj_ncc_min` (0,35 hiện dựa trên 1 ca sai
  "khoá nhầm nền" + 17 ca đúng của clip ly) — ticket 11 vẫn để mở ở mức này.
- **Không đổi**: ADR-0001 (backbone SAM 2.1 tiny + config SAMURAI), ADR-0002 (demo CPU trung thực),
  ADR-0003 (đường khuôn mặt vẫn nguyên, `reid_cue=face` là mặc định).
- **Không có trong phạm vi**: multi-object re-ID, học/online-learning đặc trưng, nhận dạng "cùng loại vật
  khác cá thể" (chai này vs chai kia cùng nhãn).
