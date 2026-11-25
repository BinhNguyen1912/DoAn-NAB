# Plan 25-11-2026 — Có nên cho hệ "tự hết nghi" (trở lại box đỏ) không, và bằng cơ chế nào?

> Plan theo **AGENTS §9.2**. Mở vì việc > 4 h và chạm đúng vết xe 21-11 (tự bỏ nghi ⇒ vẽ mask SAI
> 65 frame). Người mở: agent chính (sau khi người dùng báo *"nghi cũng đúng vật, chưa cập nhật thành
> box đỏ"* ở phiên `data/demoip_1125-100334`).

## 🎯 Câu hỏi cần quyết
Có nên thêm đường **tự động** đưa `chua_xac_minh → ok` (vẽ mask tô + ô đỏ + quỹ đạo trở lại) trên
đường `--no-reid` không? Nếu có thì bằng **bằng chứng nào**, với tham số nào, và **không** được vi
phạm: (a) 7/7 ca báo ĐÚNG đã dán nhãn phải giữ; (b) không được tuyên bố "đã xác minh danh tính" khi
chưa có bằng chứng danh tính; (c) mọi số phải tái lập bằng replay trên CSV đã commit.

Bối cảnh đo được trước khi mở plan (`data/hud_jitter_2026-11-25_metrics.json`, dò màu trên video HUD):
ô **nét đứt** chiếm **18,0 % / 34,3 % / 60,1 %** thời gian ở 3/4 phiên; riêng phiên bị phàn nán:
`nghi` 9 frame, `chua_xac_minh` **33 frame = 20,6 %**, `reselect_n = 0` (không ai bấm `c`).

## 🧭 Ba góc nhìn (vòng 1 — độc lập, không biết nhau)

### A. Chất lượng & số đo (đã trả lời)
- **A (mask-vs-mask, re-prompt SAM)** — **pilot n=15 re-prompt, 3 frame**: ô lệch **60 px** trên
  **cùng một vật** cho `IoU_ref = 0,908 / 0,270 / 0,119`; lệch ≥120 px cho 0,000–0,378 ⇒ **không tồn
  tại τ**. Nghiêm trọng hơn: lớp "vẫy nhanh" đúng là lớp có ô trễ lớn (227 px) ⇒ A **cũng** cho ~0
  trên ca cần xoá nghi. Re-prompt giá **116–343 ms** (≈ 2× bước VOS) và `engine.start()` **reset ký ức**
  (`src/tracker_engine.py:216`) ⇒ phải dựng engine thứ hai.
- **B (round-trip hình học)**: `k=2, θ=0,3×size` ⇒ xoá **2/29** lần báo, **mất 0/7** ca đúng, **không**
  xoá ca báo oan đã xác nhận (`085815#47`, `d/size = 1,16`); phiên `100334`: ẩn **9→1**, chưa **33→0**.
  `k=8` bắt đầu xoá ca thật (`144057` 37/48 → 28/18).
- **KHÔNG** dùng `track_cos`/`stability`/`drift_iou` làm cổng (đã có bằng chứng âm tính); **KHÔNG**
  chấm A trên 8 ca nhãn bằng CSV (CSV không có mask ⇒ mọi "IoU" tính từ CSV là IoU **hộp**).
- Nếu chỉ chọn 1 việc: **dựng "băng thử 3 lớp" + chốt nhãn bằng ảnh** rồi mới chọn cơ chế.

### B. Sản phẩm & bằng chứng bảo vệ (đã trả lời)
- **Đính chính quan trọng**: ở phiên bị phàn nán, vùng `chua_xac_minh` **có lúc SAI thật** — ảnh
  t=35,0 s viền mask trùm **cả khung cửa/tường**, t=39,0 s ô **lệch trái ~90 px** khỏi remote ⇒ tự
  "về box đỏ" lúc đó là **vẽ sai**. Đồng thời f94–f106 (13 bước) ô bám khung cửa **mà cổng im lặng**
  ⇒ khiếm khuyết nặng hơn là **trôi dần**, không phải báo oan.
- **Bác B nếu chỉ có B**: N=16 kiểu "ổn định rồi tự tin lại" (24-11 D1) đổi 119 frame sang "tin cậy"
  mà 97/119 nằm trong phiên đang sai.
- Đề xuất **C+**: giữ máy trạng thái, sửa **lớp sản phẩm** (HUD 3 mức phân biệt được, câu chữ nói
  đúng cơ chế "vùng bám nhảy bất thường" thay vì "nghi đổi đối tượng", drill bấm `c`, kịch bản khoá).
  Kèm bảng bằng chứng + Q&A + danh sách "cấm trích". Nếu chỉ chọn 1 việc: **diễn tập khoá kịch bản**.
- P2 phát hiện thêm (đã vá): `run_info` **thiếu** `box_smooth_tau_ms` ⇒ cấu hình hiển thị không tái lập.

### C. Độ bền & hiệu năng
- *Chưa trả lời tại thời điểm chốt.* Không chặn quyết định vì phương án được chọn (B) là **luật thuần
  số học trong state machine đã có test**, không thêm lời gọi model, không thêm luồng.

## ⚔️ Tranh chấp (vòng 2 — phản biện chéo)

| Điểm tranh chấp | A (chất lượng) | B (sản phẩm) | Chốt |
|---|---|---|---|
| Có nên tự hết nghi? | Có, bằng round-trip; đo được, rẻ, không mất ca đúng | **Không** nếu là "tự tin lại sau N bước"; nhưng **có** nếu là bằng chứng hẹp | **Đồng ý cả hai**: chỉ nhận luật **round-trip**, vì nó không nói "đã xác minh danh tính" mà nói *"ta chưa từng mất vật, chỉ rung một bước"* |
| A (mask-vs-mask) có dùng được? | **Không** (pilot: ô lệch 60 px đã 0,119–0,908) | **Không** (đã có `verify_cos` PASS 0,87 trên vùng SAI) | **Bác A**, ghi bằng chứng để không mở lại |
| Vùng `chua_xac_minh` có đúng không? | f140 ảnh cho thấy ô nét đứt **ôm sát remote** ⇒ khiếu nại đúng | t=35/t=39 ảnh cho thấy vùng đó **có tường** ⇒ đừng tô đặc | **Cả hai đúng**: round-trip trả lại box đỏ (người dùng thấy đúng ý), **nhưng** chất lượng mask/ô vẫn là khiếm khuyết đã biết ⇒ phải nói thẳng trong báo cáo, không bán như "đã xác minh" |
| Tham số | `k=2` an toàn, `k=8` xoá ca thật | phải **đăng ký trước** | **`k=2, θ=0,3`**, ghim bằng test |

## ✅ Quyết định
- **Chọn:** thêm luật **ROUND-TRIP** vào `IdentityWatch` (`round_trip_steps=2`,
  `round_trip_theta=0,3`), bật **mặc định** cho cả 3 đường (CLI `--smooth`, `run_interactive`, worker
  web) + ghi `round_trip_steps` vào `run_info`; cờ `--round-trip-steps 0` để tái lập phiên cũ.
  **Không** thêm lời gọi model, **không** đụng ngưỡng cổng nhảy.
- **Vì sao (số đo, replay trên chính code này):**
  - phiên bị phàn nán `100334`: `nghi` **9 → 1**, `chua_xac_minh` **33 → 0**, vẫn **báo đúng f114**;
  - 10 phiên đóng băng có nhãn (1 509 frame): **120 → 120** frame bị giảm hiển thị (**không đổi một
    frame nào**);
  - **7/7** ca báo ĐÚNG giữ nguyên; ca báo OAN đã xác nhận `085815#47` **vẫn báo**.
- **Bác:** (1) **A — mask-vs-mask**: pilot cho thấy ô lệch 60 px trên cùng vật đã 0,119–0,908 ⇒ không
  tồn tại τ, lại thêm ~210 ms/lần và làm nhiễm/reset bộ nhớ SAM 2; (2) **"ổn định N bước rồi tự tin"**:
  đã bác 24-11, nay thêm bằng chứng ảnh t=35/39 của chính phiên này; (3) **nới ngưỡng cổng nhảy**:
  7 luật thay thế chỉ giữ 1/7–6/7 ca đúng.
- **Giới hạn phải nói khi trích (cấm bán như "đã sửa báo oan"):** round-trip **không** xoá được ca báo
  oan đã xác nhận; nó **không** xác minh danh tính; và mask/ô vẫn có thể trôi trên nền cùng tông
  (f94–f106 của chính phiên này) — đó là ticket riêng.
- **Tiêu chí nghiệm thu (có SỐ):**
  - [x] replay `data/demoip_1125-100334_metrics.csv`: `(ẩn, chưa) = (1, 0)` khi `k=2`, `(9, 33)` khi `k=0`
  - [x] 10 phiên `data/eval_gate_config_list.json`: tổng frame bị giảm hiển thị **120** ở cả `k=0` và `k=2`
  - [x] 7/7 `CA_DUNG` giữ; `CA_SAI` `085815#47` vẫn báo
  - [x] `k=8` phải **đổi** `144057` (37/48 → 28/18) — khoá để không ai nâng tham số mà tưởng vô hại
  - [x] `--round-trip-steps 0` = hành vi trước 25-11; headless ghi `None`… (`_round_trip_steps` luôn
        trả số, ghi vào `run_info` cả khi headless vì cổng chỉ dựng ở đường tương tác)
  - [x] `./run lint` xanh + `./run test` **2 081** xanh

## 📌 Việc tách ra ticket
- [ ] **Trôi dần không cảnh báo** (bám tường/khung cửa 13 bước ở `100334`, 109,6 px/bước ở ticket 52) —
      cần mô hình chuyển động (Kalman/LK) hoặc siết ô về khối mask lớn nhất; **chưa đo được** nên không
      làm trước demo.
- [ ] **HUD 3 mức phân biệt được** (trắng liền / vàng đứt / đỏ) + câu chữ đúng cơ chế (C+ của cố vấn B).
- [ ] **Người thứ 2 dán nhãn** 8 ca cổng (điều kiện để TRÍCH "7/7" trong báo cáo).
- [ ] **Bộ eval có mask** cho ca "hoán vật tại chỗ" (repo **chưa có** clip) — nếu muốn mở lại A.
