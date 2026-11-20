# 20-11-2026 — **mIoU phân đoạn ĐẦU TIÊN trên video thật** (GT do người gán): 0,7794

## Mục tiêu

Repo chưa từng có một con số **mIoU phân đoạn trên video thật** — mọi kết luận "bám đúng" trước đây
dựa vào `drift_iou`/`stability`, mà đó chỉ là **độ tự nhất quán** (AGENTS §6). Phiên này: người dùng gán
GT tay 12 frame bằng công cụ mới (`./run gt`, PR #58/#59), rồi chấm.

## Input

- `data/binh1.mp4` (333 frame), ô chai `300,275,150,410`.
- GT: `docs/gt/b1` — **12 frame** `0,30,60,91,121,151,181,211,241,272,302,332`, `dang_gt: silhouette`,
  `nguoi_gan: Binh`, `gt_do_model_goi_y: false`; 5 frame đánh **`gt_rong`** (`121,151,272,302,332` —
  chai không còn trong hình).
- Mask model: `tools/live_worker.py --vos-every 1 --image-size 192 --dump-mask-frames 0,30,60,91,181,211,241`.

## Công việc đã thực hiện

1. Kiểm GT trước khi chấm: vẽ viền GT lên từng frame (`data/anh_tmp`, đã xoá sau khi xem). **7/7 frame
   có vật: viền bám sát chai, không lem sang tay/mặt**; frame 211 to 28 % khung là do chai **đưa sát
   camera**, không phải tô lem.
2. Chạy worker `--vos-every 1` (repo **từ chối** dump mask khi `vos_every > 1`: "mask của frame khác
   KHÔNG tồn tại ⇒ chấm mIoU sẽ ghép GT với mask của frame khác"), rồi `./run miou score`.

## Output / Kết quả

`data/miou_b1_2026-11-20_metrics.json` — **mIoU = 0,7794** trên **7** frame chấm được
(coverage 7/12 = 58 %), `dang_gt: silhouette`, `mask_ngoai_gt` trung bình **0,6 %** (tệ nhất 1,9 % ở
frame 60) ⇒ mask **không tràn ra ngoài** vật.

| frame | 0 | 30 | 60 | 91 | 181 | 211 | 241 |
|---|---|---|---|---|---|---|---|
| IoU | **0,548** | 0,776 | 0,805 | 0,834 | 0,799 | 0,850 | 0,844 |

- Frame **0 thấp nhất (0,548)** vì mới chọn ô: `dien_tich_pred` 27 640 vs GT 50 298 ⇒ model phủ **45 %**
  vật. Loại frame này ra thì trung bình 6 frame còn lại = **0,818** — nhưng **không** trích 0,818 như
  "mIoU của clip": đó là bỏ mẫu xấu nhất mà không có lý do tiên lượng trước.
- `mIoU_p05 = None` (7 < 30 mẫu — đúng ngưỡng công bố, không in p05 từ mẫu ít).
- 5 frame `gt_rong` ⇒ **không chấm** (không phải 1,0; cũng không phải 0,0) — đúng quy tắc "GT rỗng thì
  không chấm".
- Artifact còn 6 cảnh báo ⇒ exit 1 (coverage 58 %, GT rỗng nằm ngoài `frames_yeu_cau`) — số dùng được
  nhưng phải đọc kèm `meta.dang_gt`/`phuong_phap_gt`.

## Vấn đề & cách xử lý

- **`mIoU` KHÔNG dùng được để chốt `max_mad`** (ticket #38) — phát hiện quan trọng: muốn chấm mIoU hợp
  lệ phải chạy `--vos-every 1`, mà cấu hình đó **tắt hẳn LK** ⇒ `max_mad` không tham gia gì vào phép đo.
  Nói cách khác: mIoU đo **model + ô chọn**, không đo **đường nội suy LK**. Việc chọn `max_mad` phải
  dựa vào `lk_ok_frac`/`drift_iou` (đã có) + phép đo mới đề xuất dưới đây.
- GT khởi tạo bằng **gợi ý màu HSV** rồi người sửa tay (`phuong_phap_gt` đã khai). Sai số của bộ gợi ý
  **CHƯA ĐO** ⇒ không được trích 0,7794 như "GT người vẽ hoàn toàn"; nhưng `gt_do_model_goi_y: false`
  nên **không** thuộc ca bị từ chối chấm (gợi ý là ngưỡng màu, không phải mask của model).

## Next steps

1. **Đo ô hiển thị vs GT** (dùng chính GT này): mỗi frame GT có hộp bao suy ra từ mask người tô; so với
   `hien_thi_*` trong CSV drift ⇒ **IoU ô người xem thấy vs ô thật**, chạy ở 1,5 và 6,0. Đây mới là phép
   đo trả lời được `max_mad`.
2. Thêm GT cho **binh2** (clip thứ hai) để mIoU không phải n=1 clip.
3. Frame 0/1/2 của mọi clip nên được gán GT riêng: đó là lúc model kém nhất (0,548) và là thứ người xem
   thấy đầu tiên.

## Tài liệu tham khảo

- `docs/gt/b1/index.json`, `data/miou_b1_2026-11-20_metrics.json`
- `scripts/score_miou.py`, `docs/thuoc-do-bam-dung.md`, `./run gt` (PR #58/#59)
- AGENTS §6 ("muốn nói bám ĐÚNG thì phải chấm mIoU")
