# Ngày 08-11-2026 — Số đầu tiên về **độ chính xác mask** (mIoU vs GT): 0,96 thường / 0,89 khi bị che 50 %

## 🎯 Mục tiêu
- Vá lỗ hổng bằng chứng lớn nhất của đồ án: **chưa có con số nào về chất lượng phân đoạn**. Mọi
  "chất lượng" trước đây chỉ là IoU hộp bao (`scripts/experiment_occlusion.py`) và "độ ổn định" tự
  tham chiếu (`stability` = IoU mask giữa hai frame liên tiếp).
- Vì đề tài tên là *segmentation*, hội đồng chắc chắn hỏi "mIoU của mask là bao nhiêu?" — trước hôm
  nay câu trả lời là "không có số".

## 📥 Input
- Phát hiện của vòng phản biện chéo (3 cố vấn, `docs/plan/08-11-2026-…`): *"không ai có con số độ
  chính xác của mask so với ground truth… mạnh về hiệu năng, trắng về chất lượng phân đoạn"*.
- Fixture có sẵn `src/synthetic_video.py` — nhưng chỉ trả **bbox** GT, chưa có mask GT.
- `src/mask_filter.py::mask_iou` đã có (dùng cho live), chưa dùng để đo với GT.

## 🔨 Công việc đã thực hiện
1. **`src/synthetic_video.py`**: `TrackingFixture` có thêm `masks` (N, H, W) bool = **GT mask giải
   tích** (ô vuông trừ dải bị che), tính cho **mọi frame**. GT mask khớp tuyệt đối với pixel màu
   `SQUARE_COLOR` (có test).
2. **`scripts/experiment_occlusion.py`**: đo thêm **mIoU mask vs GT** cho từng frame; hàm
   `summarize()` gom số theo ba cửa sổ (trước / trong / sau khi bị che) và **ghi artifact**
   `data/occlusion_metrics_<size>_metrics.json` có `git_rev` + lệnh + môi trường.
3. **Chặn bẫy "rỗng vs rỗng = 1,0"**: frame mà GT rỗng (bị che kín) hoặc model trả mask rỗng được
   đánh dấu **NaN**, không vào mẫu; `summarize` trả `None` khi không có frame nào đo được + đếm
   `so_frame_do_miou`. Không có bước này thì "che kín 100 %" sẽ được báo là **mIoU = 1,0** (đúng
   loại số liệu sai vừa bị cấm ở PR trước).

## 📤 Output / Kết quả
Đo thật, laptop CPU, `image_size=320`, fixture 640×360, 30 frame, che 6 frame (12–17):

| Kịch bản | bbox IoU (trong che) | **mask mIoU (trong che)** | mất dấu | mIoU sau che |
|---|---|---|---|---|
| che 50 % | 0,53 | **0,89** | 0/6 | 0,96 |
| che 100 % | 0,00 | **None** (GT rỗng — không đo được) | 6/6 | 0,96 |

- mIoU nền (không bị che): **0,956–0,956**. Sau khi vật ra khỏi vật cản: **0,959–0,962** ⇒ model
  **nhận lại** đối tượng, không trôi.
- **Bài học số học quan trọng cho báo cáo:** khi bị che một nửa, `bbox IoU` tụt còn **0,53** nhưng
  `mIoU mask` vẫn **0,89** — vì mask chỉ được tính trên phần **nhìn thấy**. Nếu chỉ báo bbox IoU,
  ta tự làm mình trông tệ hơn thực tế; nếu chỉ báo mIoU mà giấu chuyện che kín thì lại tự làm mình
  trông tốt hơn. Phải báo **cả hai + tỷ lệ mất dấu**.
- Artifact: `data/occlusion_metrics_320_metrics.json` (`git_rev` = `6ae2f86`), biểu đồ
  `data/charts/occlusion_iou_320.png`.
- File thay đổi:
  - `src/synthetic_video.py` — GT mask giải tích (`TrackingFixture.masks`)
  - `scripts/experiment_occlusion.py` — `summarize()`, `_mask_iou_or_nan()`, artifact JSON
  - `tests/test_synthetic_video.py` (+4 test), `tests/test_experiment_occlusion.py` (+2 test)
  - `README.md`, `docs/plan/08-11-2026-…md` — bảng số + đánh dấu việc "mIoU vs GT" đã xong

## 🐞 Vấn đề gặp phải & cách xử lý
- **Lần chạy đầu trả `mIoU trong che = 1,0`** cho kịch bản che 100 %: GT mask rỗng, model cũng trả
  mask rỗng ⇒ `mask_iou(rỗng, rỗng) = 1,0`. Đã sửa bằng NaN + `None` (xem trên). Đây đúng là lỗi
  đã gặp ở `stability` (PR #6) tái diễn ở một metric mới — nên **mọi metric IoU đều phải có quy
  tắc "rỗng thì không tính"**.
- Fixture hiện chỉ che **dải phình từ trái trên chính vật**, chưa có **vật cản đi ngang che kín rồi
  đi qua** (kịch bản khó nhất của đề cương). Đã ghi next step.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Thêm **vật cản đi ngang** (che kín 8–15 frame rồi đi qua) vào fixture; đo độ trễ nhận lại
      theo **số lần cập nhật mask** (không phải frame hình).
- [ ] Đưa `mask_miou` vào metrics CSV của pipeline offline khi có GT (`--gt`), để bảng báo cáo sinh
      từ CSV thay vì chạy script riêng.
- [ ] Đo lại mIoU ở `image_size` 192/256/512 để có bảng "độ phân giải ↔ chất lượng" (đề cương hỏi
      đánh đổi tốc độ/chất lượng).
- [ ] Nhãn **người** trên video thật (2 clip × ~30 khung) — GT giải tích chỉ đúng cho fixture.

## 📚 Tài liệu tham khảo
- `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md` (vòng phản biện nêu lỗ hổng này).
- `scripts/experiment_occlusion.py`, `src/synthetic_video.py`.
- ADR-0002 (báo cáo trung thực — số phải kèm môi trường và `git_rev`).
