/**
 * selection.test.ts — test toán học chọn đối tượng (hàm thuần, không cần trình duyệt).
 *
 * Trọng tâm: quy đổi toạ độ chuột → pixel gốc video. Đây là lỗi hay gặp nhất của UI canvas:
 * video 1920px hiển thị ở 600px mà quên nhân tỉ lệ thì ô chọn lệch 3,2 lần.
 */

import { describe, expect, it } from 'vitest'
import {
  boxFromPoints,
  clampInt,
  describeBox,
  isUsableBox,
  MIN_BOX_SIDE,
  toImagePoint,
} from './selection'

// Khung hiển thị 600×400 cho video 1920×1280 → tỉ lệ 3,2 (đều 2 chiều)
const RECT = { left: 100, top: 50, width: 600, height: 400 }
const CANVAS = { width: 1920, height: 1280 }

describe('clampInt', () => {
  it('kẹp giá trị về khoảng cho trước và làm tròn', () => {
    expect(clampInt(-5, 0, 10)).toBe(0)
    expect(clampInt(15, 0, 10)).toBe(10)
    expect(clampInt(42.4, 0, 100)).toBe(42)
    expect(clampInt(42.6, 0, 100)).toBe(43)
  })

  it('giá trị không hữu hạn trả về biên dưới (không sinh NaN cho backend)', () => {
    expect(clampInt(Number.NaN, 3, 9)).toBe(3)
    expect(clampInt(Number.POSITIVE_INFINITY, 3, 9)).toBe(9)
  })
})

describe('toImagePoint', () => {
  it('góc trên-trái của khung hiển thị là (0,0) của video', () => {
    expect(toImagePoint(100, 50, RECT, CANVAS)).toEqual({ x: 0, y: 0 })
  })

  it('nhân đúng tỉ lệ 3,2 khi ảnh bị thu nhỏ', () => {
    // literal tính tay: (400-100)/600*1920 = 960 ; (250-50)/400*1280 = 640
    expect(toImagePoint(400, 250, RECT, CANVAS)).toEqual({ x: 960, y: 640 })
  })

  it('góc dưới-phải chạm biên phải/đáy của video', () => {
    expect(toImagePoint(700, 450, RECT, CANVAS)).toEqual({ x: 1920, y: 1280 })
  })

  it('kéo ra ngoài khung bị kẹp vào biên, không trả toạ độ âm/vượt', () => {
    expect(toImagePoint(-50, -50, RECT, CANVAS)).toEqual({ x: 0, y: 0 })
    expect(toImagePoint(9999, 9999, RECT, CANVAS)).toEqual({ x: 1920, y: 1280 })
  })

  it('khung chưa layout (width=0) không chia cho 0', () => {
    const broken = { left: 0, top: 0, width: 0, height: 0 }
    const point = toImagePoint(50, 50, broken, CANVAS)
    expect(point).toEqual({ x: 0, y: 0 })
    expect(Number.isNaN(point.x)).toBe(false)
  })

  it('tỉ lệ X và Y tính riêng (khung bị méo vẫn đúng)', () => {
    // 600×300 cho video 1200×1200 → scaleX = 2, scaleY = 4
    const rect = { left: 0, top: 0, width: 600, height: 300 }
    const canvas = { width: 1200, height: 1200 }
    expect(toImagePoint(300, 150, rect, canvas)).toEqual({ x: 600, y: 600 })
  })
})

describe('boxFromPoints', () => {
  it('kéo xuôi chiều', () => {
    expect(boxFromPoints({ x: 10, y: 20 }, { x: 40, y: 60 })).toEqual({ x: 10, y: 20, w: 30, h: 40 })
  })

  it('kéo ngược chiều vẫn cho cùng hộp', () => {
    expect(boxFromPoints({ x: 40, y: 60 }, { x: 10, y: 20 })).toEqual({ x: 10, y: 20, w: 30, h: 40 })
  })

  it('kéo chéo hai góc khác nhau cho cùng hộp', () => {
    const a = boxFromPoints({ x: 10, y: 60 }, { x: 40, y: 20 })
    const b = boxFromPoints({ x: 40, y: 20 }, { x: 10, y: 60 })
    expect(a).toEqual(b)
  })
})

describe('isUsableBox', () => {
  it('hộp bằng hoặc lớn hơn ngưỡng là dùng được', () => {
    expect(isUsableBox({ x: 0, y: 0, w: MIN_BOX_SIDE, h: MIN_BOX_SIDE })).toBe(true)
  })

  it('hộp nhỏ hơn ngưỡng (click nhầm) bị loại', () => {
    expect(isUsableBox({ x: 0, y: 0, w: MIN_BOX_SIDE - 1, h: 40 })).toBe(false)
    expect(isUsableBox({ x: 0, y: 0, w: 40, h: MIN_BOX_SIDE - 1 })).toBe(false)
  })

  it('null bị loại', () => {
    expect(isUsableBox(null)).toBe(false)
  })
})

describe('describeBox', () => {
  it('có hộp thì in toạ độ + kích thước', () => {
    expect(describeBox({ x: 1, y: 2, w: 30, h: 40 })).toBe('1, 2, 30×40')
  })

  it('chưa chọn thì nói rõ', () => {
    expect(describeBox(null)).toBe('chưa có')
  })
})
