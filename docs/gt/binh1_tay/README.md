# GT gán tay cho `data/binh1.mp4` — việc cần NGƯỜI làm

> ⚠️ **BỘ NÀY ĐANG KHÔNG DÙNG ĐƯỢC (15-11).** Khung người vẽ bị lệch ~80 px lên trên và cắt mất phần
> nhãn chai ⇒ chấm ra mIoU ~0,03–0,08 là **đo sai vùng**, không phải model bám kém. Bộ đang dùng để
> trích số là `docs/gt/binh1_hopbao` (**hộp bao**, hộp dựng từ ngưỡng màu nhãn tím + sửa tay 1 frame).
> Muốn có mIoU phân đoạn thật thì quay lại đúng quy trình dưới đây (tô **silhouette**).

> Mục đích: có **mIoU trên video THẬT**. Mọi số "chất lượng" khác trong repo (`drift_iou`,
> `stability`) chỉ là **độ tự nhất quán**, không nói được "bám đúng hay không" (AGENTS §6).

## Bạn cần làm: tô 12 ảnh (≈ 15–25 phút)

Mỗi frame có 1 ảnh gốc và 1 khung đen cùng kích thước:

| Mở để xem | Tô vào |
|---|---|
| `frames/frame_000002.png` (ảnh gốc **720×1280**, quay dọc) | `gt_000002.png` (KHÔNG còn — đã xoá) |

Quy tắc duy nhất: **vùng nào là CHAI thì tô TRẮNG (bất kỳ màu sáng), phần còn lại để ĐEN.**
Script chấm đọc "pixel > 0 là vật" ⇒ tô màu gì cũng được, miễn nền đen.

Danh sách 12 frame: **2, 12, 22, 32, 42, 52, 62, 72, 82, 92, 100, 106**
(`index.json` là nguồn sự thật; giữ nguyên tên `gt_<6 chữ số>.png`).

Cách nhanh trên Windows (chọn 1):
1. **Paint.NET / Photoshop / GIMP**: mở `frames/frame_XXXXXX.png` → thêm layer mới → tô trắng vùng
   chai → lưu layer thành `gt_XXXXXX.png` (PNG, cùng 1280×720, nền đen).
2. **Cách "lười" mà vẫn đúng**: mở ảnh gốc + một canvas đen cùng cỡ (720×1280), tô tay bằng bút
   cứng/cọ to — sai lệch 1–2 px không đáng kể so với sai lệch của model.

**CẤM**: tô lại theo mask mà SAM 2/ hệ thống đã vẽ (nếu dùng thì phải khai
`"gt_do_model_goi_y": true` trong `index.json`, và khi đó script **từ chối** dùng bộ GT này làm bằng
chứng — vì chấm mIoU trên mask model tự sinh là **đo chính nó**).

Ghi tên người tô vào `index.json` → `"nguoi_gan"` (đang là `"BinhNguyen1912"`; sửa nếu cần).

## Muốn dùng lại bộ này

Bộ này **đã bị vô hiệu hoá** (xoá 12 file `gt_*.png`, `index.json` ghi `dung_duoc: false`) để
`scripts/score_miou.py` **CHẶN** chấm nhầm. Muốn có GT silhouette thật:

```bash
python scripts/score_miou.py label --clip data/binh1.mp4 --ten binh1_silhouette \
    --frames 2,12,22,32,42,52,62,72,82,92,100,106 --nguoi-gan "<tên bạn>" \
    --dang-gt silhouette
# rồi tô ĐẶC vùng chai (không dùng công cụ hình chữ nhật) và chấm theo docs/thuoc-do-bam-dung.md
```

## Đọc kết quả cho đúng

- `GT rỗng` (frame không có chai) ⇒ **không chấm** — nếu chai đã rời khung ở frame 100/106 thì để
  nguyên khung đen, đừng tô bừa.
- Model trả mask rỗng mà GT có chai ⇒ **IoU 0,0** (bám sai thật, không phải "không đo được").
- Đây là **12 frame** của **một clip** ⇒ cấm viết "mIoU trên DAVIS" hay "mIoU cả clip"; phải nói
  "12 frame gán tay trên `binh1`, `image_size 192`, `vos_every 1`".
