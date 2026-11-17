# 17-11-2026 — Web: p95/mean độ trễ hiện kèm cỡ mẫu `n` (ticket #33)

## Mục tiêu

Đóng nợ FE của ticket #32: backend đã trả `p95_latency_ms = null` khi chưa có mẫu và gửi kèm
`p95_latency_ms_n`/`mean_latency_ms_n`, nhưng `web/src/api.ts` vẫn khai `p95_latency_ms?: number` (sai
kiểu) và `SummaryTable` in `119 ms` **không cho biết p95 dựa trên 4 hay 600 mẫu** — đúng chỗ người đọc
báo cáo trích một "phân vị" của phiên 4 frame.

## Input

- `src/metrics_logger.py::_summary_core()` (hợp đồng `summary.json` sau ticket #32): `mean_latency_ms`
  = `0,0` kèm `mean_latency_ms_n`, `p95_latency_ms` = `None` + `p95_latency_ms_n = 0` khi 0 mẫu.
- `web/src/live.ts` (tiền lệ câu chữ "chưa đo được (N mẫu) — không kết luận").
- Ràng buộc repo: `web/` **không có** `jsdom`/`@testing-library/react` ⇒ test FE phải là **hàm thuần**.

## Công việc đã thực hiện

1. `web/src/summary.ts` (mới, hàm thuần):
   - `soDo(value, n, digits, suffix)`: **`n === 0` quyết định TRƯỚC** ⇒ `— (0 mẫu)` (kể cả khi `value`
     là `0`: `mean = 0,0` của phiên rỗng **không** được in thành `0 ms`); có số ⇒ `119 ms (n=600)`;
     `n === null` ⇒ `119 ms (n=?)`; `n` thiếu (artifact cũ) ⇒ số trơn.
   - `soNguyen(v)`: `null`/`undefined`/`NaN` ⇒ `—` (trước đây `null` in ra chữ "null").
   - `summaryRows(summary)`: 7 dòng, nhãn giữ nguyên.
2. `web/src/api.ts`: `p95_latency_ms?: number | null` + `p95_latency_ms_n?` + `mean_latency_ms_n?` (kèm
   comment hợp đồng `mean = 0,0` khi rỗng).
3. `web/src/components/SummaryTable.tsx`: bỏ hàm `fmt` cục bộ, gọi `summaryRows()`.
4. `web/src/summary.test.ts`: 12 test (4 `soDo` + 4 `summaryRows` + 2 `soNguyen` + 2 null-safe).
5. `scripts/e2e_web.js`: thêm 2 check trên **DOM thật** — `mean` phải có `(n=…)`, `p95` phải có `(n=…)`
   hoặc "0 mẫu". Vì sao cần: `summary.test.ts` canh hàm thuần, nhưng **không** canh dây nối
   component → `summaryRows`; revert component về in số trực tiếp thì vitest vẫn xanh, repo không có
   jsdom ⇒ e2e là nơi duy nhất bắt được hồi quy đó.

## Output / Kết quả

- `./run webtest`: **66 passed** (54 cũ + 12 mới).
- `npm run build`: xanh (`tsc --noEmit` + vite).
- **`./run e2e`: PASS**, có 2 mục mới in từ DOM thật:
  `độ trễ trung bình 172 ms (n=5)` · `p95 237 ms (n=5)`.
- `./run lint` xanh · `./run test` **1339 passed**, 5 deselected (backend không đổi).
- Hành vi UI: phiên rỗng in `— (0 mẫu)` ở **cả** mean và p95 (trước: `0 ms (n=0)` cạnh `— (0 mẫu)`);
  `effective_fps: null` không còn ném `TypeError` trong render (repo **không có ErrorBoundary** ⇒ trước
  đây trắng cả card kết quả).

## Vấn đề & cách xử lý

- **Review độc lập vòng 1 (sau khi PR mở)**: verdict **mergeable**, **0 P0/P1**, **3 P2 + 4 P3** — cả 3
  P2 đã sửa trong cùng PR:
  1. `n === 0` phải quyết định trước `value` (nếu không, `mean = 0,0` in `0 ms (n=0)` cạnh
     `— (0 mẫu)` — hai câu cho cùng một trạng thái) ⇒ đã đảo thứ tự + test `soDo(0, 0)`.
  2. Răng hở đúng chỗ nối component → hàm thuần ⇒ **thêm 2 check e2e**.
  3. Năm dòng còn lại không null-safe (`effective_fps: null` ⇒ `null.toFixed(2)` ném, `total_frames:
     null` ⇒ in "null") ⇒ `soNguyen` + `soDo(..., undefined, 2)` + test null-safe.
  P3 đã sửa: `n === null` ⇒ `(n=?)`; log này + cập nhật ticket.
- **P3 còn treo (ghi lại, không sửa ở đây)**: ba câu chữ cho cùng trạng thái "0 mẫu" — web `— (0 mẫu)`,
  `./run summary` `mean=0 ms`, `run_live.py` `mean=chưa đo (0 mẫu đo được)`. Thống nhất `run summary`
  thuộc ticket #32 (nay đã đóng) ⇒ nằm trong Next steps của log này.

## Next steps

- `./run summary` vẫn in `mean=0 ms` cho ca `mean = 0,0` + `n = 0` ⇒ nên in "chưa đo" như web/`run_live`
  (việc nhỏ, chưa có ticket riêng).
- Ảnh `data/e2e_web.png` của lần chạy này nên xem nhanh để chắc bảng không vỡ layout khi thêm `(n=5)`
  (reviewer gợi ý; chưa làm).

## Tài liệu tham khảo

- Ticket #33 (3/3 tiêu chí), ticket #32 (nguồn nợ), AGENTS §5 (bắt buộc `webtest` + `build` + `e2e` cho
  thay đổi UI), §6 (bẫy `0/None ≠ đã đo`), CODING_STANDARDS (UI phải test headless được).
- PR #33 · review độc lập vòng 1 (verdict mergeable, 0 P0/P1).
