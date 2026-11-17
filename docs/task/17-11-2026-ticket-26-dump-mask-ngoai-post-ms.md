# Ngày 17-11-2026 — Ticket #26: ghi mask dump ngoài cửa sổ `post_ms` + không ghi đè âm thầm

## 🎯 Mục tiêu
- Đóng ticket **#26** (2 điểm tồn đọng của đường `--dump-mask-frames`, review hẹp 14-11):
  1. `_dump_mask` chạy **bên trong** cửa sổ `post_ms` ⇒ dụng cụ đo làm bẩn đúng số nó định đo
     (`post_ms` → `mask_age_total_ms`/p95, `cycle_ms`), ~1–3 ms @640×480, 5–15 ms @1080p, hơn nữa khi
     dump nhiều frame.
  2. Chọn lại ô giữa phiên: tên file mask đi theo **chỉ số frame VIDEO của phiên** ⇒ hai lần chọn có
     thể trùng tên; không có gì canh nên mask lần chọn cũ bị thay mà GT vẫn ghép theo số frame ⇒ mIoU
     SAI im lặng.

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/26-…md`; `src/live_tracking.py`
  (`_record_vos`, `_dump_mask`, `_write_mask_manifest`, `_store_vos`, `_after_vos`),
  `scripts/score_miou.py` (`kiem_khop_manifest`).
- Quy ước: `AGENTS.md` §6 ("số 0/None ≠ đã đo", "dụng cụ đo không được làm bẩn số đang đo"), §9.1.

## 🔨 Công việc đã thực hiện
1. **Tách `dump_ms` khỏi `post_ms`**: `_record_vos` trả `dump_ms` (thời gian THỬ ghi PNG); hai nơi gọi
   (`_store_vos` đường LK, `_after_vos` đường đơn luồng) **trừ** nó khỏi `post_ms`. `status.json` có
   khoá riêng `dump_ms`: `None` = **không có file nào được ghi** ở lần VOS đó (không yêu cầu dump,
   `mask is None`, `imwrite` fail), `0,0` = đã ghi, ghi cực nhanh.
2. **Ghi đè không im lặng**: file đích đã tồn tại ⇒ in CẢNH BÁO + tăng `so_file_ghi_de` (**sau khi**
   `imwrite` thành công) + khai vào `manifest.json`. Bỏ điều kiện "frame này phiên này chưa ghi" —
   chính ca "chọn lại ô giữa phiên" làm frame đó được ghi lần hai **trong cùng phiên**.
3. **Chặn double-dump tại nguồn**: frame `engine.start()` ở đường CÓ luồng VOS trước đây bị dump hai
   lần (`_after_vos` rồi worker `_store_vos` cùng `frame_video = 0`) ⇒ `_after_vos(..., dump=False)`
   cho đường LK, worker là nơi duy nhất ghi.
4. **`score_miou` đọc `so_file_ghi_de`** ⇒ cảnh báo MỀM ở chỗ CHẤM (stdout của worker không đi theo
   artifact, nên trước đây chỗ chấm vẫn im lặng).
5. **P3**: `frames_da_ghi` trong `manifest.json`; `dump_ms` vào allowlist **bắt buộc** của
   `status.json`; `measure_live_relay._worker_telemetry` giữ `dump_ms`; `cau_hinh.dump_mask_frames`
   echo cấu hình (artifact tự khai phiên có bật dump hay không).

## 📤 Output / Kết quả
- `post_ms` không còn bao gồm thời gian ghi PNG (đo bằng test: `_dump_mask` chậm 60 ms ⇒ `dump_ms ≈ 60`
  nhưng `post_ms < 30`); dump fail ⇒ `dump_ms = None` (không còn "đã dump, ghi cực nhanh").
- Ghi đè (kể cả cùng phiên) ⇒ CẢNH BÁO + `so_file_ghi_de` + manifest; `mask_000000.png` ở đường LK
  được ghi **đúng một lần** (test đếm `cv2.imwrite`).
- `./run lint` xanh · `./run test` **1312 passed**, 5 deselected.
- File thay đổi: `src/live_tracking.py`, `scripts/score_miou.py`, `scripts/measure_live_relay.py`,
  `tools/live_worker.py`, `tests/test_live_tracking.py`, `tests/test_score_miou.py`.

## 🐞 Vấn đề gặp phải & cách xử lý
- **`dump_ms` khai sai (P1 review)**: bản đầu gán `dump_ms` khi frame *nằm trong danh sách*, không hỏi
  *có file không* ⇒ frame `mask is None` vẫn báo `0,02 ms` ⇒ đọc thành "đã dump". Sửa: `_dump_mask`
  trả `bool`, status chỉ nhận số khi `True`.
- **Guard `_dumped` vô hiệu hoá đúng ca cần canh (P1 review)**: bản đầu `if dich.exists() and
  int(frame_idx) not in self._dumped` ⇒ lần ghi đè trong **cùng** phiên không cảnh báo, và test phải
  `discard(5)` thủ công mới "chứng minh" được — test đi đường khác đường thật. Sửa: bỏ điều kiện đó.
- **`cycle_ms` KHÔNG sạch (P2 review)**: `_dump_mask` chạy trong callback `_store_vos`, tức trong
  khoảng `bat_dau_i − bat_dau_{i−1}` của worker ⇒ dump của lần **trước** vẫn nằm trong `cycle_ms` của
  lần này; `queue_ms` cũng phình. Đã **sửa lời** (comment + docstring) thay vì trừ nhầm mẫu: chỉ
  `post_ms` là đã sạch. Trừ `cycle_ms` cần `_prev_dump_ms` — ghi vào Next steps kèm cách đo.

## ✅ Review độc lập (AGENTS §9.1)
- Agent `reviewer` (chỉ đọc, phiên riêng) review **hai** nhánh #26 + #32: **0 P1 chặn build, nhưng 2 P1
  thật ở #26** (nội dung ở mục 🐞) — **đã sửa hết**; 2 P2 (comment `cycle_ms`, `score_miou` không đọc
  `so_file_ghi_de`) + 3 P3 cũng đã sửa. Reviewer xác nhận: `dump_ms` không thể âm, lock đúng,
  không stale giữa các lần VOS, `--dump-mask-frames` rỗng thì `_co_dump`/`_dump_mask` khớp nhau.
- Báo cáo đầy đủ: `.scratch/rev26-32.md`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Trừ `cycle_ms` đúng mẫu: lưu `dump_ms` của lần VOS trước (`_prev_dump_ms`) và trừ vào `cycle_ms`
      của lần này; test `vos_every=3` + dump chậm 60 ms ⇒ `cycle_ms` không tăng.
- [ ] `dump_ms` vào snapshot `_vos_state` (hiện `status.json` có thể ghép `post_ms` lần N với `dump_ms`
      lần N+1).
- [ ] Đo thật ảnh hưởng của dump lên `cycle_ms` (phiên `vos_every 1` + dump gần như mọi frame) trước
      khi kết luận định lượng.
- [ ] `web/src/api.ts`: `p95_latency_ms`/`dump_ms` kiểu `number | null` (thuộc ticket #32/#26 phần FE).

## 📚 Tài liệu tham khảo
- `AGENTS.md` §6; `docs/thuoc-do-bam-dung.md` (mask dump + `manifest.json`); `.scratch/rev26-32.md`.
