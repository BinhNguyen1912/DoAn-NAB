# PR — fix(metrics): một ngưỡng duy nhất cho mọi `*p05` (30 mẫu) — ticket #23

## Chuyện gì

Ticket **#23**: cùng một đại lượng `*_p05` mà repo công bố bằng **ba ngưỡng** khác nhau — `5`
(`scripts/score_miou.py`), `20` (`scripts/make_trajectory_media.py`), `30`
(`src/live_tracking.py::_STAT_MIN_SAMPLES` + `src/drift_samples.py::MIN_SAMPLES`). Ở n nhỏ, "phân vị 5 %"
**chính là** min (chỉ số `0,05 × (n−1)` nằm giữa min và phần tử nhỏ thứ hai) ⇒ công bố nó thành `p05` là
thổi phồng độ tin cậy, và ba con số p05 trong báo cáo không so được với nhau.

Nay mọi `*_p05` công bố ra artifact đi qua **một** cửa: `phan_vi(values)` với `MIN_SAMPLES = 30`
(ghim bằng test `MIN_SAMPLES == live_tracking._STAT_MIN_SAMPLES`).

## Bằng chứng

| | trước | sau |
|---|---|---|
| `data/miou_binh1_hopbao_2026-11-15_metrics.json` (`n_cham = 12`) | `mIoU_p05 = 0,5058` từ **12** frame | **`mIoU_p05 = None`**, `mIoU_p05_n = 12`, `mIoU_p05_nguong = 30`, `mIoU = 0,6464` (không đổi) |
| `docs/media/traj/binh1_vat_ra_khung.json` (`drift_n = 271`) | `drift_iou_p05` chỉ ở stdout | `drift_iou_p05 = 0,0` **vẫn công bố**, `nguong_p05 = 30`, `thong_ke` nằm trong file provenance |
| `static_control(25 mẫu)` | p05 công bố | ĐẠT tiêu chí (ngưỡng 20 của ticket 15) nhưng p05 `None` |

- Artifact sinh trên cây sạch: `git_rev 0f8542f`, **`git_dirty_code = false`** (sinh lại **sau rebase**
  vì rebase đổi SHA — nếu không `git_rev` thành con trỏ chết).
- `./run lint` xanh · `./run test` **1298 passed**, 5 deselected.
- **Test "có răng"**: hạ `MIN_SAMPLES` về 20 ⇒ **4 test đỏ**; về 5 ⇒ **6 test đỏ** (chạy thật rồi khôi phục).
- `scripts/so_lieu_bao_cao.py --check` xanh (`docs/so-lieu-bao-cao.md` khớp artifact).

## Không làm gì (và vì sao)

- Artifact `data/miou_synthetic_2026-11-14_metrics.json` (n = 5, p05 = 0,9239) **không** sinh lại được:
  mask của nó ở `/tmp/demo_gt4` đã mất, và dump lại thì SAM 2 không tất định ⇒ số sẽ khác, làm lệch chỗ
  đang trích `mIoU = 0,9354`. Thay vào đó `docs/so-lieu-bao-cao.md` ghi rõ **cấm trích p05** của nó.
- Không đụng `p05` theo **cửa sổ** (`rolling_p05`, `flag_rate`, `low_p05_low_empty`): "đủ mẫu" ở đó do
  chính cửa sổ quyết định, khác định nghĩa — đã ghi rõ trong comment `MIN_SAMPLES` để phiên sau không
  "thống nhất" nhầm.

## Cửa một chiều hay hai chiều

Hai chiều với code/test/docs. **Một chiều về phía số**: artifact đã commit ghi `mIoU_p05 = None`; nếu
sau này có ≥ 30 frame GT thì `mIoU_p05` xuất hiện trở lại, nhưng đừng trích lại `0,9239`/`0,5058` của
artifact cũ — đó là p05 từ 5 và 12 frame.

## Ticket

`.scratch/camera-ai-realtime/issues/23-…md` — 3/3 tiêu chí, có `## Answer`.
Log: `docs/task/17-11-2026-ticket-23-nguong-p05-va-dong-ticket-19-20.md`.
