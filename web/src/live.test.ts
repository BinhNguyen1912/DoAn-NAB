import { describe, expect, it } from 'vitest'

import { DRIFT_MIN_SAMPLES, driftLine, maskRhythmLine, shownFps } from './live'

describe('maskRhythmLine', () => {
  it('hiện đủ hai nhịp khi nguồn báo mask_fps', () => {
    const line = maskRhythmLine({
      mask_fps: 8.64, stability: 0.962, latency_ms: 108.4, empty_runs: 0,
      empty_frac_window: 0, empty_window_n: 12,
    })
    // Nhãn đổi "độ ổn định" → "nhấp nháy mask": `stability` chỉ đo mask có GIẬT giữa hai lần VOS,
    // không phải chất lượng phân đoạn (review 09-11). Test cũ pin chuỗi sai nên phải sửa theo.
    // Hiện CẢ số nền (0 % trên 12 lần chạy) — dụng cụ đo phải cho thấy mẫu số, không phải chỉ
    // hiện khi có sự cố.
    expect(line).toBe('Mask mới: 8.6 lần/giây · nhấp nháy mask: 96% · độ trễ model: 108 ms'
      + ' · mất dấu: 0% của 12 lần chạy gần nhất')
  })

  it('trả null khi chế độ raw (không có model)', () => {
    expect(maskRhythmLine({
      mask_fps: 0, stability: 0, latency_ms: 0, empty_runs: 0,
      empty_frac_window: null, empty_window_n: 0,
    })).toBeNull()
  })

  it('ưu tiên tỉ lệ theo CỬA SỔ thay vì bộ đếm trọn đời (không giấu số xấu)', () => {
    const line = maskRhythmLine({
      mask_fps: 8.6, stability: 0.7, latency_ms: 100,
      empty_runs: 26, empty_frac_window: 0.112, empty_window_n: 200,
    })
    // `empty_runs` = 26 là sự việc ĐÃ QUA; con số nói "hiện tại" là 11,2 % của 200 lần gần nhất.
    expect(line).toContain('mất dấu: 11% của 200 lần chạy gần nhất')
    expect(line).not.toContain('26')
  })

  it('chưa đủ mẫu cửa sổ thì nói rõ là số cả phiên', () => {
    const line = maskRhythmLine({
      mask_fps: 8.6, stability: 0.7, latency_ms: 100,
      empty_runs: 3, empty_frac_window: null, empty_window_n: 2,
    })
    expect(line).toContain('mất dấu (cả phiên): 3 lần')
  })

  it('trả null khi chưa có status', () => {
    expect(maskRhythmLine(null)).toBeNull()
  })

  it('nhấp nháy 0% vẫn hiện (không được giấu số xấu)', () => {
    const line = maskRhythmLine({
      mask_fps: 3, stability: 0, latency_ms: 70, empty_runs: 0,
      empty_frac_window: 0, empty_window_n: 0,
    })
    expect(line).toContain('nhấp nháy mask: 0%')
  })
})

describe('driftLine', () => {
  it('chưa đủ mẫu thì nói "chưa đo được", không bao giờ là "tốt"', () => {
    const line = driftLine({ mask_fps: 8.6, drift_p05: null, drift_n: 12 })
    expect(line).toContain('chưa đo được')
    expect(line).toContain(`12/${DRIFT_MIN_SAMPLES}`)
  })

  it('drift = 0,0 đã đo được thì hiện số thật + nhãn tự nhất quán', () => {
    const line = driftLine({ mask_fps: 8.6, drift_p05: 0, drift_n: 198 })
    expect(line).toContain('0.00')
    expect(line).toContain('tự nhất quán')
    expect(line).not.toContain('độ chính xác cao')
  })

  it('null khi chế độ raw (không có model ⇒ không có drift)', () => {
    expect(driftLine({ mask_fps: 0, drift_p05: null, drift_n: 0 })).toBeNull()
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
