# 32: p95 độ trễ ở live_pipeline/metrics_logger trả 0.0 khi chưa có mẫu (bẫy 0/None, P3 của review #23)

**What to build:** `src/live_pipeline.py:54-55` (`Stats.p95_ms`) và `src/metrics_logger.py:117-120` (`p95_ms`) trả **0.0** khi danh sách latency rỗng, và công bố p95 của 1–5 frame như một p95 thật (≈ max). Đây đúng bẫy `0/None` mà `AGENTS.md` §6 cấm, nhưng ở **đại lượng khác** `*_p05` (độ trễ offline, không phải drift/mIoU) nên **không** thuộc phạm vi ticket #23 — tách ra đây để không im lặng bỏ qua.

Phát hiện bởi review độc lập 17-11 (P3, câu hỏi (a): "còn chỗ công bố `*_p05`/`*_p95` ngoài ngưỡng chung?").

**Cách làm:** trả `None` + `p95_ms_n` (và/hoặc dùng `drift_samples.MIN_SAMPLES` nếu p95 cũng cần ngưỡng), cập nhật mọi consumer (CSV/`summary.json`/plot/`run` CLI in), thêm test `n == 0 ⇒ None` và `n < ngưỡng ⇒ None`.

**Cẩn thận:** đổi hợp đồng của `metrics_logger` ⇒ phải sửa `scripts/plot_metrics.py` + mọi chỗ đọc `p95_ms` (kể cả báo cáo đang trích số p95 latency), và không được nới ngưỡng im lặng.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] `p95_ms` trả `None` (không phải 0.0) khi chưa có mẫu, kèm `p95_ms_n`; test ghim cả hai ca (n=0, n nhỏ hơn ngưỡng)
- [x] Mọi consumer (`scripts/plot_metrics.py`, `summary.json`, CLI `./run fast`/`demo`) xử lý `None` mà không in '0 ms' hay vẽ đường 0
- [ ] Số p95 latency trong docs/báo cáo được rà lại: số nào đo bằng code cũ thì ghi rõ hoặc sinh lại artifact

## Answer

Đã xong phần code (17-11, `fix/p95-latency-null-khi-chua-do`):

- `metrics_logger._summary_core`: `p95_latency_ms = None` + `p95_latency_ms_n` (0 khi rỗng, và cả khi
  TOÀN BỘ frame đóng băng — trước đó p95 của mảng rỗng bị thay bằng `0,0`).
- `live_pipeline.Stats.p95_ms` → `None` + `p95_n`.
- Consumer: `tools/run_live.py` in "chưa đo (0 mẫu đo được)" / "120 ms (n=600)"; `scripts/plot_metrics.py`
  in "—" cho `None`, và phiên mất dấu TOÀN BỘ nay là "chưa đo" (bản cũ rơi về mảng 0 ⇒ in mean 0/p95 0);
  `lost_ratio` không chia cho 0.
- Test: 5 test mới (rỗng, toàn đóng băng, kèm `_n`, `summarize` rỗng/toàn đóng băng).

**Còn nợ (tiêu chí 3):** `mean_latency_ms` giữ `0,0` vì `effective_fps = 1000/mean` là hợp đồng cũ
(đổi nó phải sửa API/web/báo cáo); và các số p95 latency đã công bố trong `docs/` đo bằng code cũ —
chúng có `n > 0` nên vẫn dùng được, nhưng **artifacts cũ không có `p95_latency_ms_n`** ⇒ khi trích số
phải ghi rõ cỡ mẫu nếu biết, hoặc sinh lại artifact.
