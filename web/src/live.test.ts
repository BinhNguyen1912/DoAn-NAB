import { describe, expect, it } from 'vitest'

import { driftLine, maskRhythmLine, shownFps } from './live'

describe('maskRhythmLine', () => {
  it('hiện đủ hai nhịp khi nguồn báo mask_fps', () => {
    const line = maskRhythmLine({
      mask_fps: 8.64, stability: 0.962, latency_ms: 108.4, empty_runs: 0,
      empty_frac_window: 0, empty_window_n: 12,
    })
    // Hai lần sửa nhãn: (1) "độ ổn định" → "nhấp nháy"; (2) nhãn nhấp nháy phải là 100 − stability
    // vì `stability = 1.0` = KHÔNG nhấp nháy (bản trước in thẳng stability*100 ⇒ đảo chiều số).
    // Hiện CẢ số nền (0 % trên 12 lần chạy) — dụng cụ đo phải cho thấy mẫu số.
    expect(line).toBe('Mask mới: 8.6 lần/giây · nhấp nháy mask: 4% · độ trễ model: 108 ms'
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

  it('stability = 0 KHÔNG được đọc là "nhấp nháy 0 %" (vừa mất dấu / chưa đo)', () => {
    // `stability = 0` vừa là default "chưa đo", vừa bị gán 0 khi mask RỖNG ⇒ in "nhấp nháy 0 %"
    // sẽ thành "êm tuyệt đối" đúng lúc model rơi vật (review 09-11, P1).
    const line = maskRhythmLine({
      mask_fps: 3, stability: 0, latency_ms: 70, empty_runs: 1,
      empty_frac_window: 0.2, empty_window_n: 10,
    })
    expect(line).toContain('nhấp nháy mask: chưa đo')
    expect(line).not.toContain('nhấp nháy mask: 0%')
  })

  it('stability 1,0 (êm tuyệt đối) phải ra 0% nhấp nháy, không phải 100%', () => {
    const line = maskRhythmLine({
      mask_fps: 8.6, stability: 1.0, latency_ms: 100, empty_runs: 0,
      empty_frac_window: 0, empty_window_n: 200,
    })
    expect(line).toContain('nhấp nháy mask: 0%')
    expect(line).not.toContain('nhấp nháy mask: 100%')
  })
})

describe('driftLine', () => {
  it('chưa đủ mẫu thì nói "chưa đo được", không bao giờ là "tốt"', () => {
    const line = driftLine({ mask_fps: 8.6, drift_p05: null, drift_n: 12 })
    expect(line).toContain('chưa đo được')
    expect(line).toContain('12 mẫu')
  })

  it('ngưỡng mẫu lấy từ backend, không nhân bản hằng số ở UI', () => {
    // Backend nâng ngưỡng (35 mẫu ⇒ vẫn null): UI không được in "35/30".
    const line = driftLine({ mask_fps: 8.6, drift_p05: null, drift_n: 35 })
    expect(line).not.toContain('35/30')
    expect(line).toContain('chưa đo được')
  })

  it('drift = 0,0 (ca xấu nhất) không được đọc thành "không lệch"', () => {
    const line = driftLine({ mask_fps: 8.6, drift_p05: 0, drift_n: 198 })
    expect(line).toContain('0.00')
    expect(line).toContain('IoU tự nhất quán')
    expect(line).not.toContain('không lệch')
    expect(line).not.toContain('LK lệch')
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
