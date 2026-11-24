# 24-11-2026 — Tầng 1 "custom model": sweep 7 siêu tham số motion-memory của SAMURAI — **kết quả ÂM TÍNH**

## Mục tiêu
Người dùng hỏi *"có cách nào đụng dô model để custom lại khôn hơn?"*. Tầng rẻ nhất: **không train**, chỉ
chỉnh siêu tham số điều khiển **cách chọn ký ức (memory bank) + Kalman filter** của SAMURAI — thứ quyết
định hệ có trôi sang nền/tóc khi vật đi nhanh hay không.

## Input
- `configs` của SAMURAI đang bật `samurai_mode: true` với 7 tham số, **chưa ai đo cái nào**:
  `kf_score_weight 0,25` · `memory_bank_kf_score_threshold 0,0` · `memory_bank_iou_threshold 0,5` ·
  `memory_bank_obj_score_threshold 0,0` · `stable_frames_threshold 15` · `stable_ious_threshold 0,3` ·
  `samurai_mode true`.
- GT có mask thật: `b1` 12 frame (binh1.mp4, 1280×720) · `binh2_tay` 12 frame (binh2.mp4) — chấm được
  **7** và **8** frame (phần còn lại GT rỗng = vật không có mặt).
- Ngưỡng nhiễu mIoU của chính GT (đo 24-11): clip đặc **0,1228**, túi mờ **0,2450**.

## Công việc đã thực hiện
1. `src/tracker_engine.MODEL_OVERRIDE_CHO_PHEP` — **danh sách trắng** 7 khoá + ép kiểu; khoá lạ ⇒
   `ValueError`. Lý do: hydra **bỏ qua khoá sai tên trong im lặng** ⇒ thí nghiệm trông như đã chạy cấu
   hình mới mà thực ra chạy mặc định.
2. `tools/run_live.py --model-override KEY=VALUE` (lặp được) → `build_default(model_overrides=…)` →
   `build_overrides()` (hydra, **không copy file config**); ghi vào `run_info.model_overrides` **và**
   `manifest.json` của mask dump.
3. `scripts/sweep_motion_memory.py` — chạy **chèn kẽ** 5 cấu hình × R vòng, chấm mIoU bằng
   `scripts/score_miou.py`, so **cặp theo frame**, CI95 bootstrap, in ngưỡng nhiễu của clip.
4. Chạy: `binh1` (3 vòng, 15 lần chạy thật) + `binh2` (2 vòng, 10 lần chạy thật).

## Output / Kết quả
**binh1 · GT `b1` · 3 vòng · 21 cặp frame** (`data/sweep_motion_b1_2026-11-24_metrics.json`):

| cấu hình | mIoU | Δ cặp | CI95 | kết luận |
|---|---|---|---|---|
| A hiện tại | **0,7794** | — | — | baseline (trùng số đã công bố 0,7794) |
| B `kf_score_weight 0,5` | 0,7652 | −0,0143 | [−0,0284, −0,0003] | **tệ hơn** một chút — nhưng 0,014 ≪ 0,12 ⇒ *không phân biệt được* |
| C `memory_bank_kf_score_threshold 0,2` | 0,7794 | **0,0000** | [0, 0] | **không đổi** (mask y hệt) |
| D `stable_frames_threshold 8` | 0,7794 | **0,0000** | [0, 0] | **không đổi** (mask y hệt) |
| E `samurai_mode false` | 0,7788 | −0,0006 | [−0,0014, +0,0001] | **không khác** ⇒ motion-aware memory không tạo khác biệt trên clip này |

**binh2 · GT `binh2_tay` · 2 vòng · 16 cặp** (`data/sweep_motion_binh2_2026-11-24_metrics.json`):

| cấu hình | mIoU | Δ cặp | CI95 |
|---|---|---|---|
| A hiện tại | **0,7644** | — | — |
| B `kf_score_weight 0,5` | 0,7634 | −0,0011 | [−0,0021, −0,0002] |
| C `kf_nguong 0,2` | 0,7658 | +0,0013 | [0,0000, +0,0033] |
| D `stable 8` | 0,7645 | +0,0000 | [0, 0] |
| E `samurai_mode false` | 0,7533 | **−0,0111** | [−0,0278, +0,0001] |

⇒ **Cả 5 cấu hình đều "không phân biệt được"** (|Δ| ≤ 0,014 so với ngưỡng nhiễu **0,12**). Đây là
**kết quả âm tính thứ 7** của repo. Ghi chú: SAMURAI mode OFF **kém hơn** 0,011 ở cả hai clip (cùng
chiều) — nhỏ hơn ngưỡng nhưng là dấu hiệu duy nhất có hướng, không đủ để tuyên bố.

Điểm phụ đáng nhớ: **`stable_frames_threshold` cho mask Y HỆT** (Δ = 0,0000 trên cả 2 clip) ⇒ tham số
này không ảnh hưởng kết quả ở cấu hình/độ dài clip của mình; và 3 vòng lặp cho mIoU **trùng khít** ⇒
SAM 2 trên máy này **tất định** ở 192 px (khác ghi chú cũ trong AGENTS §6).

## Vấn đề & cách xử lý
| vấn đề | xử lý |
|---|---|
| `score_miou` thoát mã 1 khi có cảnh báo (GT rỗng) ⇒ script sweep đầu tiên ra `mIoU=None, n=0` cho **mọi** cấu hình | điều kiện đúng là "artifact có mặt và parse được", không phải `returncode == 0` |
| GT `binh1_tay`, `binh1_silhouette` chỉ có `frames/` (ảnh nguồn), **không có `gt_*.png`** | chỉ dùng bộ có mask thật: `b1`, `binh2_tay`, `be2_lan2`, `tran_nen`, `vat_be_vaolai`, `remote_trang`, `synthetic_tong_hop` |
| Artifact ban đầu `git_dirty_code=True` | commit code trước, chấm lại bằng `--dung-lai-mask` (không nạp model) ⇒ `git_rev 7f4a80b`, `git_dirty_code=false` |

## Next steps
- **Tầng 2 (cần quyết)**: đổi model sang **Cutie** (memory tốt hơn, thiết kế cho VOS) — ~1 tuần; **chưa
  cần GPU để chạy**, nhưng muốn thử nhiều cấu hình nhanh thì nên thuê GPU (Colab T4 đo được 49,6 ms/frame).
  Trước khi tích hợp phải **đo lại ngưỡng nhiễu mIoU** cho clip dùng để chấm.
- **Tầng "prompt" (rẻ, chưa làm)**: điểm âm (negative prompt) — engine + web **đã có**, CLI **chưa nối**;
  đệm mép khung (padding) — **chưa có**, đây mới là thứ chữa "ở biên vẫn nhận diện được".
- **Bỏ**: fine-tune SAM 2 (GT ~84 frame/13 bộ ⇒ không đủ; ngưỡng nhiễu 0,12–0,245 ⇒ không chứng minh được).

## Tài liệu tham khảo
- `scripts/sweep_motion_memory.py`, `src/tracker_engine.py::build_overrides`, `tools/run_live.py --model-override`
- Artifact: `data/sweep_motion_b1_2026-11-24_metrics.json`, `data/sweep_motion_binh2_2026-11-24_metrics.json`
- Ngưỡng nhiễu GT: `docs/task/24-11-2026-*.md` (gt_noise), memory `@state.nguong-nhieu-gt-miou`
- Plan đường B: `docs/plan/24-11-2026-bam-bat-vat-bat-ky-duong-b.md`
