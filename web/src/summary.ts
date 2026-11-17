/**
 * Câu chữ/bảng số cho `SummaryTable` (tách khỏi component để test headless được).
 *
 * Vì sao cần: `summary.json` có những số **không thể** đọc như nhau ở mọi cỡ mẫu —
 * `p95_latency_ms = null` là "CHƯA ĐO" (phiên rỗng hoặc toàn frame đóng băng), khác `0,0` là
 * "đo được 0 ms". Backend đã tách đúng từ 17-11 (ticket #32) nhưng UI chỉ in "—", không nói
 * **vì sao**, và in `119 ms` mà không cho biết p95 dựa trên 4 hay 600 mẫu. Người đọc báo cáo
 * sẽ trích "p95 = 119 ms" cho một phiên 4 frame (AGENTS §6: "0/None ≠ đã đo", `n` phải đọc kèm).
 */
import type { JobSummary } from './api'

/** Số đo kèm cỡ mẫu.
 *
 * Thứ tự kiểm là **quan trọng**: `n === 0` quyết định TRƯỚC khi xem `value`. Backend mã hoá "phiên
 * rỗng" bằng `mean_latency_ms = 0.0` + `n = 0` (hợp đồng `effective_fps = 1000/mean`), nên nếu xét
 * `value` trước thì dòng mean in `0 ms (n=0)` trong khi dòng p95 ngay cạnh in `— (0 mẫu)` cho CÙNG
 * một trạng thái — đúng bẫy `0/None ≠ đã đo` mà ticket #33 đóng (P2 review độc lập 17-11).
 * Tiền lệ trong repo: `live.ts` nói "chưa đo được (N mẫu) — không kết luận" khi `n = 0`.
 */
export function soDo(
  value: number | null | undefined,
  n: number | null | undefined,
  digits = 0,
  suffix = '',
): string {
  if (n === 0) return '— (0 mẫu)'                           // chưa đo: KHÔNG in `0`, kể cả `0 ms`
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const num = `${value.toFixed(digits)}${suffix}`
  if (n === undefined) return num                          // artifact cũ: không có khoá `n`
  if (n === null) return `${num} (n=?)`                    // backend khai "chưa biết cỡ mẫu"
  return `${num} (n=${n})`
}

/** Số nguyên (đếm) — `null`/`undefined`/`NaN` ⇒ `—`. Dùng cho các dòng KHÔNG phải số đo. */
export function soNguyen(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${value}`
}

/** Bảng 2 cột của `SummaryTable` — hàm thuần, không JSX, test được bằng vitest. */
export function summaryRows(s: JobSummary): Array<[string, string]> {
  const tiLe = s.lost_ratio
  return [
    ['Số frame đã xử lý', soNguyen(s.total_frames)],
    ['Độ trễ trung bình', soDo(s.mean_latency_ms, s.mean_latency_ms_n, 0, ' ms')],
    ['Độ trễ p95', soDo(s.p95_latency_ms, s.p95_latency_ms_n, 0, ' ms')],
    // `effective_fps: null` từng làm `null.toFixed(2)` NÉM TypeError trong render, và repo không có
    // ErrorBoundary ⇒ trắng cả card kết quả (P2 review 17-11). `soDo` với `n` thiếu = số trơn.
    ['FPS hiệu dụng', soDo(s.effective_fps, undefined, 2)],
    ['Frame mất dấu', soNguyen(s.lost_count)],
    [
      'Tỷ lệ mất dấu',
      tiLe === undefined || tiLe === null || Number.isNaN(tiLe)
        ? '—'
        : `${(tiLe * 100).toFixed(1)} %`,
    ],
    ['Số lần nhận lại', soNguyen(s.reacquired_count)],
  ]
}
