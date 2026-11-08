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

## 🔁 Review độc lập (AGENTS §9.1) — "chưa merge được", đã đóng hết

| Phát hiện | Mức | Đã xử lý |
|---|---|---|
| `_mask_iou_or_nan` loại **cả** frame "model trả mask rỗng" khỏi mẫu ⇒ mIoU chỉ còn trung bình các frame sống sót, **luôn cao hơn thực tế** (một lần bám sai bị ghi là "không đo được") | **P1** | Tách rõ: **GT rỗng ⇒ NaN** (không có gì để chấm), **model rỗng mà GT có vật ⇒ 0,0**; thêm `so_frame_gt_rong`; test `_mask_iou_or_nan(rỗng, gt) == 0.0` |
| `git_rev` ghi **trước** khi commit code sinh ra số ⇒ chạy lại tại đúng rev đó sẽ `AttributeError: no attribute 'masks'`. Vi phạm ADR-0002 | **P1** | Artifact thêm `git_dirty`, `do_luc`, `lenh`; **commit code trước → chạy lại script → commit artifact** để `git_rev == HEAD` |
| `bbox_iou_*` trả **NaN literal** (JSON không hợp lệ) khi cửa sổ rỗng; không nhất quán với `mask_miou_*` (None) | P2 | Dùng `_mean()` cho cả 6 cửa sổ; validate `--fraction/--cover/--start`; test `json.dumps` không chứa `NaN` |
| README ghi dòng "**không bị che 0/12**" — không phải kịch bản của script (đó là cửa sổ `truoc` = **11** frame, và `mat_dau_truoc` không được tính) | P2 | Sửa nhãn thành "trước khi bị che (khung 1–11)", thêm `so_frame_truoc`, `so_frame_gt_rong` vào artifact |
| **Nguy cơ overclaim**: 0,956 và 0,892 đo **hai định nghĩa GT khác nhau** (đầy đủ vs chỉ phần nhìn thấy); và trên fixture, một **ngưỡng màu** cũng đạt 1,0 ⇒ con số chỉ chứng minh "mask không trôi", không phải "chất lượng phân đoạn" | P2 | Thêm câu chữ trung thực vào README + log (mục dưới) |
| `occlusion_fraction` không validate (âm ⇒ cờ "bị che" mà không che gì; >1 ⇒ che tràn) | P2 | `raise ValueError` trong `generate_tracking_sequence` + 2 test |
| `so_lan_cap_nhat_mask_trong_che` đếm số frame bị che (offline chạy VOS mỗi frame ⇒ luôn = `cover`) ⇒ vô nghĩa | P3 | Đổi tên `so_frame_bi_che_trong_cua_so` + ghi chú |
| Độ chính xác giả (4 chữ số trong khi chênh giữa hai lần chạy ~0,004) | P3 | Docs làm tròn 2 chữ số; artifact giữ 4 |
| Test "GT khớp pixel màu" có thể pass rỗng (`mask_iou(rỗng,rỗng)=1,0`) | P3 | Thêm assert `thuc_te.sum() == 30*30`; parametrize 4 ca (size 39/41/41/40, fraction 0,3/0,5/0,999/1,0) |
| Docstring `experiment_occlusion.py` ghi output CSV không tồn tại | P3 | Sửa docstring |

**Đã kiểm, không phải lỗi** (reviewer bác đúng nghi vấn của mình): `cover_w` làm tròn **không** làm GT
lỗi (frame và mask dùng **cùng** `cover_w` ⇒ GT ≡ pixel màu cam; size lẻ chỉ làm tỉ lệ đạt 0,488 thay
vì 0,5); `occlusion_frames` ngoài khoảng bị bỏ qua an toàn; ô sát mép không off-by-one;
`TrackingFixture.masks=None` hiện **không** có đường dùng nào chạm tới.

### Câu chữ TRUNG THỰC để dùng trong báo cáo
> Chất lượng phân đoạn được đo trên **ảnh tổng hợp** (ô vuông cam đặc trên nền phẳng, GT mask chính
> là các pixel của ô), `image_size=320`, laptop CPU: **mIoU ≈ 0,96** ở các khung không bị che và
> **≈ 0,89** khi bị che 50 % — mask chỉ được chấm trên phần đối tượng **còn nhìn thấy**. Đây là
> **cận trên**, không phải độ chính xác phân đoạn thực tế: SAM 2 được khởi tạo bằng **đúng ô bao GT**
> ở frame 0, và trên fixture này một bộ ngưỡng màu đơn giản cũng đạt 1,0, nên con số chỉ chứng minh
> **lan truyền mask không bị trôi/hỏng**, không dùng để so với mIoU trên DAVIS hay video thật. Khi
> vật bị che kín, GT rỗng nên **không đo được** (None; 6/6 khung mất dấu) — vì vậy phải báo **cả bbox
> IoU, mIoU và tỉ lệ mất dấu**, không trích riêng con số đẹp.

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
