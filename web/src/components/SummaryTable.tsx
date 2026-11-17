/**
 * SummaryTable — bảng số liệu đo thật của một lần bám (yêu cầu 6 của đề cương).
 *
 * Chức năng: hiển thị mean/p95 latency, FPS hiệu dụng, frame mất dấu, số lần nhận lại.
 * Input  : summary (object từ `summary.json` của pipeline).
 * Output : JSX bảng 2 cột.
 * Lưu ý  : giá trị thiếu hiển thị "—" thay vì "NaN"/"undefined" (số liệu phải trung thực).
 */

import type { JobSummary } from '../api'
import { summaryRows } from '../summary'

export function SummaryTable({ summary }: { summary: JobSummary }): JSX.Element {
  // Câu chữ nằm ở `summary.ts` (hàm thuần) để test headless được: repo không có jsdom, và
  // "p95 = 119 ms" mà không có `n` là chỗ người đọc báo cáo trích sai cỡ mẫu (ticket #33).
  const rows = summaryRows(summary)

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
