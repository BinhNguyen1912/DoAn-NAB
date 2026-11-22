/**
 * SelectionCanvas — vẽ frame đầu của video, cho người dùng kéo chuột chọn ô VÀ click điểm dương/âm.
 *
 * Chức năng: hiển thị ảnh preview trên <canvas>, bắt sự kiện chuột:
 *   - KÉO chuột  → tạo ô chữ nhật (như cũ)
 *   - CLICK      → thêm điểm DƯƠNG (thuộc vật) ở chỗ vừa click
 *   - Ctrl/Shift/Alt + CLICK → thêm điểm ÂM (vùng bám sai: nền, cửa, tường cùng tông)
 * Input  : src, value (ô đang chọn), points (điểm prompt), onChange, onPointsChange.
 * Output : toạ độ ĐÃ QUY ĐỔI về pixel gốc của video.
 * Lưu ý  : toàn bộ toán học nằm ở `selection.ts` (hàm thuần, có test vitest), gồm cả
 *          `isClickNotDrag` — nếu coi mọi thao tác chuột là kéo thì một cú click sẽ tạo ô 0×0 và
 *          XOÁ MẤT ô đang chọn (lỗi cũ). Component này chỉ vẽ + nối sự kiện.
 *
 * Vì sao có điểm âm: ca thật 21-11, vật be trơn bị bám sang cửa/tường be cùng tông; đo mask-cos
 * vùng sai 0,752–0,989 vs ca đúng 0,905 ⇒ không có ngưỡng cos nào tách được (AGENTS §6). Cách chữa
 * rẻ nhất là để người dùng chỉ thẳng vùng sai ngay ở bước prompt.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { BBox } from '../api'
import {
  addPoint,
  boxFromPoints,
  describeBox,
  describePoints,
  isClickNotDrag,
  isUsableBox,
  toImagePoint,
  type Point,
  type PromptPoint,
} from '../selection'

interface Props {
  src: string
  value: BBox | null
  onChange: (box: BBox | null) => void
  /**
   * Điểm prompt dương/âm — TUỲ CHỌN vì đường job offline chưa nhận điểm: `SelectRequest` KHAI
   * `points` nhưng `routes.select_object` chỉ chuyển bbox xuống service (routes.py:124), tức gửi
   * điểm lên đó sẽ bị bỏ IM LẶNG. Đường LIVE đã nối đủ (API → bbox.json → live_tracking).
   */
  points?: PromptPoint[]
  onPointsChange?: (points: PromptPoint[]) => void
}

export function SelectionCanvas({
  src,
  value,
  onChange,
  points = [],
  onPointsChange,
}: Props): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const startRef = useRef<Point | null>(null)
  const [draft, setDraft] = useState<BBox | null>(null)
  const [size, setSize] = useState<{ w: number; h: number } | null>(null)

  const paint = useCallback((box: BBox | null, diem: PromptPoint[]) => {
    const canvas = canvasRef.current
    const img = imageRef.current
    if (!canvas || !img) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    if (box) {
      ctx.lineWidth = Math.max(2, canvas.width / 320)
      ctx.strokeStyle = '#ffd400'
      ctx.strokeRect(box.x, box.y, box.w, box.h)
      ctx.fillStyle = 'rgba(255, 212, 0, 0.15)'
      ctx.fillRect(box.x, box.y, box.w, box.h)
    }
    // Điểm prompt: xanh = dương (vật), đỏ = âm (vùng KHÔNG phải vật).
    const r = Math.max(4, canvas.width / 140)
    for (const p of diem) {
      ctx.beginPath()
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2)
      ctx.fillStyle = p.label === 1 ? '#22c55e' : '#ef4444'
      ctx.fill()
      ctx.lineWidth = Math.max(1.5, r / 3)
      ctx.strokeStyle = '#ffffff'
      ctx.stroke()
      // Dấu + / − để người mù màu vẫn phân biệt được hai loại điểm.
      ctx.beginPath()
      ctx.lineWidth = Math.max(1.5, r / 3)
      ctx.strokeStyle = '#0b0b0b'
      ctx.moveTo(p.x - r / 2, p.y)
      ctx.lineTo(p.x + r / 2, p.y)
      if (p.label === 1) {
        ctx.moveTo(p.x, p.y - r / 2)
        ctx.lineTo(p.x, p.y + r / 2)
      }
      ctx.stroke()
    }
  }, [])

  // Nạp ảnh preview: canvas chỉ được render SAU khi biết kích thước thật của video.
  // Lý do (bug thật phát hiện bằng E2E 08-11): <canvas> chưa có width/height mặc định là
  // 300×150 → vừa nhấp nháy sai tỉ lệ, vừa làm boundingBox đổi giữa lúc kéo chuột ⇒ toạ độ lệch.
  useEffect(() => {
    setSize(null)
    imageRef.current = null
    const img = new Image()
    img.onload = () => {
      imageRef.current = img
      setSize({ w: img.naturalWidth, h: img.naturalHeight })
    }
    img.src = src
    return () => {
      img.onload = null
      img.onerror = null
    }
  }, [src])

  // Vẽ lại khi ảnh sẵn sàng hoặc khi hộp chọn thay đổi (canvas đã mount ở lần render này)
  useEffect(() => {
    if (size) paint(draft ?? value, points)
  }, [size, value, draft, points, paint])

  const loading = size === null

  const pointOf = (event: React.MouseEvent<HTMLCanvasElement>): Point => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    return toImagePoint(event.clientX, event.clientY, canvas.getBoundingClientRect(), canvas)
  }

  const onMouseDown = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (loading) return
    event.preventDefault()
    const point = pointOf(event)
    startRef.current = point
    setDraft({ x: point.x, y: point.y, w: 0, h: 0 })
  }

  const onMouseMove = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!startRef.current) return
    setDraft(boxFromPoints(startRef.current, pointOf(event)))
  }

  const finish = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const start = startRef.current
    if (!start) return
    const end = pointOf(event)
    startRef.current = null
    setDraft(null)

    if (isClickNotDrag(start, end)) {
      // CLICK = đặt ĐIỂM, không phải vẽ ô. Giữ nguyên ô đang có (trước đây click lạc xoá mất ô).
      // Ctrl/Shift/Alt = điểm ÂM (vùng bám sai); click thường = điểm DƯƠNG (thuộc vật).
      const am = event.ctrlKey || event.shiftKey || event.altKey || event.metaKey
      onPointsChange?.(addPoint(points, { x: end.x, y: end.y, label: am ? 0 : 1 }))
      return
    }
    const box = boxFromPoints(start, end)
    onChange(isUsableBox(box) ? box : null)   // kéo quá nhỏ → bỏ chọn
  }

  return (
    <div className="canvas-wrap">
      {size && (
        <canvas
          ref={canvasRef}
          width={size.w}
          height={size.h}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={finish}
          onMouseLeave={(event) => {
            if (startRef.current) finish(event)
          }}
        />
      )}
      {loading && <p className="hint">Đang tải khung hình…</p>}
      <p className="hint" data-testid="bbox-hint">
        <strong>Kéo</strong> chuột vẽ ô quanh vật thể cần bám. Toạ độ đang chọn: {describeBox(value)}
      </p>
      <p className="hint" data-testid="points-hint">
        <strong>Click</strong> = điểm <span style={{ color: '#22c55e' }}>dương</span> (thuộc vật) ·{' '}
        <strong>Ctrl/Shift + Click</strong> = điểm <span style={{ color: '#ef4444' }}>âm</span>{' '}
        (vùng bám <em>sai</em>: nền, cửa, tường cùng tông). Điểm đang đặt: {describePoints(points)}
      </p>
    </div>
  )
}
