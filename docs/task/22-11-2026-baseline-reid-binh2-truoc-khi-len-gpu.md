# Ngày 22-11-2026 — Baseline "nhận lại đúng vật" trên `binh2` (TRƯỚC khi thuê GPU)

> Log theo `AGENTS.md` §2. Đây là **mốc số** để sau này A/B với Cutie trên GPU — không có mốc thì
> mọi câu "tốt hơn" đều là cảm tính (ADR-0002).

## 🎯 Mục tiêu
Đo chất lượng bám + nhận lại của **pipeline hiện tại** (SAM 2 tiny @192, `vos_every=1`, KHÔNG bật
`--reid`) trên clip có **vật rời khung rồi quay lại**, để có mốc so sánh trước khi đổi lõi sang Cutie.

## 📥 Input
- `data/binh2.mp4` — 360 frame, 720×1280, 30 fps (12 s).
- GT tay `docs/gt/binh2_tay/` (silhouette, người gán: Binh), 12 frame:
  `0, 33, 65, 98, 131, 163, 228, 261` (vật có) và `196, 294, 326, 359` (**GT rỗng = vật đã rời khung**).
- Ô chọn suy TRỰC TIẾP từ GT frame 0 (không đoán): mask GT f0 ⇒ `xywh = 334, 319, 158, 568`.

## 🛠️ Lệnh chạy (tái lập được)
```bash
tools/live_worker.py --source data/binh2.mp4 --out-dir /tmp/b2 \
  --bbox 334,319,158,568 --image-size 192 --vos-every 1 \
  --dump-mask-frames 0,33,65,98,131,163,228,261 --dump-mask-dir /tmp/b2/masks \
  --stop-after-frames 360
./run miou score --gt docs/gt/binh2_tay --pred-dir /tmp/b2/masks \
  --out data/miou_baseline_binh2_2026-11-22_metrics.json
```

## 📤 Kết quả (CPU Iris Xe, không GPU rời)
- **mIoU = 0,7644** trên **8 frame** chấm được · `mask_ngoai_gt` = 4,6 % (tệ nhất 20,4 % ở f163).
- Tốc độ phiên: **6,8 FPS** (VOS mỗi frame) ⇒ `vos_every=1` trên CPU không dùng cho live được.
- **Từng frame:**

| frame | 0 | 33 | 65 | 98 | 131 | 163 | **228 (quay lại)** | **261 (quay lại)** |
|---|---|---|---|---|---|---|---|---|
| IoU | 0,685 | 0,793 | 0,782 | 0,758 | 0,758 | 0,750 | **0,776** | **0,814** |

- 4 frame GT rỗng (196, 294, 326, 359) **không chấm** (đúng luật: GT rỗng ⇒ `None`, không phải 0).
- `mIoU_p05 = None` (8 < 30 mẫu — đúng ngưỡng công bố của repo).

## 🐞 Phát hiện quan trọng (làm đổi giả thuyết ban đầu)
- Ở mức GT 12 frame, **SAM 2 streaming vẫn bám được sau khi vật quay lại** (f228 = 0,776 · f261 = 0,814),
  dù **không** bật `--reid`. Nghĩa là "mất dấu rồi không nhận lại" **không** tái hiện được trên các frame
  GT hiện có.
- Nhưng **khoảng trống 164–227 (64 frame) KHÔNG có GT** — mà đúng đó là nơi ticket #42 ghi nhận
  "nhận lại lặp 3 lần (172/175/178)". ⇒ **Chưa đủ dữ liệu để nói hiện tượng đó là bám nhầm hay chỉ là
  dao động của cổng**. Muốn chứng minh phải **tô thêm GT trong 164–260**.
- mIoU 0,75–0,81 (không phải 0,95) phản ánh mask **thiếu diện tích** (`dien_tich_pred` 27k–46k so với
  GT 32k–56k) — tức lỗi hiện tại là **phân đoạn hụt**, không hẳn là bám nhầm vật.

## ⚠️ Hạn chế của số này
- 8 frame chấm được ⇒ **không** kết luận được cho "cả clip"; cấm trích như mIoU của `binh2`.
- Chạy trên cây **bẩn** (`git_dirty_code = true` trong artifact) ⇒ dùng làm mốc nội bộ, không phải số
  công bố.
- Chỉ 1 lần chạy ⇒ **không có `±` nhiễu**; so sánh phải chạy lại ≥ 3 lần (`./run ab`).

## 📌 Việc cần làm tiếp
- [ ] **Tô thêm GT frame 164–260** (`./run gt --clip data/binh2.mp4 --ten binh2_tay2 --frames 170,180,190,200,215,230,250`) để đo được đúng hiện tượng "nhận lại lặp / ô ma".
- [ ] Dựng script đo Cutie chạy trên **Colab T4** (offline: upload clip → xuất mask từng frame → `./run miou`).
- [ ] Sau khi có số Cutie: A/B 3 lần, nêu `±` (ngưỡng nhiễu theo ô chọn, không dùng ±0,004 của ô mặt).

## 📚 Tài liệu tham khảo
- Cutie (CVPR 2024) — long-term VOS với object-level memory.
- `docs/task/22-11-2026-bo-thu-cong-thay-bang-yolo-world-tu-tim-muc-tieu.md`.
