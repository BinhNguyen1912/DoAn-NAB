# Ngày 17-11-2026 — Ticket #32: `p95` độ trễ trả `None` khi chưa có mẫu (+ `./run summary` không crash)

## 🎯 Mục tiêu
- Đóng ticket **#32** (P3 của review ticket #23): `p95` độ trễ trả `0.0` khi danh sách latency rỗng —
  đúng bẫy `0/None` mà `AGENTS.md` §6 cấm, và `p95` của 1–5 frame vẫn được công bố như phân vị thật.
- Không nới ngưỡng/không im lặng: mọi chỗ đọc `p95` phải phân biệt được "chưa đo" với "0 ms".

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/32-…md`.
- Code: `src/metrics_logger.py` (`_summary_core`), `src/live_pipeline.py` (`SessionSummary`),
  `tools/run_live.py` (CLI), `scripts/plot_metrics.py` (bảng + ảnh so sánh), **`run` (lệnh `summary`)** —
  consumer bị bỏ sót ở vòng 1.
- Quy ước: `AGENTS.md` §6, §9.1; `requirements.txt` (`pytest-timeout`).

## 🔨 Công việc đã thực hiện
1. **`metrics_logger`**: `p95_latency_ms = None` + `p95_latency_ms_n` khi không có mẫu đo được — **kể cả
   ca TOÀN BỘ frame đóng băng** (trước rơi về `0,0`). `mean_latency_ms` giữ `0,0` (vì
   `effective_fps = 1000/mean` là hợp đồng cũ) nhưng nay có `mean_latency_ms_n` + comment tại chỗ.
2. **`live_pipeline.SessionSummary`**: `p95_ms → float | None` + property `p95_n`, `mean_n`.
3. **Consumer**:
   - `tools/run_live.py`: in `p95=chưa đo (0 mẫu đo được)` hoặc `p95=120 ms (n=600)`; `mean` cũng kèm `n`.
   - `scripts/plot_metrics.py`: bảng in "—" cho `None`; **phiên mất dấu toàn bộ** nay là "chưa đo"
     (bản cũ rơi về mảng 0 ⇒ in mean 0/p95 0); `lost_ratio` không chia 0; **ảnh so sánh** bỏ các lần
     đo không có mẫu (không vẽ cột `0` trên thang log).
   - **`run summary`**: `d.get("p95_latency_ms", 0):7.0f` từng **crash** (`TypeError`) khi giá trị là
     `null` (`.get(k, 0)` chỉ cứu khi THIẾU khoá) ⇒ chết giữa vòng lặp, các file sau không được in.
     Nay in `chưa đo` / `(n=…)`.

## 📤 Output / Kết quả
- Không còn chỗ nào biến "chưa đo" thành `0 ms` (trừ `mean` — có `_n` + comment + in "chưa đo" ở CLI).
- `./run lint` xanh · `./run test` **1316 passed**, 5 deselected.
- Test mới: summary rỗng ⇒ `None`/`n=0`; toàn đóng băng ⇒ `None`; `p95` có `_n`; `mean_n`;
  `summarize` của `plot_metrics` (rỗng + toàn đóng băng); `plot_compare` không vẽ khi < 2 lần đo có
  mẫu; `SessionSummary.p95_ms/p95_n/mean_n`; `_p95_txt` (None / có số / artifact cũ thiếu `n`);
  `./run summary` với `p95_latency_ms: null` (chạy thật script).
- File thay đổi: `src/metrics_logger.py`, `src/live_pipeline.py`, `tools/run_live.py`,
  `scripts/plot_metrics.py`, `run`, `tests/test_metrics_logger.py`, `tests/test_plot_metrics.py`,
  `tests/test_live_pipeline_summary.py` (mới), `tests/test_run_script.py`.

## 🐞 Vấn đề gặp phải & cách xử lý
- **`./run summary` crash (P1 review)**: xem mục 3 — đây là consumer **không test nào chạy**, nên vòng 1
  lọt. Nay có test dựng `data/zz_test_null_summary.json` rồi gọi `./run summary`.
- **`plot_compare` vẫn vẽ cột 0 (P2 review)**: `s["p95_ms"] or 0.0` biến `None` thành 0 trên thang log.
  Sửa: lọc theo `n_do_ms`, trả `None` khi < 2 lần đo có mẫu.
- **Hai encoding cho `lost_ratio`** (`metrics_logger` trả `0.0`, `plot_metrics` trả `None` khi rỗng):
  chưa thống nhất — ghi ở Next steps (đổi `metrics_logger` phải sửa web/báo cáo).

## ✅ Review độc lập (AGENTS §9.1)
- Agent `reviewer` (chỉ đọc): **0 P0**, **1 P1** (`run summary` crash) + 3 P2 + 3 P3 — **đã sửa**: P1,
  `plot_compare`, `mean` thiếu `_n`, thiếu test cho `live_pipeline`/`_p95_txt`, `n=None` ở artifact cũ.
- **Không sửa, có lý do (ghi trong ticket):** chưa áp ngưỡng `n ≥ 30` cho `p95` độ trễ — ngưỡng đó
  sinh ra cho **phân vị phán quyết** (drift/mIoU), còn `p95` độ trễ là số **mô tả** của một phiên và
  consumer đang đọc nó như vậy; bù lại **mọi chỗ in đều kèm `n`**. Phần FE (`api.ts`, `SummaryTable`
  hiện `n`) tách ticket vì cần `./run webtest` + `./run e2e`.
- Báo cáo đầy đủ: `.scratch/rev26-32.md`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] `web/src/api.ts`: `p95_latency_ms?: number | null` + `p95_latency_ms_n?: number`, và
      `SummaryTable` in "— (0 mẫu)" / "119 ms (n=4)".
- [ ] Thống nhất `lost_ratio` rỗng: `None` ở cả hai chỗ (kèm `lost_ratio_n`) hoặc ghi ngoại lệ.
- [ ] Rà các số `p95` latency đã công bố trong `docs/` (đo bằng code cũ, không có `_n`): chúng có
      `n > 0` nên vẫn dùng được — nhưng khi trích phải ghi rõ cỡ mẫu nếu biết.

## 📚 Tài liệu tham khảo
- `AGENTS.md` §6; `.scratch/rev26-32.md`; `tests/test_metrics_logger.py`, `tools/run_live.py`.
