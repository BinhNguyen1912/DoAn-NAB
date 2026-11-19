# 19-11-2026 — Kiểm chứng cuối ngày: diễn tập THẬT + full suite (sau 9 PR)

## Mục tiêu

Hôm nay có 9 PR chạm **đường chạy mỗi frame** của phiên live (`_update_stats_locked`,
`_apply_drift_locked`, `_lk_ok_of`, cờ `suc_khoe`) nhưng làn nhanh (`pytest -m "not slow"`) **không**
nạp model SAM 2 ⇒ chưa chứng minh gì trên pipeline thật. Phiên này chạy hai cửa kiểm còn thiếu:
`./run democheck --full` (diễn tập thật, có nạp model) và `./run testall` (full suite).

## Input

- `main` = `fe43006`, cây sạch.
- `data/binh1.mp4` (720×1280, 333 frame), ô chai `300,275,150,410`, checkpoint tiny.

## Công việc đã thực hiện

1. `./run democheck --source data/binh1.mp4` (không nạp model) — trước đó `web/dist` **CŨ hơn** `web/src`
   (mình sửa `api.ts`/`live.ts`/`LivePanel.tsx` sau lần build trước) ⇒ chạy `./run web` rồi kiểm lại.
2. `./run democheck --full --bbox 300,275,150,410 --source data/binh1.mp4`.
3. Đọc `status.json` của **chính phiên diễn tập** để xác nhận cờ #14 chạy trên đường thật.
4. `./run testall` (full suite, có nạp model).

## Output / Kết quả

**(a) `democheck` không `--full`: 8 OK · 1 cảnh báo · 0 LỖI** (cảnh báo còn lại là "API chưa chạy", đúng).

**(b) `democheck --full`: 10 OK · 0 cảnh báo · 0 LỖI** — `diễn tập phiên: +298 frame / 10 s, mask 9,5 FPS`,
`mã nguồn fe43006 — sạch`.

**(c) Cờ #14 trên phiên thật** (`/dev/shm/doan-live/status.json`):
```json
"suc_khoe": {"co": "drift_trend", "n": 30, "p05": 0.0, "empty_frac": 0.0, "empty_so_mau": 0,
             "cua_so": 30, "nguong_vao": 0.3, "nguong_ra": 0.45, "empty_tran": 0.03,
             "empty_min_mau": 2, "empty_chua_do": false,
             "ly_do": "p05 thấp nhưng mask KHÔNG rỗng ⇒ ô hiển thị và ô VOS bất nhất"}
"suc_khoe_cau": "Chất lượng bám: ô hiển thị lệch ô VOS (p05 0.00, mask rỗng thấp)"
"drift_n": 61, "drift_iou_p05": 0.0, "cau_hinh": {"lk_max_mad": 1.5, ...}
```
⇒ cờ **bật đúng** trên chính `binh1` (đoạn ô chai trượt như PR #48 kết luận), `cau_hinh.lk_max_mad`
echo đúng 1,5, và `drift_n 61` vs `suc_khoe.n 30` **khác cửa sổ** đúng như tài liệu đã ghi.

**(d) `./run testall`: 1512 passed** (5 FutureWarning của torch, không phải lỗi), 210 s.

## Vấn đề & cách xử lý

- `democheck --source 0` báo **LỖI** ở mục nguồn: webcam WSL vẫn kẹt driver `usbipd` (AGENTS §6) —
  **không phải regression** của hôm nay. Kiểm bằng clip: 0 LỖI.
- `web/dist` cũ là cảnh báo **thật** (demo sẽ chạy mã UI cũ không có dòng cờ mới) — đã build lại.
  Bài học: sau khi sửa `web/src`, chạy `./run web` **trước** `democheck`, không chỉ `npm run build`
  (democheck so mtime của `dist` với `src`).
- Hai lần trong ngày mình commit nhầm lên **local** `main` (vi phạm §7b). Cả hai lần phát hiện **trước
  khi push**, đã `git reset --hard origin/main` rồi mở PR riêng (`#51`, `#55`) ⇒ `origin/main` không bị
  ảnh hưởng. Đã ghi vào memory: kiểm `git branch --show-current` trước mỗi commit.

## Next steps

- Chờ **GT 12 frame** của người dùng ⇒ mIoU ⇒ chốt `max_mad` (1,5 vs 6,0), đổi nhãn HUD thành "LK trượt",
  hiệu chuẩn `EMPTY_TRAN`.
- Ticket #11/#09/#21 vẫn cần dữ liệu/thiết bị từ người dùng.

## Tài liệu tham khảo

- `./run democheck`, `./run testall`, `docs/task/19-11-2026-co-phan-quyet-chat-luong-bam.md`
- ticket #14 (comment 19-11), PR #54/#55
