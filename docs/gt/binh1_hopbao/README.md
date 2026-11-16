# GT **hộp bao** cho `data/binh1.mp4` (bộ đang dùng để trích số)

- 12 frame: `2, 12, 22, 32, 42, 52, 62, 72, 82, 92, 100, 106`.
- Hộp dựng từ **ngưỡng màu nhãn tím** (HSV) + phần trắng phía trên — **KHÔNG** dùng mask của model;
  người soi 12/12 frame bằng ảnh; frame 62 (chai nghiêng) sửa tay vì ngưỡng màu bắt dính nền.
- `index.json` khai `dang_gt = hop_bao` + `phuong_phap_gt` + `nguon_gt` + `frame_hw`.

## Đọc số cho đúng

- Con số là **IoU(mask, HỘP BAO)**, KHÔNG phải mIoU phân đoạn. Hộp > vật ⇒ **chặn trên ~0,75–0,85**;
  max quan sát được là **0,774** (frame 92), cận trên lý thuyết `max(|vật ∩ hộp|/|hộp|)` **chưa đo**.
- Không phải GT gán tay ⇒ **sai số của hộp chưa đo**. Muốn mIoU phân đoạn thì tô silhouette
  (`docs/thuoc-do-bam-dung.md`, `score_miou.py label --dang-gt silhouette`).

## Lệnh chấm (mask model đã có trong `data/masks_binh1_192_2026-11-15/`)

```bash
python scripts/score_miou.py score --gt docs/gt/binh1_hopbao \
    --pred-dir data/masks_binh1_192_2026-11-15 \
    --out data/miou_binh1_hopbao_2026-11-15_metrics.json
# exit 1 (cảnh báo "GT hộp bao") là ĐÚNG hợp đồng — xem docs/thuoc-do-bam-dung.md §1.1
```

## Cổng kiểm (từ 16-11, ticket #30)

Vì `dang_gt = hop_bao`, mỗi frame có `hop_bao_xywh = [x, y, w, h]` trong `index.json` và mask GT phải
**đúng là hộp đó**: sai định dạng · vượt biên khung · `số pixel ≠ w*h` · bao thực lệch `(x, y, w, h)`
⇒ **CHẶN (exit 2, không ghi artifact)**. Hộp chạm mép khung (`x+w == W`) là hợp lệ.
Vật đã rời khung thì **bỏ** `hop_bao_xywh` ở frame đó (GT rỗng không chấm, đếm riêng).
Giới hạn: cổng này kiểm **tự nhất quán** (mask ↔ hộp khai), **không** bắt copy-paste: hai frame khai
**cùng một** `hop_bao_xywh` chỉ bị **cảnh báo mềm** ("CÙNG một hộp … copy-paste?"), và hộp chỉnh lệch
1 px thì im lặng. Chi tiết: `docs/thuoc-do-bam-dung.md` §1.2.
