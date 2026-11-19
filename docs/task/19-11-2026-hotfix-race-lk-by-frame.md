# 19-11-2026 — Hotfix P1: `_lk_ok_of` duyệt `deque` **ngoài lock** (lỗi do chính PR #50 vừa merge)

## Mục tiêu

Reviewer độc lập của PR #50 (bị treo 30 phút, trả kết quả **sau khi** PR đã merge) bắt một **P1 race**
trong đúng đoạn code mình vừa thêm. Sửa ngay bằng PR hotfix riêng, có test bắt hồi quy.

## Input

- `src/live_tracking.py`: `_lk_by_frame` được **append trong `_stats_lock`** (`_update_stats_locked`),
  còn `_measure_drift` chạy ở **luồng VOS**.
- Bản #50 gọi `self._lk_ok_of(frame_idx)` ở **nhánh đo-ngay**, tức **ngoài** `_stats_lock`.

## Công việc đã thực hiện

1. **P1 (chặn)**: tra `lk_ok` **trong chính `with self._stats_lock`** đã có sẵn của `_measure_drift`
   (`lk_ok = self._lk_ok_of(frame_idx) if found else None`), rồi truyền biến đó xuống.
   Hệ quả nếu để nguyên: CPython có thể ném `RuntimeError: deque mutated during iteration` ⇒
   `_VosWorker` bắt `Exception` ⇒ `_on_error` ⇒ **cả phiên live thành `state=error`** (không chỉ mất một
   mẫu số liệu). Xác suất thấp (cửa sổ µs, ~7 lần VOS/s) nhưng đây là regression, không phải lý thuyết.
2. **P2**: mẫu `_pending_drift` bị kết quả VOS mới **đẩy ra** từng ghi `lk_ok = None` chụp lúc frame
   *chưa* phát ⇒ mất khỏi mẫu số của `lk_ok_frac` **một cách không ngẫu nhiên** (chỉ các frame "VOS về
   trước khi phát"). Nay **tra lại trong lock** lúc drain.
3. **Test bắt hồi quy** (`TestLkByFrameDuyetTrongLock`): dùng `deque` con ghi lại `lock.locked()` mỗi lần
   `__reversed__` (đúng khuôn `_DequeTheoDoi` đã dùng cho `_shown_by_frame`) ⇒ duyệt ngoài lock là **đỏ**.

## Output / Kết quả

- `./run lint` xanh · `tests/test_live_tracking.py` **xanh toàn bộ**.
- **Diễn tập ngược 2/2 mutant bị bắt**: (a) đưa `_lk_ok_of` ra ngoài lock ⇒ `test_do_lk_ok_duoi_lock` đỏ;
  (b) drain dùng `None` thay vì tra lại ⇒ `test_pending_bi_day_ra_van_tinh_lai_lk_ok` đỏ.
- Số liệu đã công bố (0,093 = 4/43; 0,10 = 5/50) **không đổi**: reviewer xác nhận mức hụt mẫu do cơ chế
  này = 0 ngoài frame 0 ở artifact đó (`queue_ms` 83,6 ms ⇒ VOS luôn chậm hơn nhịp phát).

## Vấn đề & cách xử lý

- **Quy trình**: PR #50 merge khi review còn treo; kết quả về muộn và bắt được P1. Bài học ghi lại: khi
  reviewer timeout, **phải** chạy lại (§9.3) và **chỉ merge sau khi có kết quả** — lần này mình merge
  trước rồi mới nhận P1, nên phải mở hotfix.
- Reviewer cũng đúng ở P3: 32/83 dòng CSV không có `lk_ok` (frame chưa từng phát) ⇒ câu chữ phải là
  "~90 % **của 50 mẫu có `lk_ok`**", không phải "90 % thời gian" trống. Đã sửa trong log #50.

## Next steps

- Ticket **#38** (A/B `max_mad`) vẫn là việc lớn tiếp theo của LK.
- Ticket **#14** (cờ `drift_trend`) giờ có đủ đầu vào trực tiếp (`drift_iou` + `lk_ok`), không cần phát lại.

## Tài liệu tham khảo

- `docs/task/19-11-2026-csv-drift-ghi-o-hien-thi-va-lk-ok.md` (PR #50), `src/live_tracking.py:1158-1220`
- `tests/test_live_tracking.py::TestLkByFrameDuyetTrongLock`, `AGENTS.md` §9.1/§9.3
