/**
 * Test `summary.ts` (ticket #33): `p95`/`mean` phải hiện kèm cỡ mẫu, và "chưa đo" không được in `0`.
 *
 * Hàm thuần nên chạy được bằng vitest mà không cần jsdom (repo không có `@testing-library/react`).
 */
import { describe, expect, it } from 'vitest'

import { soDo, summaryRows } from './summary'

describe('soDo', () => {
  it('có số + có n ⇒ in kèm n', () => {
    expect(soDo(119.4, 600, 0, ' ms')).toBe('119 ms (n=600)')
  })

  it('null + n = 0 ⇒ nói rõ CHƯA ĐO, không in 0', () => {
    expect(soDo(null, 0, 0, ' ms')).toBe('— (0 mẫu)')
    expect(soDo(undefined, 0, 0, ' ms')).toBe('— (0 mẫu)')
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
    expect(o['Độ trễ trung bình']).toBe('0 ms (n=0)')
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
