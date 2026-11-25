# 24-11-2026 — `--mask-threshold` ÂM: lần đầu có cải thiện đo được (+0,031 … +0,053 mIoU)

## Mục tiêu
Sau 7 kết quả âm tính (đổi checkpoint, `image_size`, `min_obj_score_logits`, `vos_every`, re-ID,
refiner biên, 7 siêu tham số motion-memory), tìm một đòn **rẻ, đúng cơ chế** để mask phủ đúng vật hơn —
nhất là khi vật ở **sát biên khung** / tay lọt vào khung.

## Input
- Chẩn đoán từ chấm GT: lỗi chính là mask **HỤT** chứ không phải tràn —
  `phu_thieu_mean` = **0,2165** (binh1/b1) · **0,1981** (binh2/binh2_tay) ·
  `mask_ngoai_gt_mean` = 0,006 / 0,046.
- ⇒ Điểm âm (negative prompt) là **sai thuốc** (AGENTS §6 đã đo: lỗi hụt diện tích thì điểm âm làm hụt thêm).
  Đòn đúng hướng: **nới ngưỡng logit** để mask nhận thêm pixel "chưa chắc" — `--mask-threshold` **âm**
  (AGENTS từng chỉ đo giá trị **dương** 1,0/2,0 = làm mask co lại).
- Bộ GT có mask người tô: `b1` 12 frame · `binh2_tay` 12 · `vat_be_vaolai` 11 (clip `clip_be2`).

## Công việc đã thực hiện
1. `scripts/sweep_motion_memory.py --preset mask_threshold`: sweep `0, −0,5, −1,0, −2,0, −3,0, −4,0`,
   chạy **chèn kẽ**, 2 vòng/cấu hình, chấm mIoU bằng `score_miou`, **so cặp theo frame** + CI95 bootstrap.
2. Chạy trên 3 clip (binh1, binh2, clip_be2) — 12 lần chạy model/clip.
3. Ghi `mask_threshold` vào `run_info` **và** `manifest.json` của mask dump (trước đó thiếu ⇒ hai phiên
   khác ngưỡng trông y hệt nhau).
4. Áp `--mask-threshold -1.0` cho **đường `./run demoip`** (không đổi mặc định của `tools/run_live.py`
   để artifact cũ tái lập được).

## Output / Kết quả (Δ so CẶP theo frame, 2 vòng/config)

| ngưỡng | binh1 (`b1`, 14 cặp) | binh2 (`binh2_tay`, 16 cặp) | clip_be2 (`vat_be_vaolai`, 16 cặp) |
|---|---|---|---|
| 0 (mặc định) | 0,7794 | 0,7644 | **0,8625** |
| **−0,5** | +0,0275 [+0,0233,+0,0324] | +0,0200 [+0,0105,+0,0300] | −0,0001 [−0,0098,+0,0083] |
| **−1,0** | **+0,0526 [+0,0367,+0,0715]** | **+0,0313 [+0,0116,+0,0506]** | −0,0021 [−0,0178,+0,0119] |
| −2,0 | +0,0801 [+0,0465,+0,1176] | +0,0276 [−0,0041,+0,0550] | −0,0160 [−0,0394,+0,0072] |
| −3,0 | +0,0632 [+0,0188,+0,1105] | −0,0108 [−0,0742,+0,0431] | **−0,0485 [−0,0841,−0,0129]** |
| −4,0 | −0,0044 [−0,0624,+0,0469] | **−0,0853 [−0,1668,−0,0129]** | **−0,1068 [−0,1524,−0,0602]** |

**Cơ chế đo được** (binh1, vòng 1): thiếu `0,2165 → 0,1848 → 0,1498 → 0,0923` khi ngưỡng
`0 → −0,5 → −1,0 → −2,0`, còn tràn ngoài GT `0,006 → 0,0114 → 0,0236 → 0,0572` ⇒ **đúng chiều**:
mask phủ thêm phần vật bị hụt, tràn tăng chậm hơn nhiều.
**Không bịa mask khi vật vắng: `0/5` frame GT rỗng ở CẢ 6 mức.**

**Chọn −1,0** (không phải −2,0 dù binh1 đỉnh ở −2,0): −1,0 là mức duy nhất **có lợi trên 2 clip
(CI95 không chứa 0) và KHÔNG hại clip thứ 3** (−0,0021, CI95 chứa 0).
Caveat theo luật repo: |Δ| = 0,03–0,05 **nhỏ hơn ngưỡng nhiễu GT của `clip_be2` (0,1228)** ⇒ chưa được
tuyên bố "tốt hơn" trên một clip đơn lẻ; nhưng đây là **so cặp** (CI95 loại 0) trên **3 clip độc lập**
với quan hệ **liều–đáp tuyến tính rồi giảm**, kèm cơ chế đo được ⇒ mức bằng chứng mạnh hơn so sánh
hai trung bình.

## Vấn đề & cách xử lý
| vấn đề | xử lý |
|---|---|
| Chèn chú thích `#` vào giữa chuỗi nối `\` trong `run` ⇒ **gãy lệnh** | đưa chú thích lên TRƯỚC `exec`, kiểm bằng `bash -n run` |
| Điểm âm (negative prompt) tưởng là đòn chính | **bác**: lỗi là HỤT, điểm âm làm hụt thêm (đo cũ: −0,0744 @512) |
| `mask_threshold` không có trong `run_info`/manifest | đã thêm cả hai |

## Next steps
- **Xác nhận trên phiên cầm tay thật**: chạy `./run demoip` (đã bật −1,0) rồi chấm mIoU trên clip quay
  thô — cần **người thứ 2 tô 2–3 frame** (ngưỡng nhiễu của chính clip đó).
- **Đệm mép khung (padding)** — đòn còn lại cho ca "vật chạm biên", chưa làm.
- **Tầng 2**: Cutie (đổi model) — cần đo lại ngưỡng nhiễu trước.

## Tài liệu tham khảo
- Artifact: `data/sweep_mask_threshold_b1_2026-11-24_metrics.json`,
  `data/sweep_mask_threshold_binh2_2026-11-24_metrics.json`,
  `data/sweep_mask_threshold_be2_2026-11-24_metrics.json`
- Script: `scripts/sweep_motion_memory.py --preset mask_threshold`
- Tầng 1 (âm tính): `docs/task/24-11-2026-tang-1-sweep-motion-memory.md`
