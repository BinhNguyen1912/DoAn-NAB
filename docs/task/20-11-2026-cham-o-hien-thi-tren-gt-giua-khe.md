# 20-11-2026 — Chấm ô hiển thị vs GT NGƯỜI TÔ ở frame GIỮA KHE (`b1b`) — lần đo đầu đúng chỗ

## 1. Mục tiêu

Đo `max_mad` của `LkBoxTracker` ở **đúng chỗ nó có tác dụng**: frame `≡ vos_every-1` — nơi ô hiển thị
**chắc chắn không phải ô của frame VOS** mà là nội suy từ mốc VOS gần nhất. Bộ `b1` cũ (≡ 0 mod 3)
không trả lời được câu này.

## 2. Input

- Clip `data/binh1.mp4` (333 frame, 1280×720), ô chọn `300,275,150,410` (ô **chai**, đúng vật).
- GT người tô: `docs/gt/b1b` — 7 frame `2,32,62,92,182,212,242` (sinh bằng
  `./run gt … --giua-khe --khung 0:110,165:262`, PR #63).
  `index.json` khai `chon_frame = {giua_khe: 12, vos_every: 3, khung: "0:110,165:262"}`.
- Kiểm GT trước khi chấm: mỗi mask **1 blob duy nhất (100 % diện tích blob lớn nhất)**, diện tích
  4,7–25,8 %, `frame_hw 1280×720`; f62 chạm mép trên (`row 0` = 61 px) vì chai bị cắt khung — hợp lệ.
- Dụng cụ: `scripts/ab_o_hien_thi_vs_gt.py` (chấm **ô hiển thị** `--dump-shown-csv` vs hộp GT),
  3 lần/cấu hình chèn kẽ, `--frames 300`, `--image-size 192`, `--vos-every 3`.

## 3. Công việc đã thực hiện

1. Commit bộ GT `docs/gt/b1b` (mask + goiy; `frames/` bị `.gitignore`) — **bắt buộc trước khi chấm**:
   lần chấm đầu ra `git_dirty_code = true` chỉ vì GT còn untracked ⇒ số đo không tái lập được.
2. Chấm lại trên cây sạch hai lần (lần 1 trên cây bẩn để đối chứng độ tái lập).
3. Phân tích **theo từng frame**: lệch X/Y/W/H của ô hiển thị so với hộp GT.

## 4. Output / Kết quả

### 4.1 Hai lần A/B cho HAI phán quyết ngược nhau (đây là kết quả quan trọng nhất)

> **Dòng 1 KHÔNG tái lập được**: đó là phiên trên cây **bẩn**, artifact của nó đã bị phiên 2 ghi đè
> cùng đường dẫn (xem §8). Số của dòng 1 KHÔNG tồn tại trong tệp nào của cây — chỉ dùng làm đối chứng
> "hai phiên lật phán quyết", không trích như số đo tái lập được.

| Lần | Cây | 1.5 (`iou_mean`) | 6.0 | chênh | ngưỡng nhiễu | phán quyết |
|---|---|---|---|---|---|---|
| 1 | bẩn (`git_dirty_code=true`), **artifact đã mất** | 0,6232 ± 0,0342 | 0,6431 ± 0,0332 | **+0,020** | 0,0342 | KHÔNG phân biệt được |
| 2 | **sạch** (`891f4f5`, `git_dirty_code=false`) | 0,6015 ± 0,0045 | 0,6302 ± 0,0218 | **+0,029** | 0,0218 | "6.0 tốt hơn 0,029" |

⇒ **Cấm kết luận theo một lần**: cùng clip, cùng GT, cùng 3 lần/cấu hình mà ngưỡng nhiễu đổi 0,0342 →
0,0218 và phán quyết lật. Dấu chênh **nhất quán** (6.0 nhích hơn 0,020–0,029) nhưng độ lớn **nằm
trong dải nhiễu giữa phiên** (chính `iou_mean` của 1.5 đổi 0,0217 giữa hai lần). Kết luận trung thực:
**chưa chứng minh được `max_mad` 6.0 tốt hơn 1.5**, và 1,5 vẫn giữ vì tail ổn định hơn
(`iou_min` 0,3835 ± **0,0007** so với 0,3863 ± 0,0009 — như nhau; lần 1 có outlier 0,145 ở 6.0).

### 4.2 Phát hiện BỀN VỮNG (không phụ thuộc lần chạy): `lk_ok`

| `max_mad` | `lk_ok_frac` (3 lần) | nghĩa |
|---|---|---|
| 1,5 (mặc định) | **0,048 ± 0,083** (2/3 lần = **0,000**) | ở frame giữa khe LK **từ chối gần như 100 %** ⇒ ô hiển thị là **ô ĐÓNG BĂNG** của lần VOS trước, KHÔNG phải nội suy |
| 6,0 | 0,524 ± 0,082 | LK nhận ~52 % mẫu ⇒ ô **có** dịch chuyển |

Đây là số phải đưa vào báo cáo thay cho câu "hybrid nội suy ô ở giữa khe": với cấu hình mặc định,
trên clip này, **nội suy gần như không xảy ra** ở các frame giữa khe (chuyển động chai quá nhanh so với
ngưỡng `max_mad 1.5`).

### 4.3 Sai số nằm ở ĐÂU (lệch ô hiển thị − hộp GT, px, lần chạy 1)

| frame | IoU 1.5 | IoU 6.0 | ΔX | ΔY | ΔW | ΔH | LK(6.0) |
|---|---|---|---|---|---|---|---|
| 2 | 0,579 | 0,565 | +15 | **+128** | −30 | **−132** | ✔ |
| 32 | 0,582 | **0,783** | −19 | +24 | −22 | −45 | ✔ |
| 62 | 0,579 | 0,578 | +39 | +52 | −23 | −5 | ✘ |
| 92 | **0,383** | 0,387 | +37 | **−122** | +1 | −19 | ✘ |
| 182 | 0,753 | **0,816** | −7 | +22 | −17 | −61 | ✔ |
| 212 | 0,504 | 0,505 | **+111** | +30 | **−50** | **−91** | ✘ |
| 242 | 0,867 | 0,869 | +5 | +8 | −7 | −35 | ✔ |

Đọc bảng: ô hiển thị **luôn hơi nhỏ hơn** GT (ΔW −7…−50, ΔH −5…−132) và lệch tới **111–128 px** ở
frame xấu. Khi LK bật, nó **dịch** ô nên chữa được lệch dịch (f32 +0,20; f182 +0,06) nhưng **không
chữa được lệch kích thước** — `LkBoxTracker` trả `(x+dx, y+dy, w, h)`, giữ nguyên `w,h`
(`src/light_tracker.py`: `bbox = (x+dx, y+dy, w, h)`), nên lệch tỉ lệ (vật ra gần/xa) là **trần cứng**.
f2/f92/f212 lệch Y 122–128 px đúng là lệch **kích thước** (ô thiếu 132 px chiều cao) chứ không phải lỗi
dịch.

## 5. Vấn đề & cách xử lý

- **GT untracked làm bẩn số đo**: lần chấm đầu ra `git_dirty_code=true` ⇒ không tái lập. Đã commit GT
  (`891f4f5`) rồi chấm lại. Bài học: chấm xong **kiểm `git_dirty_code` trước khi trích số**.
- **Suýt kết luận sai bằng "trần IoU của ô cố định"** (0,708): phép tính đó giả định `w,h` không đổi,
  nhưng VOS **có** cập nhật `w,h` (f212 hiển thị 265×973, không phải 150×410). Đã loại bỏ phân tích đó
  sau khi đọc `hop` thật trong artifact.
- `iou_mean` 0,60–0,63 **chỉ là IoU hộp bao vs hộp GT**, không phải chất lượng mask.

## 6. Next steps

1. **Nội suy cả TỈ LỆ trong `LkBoxTracker`** (hiện chỉ dịch `x,y`, giữ `w,h`): bảng 4.3 cho thấy lệch
   kích thước là nguồn sai số chính ở 3/7 frame. Đây là con đường duy nhất còn lại để **tăng** IoU.
2. A/B `--image-size 192 vs 320` trên chính bộ GT `b1b` (lần đầu đo **độ chính xác** theo `image_size`,
   trước đây chỉ đo `drift_iou`): 192 làm ô thô ⇒ có thể chính là nguồn lệch 111–128 px.
3. Mọi so sánh phải chạy **chèn kẽ trong cùng phiên** (`./run ab` hoặc mở rộng
   `ab_o_hien_thi_vs_gt.py` thành A/B nhiều cấu hình) — mục 4.1 chứng minh so hai phiên là vô nghĩa.

## 7. Tài liệu tham khảo

- `docs/task/20-11-2026-gt-chon-frame-giua-khe.md` (sinh bộ GT `b1b`, 2 vòng review)
- `docs/task/20-11-2026-o-hien-thi-vs-gt-chot-max-mad.md` (4 lần A/B trên bộ `b1` ⇒ giữ `1,5`)
- `docs/thuoc-do-bam-dung.md`
- Artifact: `data/ab_max_mad_b1b_2026-11-20_metrics.json` (đổi tên từ `ab_o_hien_thi_vs_gt_…` — tên cũ
  bị phiên `b1` cùng ngày dùng chung đường dẫn; `git_rev 891f4f5`, `git_dirty_code=false`)
