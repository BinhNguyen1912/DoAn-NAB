# 33: Web: `api.ts` cho `p95_latency_ms` là `null` được + `SummaryTable` hiện cỡ mẫu `n`

**What to build:** Nợ FE của ticket #32 (backend đã xong: `p95_latency_ms = None` khi chưa có mẫu, `p95_latency_ms_n`/`mean_latency_ms_n` đi kèm).

Hiện `web/src/api.ts:23` khai `p95_latency_ms?: number` — sai kiểu: backend có thể trả `null`. `SummaryTable` (`web/src/components/SummaryTable.tsx`) đã an toàn nhờ `fmt` kiểm `value === null` nhưng **không in `n`** ⇒ người xem báo cáo vẫn thấy "119 ms" mà không biết p95 dựa trên 4 hay 600 mẫu (đúng bẫy mà ticket #32 đóng ở CLI).

Việc:
- `api.ts`: `p95_latency_ms?: number | null`, `p95_latency_ms_n?: number`, `mean_latency_ms_n?: number`.
- `SummaryTable`: p95 `null`/thiếu ⇒ `— (0 mẫu)`; có số ⇒ `119 ms (n=600)`.
- Test vitest (`web/src/components/SummaryTable.test.tsx` hoặc tương đương) cho **cả hai** nhánh.
- Chạy `./run webtest`, `npm run build`, `./run e2e` (bắt buộc với thay đổi UI — AGENTS §5) trước khi merge.

**Vì sao chưa làm trong PR #29:** PR đó là backend + `run summary`; trộn FE vào sẽ phải chạy e2e (Windows/Playwright) và làm PR vượt phạm vi một ticket.

**Status:** resolved

Acceptance:
- [x] `api.ts` cho phép `null` + có `_n` cho p95 và mean
- [x] `SummaryTable` in `— (0 mẫu)` / `119 ms (n=600)` — có vitest canh cả hai
- [x] `./run webtest` + `npm run build` + `./run e2e` xanh

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] `web/src/api.ts`: `p95_latency_ms?: number | null` + `p95_latency_ms_n?: number` + `mean_latency_ms_n?: number`
- [x] `SummaryTable` in `— (0 mẫu)` khi `p95_latency_ms === null`/thiếu, và `119 ms (n=600)` khi có số — có vitest canh cả hai nhánh
- [x] `./run webtest` + `npm run build` + `./run e2e` xanh (thay đổi UI nên e2e là bắt buộc theo AGENTS §5)

## Answer

Xong (PR #33). Hàm thuần `web/src/summary.ts` (`soDo`/`soNguyen`/`summaryRows`) + `api.ts` cho `null` +
`_n` + `SummaryTable` gọi hàm thuần. `p95`/`mean` hiện `119 ms (n=600)`; `n = 0` ⇒ `— (0 mẫu)` (kể cả
`mean = 0,0` — không in `0 ms`); `n = null` ⇒ `(n=?)`; `effective_fps: null` không còn ném TypeError.

Kiểm: `./run webtest` **66 passed** · `npm run build` xanh · **`./run e2e` PASS** (2 check mới trên DOM
thật: `mean 172 ms (n=5)`, `p95 237 ms (n=5)`) · `./run lint` + `./run test` **1339 passed**.

Review độc lập vòng 1: **0 P0/P1**, 3 P2 + 4 P3 → **cả 3 P2 đã sửa** (`n = 0` quyết định trước `value`;
2 check e2e canh dây nối component → hàm thuần; `soNguyen` cho 5 dòng còn lại), P3 `n = null` → `(n=?)`.
Log: `docs/task/17-11-2026-ticket-33-web-in-co-mau-p95.md`. Còn treo (P3, ngoài phạm vi): `./run summary`
vẫn in `mean=0 ms` cho ca 0 mẫu.
