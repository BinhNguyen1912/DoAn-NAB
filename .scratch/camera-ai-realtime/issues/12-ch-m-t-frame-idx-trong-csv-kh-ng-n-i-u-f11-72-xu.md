# 12: Chế độ mượt: frame_idx trong CSV không đơn điệu (f11..72 xuất hiện sau f180..186)

**What to build:** Bằng chứng thật (data/smooth_metrics.csv, lần chạy 27-10 của người dùng, 257 frame): khi gom các đoạn `lost=1` theo thứ tự file, thu được f39..52, f54..167, f169..178, f180..186, rồi **f11..72** — tức `frame_idx` KHÔNG tăng đơn điệu.

Nghi vấn: trong `src/smooth_display.py`, `InferenceWorker` ghi metrics từ luồng suy luận; khi `engine.start()` được gọi lại (chọn lại bằng `r` hoặc nhận lại sau mất dấu), bộ đếm frame của engine reset về 0 trong khi `ReIdSession._stamp_frame_idx` chỉ gán lại cho đường đi qua session — nếu worker ghi thẳng `result.frame_idx` thì số bị lùi.

Hệ quả: biểu đồ quỹ đạo/`./run charts` sai trục thời gian; đếm frame mất dấu theo đoạn cũng sai.

Phạm vi: chỉ sửa cách đánh số + test; KHÔNG đổi logic bám.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Xác định nguyên nhân: `frame_idx` do engine cấp bị reset khi `engine.start()` (chọn lại/nhận lại) trong chế độ mượt
- [x] CSV `smooth_metrics.csv` phải có `frame_idx` tăng đơn điệu (test: đọc CSV sau khi chạy fixture có 1 lần nhận lại)
- [x] Biểu đồ `./run charts` không bị lùi trục thời gian
- [x] `pytest -m "not slow"` + `ruff check .` xanh
