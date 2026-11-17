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

/** Một số đo kèm cỡ mẫu: `n` thiếu/0 ⇒ "chưa đo", không bao giờ in `0`. */
export function soDo(
  value: number | null | undefined,
  n: number | null | undefined,
  digits = 0,
  suffix = '',
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return n === 0 ? `— (0 mẫu)` : '—'
  }
  const num = `${value.toFixed(digits)}${suffix}`
  if (n === null || n === undefined) return num            // artifact cũ: không có khoá `n`
  return `${num} (n=${n})`
}

/** Bảng 2 cột của `SummaryTable` — hàm thuần, không JSX, test được bằng vitest. */
export function summaryRows(s: JobSummary): Array<[string, string]> {
  const tiLe = s.lost_ratio
  return [
    ['Số frame đã xử lý', s.total_frames === undefined ? '—' : `${s.total_frames}`],
    ['Độ trễ trung bình', soDo(s.mean_latency_ms, s.mean_latency_ms_n, 0, ' ms')],
    ['Độ trễ p95', soDo(s.p95_latency_ms, s.p95_latency_ms_n, 0, ' ms')],
    ['FPS hiệu dụng', s.effective_fps === undefined ? '—' : s.effective_fps.toFixed(2)],
    ['Frame mất dấu', s.lost_count === undefined ? '—' : `${s.lost_count}`],
    [
      'Tỷ lệ mất dấu',
      tiLe === undefined || tiLe === null ? '—' : `${(tiLe * 100).toFixed(1)} %`,
    ],
    ['Số lần nhận lại', s.reacquired_count === undefined ? '—' : `${s.reacquired_count}`],
  ]
}
