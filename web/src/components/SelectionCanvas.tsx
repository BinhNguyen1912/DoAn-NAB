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
import type { BBox } from '../api'
import { boxFromPoints, describeBox, isUsableBox, toImagePoint, type Point } from '../selection'

interface Props {
  src: string
  value: BBox | null
  onChange: (box: BBox | null) => void
}

export function SelectionCanvas({ src, value, onChange }: Props): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const startRef = useRef<Point | null>(null)
  const [draft, setDraft] = useState<BBox | null>(null)
  const [size, setSize] = useState<{ w: number; h: number } | null>(null)

  const paint = useCallback((box: BBox | null) => {
    const canvas = canvasRef.current
    const img = imageRef.current
    if (!canvas || !img) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    if (!box) return
    ctx.lineWidth = Math.max(2, canvas.width / 320)
    ctx.strokeStyle = '#ffd400'
    ctx.strokeRect(box.x, box.y, box.w, box.h)
    ctx.fillStyle = 'rgba(255, 212, 0, 0.15)'
    ctx.fillRect(box.x, box.y, box.w, box.h)
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
    if (size) paint(draft ?? value)
  }, [size, value, draft, paint])

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
    if (!startRef.current) return
    const box = boxFromPoints(startRef.current, pointOf(event))
    startRef.current = null
    setDraft(null)
    onChange(isUsableBox(box) ? box : null)   // click nhầm (hộp quá nhỏ) → bỏ chọn
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
        Kéo chuột vẽ ô quanh vật thể cần bám. Toạ độ đang chọn: {describeBox(value)}
      </p>
    </div>
  )
}
