/**
 * selection.test.ts — test toán học chọn đối tượng (hàm thuần, không cần trình duyệt).
 *
 * Trọng tâm: quy đổi toạ độ chuột → pixel gốc video. Đây là lỗi hay gặp nhất của UI canvas:
 * video 1920px hiển thị ở 600px mà quên nhân tỉ lệ thì ô chọn lệch 3,2 lần.
 */

import { describe, expect, it } from 'vitest'
import {
  addPoint,
  boxFromPoints,
  clampInt,
  clampPointInCanvas,
  clickToleranceImagePx,
  CLICK_TOLERANCE_CSS,
  pointMergeRadiusImagePx,
  countPoints,
  describeBox,
  describePoints,
  isClickNotDrag,
  MAX_PROMPT_POINTS,
  MIN_POINT_DIST,
  removeLastPoint,
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

// ─── Điểm prompt dương/âm (khôi phục 22-11: ca vật be trơn bám sang cửa/tường cùng tông) ──────────

describe('addPoint', () => {
  it('thêm điểm dương rồi điểm âm, giữ đúng nhãn', () => {
    let pts = addPoint([], { x: 10, y: 10, label: 1 })
    pts = addPoint(pts, { x: 200, y: 200, label: 0 })
    expect(pts).toHaveLength(2)
    expect(countPoints(pts)).toEqual({ duong: 1, am: 1 })
  })

  it('click đè lên điểm cũ thì THAY, không cộng dồn (kể cả đổi nhãn)', () => {
    const pts = addPoint([{ x: 10, y: 10, label: 1 }], { x: 12, y: 11, label: 0 })
    expect(pts).toHaveLength(1)
    expect(pts[0].label).toBe(0)
  })

  it(`hai điểm cách nhau >= ${MIN_POINT_DIST}px là hai điểm khác nhau`, () => {
    const pts = addPoint([{ x: 10, y: 10, label: 1 }], { x: 10 + MIN_POINT_DIST, y: 10, label: 1 })
    expect(pts).toHaveLength(2)
  })

  it(`chặn ở ${MAX_PROMPT_POINTS} điểm và bỏ điểm CŨ NHẤT`, () => {
    let pts: { x: number; y: number; label: 0 | 1 }[] = []
    for (let i = 0; i < MAX_PROMPT_POINTS + 3; i += 1) {
      pts = addPoint(pts, { x: i * 20, y: 0, label: 1 })
    }
    expect(pts).toHaveLength(MAX_PROMPT_POINTS)
    expect(pts[0].x).toBe(3 * 20)                // 3 điểm đầu đã bị bỏ
    expect(pts[pts.length - 1].x).toBe((MAX_PROMPT_POINTS + 2) * 20)
  })

  it('không sửa mảng đầu vào (hàm thuần)', () => {
    const goc = [{ x: 1, y: 1, label: 1 as const }]
    addPoint(goc, { x: 100, y: 100, label: 0 })
    expect(goc).toHaveLength(1)
  })
})

describe('removeLastPoint', () => {
  it('bỏ điểm thêm sau cùng; mảng rỗng vẫn rỗng', () => {
    const pts = [
      { x: 1, y: 1, label: 1 as const },
      { x: 50, y: 50, label: 0 as const },
    ]
    expect(removeLastPoint(pts)).toEqual([{ x: 1, y: 1, label: 1 }])
    expect(removeLastPoint([])).toEqual([])
  })
})

describe('describePoints', () => {
  it('chưa có điểm thì nói rõ, không hiện "0 điểm" mơ hồ', () => {
    expect(describePoints([])).toBe('chưa có điểm nào')
    expect(describePoints([{ x: 1, y: 1, label: 1 }])).toContain('1 điểm dương')
    expect(describePoints([{ x: 1, y: 1, label: 0 }])).toContain('1 điểm âm')
  })
})

describe('isClickNotDrag', () => {
  it('nhấn-nhả cùng chỗ là CLICK (đặt điểm), không phải kéo (vẽ ô)', () => {
    expect(isClickNotDrag({ x: 100, y: 100 }, { x: 101, y: 100 })).toBe(true)
    expect(isClickNotDrag({ x: 100, y: 100 }, { x: 100 + MIN_BOX_SIDE, y: 100 })).toBe(false)
    expect(isClickNotDrag({ x: 100, y: 100 }, { x: 300, y: 250 })).toBe(false)
  })
})

// ─── P0 (review độc lập 22-11): ngưỡng click/kéo phải ở KHÔNG GIAN NGƯỜI DÙNG ────────────────────
describe('clickToleranceImagePx', () => {
  it('khung 1920 hiển thị 600 CSS px ⇒ ngưỡng quy đổi đúng, KHÔNG phải 4 px ảnh', () => {
    const nguong = clickToleranceImagePx({ left: 0, top: 0, width: 600, height: 400 }, CANVAS)
    // 5 CSS px * (1920/600) = 16 px ảnh
    expect(nguong).toBeCloseTo((CLICK_TOLERANCE_CSS * 1920) / 600, 6)
    expect(nguong).toBeGreaterThan(4)
  })

  it('ngưỡng LUÔN nhất quán trong không gian người dùng (≈5 CSS px) ở mọi cỡ khung', () => {
    const rect = { left: 0, top: 0, width: 600, height: 400 }
    for (const w of [160, 640, 1280, 1920, 3840]) {
      const canvas = { width: w, height: Math.round(w * 0.75) }
      const cssPx = (clickToleranceImagePx(rect, canvas) * rect.width) / canvas.width
      expect(cssPx).toBeCloseTo(CLICK_TOLERANCE_CSS, 6)
    }
  })

  it('rung tay 2 CSS px trên khung 1920 vẫn là CLICK (bug P0: trước đây bị coi là KÉO)', () => {
    const rect = { left: 0, top: 0, width: 600, height: 400 }
    const nguong = clickToleranceImagePx(rect, CANVAS)
    const tiLe = CANVAS.width / rect.width
    // nhấn-nhả lệch 2 CSS px theo phương ngang = 6,4 px ảnh
    expect(isClickNotDrag({ x: 100, y: 100 }, { x: 100 + 2 * tiLe, y: 100 }, nguong)).toBe(true)
  })

  it('kéo thật 40 CSS px vẫn là KÉO', () => {
    const rect = { left: 0, top: 0, width: 600, height: 400 }
    const nguong = clickToleranceImagePx(rect, CANVAS)
    const tiLe = CANVAS.width / rect.width
    expect(isClickNotDrag({ x: 100, y: 100 }, { x: 100 + 40 * tiLe, y: 100 }, nguong)).toBe(false)
  })

  it('khung chưa layout (width = 0) thì dùng ngưỡng px ảnh, không chia cho 0', () => {
    expect(clickToleranceImagePx({ left: 0, top: 0, width: 0, height: 0 }, CANVAS)).toBe(MIN_BOX_SIDE)
    expect(pointMergeRadiusImagePx({ left: 0, top: 0, width: 0, height: 0 }, CANVAS)).toBe(MIN_POINT_DIST)
  })
})

describe('pointMergeRadiusImagePx', () => {
  it('khung 1920@600: hai cú click cách 3 CSS px là CÙNG chỗ ⇒ thay điểm (trước đây thành 2 điểm)', () => {
    const rect = { left: 0, top: 0, width: 600, height: 400 }
    const banKinh = pointMergeRadiusImagePx(rect, CANVAS)
    const tiLe = CANVAS.width / rect.width
    const pts = addPoint([{ x: 500, y: 400, label: 1 }], { x: 500 + 3 * tiLe, y: 400, label: 0 }, banKinh)
    expect(pts).toHaveLength(1)
    expect(pts[0].label).toBe(0)
  })

  it('khung nhỏ 160@600: hai cú click cách 20 CSS px là HAI điểm (trước đây bị gộp)', () => {
    const rect = { left: 0, top: 0, width: 600, height: 450 }
    const nho = { width: 160, height: 120 }
    const banKinh = pointMergeRadiusImagePx(rect, nho)
    const tiLe = nho.width / rect.width
    const pts = addPoint([{ x: 20, y: 20, label: 1 }], { x: 20 + 20 * tiLe, y: 20, label: 1 }, banKinh)
    expect(pts).toHaveLength(2)
  })
})

// ─── P2 (review độc lập 22-11): điểm ở px CUỐI làm `engine.start` ném ValueError ────────────────
describe('clampPointInCanvas', () => {
  it('kẹp vào TRONG khung (w-1, h-1) — biên phải không hợp lệ với điểm', () => {
    expect(clampPointInCanvas({ x: 1920, y: 1280 }, CANVAS)).toEqual({ x: 1919, y: 1279 })
    expect(clampPointInCanvas({ x: -3, y: 5000 }, CANVAS)).toEqual({ x: 0, y: 1279 })
    expect(clampPointInCanvas({ x: 100, y: 200 }, CANVAS)).toEqual({ x: 100, y: 200 })
  })
})
