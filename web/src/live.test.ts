import { describe, expect, it } from 'vitest'

import { maskRhythmLine, shownFps } from './live'

describe('maskRhythmLine', () => {
  it('hiện đủ hai nhịp khi nguồn báo mask_fps', () => {
    const line = maskRhythmLine({ mask_fps: 8.64, stability: 0.962, latency_ms: 108.4, empty_runs: 0 })
    expect(line).toBe('Mask mới: 8.6 lần/giây · độ ổn định: 96% · độ trễ model: 108 ms')
  })

  it('trả null khi chế độ raw (không có model)', () => {
    expect(maskRhythmLine({ mask_fps: 0, stability: 0, latency_ms: 0, empty_runs: 0 })).toBeNull()
  })

  it('hiện số lần mất dấu khi có (không giấu số xấu)', () => {
    const line = maskRhythmLine({ mask_fps: 8.6, stability: 0.7, latency_ms: 100, empty_runs: 3 })
    expect(line).toContain('mất dấu: 3 lần')
  })

  it('trả null khi chưa có status', () => {
    expect(maskRhythmLine(null)).toBeNull()
  })

  it('độ ổn định 0% vẫn hiện (không được giấu số xấu)', () => {
    const line = maskRhythmLine({ mask_fps: 3, stability: 0, latency_ms: 70, empty_runs: 0 })
    expect(line).toContain('độ ổn định: 0%')
  })
})

describe('shownFps', () => {
  it('ưu tiên số của worker khi có', () => {
    expect(shownFps({ measured_fps: 15, display_fps: 29.9 })).toBe(29.9)
  })

  it('rơi về số của API khi worker không báo (chế độ raw)', () => {
    expect(shownFps({ measured_fps: 14.9, display_fps: 0 })).toBe(14.9)
  })

  it('không có status thì 0', () => {
    expect(shownFps(null)).toBe(0)
  })
})
