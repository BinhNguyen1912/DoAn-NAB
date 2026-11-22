# Ngày 22-11-2026 — GT mới `binh2_tay2` + chẩn đoán lỗi + script quét `image_size` cho Colab T4

> Tiếp theo `docs/task/22-11-2026-baseline-reid-binh2-truoc-khi-len-gpu.md`. Người dùng đã tô thêm
> 7 frame (170,180,190,200,215,230,250) — trong đó **170–215 là GT RỖNG** (vật đã rời khung).

## 🎯 Mục tiêu
- Đo đúng hiện tượng "mất dấu → quay lại" (trước đó khoảng 164–227 không có GT ⇒ không chứng minh được).
- Đo "ô ma" (mask vẽ ra khi vật đã rời khung) — hiện tượng ticket #42.
- Chuẩn bị script để **quét `image_size` trên GPU** (loại trừ giả thuyết rẻ nhất trước khi đổi lõi Cutie).

## 📥 Input
- `docs/gt/binh2_tay2/` — 7 frame, `dang_gt = silhouette`, người gán: Binh.
  `170,180,190,200,215` **rỗng** · `230` = 50 723 px · `250` = 58 540 px.
- Cùng ô chọn suy từ GT f0: `xywh = 334,319,158,568`.

## 📤 Kết quả đo (SAM 2 tiny @192, `vos_every=1`, **KHÔNG** bật `--reid`)

**Vật quay lại (bộ GT mới):**

| frame | 230 (vừa vào lại) | 250 |
|---|---|---|
| IoU | **0,713** | **0,824** |
| diện tích GT / pred | 50 723 / **40 018** | 58 540 / **48 416** |

⇒ **Nhận lại được**, nhưng **hụt diện tích 20 %**. mIoU 2 frame = 0,7682.

**"Ô ma" — mask vẽ ra khi GT rỗng:**

| frame | 170 | 180 | 190 | 196 | 200 | 215 | 294 | **326** | 359 |
|---|---|---|---|---|---|---|---|---|---|
| mask px | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **11 413** | 7 |

⇒ Lần rời **thứ nhất sạch (0 px ở cả 6 frame)**; **lần rời thứ hai có ô ma ở f326** (11,4k px).
Đây là số ĐẦU TIÊN chứng minh hiện tượng của ticket #42, ở mức 1/9 frame GT rỗng của clip.

## 🧭 Chẩn đoán chốt lại
1. **Lỗi chính = PHÂN ĐOẠN HỤT**, không phải bám nhầm vật: `pred` luôn nhỏ hơn GT 15–20 %
   (27k–48k so với 32k–58k). `image_size 192` quá thô cho vật mảnh/cầm tay.
2. **"Không nhận lại được" KHÔNG tái hiện** ở mức GT hiện có: f230 = 0,713 và f261 = 0,814 dù **không**
   có cơ chế re-ID nào.
3. **"Ô ma"** có thật nhưng **thưa** (1/9 frame GT rỗng) ⇒ ưu tiên thấp hơn (1).

⇒ Trước khi đổi lõi sang **Cutie** (thay model = rủi ro + 1 ngày), phải loại trừ giả thuyết **rẻ hơn**:
**cùng SAM 2 nhưng `image_size` lớn trên GPU**. Trên CPU bất khả thi (1024 ≈ 4 s/frame).

## 🛠️ Đã làm
- `scripts/bench_gpu_binh2.py` (mới): quét `--sizes 192,320,512,1024`, mỗi cấu hình chạy
  `tools/live_worker.py` **cùng một ô chọn**, dump mask tại **union** các frame GT của cả hai bộ,
  chấm `mIoU` / `mask_ngoai_gt` / `ms_moi_frame`, xuất artifact có `git_rev`/`git_dirty_code`/`lenh`.
  - `git_dirty_code` **bỏ qua `data/`** (quy ước AGENTS §6) để artifact không tự làm cây bẩn.
  - Ghi rõ trong artifact: `ms_moi_frame` = thời gian tường / số frame phát ⇒ **CẬN TRÊN** của độ trễ.
- Chạy smoke trên CPU (`--sizes 192 --max-frames 60`): đường ống chạy đúng, `mIoU binh2_tay = 0,7392`
  (số smoke, **không** công bố vì chỉ 2 frame GT).
- Đã **push** nhánh `feat/nhan-lai-vat-live` lên `origin` để Colab clone được code mới.

## 📌 Việc cần làm tiếp
- [ ] Chạy trên **Colab T4**: `!python scripts/bench_gpu_binh2.py --device cuda --sizes 192,320,512,1024`
      rồi gửi lại `data/gpu_sweep_binh2_*_metrics.json`.
- [ ] Nếu 512/1024 trên GPU cho mIoU ≥ 0,90 ⇒ **không cần Cutie**; chỉ cần đổi cấu hình theo thiết bị.
- [ ] Nếu vẫn < 0,85 ⇒ mới đổi lõi sang Cutie và đo lại **cùng** hai bộ GT này.

## ⚠️ Hạn chế
- 8 + 7 = 15 frame GT trên 360 frame ⇒ mIoU **không** đại diện cả clip (coverage 15/360).
- Chỉ 1 lần chạy ⇒ chưa có `±`; muốn so sánh phải ≥ 3 lần (`./run ab`).
- Số trên là **CPU @192**; số GPU **chưa có** (chưa thuê/chưa chạy Colab).

## 🐞 Bẫy đã gặp: Colab KHÔNG mở được notebook trên nhánh có dấu `/`
- URL `.../blob/feat/nhan-lai-vat-live/notebooks/x.ipynb` ⇒ Colab gọi API
  `/contents/nhan-lai-vat-live/notebooks?ref=feat` — nó cắt chuỗi ở dấu `/` ĐẦU TIÊN sau `blob/`,
  nên hiểu nhầm nhánh là `feat` và đường dẫn là `nhan-lai-vat-live/notebooks`.
- Cách chữa: giữ một nhánh **KHÔNG có dấu `/`** trỏ đúng commit cần dùng (`colab-bench`), rồi mở
  `.../blob/colab-bench/notebooks/colab_gpu_evaluation.ipynb`.
- Kiểm tra trước khi gửi link (1 lệnh): `curl -o /dev/null -w "%{http_code}" \
  "https://api.github.com/repos/<owner>/<repo>/contents/notebooks?ref=<nhánh>"` phải trả `200`.
- Nhánh `colab-bench` là nhánh TẠM cho Colab — xoá sau khi đo xong.
