# Thước đo "BÁM ĐÚNG" — mIoU mask vs GT (việc #6)

> Trả lời câu hỏi hội đồng chắc chắn hỏi: **"hệ thống bám có ĐÚNG không?"**.
> Mọi con số "chất lượng" khác trong repo (`drift_iou`, `stability`) chỉ là **độ tự nhất quán**:
> VOS bám lệch một cách ổn định thì `drift_iou` vẫn cao (AGENTS §6).

## 1. Thước đo là gì

- **mIoU** = trung bình `IoU(mask_model, mask_GT)` trên các frame chấm được.
- **GT mask** = mask nhị phân do **người** tô trên frame gốc (`docs/gt/<tên>/gt_<frame>.png`).
- Script: `scripts/score_miou.py`; mask của model do worker xuất ra:
  `tools/live_worker.py --dump-mask-frames "0,50,120"`.

### Quy tắc chấm (đây là phần dễ làm sai nhất)

| Ca | Kết quả | Vì sao |
|---|---|---|
| GT có vật, model trả mask rỗng | **0,0** | bám sai thật; gộp vào "không đo được" là thổi phồng điểm |
| GT rỗng (không có vật trong frame) | **không chấm** (`None`) | `IoU(rỗng, rỗng) = 1,0` theo công thức ⇒ nếu nhận thì "bám đúng tuyệt đối" mà chẳng đo gì |
| Thiếu file mask của model | `None` + `so_frame_thieu_mask` | *chưa chạy* ≠ *bám sai* |
| Không chấm được frame nào | `mIoU = None` | không bao giờ in `0` cho "chưa đo" |
| GT có phần do **model gợi ý** | **từ chối chấm** | chấm mIoU trên mask model tự sinh = đo chính nó, không phải đo chất lượng |

## 2. Cách làm GT cho video THẬT (≈ 20–30 phút cho 10–20 frame)

```bash
# 1) cắt frame ra PNG để tô (chọn frame rải đều clip, có cả lúc vật bị che/một phần ra khung)
python scripts/score_miou.py label --clip data/binh1.mp4 \
    --frames 0,40,80,120,160,200,240,280 --ten binh1_tay --nguoi-gan "Nguyễn Văn A"

# 2) tô trắng vùng vật trên docs/gt/binh1_tay/frames/frame_000040.png
#    rồi lưu thành docs/gt/binh1_tay/gt_000040.png (cùng thư mục gốc của bộ GT, nền đen, vật trắng)

# 3) kiểm GT hợp lệ (đủ file, đủ người chịu trách nhiệm, không frame trùng)
python scripts/score_miou.py score --gt docs/gt/binh1_tay --pred-dir /tmp/x --check-index

# 4) chạy model trên đúng clip đó, xuất mask tại ĐÚNG các frame đã gán
#    ⚠ --vos-every 1 là BẮT BUỘC khi gán GT: với vos_every > 1 chỉ frame chia hết cho N mới có lần
#    VOS, nên frame 40 (N=3) không có mask nào và lần chấm sẽ thiếu frame mà không rõ vì sao.
#    Tên file mask = **chỉ số frame VIDEO** (không phải bộ đếm nội bộ của engine) — đã sửa 14-11.
python tools/live_worker.py --source data/binh1.mp4 --out-dir /tmp/run1 \
    --image-size 192 --vos-every 1 --dump-mask-frames "0,40,80,120,160,200,240,280" \
    --stop-after-frames 300
# (ô chọn phải nằm ở /tmp/run1/bbox.json, dạng {"x":…,"y":…,"w":…,"h":…})

# 5) chấm
python scripts/score_miou.py score --gt docs/gt/binh1_tay --pred-dir /tmp/run1/masks \
    --out data/miou_binh1_tay_metrics.json
```

Mask dump là mask **thô** của model (trước bước làm mượt `--mask-smoothing`) — đúng cái cần chấm.

Lưu ý khi tô: **không** dùng chính SAM 2 để sinh mask rồi sửa lại — nếu dùng thì phải khai
`--gt-do-model-goi-y` và script sẽ **từ chối** dùng bộ GT đó làm bằng chứng (nó có thể dùng để tự
kiểm đường ống, không để tuyên bố độ chính xác).

## 3. Demo đã chạy: fixture TỔNG HỢP (chỉ để kiểm đường chấm)

```bash
python scripts/make_synthetic_gt_clip.py          # clip + GT biết trước (ô vuông 60 px trên nền nhiễu)
python tools/live_worker.py --source data/synthetic_gt.mp4 --out-dir /tmp/demo_gt \
    --image-size 192 --vos-every 1 --dump-mask-frames "0,6,12,18,23" --stop-after-frames 30
python scripts/score_miou.py score --gt docs/gt/synthetic_tong_hop --pred-dir /tmp/demo_gt/masks \
    --out data/miou_synthetic_2026-11-14_metrics.json
```

Kết quả: **mIoU 0,9354 trên 5 frame** (`data/miou_synthetic_2026-11-14_metrics.json`).
**Đây là CẬN TRÊN**: GT ≡ đúng vùng pixel của ô vuông và prompt là đúng bbox của nó. Cấm trích như
"mIoU trên video thật/DAVIS" (AGENTS §6).

## 4. Vì sao chưa có mIoU trên video thật

Cần **người** gán tay (bước 2 ở trên). Việc này không tự động hoá được một cách trung thực — và
đó chính là lý do nó chưa có trong repo. Khi có GT tay:
`mIoU` + `mIoU_p05` + bảng từng frame trong artifact; thêm dòng vào `REGISTRY` của
`scripts/so_lieu_bao_cao.py` rồi chạy lại script đó để số vào `docs/so-lieu-bao-cao.md`.

## 5. Liên quan

- `docs/so-lieu-bao-cao.md` — nơi mọi số được trích (kèm cột "CẤM trích thành").
- `docs/bang-cau-hinh.md` — chọn cấu hình (`image_size` × `vos_every`) có ngưỡng nhiễu.
- `scripts/measure_live_relay.py` — đo đường ống trên camera thật (KHÔNG đo độ chính xác).
