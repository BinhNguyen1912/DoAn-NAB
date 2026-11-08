/**
 * Câu chữ cho phần "nhịp mask" của chế độ live (tách khỏi component để test headless được).
 *
 * Vì sao cần: khi chạy hybrid, FPS phát (~30) KHÔNG phải nhịp mask (~8,5). UI phải nói rõ hai
 * con số, nếu không người xem báo cáo sẽ tưởng mask được suy luận 30 lần/giây.
 */
import type { LiveStatus } from './api'

type Rhythm = Pick<LiveStatus, 'mask_fps' | 'stability' | 'latency_ms'>

/** Dòng mô tả nhịp mask; `null` khi nguồn không báo (chế độ raw / webcam thường). */
export function maskRhythmLine(status: Rhythm | null | undefined): string | null {
  if (!status || !(status.mask_fps > 0)) return null
  const fps = status.mask_fps.toFixed(1)
  const stability = Math.round(status.stability * 100)
  const latency = Math.round(status.latency_ms)
  return `Mask mới: ${fps} lần/giây · độ ổn định: ${stability}% · độ trễ model: ${latency} ms`
}
