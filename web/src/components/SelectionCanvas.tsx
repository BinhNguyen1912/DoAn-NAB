/**
 * SelectionCanvas — vẽ frame đầu của video và cho người dùng kéo chuột chọn đối tượng.
 *
 * Chức năng: hiển thị ảnh preview trên <canvas>, bắt sự kiện chuột để tạo/ sửa ô chữ nhật.
 * Input  : src (URL ảnh preview), value (ô đang chọn, null = chưa chọn), onChange (callback).
 * Output : gọi onChange với toạ độ ĐÃ QUY ĐỔI về pixel gốc của video.
 * Lưu ý  : canvas có kích thước nội tại = kích thước ảnh gốc, CSS chỉ thu nhỏ để vừa khung →
 *          mọi toạ độ chuột phải nhân với (canvas.width / rect.width), nếu không ô chọn
 *          sẽ lệch khi ảnh bị scale (bug rất dễ gặp khi video 1280px hiển thị 600px).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { BBox } from '../api'

interface Props {
  src: string
  value: BBox | null
  onChange: (box: BBox | null) => void
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function boxFrom(a: { x: number; y: number }, b: { x: number; y: number }): BBox {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    w: Math.abs(a.x - b.x),
    h: Math.abs(a.y - b.y),
  }
}

export function SelectionCanvas({ src, value, onChange }: Props): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const startRef = useRef<{ x: number; y: number } | null>(null)
  const [draft, setDraft] = useState<BBox | null>(null)
  const [loading, setLoading] = useState(true)

  const paint = useCallback((box: BBox | null) => {
    const canvas = canvasRef.current
    const img = imageRef.current
    if (!canvas || !img) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    if (!box || box.w <= 0 || box.h <= 0) return
    ctx.lineWidth = Math.max(2, canvas.width / 320)
    ctx.strokeStyle = '#ffd400'
    ctx.setLineDash([])
    ctx.strokeRect(box.x, box.y, box.w, box.h)
    ctx.fillStyle = 'rgba(255, 212, 0, 0.15)'
    ctx.fillRect(box.x, box.y, box.w, box.h)
  }, [])

  // Nạp ảnh preview một lần cho mỗi src
  useEffect(() => {
    setLoading(true)
    const img = new Image()
    img.onload = () => {
      imageRef.current = img
      const canvas = canvasRef.current
      if (canvas) {
        canvas.width = img.naturalWidth
        canvas.height = img.naturalHeight
      }
      paint(value)
      setLoading(false)
    }
    img.onerror = () => setLoading(false)
    img.src = src
    return () => {
      img.onload = null
      img.onerror = null
    }
  }, [src, paint])

  useEffect(() => {
    paint(draft ?? value)
  }, [value, draft, paint])

  const toNatural = (event: React.MouseEvent<HTMLCanvasElement>): { x: number; y: number } => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    return {
      x: clamp(Math.round((event.clientX - rect.left) * scaleX), 0, canvas.width),
      y: clamp(Math.round((event.clientY - rect.top) * scaleY), 0, canvas.height),
    }
  }

  const onMouseDown = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (loading) return
    event.preventDefault()
    const point = toNatural(event)
    startRef.current = point
    setDraft({ x: point.x, y: point.y, w: 0, h: 0 })
  }

  const onMouseMove = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!startRef.current) return
    setDraft(boxFrom(startRef.current, toNatural(event)))
  }

  const finish = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!startRef.current) return
    const box = boxFrom(startRef.current, toNatural(event))
    startRef.current = null
    setDraft(null)
    // Ô quá nhỏ (click nhầm) → coi như bỏ chọn
    if (box.w < 4 || box.h < 4) {
      onChange(null)
      return
    }
    onChange(box)
  }

  return (
    <div className="canvas-wrap">
      <canvas
        ref={canvasRef}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={finish}
        onMouseLeave={(event) => {
          if (startRef.current) finish(event)
        }}
      />
      {loading && <p className="hint">Đang tải khung hình…</p>}
      <p className="hint">
        Kéo chuột vẽ ô quanh vật thể cần bám. Toạ độ đang chọn:{' '}
        {value ? `${value.x}, ${value.y}, ${value.w}×${value.h}` : 'chưa có'}
      </p>
    </div>
  )
}
