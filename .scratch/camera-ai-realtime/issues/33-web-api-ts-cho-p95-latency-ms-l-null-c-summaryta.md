# 33: Web: `api.ts` cho `p95_latency_ms` là `null` được + `SummaryTable` hiện cỡ mẫu `n`

**What to build:** Nợ FE của ticket #32 (backend đã xong: `p95_latency_ms = None` khi chưa có mẫu, `p95_latency_ms_n`/`mean_latency_ms_n` đi kèm).

Hiện `web/src/api.ts:23` khai `p95_latency_ms?: number` — sai kiểu: backend có thể trả `null`. `SummaryTable` (`web/src/components/SummaryTable.tsx`) đã an toàn nhờ `fmt` kiểm `value === null` nhưng **không in `n`** ⇒ người xem báo cáo vẫn thấy "119 ms" mà không biết p95 dựa trên 4 hay 600 mẫu (đúng bẫy mà ticket #32 đóng ở CLI).

Việc:
- `api.ts`: `p95_latency_ms?: number | null`, `p95_latency_ms_n?: number`, `mean_latency_ms_n?: number`.
- `SummaryTable`: p95 `null`/thiếu ⇒ `— (0 mẫu)`; có số ⇒ `119 ms (n=600)`.
- Test vitest (`web/src/components/SummaryTable.test.tsx` hoặc tương đương) cho **cả hai** nhánh.
- Chạy `./run webtest`, `npm run build`, `./run e2e` (bắt buộc với thay đổi UI — AGENTS §5) trước khi merge.

**Vì sao chưa làm trong PR #29:** PR đó là backend + `run summary`; trộn FE vào sẽ phải chạy e2e (Windows/Playwright) và làm PR vượt phạm vi một ticket.

**Status:** claimed

Acceptance:
- [ ] `api.ts` cho phép `null` + có `_n` cho p95 và mean
- [ ] `SummaryTable` in `— (0 mẫu)` / `119 ms (n=600)` — có vitest canh cả hai
- [ ] `./run webtest` + `npm run build` + `./run e2e` xanh

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `web/src/api.ts`: `p95_latency_ms?: number | null` + `p95_latency_ms_n?: number` + `mean_latency_ms_n?: number`
- [ ] `SummaryTable` in `— (0 mẫu)` khi `p95_latency_ms === null`/thiếu, và `119 ms (n=600)` khi có số — có vitest canh cả hai nhánh
- [ ] `./run webtest` + `npm run build` + `./run e2e` xanh (thay đổi UI nên e2e là bắt buộc theo AGENTS §5)
