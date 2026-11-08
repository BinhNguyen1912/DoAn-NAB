/**
 * SummaryTable — bảng số liệu đo thật của một lần bám (yêu cầu 6 của đề cương).
 *
 * Chức năng: hiển thị mean/p95 latency, FPS hiệu dụng, frame mất dấu, số lần nhận lại.
 * Input  : summary (object từ `summary.json` của pipeline).
 * Output : JSX bảng 2 cột.
 * Lưu ý  : giá trị thiếu hiển thị "—" thay vì "NaN"/"undefined" (số liệu phải trung thực).
 */

import type { JobSummary } from '../api'

function fmt(value: number | undefined, digits = 1, suffix = ''): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  return `${value.toFixed(digits)}${suffix}`
}

export function SummaryTable({ summary }: { summary: JobSummary }): JSX.Element {
  const rows: Array<[string, string]> = [
    ['Số frame đã xử lý', fmt(summary.total_frames, 0)],
    ['Độ trễ trung bình', fmt(summary.mean_latency_ms, 0, ' ms')],
    ['Độ trễ p95', fmt(summary.p95_latency_ms, 0, ' ms')],
    ['FPS hiệu dụng', fmt(summary.effective_fps, 2)],
    ['Frame mất dấu', fmt(summary.lost_count, 0)],
    ['Tỷ lệ mất dấu', summary.lost_ratio === undefined ? '—' : fmt(summary.lost_ratio * 100, 1, ' %')],
    ['Số lần nhận lại', fmt(summary.reacquired_count, 0)],
  ]

  return (
    <table className="summary">
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label}>
            <th>{label}</th>
            <td>{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
