# 17: `_drift_window` có 2 luồng ghi và bị lặp ngoài lock ⇒ có thể `RuntimeError: deque mutated during iteration`

**What to build:** `src/live_tracking.py`: `_drift_window` (deque 200) bị **hai** nguồn ghi:

- `_record_drift()` (luồng VOS) — `append` **ngoài** `_stats_lock` rồi mới vào lock để tính lại thống kê;
- `_update_stats_locked()` (luồng chính, nhánh `_pending_drift`) — `append` **trong** lock.

Trong khi đó `_apply_drift_locked()` chạy `np.fromiter(self._drift_window, ...)` **trong** lock. Vì một nguồn ghi ở ngoài lock, deque có thể bị sửa giữa lúc `np.fromiter` duyệt ⇒ `RuntimeError: deque mutated during iteration` ⇒ luồng VOS chết ⇒ `state=error`.

Có từ 08-11 (trước nhánh chẩn đoán 09-11), phát hiện khi review nhánh `feat/chan-doan-chat-luong-bam` (P3). Chưa có test/đo nào chứng minh thực nghiệm — chỉ suy ra từ đường gọi.

Cách sửa: đưa `append` của `_record_drift` vào trong `_stats_lock` (cùng chỗ gọi `_apply_drift_locked`), hoặc thêm lock riêng cho deque. Test: hai thread ghi liên tục + một thread đọc thống kê 1.000 vòng (test kiểu "stress" phải **thấy** lỗi trước khi sửa, không phải chỉ xanh).

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Chỉ còn MỘT chỗ ghi `_drift_window` và mọi lần ghi đều dưới `_stats_lock`
- [x] Test stress: 2 thread gọi `_record_drift` + 1 thread đọc `_apply_drift_locked` 1.000 vòng, không ném `RuntimeError` (trước khi sửa phải đỏ)
- [x] `./run test` + `./run testall` xanh, không chậm thêm quá 5 %


## Đã làm (10-11-2026)
- Nhánh `feat/chan-doan-chat-luong-bam`: sửa + test bắt hồi quy (xem mục tick ở trên).
