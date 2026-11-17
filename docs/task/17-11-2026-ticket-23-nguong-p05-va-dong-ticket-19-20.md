# Ngày 17-11-2026 — Ticket #23: một ngưỡng duy nhất cho mọi `*_p05` (+ dọn phần đóng ticket 19/20)

## 🎯 Mục tiêu
- Đóng ticket **#23** (`ready-for-agent`): cùng một đại lượng `*_p05` mà repo có **ba ngưỡng công bố**
  khác nhau — `5` (`scripts/score_miou.py`), `20` (`scripts/make_trajectory_media.py`), `30`
  (`src/live_tracking.py::_STAT_MIN_SAMPLES`, `src/drift_samples.py::MIN_SAMPLES`) ⇒ người đọc báo cáo
  không biết con số p05 nào đáng tin. Đây là bẫy "0/None ≠ đã đo" phiên bản **phân vị**.
- Dọn 12 dòng tracker của ticket 19/20 (đã resolve từ 11-11 nhưng chưa commit) để mỗi phiên sau không
  thấy cây bẩn.

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/23-nguong-cong-bo-phan-vi-5-20-30-khong-thong-nhat.md`.
- Code: `src/drift_samples.py`, `src/live_tracking.py` (`_STAT_WINDOW=200`, `_STAT_MIN_SAMPLES=30`),
  `scripts/score_miou.py`, `scripts/make_trajectory_media.py`.
- Artifact đang có: `data/miou_binh1_hopbao_2026-11-15_metrics.json` (**n_cham = 12**, p05 = 0,5058),
  `data/miou_synthetic_2026-11-14_metrics.json` (**n_cham = 5**, p05 = 0,9239),
  `docs/media/traj/binh1_vat_ra_khung.json` (drift n = 271).
- Quy ước: `AGENTS.md` §2 (log), §6 (kết luận đã đo), §7b (1 nhánh/nhiệm vụ + PR), §9.1 (review độc lập).

## 🔨 Công việc đã thực hiện
1. **Dọn tracker 19/20** (nhánh `chore/dong-ticket-19-20`, PR **#25**, merge commit `d31e376`):
   commit đúng 12 dòng `**Status:** resolved` + `## Answer` đã nằm sẵn trong working tree từ 11-11.
   Không đổi code. CI (`ruff`, `pytest (fast lane)`) xanh trước khi merge.
2. **Một cửa duy nhất cho phân vị** — `src/drift_samples.py`:
   - thêm `phan_vi(values, q=5, min_samples=MIN_SAMPLES, digits=4) -> float | None`: `None` khi
     `n < 30`, kèm giải thích số học "với n nhỏ, p05 **chính là** min (chỉ số `0,05 × (n−1)` nằm giữa
     min và phần tử nhỏ thứ hai)";
   - `summarize()` và `static_control()` đi qua `phan_vi()`; **tiêu chí đạt** của `static_control` vẫn
     dùng `min_samples = 20` (ticket 15 yêu cầu `drift_n ≥ 20`) nhưng **p05 chỉ công bố từ 30 mẫu**;
   - comment của `MIN_SAMPLES` liệt kê **mọi** chỗ công bố p05 và nói rõ p05 theo **cửa sổ**
     (`rolling_p05`, `flag_rate`, `low_p05_low_empty`) **không** bị ngưỡng này chi phối (ở đó "đủ mẫu"
     do chính cửa sổ quyết định), để phiên sau không "thống nhất" nhầm chúng thành 30.
3. **`scripts/score_miou.py`**: bỏ hằng `5`; `cham()` trả thêm `mIoU_p05_n` (cỡ mẫu) và
   `mIoU_p05_nguong` (30); CLI in `mIoU_p05 = CHƯA CÔNG BỐ (n < 30)` thay vì **im lặng bỏ dòng** —
   im lặng thì người đọc artifact cũ vẫn tưởng `mIoU_p05 = 0,9239` còn hiệu lực.
4. **`scripts/make_trajectory_media.py`**: bỏ hằng `20`, dùng `phan_vi`; thêm `nguong_p05` và đưa cả
   `thong_ke` vào **file provenance JSON** (trước đây các số này chỉ in ra stdout ⇒ `.json` đi kèm ảnh
   không nói được p05 có được công bố hay không); cảnh báo thiếu mẫu dùng `MIN_SAMPLES`.
5. **Sinh lại artifact trên cây sạch** (`git_dirty_code = false`):
   - `data/miou_binh1_hopbao_2026-11-15_metrics.json` → `mIoU = 0,6464` (không đổi), **`mIoU_p05 = None`**
     (`mIoU_p05_n = 12` < 30) — trước là 0,5058 từ 12 frame;
   - `docs/media/traj/binh1_vat_ra_khung.json` → thêm `thong_ke` (`drift_n = 271`, `nguong_p05 = 30`,
     `drift_iou_p05 = 0,0` **vẫn công bố** vì 271 ≥ 30), cổng `--expect-bbox` vẫn `khop` IoU 0,7115.
   - Artifact fixture tổng hợp (`miou_synthetic_2026-11-14`, n = 5 → p05 0,9239) **không sinh lại được**:
     mask của nó nằm ở `/tmp/demo_gt4/masks` đã mất, muốn sinh lại phải dump mask mới (SAM 2 không tất
     định ⇒ số sẽ khác, làm lệch các chỗ đang trích `mIoU = 0,9354`). Xử lý: ghi rõ trong
     `docs/so-lieu-bao-cao.md` (**sinh từ** `scripts/so_lieu_bao_cao.py`) là **cấm trích p05 của nó**.
6. **Docs**: `AGENTS.md` §6 thêm kết luận "mọi `*_p05` đi qua một ngưỡng 30" + hệ quả (GT thật `binh1`
   chỉ 12 frame ⇒ `mIoU_p05 = None`; `None` = "chưa công bố", không phải "p05 = 0"); 2 dòng của
   `docs/so-lieu-bao-cao.md` được cập nhật qua `scripts/so_lieu_bao_cao.py` rồi `--check` xanh;
   `docs/thuoc-do-bam-dung.md` giải thích tại sao `mIoU_p05` là `None` trên artifact 12 frame.

## 📤 Output / Kết quả
- **Chỉ còn MỘT hằng ngưỡng** cho phân vị: `MIN_SAMPLES = 30`, ghim bằng test
  `MIN_SAMPLES == live_tracking._STAT_MIN_SAMPLES`; mọi chỗ công bố p05 đi qua `phan_vi()`.
- Artifact tái lập được: `git_rev b6e7a8d`… `0f8542f`, `git_dirty_code false`; artifact được **sinh lại
  sau rebase** vì rebase đổi SHA (nếu không `git_rev` thành con trỏ chết — đúng bẫy provenance của repo).
- `./run lint` xanh · `./run test` **1298 passed**, 5 deselected (86 s).
- Test mới (8): `phan_vi` dưới/đủ ngưỡng · mảng rỗng và n = 1 không bịa số · `static_control` 25 mẫu
  vẫn ĐẠT nhưng p05 `None` · `cham()` với 5 / 25 / 30 frame · `make_trajectory_media` 29 mẫu ⇒ `None` ·
  CLI traj ghi `thong_ke` vào provenance.
- **Kiểm "có răng"**: hạ `MIN_SAMPLES` về **20** ⇒ 4 test đỏ; về **5** ⇒ 6 test đỏ (đã chạy thật, rồi
  khôi phục file).
- File thay đổi:
  - `src/drift_samples.py` — `phan_vi()`, comment `MIN_SAMPLES`, `static_control`/`summarize` dùng chung
  - `scripts/score_miou.py` — bỏ hằng 5, `mIoU_p05_n`/`mIoU_p05_nguong`, CLI in "CHƯA CÔNG BỐ"
  - `scripts/make_trajectory_media.py` — bỏ hằng 20, `thong_ke` vào provenance, cảnh báo dùng hằng chung
  - `scripts/so_lieu_bao_cao.py` + `docs/so-lieu-bao-cao.md` — ghi cảnh báo p05 của 2 artifact
  - `AGENTS.md`, `docs/thuoc-do-bam-dung.md` — kết luận ngưỡng 30 + hệ quả
  - `tests/test_drift_samples.py`, `tests/test_score_miou.py`, `tests/test_make_trajectory_media.py` — 8 test
  - `data/miou_binh1_hopbao_2026-11-15_metrics.json`, `docs/media/traj/binh1_vat_ra_khung.json` — sinh lại

## 🐞 Vấn đề gặp phải & cách xử lý
- **`git_dirty_code = true` ở lần sinh artifact đầu tiên**: nguyên nhân không phải code mà là
  `.scratch/…/23-…md` (tracker vừa `claim`) — hàm `_dirty_code()` chỉ miễn trừ `data/` và `docs/media/`.
  Xử lý: commit file ticket trước rồi sinh lại; nay cả 2 artifact ghi `git_dirty_code: false`.
- **`git rev-parse` sau rebase**: rebase `feat/p05-mot-nguong` lên `origin/main` (đã merge PR #25) làm
  đổi SHA của chính commit chứa code sinh artifact ⇒ `git_rev 940ae09` không còn tồn tại. Xử lý: sinh
  lại artifact ở HEAD mới + commit riêng ("sinh lại artifact sau rebase"). Đây là biến thể của quy ước
  "PR có artifact phải merge commit, không squash".
- **`thong_ke` không vào JSON**: `draw()` trả `(fig, thong_ke)` nhưng `main()` chỉ in ra stdout ⇒ bổ
  sung `meta["thong_ke"]` và một test CLI canh (nếu không, `drift_iou_p05 = None` trong JSON không đọc
  được là "n < 30").
- **Backtick trong commit message bị bash thực thi** (`thong_ke: command not found`) ⇒ amend lại bằng
  `git commit -F file`. Nhắc cho phiên sau: viết message qua file khi có backtick.
- **PR/merge khi không có `gh` CLI**: REST API bằng token của Git Credential Manager
  (`git credential fill`). Bẫy nhỏ: endpoint merge là **PUT**; `urllib` với `data=` mặc định là **POST**
  ⇒ 404 vô nghĩa dù PR `mergeable: true`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Ticket **#24**: `vos_every = 1` không bao giờ ghi `mask_age_total_ms` (đúng cấu hình đã dùng cho
      mIoU fixture và các số "1 luồng 8,8 FPS").
- [ ] Ticket **#26**: `--dump-mask-frames` chạy trong cửa sổ `post_ms` (dụng cụ đo làm bẩn số đang đo);
      chọn lại ô giữa phiên chưa có test canh.
- [ ] Ticket **#22**: test `tracker_engine` IoU đỏ khi chạy full suite (flaky) — cần đo tần suất (n ≥ 3
      lần full suite) trước khi sửa, không nới ngưỡng im lặng.
- [ ] Ticket **#14**: vẫn **chờ dữ liệu** — cần clip có `drift_iou_p05 < 0,30` mà `empty ≈ 0`.
- [ ] Việc của người dùng: **tô silhouette 10–20 frame `binh1`** ⇒ mIoU phân đoạn thật; muốn `mIoU_p05`
      có nghĩa thì cần **≥ 30 frame** GT (ngưỡng mới).
- [ ] Muốn p05 của fixture tổng hợp dùng được: dump lại mask (SAM 2 không tất định ⇒ số mới) rồi sinh
      artifact mới, thay vì trích artifact 14-11.

## 📚 Tài liệu tham khảo
- `AGENTS.md` §6 (`0/None ≠ đã đo`, "số 0,0 trong artifact là cạm bẫy"), §7b (git/PR), §9.1 (review).
- `docs/thuoc-do-bam-dung.md`, `docs/so-lieu-bao-cao.md`, `.scratch/camera-ai-realtime/issues/23-…md`.
- `src/drift_samples.py` (docstring `rolling_p05`/`static_control`), `src/live_tracking.py:54-60`.
