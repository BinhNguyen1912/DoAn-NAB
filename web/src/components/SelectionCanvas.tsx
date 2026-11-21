/**
 * SelectionCanvas — vẽ frame đầu của video và cho người dùng kéo chuột chọn đối tượng.
 *
 * Chức năng: hiển thị ảnh preview trên <canvas>, bắt sự kiện chuột để tạo ô chữ nhật.
 * Input  : src (URL ảnh preview), value (ô đang chọn, null = chưa chọn), onChange (callback).
 * Output : gọi onChange với toạ độ ĐÃ QUY ĐỔI về pixel gốc của video.
 * Lưu ý  : toàn bộ toán học nằm ở `selection.ts` (hàm thuần, có test vitest). Component này chỉ
 *          lo vẽ + nối sự kiện, nhờ vậy không có hai bản logic quy đổi toạ độ lệch nhau.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { BBox, PointPrompt } from '../api'
import { boxFromPoints, describeBox, isUsableBox, toImagePoint, type Point } from '../selection'

interface Props {
  src: string
  value: BBox | null
  points?: PointPrompt[]
  onChange: (box: BBox | null, points?: PointPrompt[]) => void
}

export function SelectionCanvas({ src, value, points: initialPoints, onChange }: Props): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const startRef = useRef<Point | null>(null)
  const [draft, setDraft] = useState<BBox | null>(null)
  const [size, setSize] = useState<{ w: number; h: number } | null>(null)
  const [pointList, setPointList] = useState<PointPrompt[]>(initialPoints || [])
  const [pointMode, setPointMode] = useState<'positive' | 'negative'>('positive')

  // Đồng bộ points từ props
  useEffect(() => {
    if (initialPoints) setPointList(initialPoints)
  }, [initialPoints])

  const paint = useCallback((box: BBox | null, pts: PointPrompt[]) => {
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
    if (pts && pts.length > 0) {
      const radius = Math.max(4, Math.round(canvas.width / 160))
      for (const p of pts) {
        ctx.beginPath()
        ctx.arc(p.x, p.y, radius, 0, 2 * Math.PI)
        ctx.fillStyle = p.label === 1 ? '#00e676' : '#ff1744'
        ctx.fill()
        ctx.lineWidth = 2
        ctx.strokeStyle = '#ffffff'
        ctx.stroke()
      }
    }
  }, [])

  // Nạp ảnh preview: canvas chỉ được render SAU khi biết kích thước thật của video.
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

  // Vẽ lại khi ảnh sẵn sàng hoặc khi hộp chọn/điểm thay đổi
  useEffect(() => {
    if (size) paint(draft ?? value, pointList)
  }, [size, value, draft, pointList, paint])

  const loading = size === null

  const pointOf = (event: React.MouseEvent<HTMLCanvasElement>): Point => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    return toImagePoint(event.clientX, event.clientY, canvas.getBoundingClientRect(), canvas)
  }

  const onMouseDown = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (loading) return
    if (event.button !== 0) return // Chỉ bắt chuột trái
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
    if (!startRef.current) return
    const endPoint = pointOf(event)
    const box = boxFromPoints(startRef.current, endPoint)
    const isDrag = Math.hypot(endPoint.x - startRef.current.x, endPoint.y - startRef.current.y) > 6

    startRef.current = null
    setDraft(null)

    if (isDrag) {
      // Người dùng vừa kéo một ô mới
      const usable = isUsableBox(box) ? box : null
      setPointList([])
      onChange(usable, [])
    } else if (value) {
      // Người dùng click điểm khi đã có ô bao
      const label = event.shiftKey || pointMode === 'negative' ? 0 : 1
      const newPoint: PointPrompt = { x: endPoint.x, y: endPoint.y, label }
      const nextPoints = [...pointList, newPoint]
      setPointList(nextPoints)
      onChange(value, nextPoints)
    } else {
      onChange(null, [])
    }
  }

  const onContextMenu = (event: React.MouseEvent<HTMLCanvasElement>) => {
    event.preventDefault()
    if (!value) return
    const p = pointOf(event)
    const newPoint: PointPrompt = { x: p.x, y: p.y, label: 0 }
    const nextPoints = [...pointList, newPoint]
    setPointList(nextPoints)
    onChange(value, nextPoints)
  }

  const posCount = pointList.filter((p) => p.label === 1).length
  const negCount = pointList.filter((p) => p.label === 0).length

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
          onContextMenu={onContextMenu}
          onMouseLeave={(event) => {
            if (startRef.current) finish(event)
          }}
        />
      )}
      {loading && <p className="hint">Đang tải khung hình…</p>}

      {value && (
        <div style={{ marginTop: '0.4rem', display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="hint" style={{ fontWeight: 600 }}>Chấm điểm:</span>
          <button
            type="button"
            className={`button small ${pointMode === 'positive' ? '' : 'ghost'}`}
            style={{ padding: '0.2rem 0.5rem', fontSize: '0.85rem' }}
            onClick={() => setPointMode('positive')}
          >
            (+) Thân vật ({posCount})
          </button>
          <button
            type="button"
            className={`button small ${pointMode === 'negative' ? '' : 'ghost'}`}
            style={{ padding: '0.2rem 0.5rem', fontSize: '0.85rem' }}
            onClick={() => setPointMode('negative')}
          >
            (-) Nền ngoài ({negCount})
          </button>
          {pointList.length > 0 && (
            <button
              type="button"
              className="button small ghost"
              style={{ padding: '0.2rem 0.5rem', fontSize: '0.85rem' }}
              onClick={() => {
                setPointList([])
                onChange(value, [])
              }}
            >
              Xoá {pointList.length} điểm
            </button>
          )}
        </div>
      )}

      <p className="hint" data-testid="bbox-hint">
        Kéo chuột vẽ ô quanh đối tượng. {value ? 'Click chuột để thêm điểm (+) vật thể hoặc (-) nền sát viền để chặn tràn mask. ' : ''}Toạ độ: {describeBox(value)}
      </p>
    </div>
  )
}
