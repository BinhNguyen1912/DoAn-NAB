# GT **silhouette** cho `data/binh1.mp4` — việc cần NGƯỜI (≈ 20–30 phút)

> Đích: **mIoU phân đoạn** trên video thật (thứ duy nhất trả lời "bám có ĐÚNG không"). Hiện repo mới
> có **IoU với hộp bao** = 0,6464 (`docs/gt/binh1_hopbao`) — con số đó bị chặn trên ~0,75–0,85 vì GT
> là hộp, nên KHÔNG dùng để nói "chất lượng phân đoạn".

## Đã chuẩn bị sẵn

- 12 frame (giữ y hệt bộ hộp bao để **so trực tiếp**): `2, 12, 22, 32, 42, 52, 62, 72, 82, 92, 100, 106`.
- `frames/frame_XXXXXX.png` — ảnh gốc **720×1280** (quay dọc) để nhìn.
- Bạn cần tạo: `gt_XXXXXX.png` — PNG **nhị phân**, **cùng cỡ 720×1280**, **nền đen / vùng chai TRẮNG**.

## Cách nhanh nhất: công cụ vẽ trong trình duyệt (không cần cài gì)

Mở `docs/gt/ve_gt.html` bằng **double-click** (Chrome/Edge):

1. Bấm **“Chọn 12 frame”** → chọn cả 12 file trong `docs\gt\binh1_silhouette\frames\`
   (hoặc bấm **“…hoặc chọn cả thư mục”** rồi chọn thư mục `frames`).
2. **Tô ĐẶC** vùng chai bằng cọ (mặc định 48 px; `[` `]` đổi cỡ, `E` = tẩy, `Ctrl+Z` hoàn tác,
   `Tab`/`←` `→` chuyển frame). Nét được nhớ theo từng frame.
   - Công cụ này **không có** công cụ hình chữ nhật — đúng ý: lần trước vẽ bằng hình chữ nhật (chỉ ra
     viền, lệch 80 px) làm mIoU ra 0,03.
   - Frame nào **không có chai** trong khung thì **để trống** (khung đen) — frame đó sẽ không được chấm.
3. Bấm **“Tải TẤT CẢ PNG”** → 12 file `gt_XXXXXX.png` vào thư mục Downloads →
   **chép vào `docs\gt\binh1_silhouette\`** (cùng chỗ với `index.json`).
4. Kiểm: `python scripts/gt_check_silhouette.py --gt docs/gt/binh1_silhouette`
   → phải ra `không thấy dấu hiệu viền rỗng / hình chữ nhật / copy-paste`.

## Cách khác: Paint.NET / GIMP / Photoshop

Mở `frames/frame_XXXXXX.png` → thêm layer → tô trắng vùng chai → xuất `gt_XXXXXX.png`
(**xuất cả ảnh ở cỡ gốc**, nền đen). Nếu công cụ hỏi có giữ alpha thì **bỏ alpha** (ảnh 4 kênh vẫn
đọc được — code đã bỏ kênh alpha — nhưng 3 kênh là an toàn nhất).

## Bộ kiểm sẽ bắt gì (đừng bỏ qua)

| Dấu hiệu | Ngưỡng | Nghĩa |
|---|---|---|
| `lấp đầy` = diện tích / diện tích khung bao | `< 0,45` | gần như **VIỀN RỖNG** ⇒ phải tô đặc |
| `lấp đầy` | `> 0,95` | gần như **HÌNH CHỮ NHẬT ĐẶC** ⇒ nếu đúng ý thì khai `dang_gt = hop_bao` |
| diện tích / diện tích frame | `> 0,35` | có thể đã **tô cả nền** |
| IoU giữa 2 frame | `> 0,98` | **copy-paste** GT giữa hai frame (vật có di chuyển) |
| thiếu file / sai cỡ | — | **CHẶN** chấm (mã 2) |

## Sau khi xong (agent chạy, ~5 giây)

```bash
python scripts/score_miou.py score --gt docs/gt/binh1_silhouette \
    --pred-dir data/masks_binh1_192_2026-11-15 \
    --out data/miou_binh1_silhouette_2026-11-15_metrics.json
```

Mask model đã có sẵn (`data/masks_binh1_192_2026-11-15/`, @192, `vos_every 1`, prompt
`300,275,150,410`) — cùng 12 frame, nên **so được trực tiếp** với IoU-vs-hộp-bao 0,6464.

**Cấm**: tô lại theo mask mà hệ thống đã vẽ (nếu dùng thì phải khai `gt_do_model_goi_y = true` và
`score_miou` sẽ **từ chối** dùng làm bằng chứng — chấm trên mask model tự sinh là đo chính nó).
