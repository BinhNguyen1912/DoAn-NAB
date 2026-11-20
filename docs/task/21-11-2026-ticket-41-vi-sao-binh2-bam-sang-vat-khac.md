# 21-11-2026 · Ticket #41 — vì sao `binh2` bám SANG VẬT KHÁC (f163) và ô co sai (f228)

## 1. Mục tiêu

A/B của ticket #40 cho `iou_min = 0,000` ở **cả 9 lần chạy** vì 2 frame GT (163, 228). Câu hỏi: đó là **ô VOS
đã sai trước khi LK bước** hay **LK kéo sang**, và có "chữa" được bằng cấu hình không?

## 2. Input & cách đo

- `tools/live_worker.py --source data/binh2.mp4 --bbox 330,330,150,360 --vos-every 3 --image-size 192
  --lk-max-mad 100 --dump-shown-csv … --stop-after-frames 275`.
- `drift_samples.csv` (tự sinh) có **cả hai** ô ở mỗi lần VOS: `bbox_*` = ô **VOS**, `hien_thi_*` = ô
  **ĐANG HIỂN THỊ** (LK hoặc ô đóng băng) ⇒ tách được "VOS sai" khỏi "LK kéo sai" **bằng số**, không suy từ code.
- Ảnh kiểm: `docs/media/gt/binh2_loi_base_vos_f163_f178_f228.jpg`.

## 3. Kết quả — ba nguyên nhân KHÁC NHAU, không cái nào là `max_mad`

| frame | ô **VOS** | ô **hiển thị** | GT (người tô) | IoU(VOS, GT) | kết luận |
|---|---|---|---|---|---|
| 162 (bước VOS ngay trước GT 163) | `412,299,518,557` | `405,260,522,644` | `179,314,304,637` | **0,000** | **VOS đã sai TRƯỚC khi LK bước** — ô VOS nằm trên **chai ĐEN**, GT là **chai TRẮNG** |
| 163 | — | `405,260,522,644` | `179,314,304,637` | — | `lk_ok = true`, `n_diem 47/64`, `ly_do = ok_shift` ⇒ **LK làm đúng việc của nó** trên một base sai |
| 180–216 | `0,0,0,0` | (không vẽ ô) | — | — | **ĐÚNG**: vật đã rời khung (ảnh f178: hai tay trống, cả hai chai ngoài khung) |
| 222 | `126,434,157,502` (31×68) | — | — | — | VOS trả ô nhỏ lệch khi vật **vào lại** khung |
| 228 | — | `129,431,175,498` (30×65) | `20,240,155,582` | — | `lk_ok = false` ⇒ hiển thị ô rác; GT là chai trắng ở **mép trái**, to (135×342) |
| 234–261 | `352,222,485,675` … | `415,274,548,727` | `422,221,587,730` (f261) | — | bám lại đúng chai trắng (IoU 0,796) |

⇒ **Nguyên nhân là VOS, không phải ngưỡng**: ở f162 ô VOS **đã** ở vật khác trước khi LK chạy. Đổi
`max_mad`/`lk_scale` **không thể** chữa (đúng như #38/#40 đã chốt: hai tham số đó chỉ ảnh hưởng *bước giữa
hai lần VOS*).

### Tỉ lệ "bám sang vật khác" (định nghĩa tường minh của ticket)

`IoU(ô, GT) < 0,1` **VÀ** tâm ô cách tâm GT > **1 chiều rộng GT**:

| clip | cấu hình | số frame | frame vi phạm |
|---|---|---|---|
| `binh2` | `1,5` | **1/8** | 163 (IoU 0,000 · lệch tâm 246 px · GT rộng 125) |
| `binh2` | `100` | **2/8** | 163 (0,000 · 274 px) · 228 (0,017 · 160 px) |
| `binh1` | 1,5 và 100 | **0/7** | — |

### Ô demo có cắt vật không? (giả thuyết bị bác)

Ô `330,330,150,360` chỉ phủ **65 %** chiều cao chai (GT frame 0 = `334,319,492,887`, cao 568 px). Thử ô đúng
`334,319,158,568` (1 lần chạy, `max_mad 100`): IoU trung bình 8 frame **0,5483** vs **0,5660** của ô cũ ⇒
**không cải thiện**, f163 vẫn 0,000 và f228 vẫn 0,013 ⇒ **cắt đuôi vật KHÔNG phải nguyên nhân** của hai
frame hỏng. (Vẫn nên sửa ô demo cho đúng vật — xem AGENTS §6 về ô chọn sai.)

## 4. Ảnh hưởng tới báo cáo/demo

1. **Mọi trung bình IoU trên `binh2` phải nêu cửa sổ frame.** Trong `0:160` (cửa sổ demo của repo,
   `docs/demo-clip-va-o-chon.md`) vật còn trong khung; 163 và 228 nằm trong đoạn **vật rời/vào khung**.
2. **Không** được trình bày "hybrid bám được vật ra/vào khung": đo được là **KHÔNG** — vật vào lại thì VOS
   bám vào **mặt người** (f228) chứ không phải chai.
3. Con số "IoU 0,45–0,57 trên `binh2`" thấp hơn `binh1` (0,59–0,60) **không phải** vì cấu hình: nó bị kéo bởi
   2 frame này (bỏ 2 frame: `1,5` → 0,5931 · `100` → 0,7500, log #40 §4B).

## 5. Đề xuất (không làm trong ticket này)

- **Ẩn ô khi VOS mất dấu** thay vì hiển thị ô rác/lệch: hiện `(0,0,0,0)` đã bị `_bbox_hop_le` loại (tốt), nhưng
  ô **nhỏ bất thường** (31×68 khi vật thật 135×342) vẫn được vẽ ⇒ thêm cổng "diện tích mask so với EMA".
- **Cơ chế nhận lại vật** ở đường live: `src/reid.py` là re-ID **khuôn mặt** (SFace) và **không** được
  `src/live_tracking.py` dùng (grep: 0 tham chiếu) ⇒ đường live **không có** khả năng nhận lại vật sau khi rời
  khung. Đây là khoảng trống so với đề cương mục 4 ("chịu được che khuất") và mục 2 ("vật ra/vào khung") ⇒
  ticket riêng.

## 6. Kiểm máy

`./run lint` xanh · không đổi code sản phẩm (chỉ log + 2 ảnh + artifact #40 đã commit). Số VOS/LK ở trên
đọc từ `/tmp/b2vos/drift_samples.csv` của **một** lần chạy (`max_mad 100`, 275 frame); chạy lại cho kết quả
cùng kết luận nhưng **giá trị từng frame sẽ khác** (SAM 2 không tất định — AGENTS §6) ⇒ trích **cơ chế**
(VOS sai trước LK), không trích số lẻ từng frame như hằng số.
