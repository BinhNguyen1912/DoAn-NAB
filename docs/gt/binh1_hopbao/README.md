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
