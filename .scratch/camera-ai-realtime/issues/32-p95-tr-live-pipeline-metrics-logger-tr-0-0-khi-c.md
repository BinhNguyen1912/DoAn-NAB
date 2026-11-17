# 32: p95 độ trễ ở live_pipeline/metrics_logger trả 0.0 khi chưa có mẫu (bẫy 0/None, P3 của review #23)

**What to build:** `src/live_pipeline.py:54-55` (`Stats.p95_ms`) và `src/metrics_logger.py:117-120` (`p95_ms`) trả **0.0** khi danh sách latency rỗng, và công bố p95 của 1–5 frame như một p95 thật (≈ max). Đây đúng bẫy `0/None` mà `AGENTS.md` §6 cấm, nhưng ở **đại lượng khác** `*_p05` (độ trễ offline, không phải drift/mIoU) nên **không** thuộc phạm vi ticket #23 — tách ra đây để không im lặng bỏ qua.

Phát hiện bởi review độc lập 17-11 (P3, câu hỏi (a): "còn chỗ công bố `*_p05`/`*_p95` ngoài ngưỡng chung?").

**Cách làm:** trả `None` + `p95_ms_n` (và/hoặc dùng `drift_samples.MIN_SAMPLES` nếu p95 cũng cần ngưỡng), cập nhật mọi consumer (CSV/`summary.json`/plot/`run` CLI in), thêm test `n == 0 ⇒ None` và `n < ngưỡng ⇒ None`.

**Cẩn thận:** đổi hợp đồng của `metrics_logger` ⇒ phải sửa `scripts/plot_metrics.py` + mọi chỗ đọc `p95_ms` (kể cả báo cáo đang trích số p95 latency), và không được nới ngưỡng im lặng.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] `p95_ms` trả `None` (không phải 0.0) khi chưa có mẫu, kèm `p95_ms_n`; test ghim ca n=0 và ca toàn bộ frame đóng băng (KHÔNG có ngưỡng tối thiểu cho `p95` độ trễ — xem Answer)
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

## Answer (vòng 2 — sau review độc lập)

Review vòng 1: **0 P0, 3 P1/P2 còn lại đã sửa**:

- **P1 `run summary` CRASH**: `run:505` dùng `d.get("p95_latency_ms", 0):7.0f` — `.get(k, 0)` chỉ cứu
  khi THIẾU khoá, còn `null` thì `f"{None:7.0f}"` ném `TypeError` và chết giữa vòng lặp (các file sau
  không được in). Nay in `chưa đo` / `(n=…)`; có test `tests/test_run_script.py` dựng summary có
  `p95_latency_ms: null` rồi chạy `./run summary`.
- **P2 `plot_compare` vẽ cột 0**: lọc các lần đo `n_do_ms == 0` ra khỏi ảnh so sánh (vẽ cột `0` trên
  thang log = nói "xử lý tức thì"), trả `None` khi còn < 2 lần đo có mẫu; 2 test.
- **P2 `mean` không có `_n`**: thêm `mean_latency_ms_n` (+ `SessionSummary.mean_n`, + comment tại chỗ,
  + `run_live` in `mean=chưa đo` khi `n == 0`). `mean` vẫn giữ `0,0` vì `effective_fps = 1000/mean` là
  hợp đồng cũ — ngoại lệ này nay **ghi trong code** và trong ticket.
- **P2 thiếu test cho `live_pipeline.p95_ms`/`_p95_txt`**: thêm `tests/test_live_pipeline_summary.py`
  (rỗng ⇒ `None`, có mẫu ⇒ kèm `n`, `_p95_txt` với `None`/có số/artifact cũ thiếu khoá `n`).
- **P3 `n=None`**: `_p95_txt` in `n=?` cho artifact cũ thiếu khoá.

**Không sửa (có lý do, đã ghi):**
- Chưa áp ngưỡng `n >= 30` cho `p95` độ trễ: ngưỡng đó sinh ra cho **phân vị của một dãy mẫu dùng để
  phán quyết** (drift/mIoU). `p95` độ trễ là số **mô tả** của một phiên (mỗi frame là một mẫu), và
  consumer (web `SummaryTable`, `colab_run_all`, báo cáo) đang đọc nó như số của phiên — áp ngưỡng sẽ
  biến mọi phiên ngắn thành `None` mà không giải quyết bẫy nào. Bù lại: **mọi chỗ in p95 độ trễ nay in
  kèm `n`** (CLI, `run summary`), và ticket ghi rõ ngoại lệ này thay vì để checkbox nói sai.
- `web/src/api.ts` (`p95_latency_ms?: number`) và `SummaryTable` chưa hiện `n`: là thay đổi FE (cần
  `./run webtest` + `./run e2e`) ⇒ **đã tách thành ticket #33**, không trộn vào PR backend.
- Số p95 latency đã công bố trong `docs/` đo bằng code cũ (không có `_n`): chúng có `n > 0` nên vẫn
  dùng được, nhưng khi trích phải ghi rõ cỡ mẫu nếu biết.
