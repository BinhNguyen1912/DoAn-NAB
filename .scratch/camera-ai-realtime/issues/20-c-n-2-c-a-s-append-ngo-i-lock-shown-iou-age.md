# 20: còn 2 cửa sổ `append` ngoài lock (`_shown_iou_window`, `_age_window`)

**What to build:** `src/live_tracking.py`: cùng mẫu sai mà ticket 17 vừa sửa cho `_drift_window`:

- `_shown_iou_window.append(...)` ở nhánh `_smooth` nằm **ngoài** `with self._stats_lock:`, rồi
  `sum()` **trong** lock;
- `_age_window.append(...)` + `np.fromiter(...)` ngoài lock (`_note_mask_age`).

Hôm nay **không phải lỗi**: mỗi cửa sổ chỉ có **một** luồng ghi (`_smooth` chạy ở luồng VOS *hoặc*
luồng chính tuỳ `vos_every`; `_note_mask_age` chỉ luồng chính). Nhưng đây đúng là mẫu code mà
comment 16 dòng trên trong `_measure_stability` cấm ("một luồng ghi ≠ miễn lock") — và đã bị bắt
2 lần trong review 09-11. Người sửa sau sẽ copy mẫu này vào chỗ có 2 luồng ghi.

Cách sửa: gộp `append` + tính thống kê vào CÙNG khối `with self._stats_lock`. Test: mở rộng bài
`TestDriftWindowChiMotNguonGhiTrongLock` thành tham số hoá cho cả 3 cửa sổ (deque tự báo nếu
`append` chạy khi không giữ lock).

**Blocked by:** None. **Status:** done

- [x] `append` của `_shown_iou_window` và `_age_window` đều nằm trong `_stats_lock`
- [x] Test tham số hoá kiểm cả 3 cửa sổ bằng deque tự theo dõi (đỏ khi trả append ra ngoài)
- [x] `./run test` + `./run testall` xanh

## Đã làm (10-11-2026)
- `_note_mask_age`: `append` + `np.fromiter` + `percentile` gộp vào CÙNG `with self._stats_lock`.
- `_smooth`: `append` + `sum()` của `_shown_iou_window` trong cùng lock.
- `TestDriftWindowChiMotNguonGhiTrongLock` → `TestCuaSoThongKeChiMotNguonGhiTrongLock`
  (`pytest.mark.parametrize` cho `_drift_window`, `_shown_iou_window`, `_age_window`; deque tự theo
  dõi). Đã kiểm "có răng": trả `append` của từng cửa sổ ra ngoài lock ⇒ đỏ đúng tham số đó.
