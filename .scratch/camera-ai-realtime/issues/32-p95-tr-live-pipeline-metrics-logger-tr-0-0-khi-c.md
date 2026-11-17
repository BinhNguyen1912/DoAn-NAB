# 32: p95 độ trễ ở live_pipeline/metrics_logger trả 0.0 khi chưa có mẫu (bẫy 0/None, P3 của review #23)

**What to build:** `src/live_pipeline.py:54-55` (`Stats.p95_ms`) và `src/metrics_logger.py:117-120` (`p95_ms`) trả **0.0** khi danh sách latency rỗng, và công bố p95 của 1–5 frame như một p95 thật (≈ max). Đây đúng bẫy `0/None` mà `AGENTS.md` §6 cấm, nhưng ở **đại lượng khác** `*_p05` (độ trễ offline, không phải drift/mIoU) nên **không** thuộc phạm vi ticket #23 — tách ra đây để không im lặng bỏ qua.

Phát hiện bởi review độc lập 17-11 (P3, câu hỏi (a): "còn chỗ công bố `*_p05`/`*_p95` ngoài ngưỡng chung?").

**Cách làm:** trả `None` + `p95_ms_n` (và/hoặc dùng `drift_samples.MIN_SAMPLES` nếu p95 cũng cần ngưỡng), cập nhật mọi consumer (CSV/`summary.json`/plot/`run` CLI in), thêm test `n == 0 ⇒ None` và `n < ngưỡng ⇒ None`.

**Cẩn thận:** đổi hợp đồng của `metrics_logger` ⇒ phải sửa `scripts/plot_metrics.py` + mọi chỗ đọc `p95_ms` (kể cả báo cáo đang trích số p95 latency), và không được nới ngưỡng im lặng.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `p95_ms` trả `None` (không phải 0.0) khi chưa có mẫu, kèm `p95_ms_n`; test ghim cả hai ca (n=0, n nhỏ hơn ngưỡng)
- [ ] Mọi consumer (`scripts/plot_metrics.py`, `summary.json`, CLI `./run fast`/`demo`) xử lý `None` mà không in '0 ms' hay vẽ đường 0
- [ ] Số p95 latency trong docs/báo cáo được rà lại: số nào đo bằng code cũ thì ghi rõ hoặc sinh lại artifact
