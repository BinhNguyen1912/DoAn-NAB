# GT gán tay cho `data/binh1.mp4` — việc cần NGƯỜI làm

> Mục đích: có **mIoU trên video THẬT**. Mọi số "chất lượng" khác trong repo (`drift_iou`,
> `stability`) chỉ là **độ tự nhất quán**, không nói được "bám đúng hay không" (AGENTS §6).

## Bạn cần làm: tô 12 ảnh (≈ 15–25 phút)

Mỗi frame có 1 ảnh gốc và 1 khung đen cùng kích thước:

| Mở để xem | Tô vào |
|---|---|
| `frames/frame_000002.png` (ảnh gốc 1280×720) | `gt_000002.png` (đang **toàn đen**) |

Quy tắc duy nhất: **vùng nào là CHAI thì tô TRẮNG (bất kỳ màu sáng), phần còn lại để ĐEN.**
Script chấm đọc "pixel > 0 là vật" ⇒ tô màu gì cũng được, miễn nền đen.

Danh sách 12 frame: **2, 12, 22, 32, 42, 52, 62, 72, 82, 92, 100, 106**
(`index.json` là nguồn sự thật; giữ nguyên tên `gt_<6 chữ số>.png`).

Cách nhanh trên Windows (chọn 1):
1. **Paint.NET / Photoshop / GIMP**: mở `frames/frame_XXXXXX.png` → thêm layer mới → tô trắng vùng
   chai → lưu layer thành `gt_XXXXXX.png` (PNG, cùng 1280×720, nền đen).
2. **Cách "lười" mà vẫn đúng**: mở cả 2 ảnh cạnh nhau (ảnh gốc + khung đen), tô tay bằng bút
   cứng/cọ to, không cần viền đẹp — sai lệch 1–2 px không đáng kể so với sai lệch của model.

**CẤM**: tô lại theo mask mà SAM 2/ hệ thống đã vẽ (nếu dùng thì phải khai
`"gt_do_model_goi_y": true` trong `index.json`, và khi đó script **từ chối** dùng bộ GT này làm bằng
chứng — vì chấm mIoU trên mask model tự sinh là **đo chính nó**).

Ghi tên người tô vào `index.json` → `"nguoi_gan"` (đang là `"BinhNguyen1912"`; sửa nếu cần).

## Sau khi tô xong — 2 lệnh để kiểm

```bash
./run miou                      # in quy trình
python scripts/score_miou.py score --gt docs/gt/binh1_tay \
    --pred-dir data/masks_binh1_192_2026-11-15 --check-index    # phải ra "hợp lệ"
```

`--check-index` hiện báo `12 cảnh báo GT toàn đen` — đúng, vì chưa tô. Sau khi tô, phải còn **0 cảnh báo**.

## Rồi chấm điểm (agent làm, ~5 s)

```bash
python scripts/score_miou.py score --gt docs/gt/binh1_tay \
    --pred-dir data/masks_binh1_192_2026-11-15 \
    --out data/miou_binh1_tay_2026-11-15_metrics.json
```

Mask của model đã có sẵn trong `data/masks_binh1_192_2026-11-15/` (sinh bằng
`tools/live_worker.py --image-size 192 --vos-every 1 --dump-mask-frames "2,12,…,106"`, ô chọn
**`300,275,150,410`** — ô CHUẨN cho chai `binh1` theo `docs/demo-clip-va-o-chon.md`;
`manifest.json` ghi `image_size` hiệu lực = **192**, `cau_hinh_lech = []`).

> ⚠️ Đừng dùng `288,287,431,734` (ô xuất hiện trong CSV drift và trong bảng cấu hình 14-11/15-11) làm
> **prompt**: ô đó là ô **LAN TRUYỀN** giữa clip (431×734, phủ chai + tay + thân người), dùng nó làm
> prompt thì model bám luôn tay/áo — đã gặp 15-11 (mask 168k px thay vì ~40k px).

## Đọc kết quả cho đúng

- `GT rỗng` (frame không có chai) ⇒ **không chấm** — nếu chai đã rời khung ở frame 100/106 thì để
  nguyên khung đen, đừng tô bừa.
- Model trả mask rỗng mà GT có chai ⇒ **IoU 0,0** (bám sai thật, không phải "không đo được").
- Đây là **12 frame** của **một clip** ⇒ cấm viết "mIoU trên DAVIS" hay "mIoU cả clip"; phải nói
  "12 frame gán tay trên `binh1`, `image_size 192`, `vos_every 1`".
