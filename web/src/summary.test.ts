/**
 * Test `summary.ts` (ticket #33): `p95`/`mean` phải hiện kèm cỡ mẫu, và "chưa đo" không được in `0`.
 *
 * Hàm thuần nên chạy được bằng vitest mà không cần jsdom (repo không có `@testing-library/react`).
 */
import { describe, expect, it } from 'vitest'

import { soDo, soNguyen, summaryRows } from './summary'

describe('soDo', () => {
  it('có số + có n ⇒ in kèm n', () => {
    expect(soDo(119.4, 600, 0, ' ms')).toBe('119 ms (n=600)')
  })

  it('n = 0 quyết định TRƯỚC value: `0` + 0 mẫu vẫn là CHƯA ĐO', () => {
    expect(soDo(null, 0, 0, ' ms')).toBe('— (0 mẫu)')
    expect(soDo(undefined, 0, 0, ' ms')).toBe('— (0 mẫu)')
    // `mean_latency_ms = 0,0` + `n = 0` là "phiên rỗng"; in `0 ms` là nói "xử lý tức thì" (bẫy §6).
    expect(soDo(0, 0, 0, ' ms')).toBe('— (0 mẫu)')
  })

  it('n = null (backend khai chưa biết cỡ mẫu) ⇒ giữ số và đánh dấu `?`', () => {
    expect(soDo(119.4, null, 0, ' ms')).toBe('119 ms (n=?)')
  })

  it('0,0 là số ĐO ĐƯỢC (n > 0) — không được biến thành "chưa đo"', () => {
    expect(soDo(0, 3, 0, ' ms')).toBe('0 ms (n=3)')
  })

  it('artifact cũ thiếu khoá n ⇒ in số trơn, không bịa n', () => {
    expect(soDo(195.0, undefined, 0, ' ms')).toBe('195 ms')
    expect(soDo(null, undefined)).toBe('—')
  })
})

describe('summaryRows', () => {
  it('phiên rỗng: p95 là "— (0 mẫu)", tỷ lệ mất dấu vẫn in số (0 mẫu ⇒ 0,0 % là hợp đồng)', () => {
    const rows = summaryRows({
      total_frames: 0,
      mean_latency_ms: 0.0,
      mean_latency_ms_n: 0,
      p95_latency_ms: null,
      p95_latency_ms_n: 0,
      effective_fps: 0.0,
      mean_score: 0.0,
      lost_count: 0,
      lost_ratio: 0.0,
      reacquired_count: 0,
    })
    const o = Object.fromEntries(rows)
    expect(o['Độ trễ p95']).toBe('— (0 mẫu)')
    // CÙNG một trạng thái "0 mẫu" phải in CÙNG một câu ở cả hai dòng (P2 review 17-11).
    expect(o['Độ trễ trung bình']).toBe('— (0 mẫu)')
    expect(o['Số frame đã xử lý']).toBe('0')
  })

  it('phiên thật: p95 kèm n, mean kèm n', () => {
    const rows = summaryRows({
      total_frames: 600,
      mean_latency_ms: 108.4,
      mean_latency_ms_n: 600,
      p95_latency_ms: 119.4,
      p95_latency_ms_n: 600,
      effective_fps: 20.15,
      lost_count: 12,
      lost_ratio: 0.02,
      reacquired_count: 3,
    })
    const o = Object.fromEntries(rows)
    expect(o['Độ trễ p95']).toBe('119 ms (n=600)')
    expect(o['Độ trễ trung bình']).toBe('108 ms (n=600)')
    expect(o['Tỷ lệ mất dấu']).toBe('2.0 %')
    expect(o['Số lần nhận lại']).toBe('3')
  })

  it('p95 của 4 frame vẫn phải lộ ra cỡ mẫu nhỏ (không được đọc như phân vị thật)', () => {
    const rows = summaryRows({ total_frames: 4, p95_latency_ms: 130.0, p95_latency_ms_n: 4 })
    expect(Object.fromEntries(rows)['Độ trễ p95']).toBe('130 ms (n=4)')
  })

  it('summary thiếu hẳn khoá ⇒ "—", không "NaN"/"undefined"', () => {
    const rows = summaryRows({})
    const o = Object.fromEntries(rows)
    for (const value of Object.values(o)) {
      expect(value).not.toMatch(/NaN|undefined/)
    }
    expect(o['Độ trễ p95']).toBe('—')
  })
})

describe('soNguyen', () => {
  it('null/undefined/NaN ⇒ "—", không in chữ "null"', () => {
    expect(soNguyen(null)).toBe('—')
    expect(soNguyen(undefined)).toBe('—')
    expect(soNguyen(Number.NaN)).toBe('—')
    expect(soNguyen(0)).toBe('0')
  })
})

describe('summaryRows null-safe (P2 review 17-11)', () => {
  it('API trả `null` cho các dòng khác p95 ⇒ "—", KHÔNG ném TypeError', () => {
    // `effective_fps: null` từng làm `null.toFixed(2)` ném trong render ⇒ trắng card kết quả (repo
    // không có ErrorBoundary). `Summary` của API là `Optional[dict]` nên không schema nào chặn `null`.
    const rows = summaryRows({
      total_frames: null,
      effective_fps: null,
      lost_count: null,
      reacquired_count: null,
      lost_ratio: Number.NaN,
    } as never)
    const o = Object.fromEntries(rows)
    for (const [nhan, value] of Object.entries(o)) {
      expect(value, nhan).not.toMatch(/NaN|undefined|null/)
    }
    expect(o['FPS hiệu dụng']).toBe('—')
    expect(o['Tỷ lệ mất dấu']).toBe('—')
  })

  it('FPS bình thường vẫn 2 chữ số thập phân, không kèm n', () => {
    const o = Object.fromEntries(summaryRows({ effective_fps: 29.832 }))
    expect(o['FPS hiệu dụng']).toBe('29.83')
  })
})
