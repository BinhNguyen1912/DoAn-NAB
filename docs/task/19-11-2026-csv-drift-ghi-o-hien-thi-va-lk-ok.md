# 19-11-2026 — CSV drift ghi **ô đang hiển thị** + `lk_ok`: cơ chế đo trực tiếp, và phát hiện LK `ok` chỉ ~9 %

## Mục tiêu

`drift_iou = IoU(ô đang hiển thị, ô VOS)` nhưng CSV **chỉ ghi ô VOS** ⇒ không trả lời được "ai sai".
Ngày 19-11 phải dựng `scripts/replay_lk_frame.py` để **suy ra**, và bản phát lại chỉ khớp CSV ở **3/6**
cặp (đường đa luồng: `base` lúc phát phụ thuộc VOS trước đã về chưa). Mục tiêu: ghi trực tiếp 2 thứ đó.

## Input

- `src/live_tracking.py::_result_threaded` (`_interp.update` → `ok`), `_shown_by_frame`
  (`src/live_tracking.py:1134-1146`), `src/drift_samples.py::CSV_HEADER`.
- Artifact cũ `data/drift_samples_binh1_2026-11-14_*.csv` (không có 2 cột này — phải đọc ra `None`).

## Công việc đã thực hiện

1. `CSV_HEADER` thêm **5 cột**: `hien_thi_x1..y2` (ô người xem đã thấy) và `lk_ok`
   (`1` = LK ok, `0` = LK `not-ok` ⇒ pipeline phát **ô base**, trống = chưa đo).
2. `live_tracking`: `_lk_by_frame` song song `_shown_by_frame`; `_lk_ok_frame` đặt trong
   `_result_threaded` (`= ok`), `None` ở `_result_inline` (tắt LK); `_lk_ok_of(frame)`; truyền vào
   **cả 4** đường ghi CSV (đo ngay, `_pending_drift`, `_flush_pending_csv`, `_update_stats_locked`).
3. `read_samples` đọc 2 cột mới; CSV cũ ⇒ `None` (chưa đo), **không** phải `0`/`False`.
4. `thong_ke_mau`/`summarize` thêm `n_lk_do_duoc` + `lk_ok_frac`; `analyze_drift_samples` in cột `lk_ok`.
5. Test: 3 test trong `tests/test_live_tracking.py` (công thức IoU cho **mọi** dòng; `lk_ok=0` ⇒ ô hiển
   thị = ô VOS của lần trước; CSV cũ vẫn đọc được) + 2 test `lk_ok_frac`; cập nhật kỳ vọng dict (không
   nới assert) + tuple `_pending_drift` trong 1 test cũ.

## Output / Kết quả

**Đo trực tiếp** (`data/lk_ok_binh1_2026-11-19_metrics.json`, `git_rev e4f4464`, `git_dirty_code false`,
`binh1` @192, `vos_every 3`, 12 s, khung `0:110` ∪ `165:262`):

| đại lượng | số |
|---|---|
| `n_drift` trong khung | 44 |
| `lk_ok_frac` trong khung | **0,093** |
| `lk_ok_frac` toàn dãy (51 mẫu) | **0,10** |
| `drift_iou_mean` trong khung | 0,4434 |
| `empty_frac` trong khung | 0,021 |

Hai kết quả quan trọng:

1. **Cột mới tự nhất quán**: `IoU(hien_thi, bbox)` vs `drift_iou` lệch **tối đa 4e-05** trên cả 25 mẫu
   của một lần chạy (chỉ do làm tròn 4 chữ số) ⇒ từ nay kiểm bằng **công thức**, không cần phát lại.
2. **LK trả `ok` chỉ ~9–10 % số mẫu** ở cấu hình này ⇒ **~90 % thời gian, ô người xem thấy là ô của lần
   VOS CŨ (đóng băng)**, không phải nội suy. Đây là số **đo**, thay cho suy luận trước đó; và nó nói
   rằng "HUD 30 FPS" **không** đồng nghĩa "nội suy mượt" — đúng cảnh báo `mask_age`, nhưng ở đây là ô
   bao chứ không chỉ mask.
   ⚠ **Chưa** kết luận được nguyên nhân (LK fail vì chuyển động nhanh? `max_mad`/`grid` quá chặt cho ô
   chai 150×410? hay vì `vos_every=3` = bước nhảy 3 frame) ⇒ **ticket riêng**, không sửa ngưỡng LK ở PR
   này.

## Vấn đề & cách xử lý

- Bản đầu tiên của mình chỉ truyền `lk_ok` cho **nhánh đo ngay**; test đỏ vì CSV toàn ô trống ⇒ phát
  hiện còn 3 nhánh ghi khác (`_pending_drift`, `_flush_pending_csv`, `_update_stats_locked`). Đã sửa cả
  4; tuple `_pending_drift` dài thêm 1 phần tử (test cũ khoá tuple ⇒ cập nhật tường minh, kèm ghi chú
  `None` = chưa biết LK, không phải `False`).
- Dòng của frame `engine.start()` **không có** `lk_ok` (chưa có lần phát nào) ⇒ test cho phép `None`
  **đúng 1** dòng đầu, các dòng còn lại bắt buộc có.
- Diễn tập ngược **2/2 mutant bị bắt**: (a) ghi `lk_ok=None` ⇒ 2 test đỏ; (b) ghi nhầm ô VOS làm ô hiển
  thị ⇒ test công thức đỏ.
- Vì sao không dùng `stability_shown`: nó đo **mask** hiển thị, còn đây là **ô bao**; hai đại lượng khác.

## Next steps

- **Ticket mới**: vì sao LK `ok` chỉ ~9 %? Đo tách bạch `max_mad`/`grid`/`min_points` và bước nhảy
  `vos_every`, trên 3 clip; nếu không cải thiện được thì phải **thôi hiển thị ô cũ** (hiện ô mờ/không vẽ
  ô giữa hai lần VOS) thay vì trình bày một ô sai như ô đang bám.
- Ngưỡng cờ `drift_trend` (ticket 14) nên dùng chính `lk_ok_frac` làm đầu vào phụ: `drift_iou = 0` **và**
  `lk_ok = 0` ⇒ "ô đóng băng", khác với `drift_iou = 0` **và** `lk_ok = 1` ⇒ "LK trượt".

## Tài liệu tham khảo

- `src/live_tracking.py:847-856` (reset base + `not ok` ⇒ `base_result`), `docs/task/19-11-2026-p05-theo-khung-va-mo-ticket-14.md`
- `data/lk_ok_binh1_2026-11-19_metrics.json`, `data/drift_samples_binh1_2026-11-19_123641.{csv,meta.json}`
- `AGENTS.md` §6 (`drift_iou` không phải độ chính xác; 0/None ≠ đã đo)
