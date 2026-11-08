import { describe, expect, it } from 'vitest'

import { maskRhythmLine } from './live'

describe('maskRhythmLine', () => {
  it('hiện đủ hai nhịp khi nguồn báo mask_fps', () => {
    const line = maskRhythmLine({ mask_fps: 8.64, stability: 0.962, latency_ms: 108.4 })
    expect(line).toBe('Mask mới: 8.6 lần/giây · độ ổn định: 96% · độ trễ model: 108 ms')
  })

  it('trả null khi chế độ raw (không có model)', () => {
    expect(maskRhythmLine({ mask_fps: 0, stability: 0, latency_ms: 0 })).toBeNull()
  })

  it('trả null khi chưa có status', () => {
    expect(maskRhythmLine(null)).toBeNull()
  })

  it('độ ổn định 0% vẫn hiện (không được giấu số xấu)', () => {
    const line = maskRhythmLine({ mask_fps: 3, stability: 0, latency_ms: 70 })
    expect(line).toContain('độ ổn định: 0%')
  })
})
