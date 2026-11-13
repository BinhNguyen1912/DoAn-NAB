import { describe, expect, it } from 'vitest'

import { deviceLine, driftLine, maskRhythmLine, shownFps, sourceCheckLine, stallLine } from './live'

describe('maskRhythmLine', () => {
  it('hiện đủ hai nhịp khi nguồn báo mask_fps', () => {
    const line = maskRhythmLine({
      mask_fps: 8.64, stability: 0.962, stability_n: 200, latency_ms: 108.4, empty_runs: 0,
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
      mask_fps: 0, stability: null, stability_n: 0, latency_ms: 0, empty_runs: 0,
      empty_frac_window: null, empty_window_n: 0,
    })).toBeNull()
  })

  it('stability thiếu/NaN/rỗng/âm đều là "chưa đo", không phải "êm tuyệt đối"', () => {
    // Backend giờ có encoding "chưa đo" (`stability = null` + `stability_n = 0`), nhưng UI vẫn phải
    // chặn ca trường bị thiếu (API cũ), NaN (chia 0 trong numpy) và số âm.
    for (const stability of [undefined, NaN, -0.2, null] as any[]) {
      for (const stability_n of [0, 200]) {
        const line = maskRhythmLine({
          mask_fps: 8, stability, stability_n, latency_ms: 1, empty_runs: 0,
          empty_frac_window: null, empty_window_n: 0,
        } as any)
        expect(line).toContain('nhấp nháy mask: chưa đo')
        expect(line).not.toContain('nhấp nháy mask: 0%')
        expect(line).not.toMatch(/NaN/)
      }
    }
  })

  it('stability_n = 0 ⇒ "chưa đo" dù `stability` là 0 (không có mẫu nào)', () => {
    const line = maskRhythmLine({
      mask_fps: 8, stability: 0, stability_n: 0, latency_ms: 1, empty_runs: 0,
      empty_frac_window: null, empty_window_n: 0,
    })
    expect(line).toContain('nhấp nháy mask: chưa đo')
  })

  it('ưu tiên tỉ lệ theo CỬA SỔ thay vì bộ đếm trọn đời (không giấu số xấu)', () => {
    const line = maskRhythmLine({
      mask_fps: 8.6, stability: 0.7, stability_n: 200, latency_ms: 100,
      empty_runs: 26, empty_frac_window: 0.112, empty_window_n: 200,
    })
    // `empty_runs` = 26 là sự việc ĐÃ QUA; con số nói "hiện tại" là 11,2 % của 200 lần gần nhất.
    expect(line).toContain('mất dấu: 11% của 200 lần chạy gần nhất')
    expect(line).not.toContain('26')
  })

  it('chưa đủ mẫu cửa sổ thì nói rõ là số cả phiên', () => {
    const line = maskRhythmLine({
      mask_fps: 8.6, stability: 0.7, stability_n: 200, latency_ms: 100,
      empty_runs: 3, empty_frac_window: null, empty_window_n: 2,
    })
    expect(line).toContain('mất dấu (cả phiên): 3 lần')
  })

  it('trả null khi chưa có status', () => {
    expect(maskRhythmLine(null)).toBeNull()
  })

  it('stability = 0 ĐO ĐƯỢC (stability_n > 0) ⇒ "nhấp nháy 100 %", không phải "êm tuyệt đối"', () => {
    // `0` cũ vừa là default "chưa đo" vừa bị gán 0 khi mask RỖNG. Nay `stability_n` tách hai nghĩa:
    // có mẫu ⇒ `0` là số đo được (mask rời nhau hoàn toàn) ⇒ 100 % nhấp nháy, KHÔNG bao giờ là 0 %.
    const line = maskRhythmLine({
      mask_fps: 3, stability: 0, stability_n: 150, latency_ms: 70, empty_runs: 1,
      empty_frac_window: 0.2, empty_window_n: 10,
    })
    expect(line).toContain('nhấp nháy mask: 100%')
    expect(line).not.toContain('nhấp nháy mask: 0%')
  })

  it('stability 1,0 (êm tuyệt đối) phải ra 0% nhấp nháy, không phải 100%', () => {
    const line = maskRhythmLine({
      mask_fps: 8.6, stability: 1.0, stability_n: 200, latency_ms: 100, empty_runs: 0,
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

describe('deviceLine', () => {
  it('nói GPU khi worker báo cuda', () => {
    expect(deviceLine({ device: 'cuda' })).toBe(
      'Thiết bị chạy model: cuda (GPU) — FPS/độ trễ chỉ đúng cho thiết bị này')
  })

  it('nói CPU khi worker báo cpu', () => {
    expect(deviceLine({ device: 'cpu' })).toBe(
      'Thiết bị chạy model: cpu (CPU) — FPS/độ trễ chỉ đúng cho thiết bị này')
  })

  it('chuỗi rỗng = CHƯA BIẾT ⇒ ẩn dòng, không in "cpu" (ticket 21)', () => {
    // `''` là chế độ raw hoặc worker bản cũ chưa ghi `device` — in "cpu" ở đây là khẳng định sai.
    expect(deviceLine({ device: '' })).toBeNull()
    expect(deviceLine({ device: '   ' })).toBeNull()
    expect(deviceLine(null)).toBeNull()
    expect(deviceLine(undefined)).toBeNull()
  })

  it('giá trị lạ thì hiện nguyên văn, không đoán', () => {
    expect(deviceLine({ device: 'mps' })).toBe(
      'Thiết bị chạy model: mps — FPS/độ trễ chỉ đúng cho thiết bị này')
  })
})

describe('stallLine — ảnh đứng thì phải nói, không được im', () => {
  const running = { state: 'running' as const, frames: 120, measured_fps: 0 }

  it('dưới 3 s thì chưa cảnh báo (tránh nháy khi cảnh tĩnh ngắn)', () => {
    expect(stallLine(running, 2.9)).toBeNull()
  })

  it('≥ 3 s thì nói rõ "không có frame mới", KHÔNG nói "nguồn đã chết"', () => {
    const line = stallLine(running, 3.4)
    expect(line).toContain('Không có frame mới trong 3.4 s')
    expect(line).toContain('frame đứng ở 120')
    expect(line).not.toContain('chết')
  })

  it('phiên không chạy (stopped/error/loading) thì không cảnh báo đứng hình', () => {
    expect(stallLine({ ...running, state: 'stopped' }, 10)).toBeNull()
    expect(stallLine({ ...running, state: 'error' }, 10)).toBeNull()
    expect(stallLine(null, 10)).toBeNull()
  })
})

describe('sourceCheckLine — bằng chứng đo được thay cho chữ "đã kiểm"', () => {
  it('in mốc thời gian + bằng chứng + thời gian dò', () => {
    expect(sourceCheckLine({ check: 'nhận được ảnh JPEG', latency_ms: 6 }, '2026-11-13T22:41:03'))
      .toBe('dò lúc 22:41:03 · nhận được ảnh JPEG · 6 ms')
  })

  it('chưa dò thì nói chưa dò, không bịa bằng chứng', () => {
    expect(sourceCheckLine(null)).toBe('chưa dò nguồn')
  })
})
