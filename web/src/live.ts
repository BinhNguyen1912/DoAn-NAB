/**
 * Câu chữ cho phần "nhịp mask" của chế độ live (tách khỏi component để test headless được).
 *
 * Vì sao cần: khi chạy hybrid, FPS phát (~30) KHÔNG phải nhịp mask (~8,5). UI phải nói rõ hai
 * con số, nếu không người xem báo cáo sẽ tưởng mask được suy luận 30 lần/giây.
 */
import type { LiveStatus } from './api'

type Rhythm = Pick<LiveStatus, 'mask_fps' | 'stability' | 'latency_ms' | 'empty_runs'
  | 'empty_frac_window' | 'empty_window_n'>

/** Dòng mô tả nhịp mask; `null` khi nguồn không báo (chế độ raw / webcam thường).
 *
 * Hai nhãn ở đây từng gây hiểu sai (review 09-11):
 *  - "độ ổn định N%" ⇒ `stability` chỉ là IoU giữa hai mask **liên tiếp** = đo **nhấp nháy**, không
 *    đo độ chính xác. Đổi thành "nhấp nháy mask N%".
 *  - "mất dấu: N lần" ⇒ `empty_runs` là bộ đếm **trọn đời, không bao giờ giảm**; in nó cho người
 *    xem tưởng "hiện đang mất dấu 26 lần". Ưu tiên tỉ lệ theo **cửa sổ 200 lần chạy gần nhất**.
 */
export function maskRhythmLine(status: Rhythm | null | undefined): string | null {
  if (!status || !(status.mask_fps > 0)) return null
  const fps = status.mask_fps.toFixed(1)
  const flicker = Math.round(status.stability * 100)
  const latency = Math.round(status.latency_ms)
  let lost = ''
  const windowN = status.empty_window_n ?? 0
  const windowFrac = status.empty_frac_window
  if (windowN > 0 && windowFrac != null) {
    lost = ` · mất dấu: ${Math.round(windowFrac * 100)}% của ${windowN} lần chạy gần nhất`
  } else if (status.empty_runs > 0) {
    lost = ` · mất dấu (cả phiên): ${status.empty_runs} lần`
  }
  return `Mask mới: ${fps} lần/giây · nhấp nháy mask: ${flicker}% · độ trễ model: ${latency} ms${lost}`
}

type Drift = Pick<LiveStatus, 'mask_fps' | 'drift_p05' | 'drift_n'>

/** Số mẫu tối thiểu để được nói về `drift_p05` (dưới mức này p05 ≈ min của N mẫu). */
export const DRIFT_MIN_SAMPLES = 30

/** Dòng chẩn đoán "LK nội suy lệch bao nhiêu"; `null` khi chế độ không có model.
 *
 * Tuyệt đối không hiện "tốt" khi chưa đo: `drift_n < 30` (hoặc `vos_every=1`) ⇒ nói rõ **chưa đo**,
 * vì vắng số không phải bằng chứng chất lượng (AGENTS §6).
 */
export function driftLine(status: Drift | null | undefined): string | null {
  if (!status || !(status.mask_fps > 0)) return null
  const n = status.drift_n ?? 0
  if (status.drift_p05 == null || n < DRIFT_MIN_SAMPLES) {
    return `LK: chưa đo được (${n}/${DRIFT_MIN_SAMPLES} mẫu) — không kết luận`
  }
  return `LK lệch p05: ${status.drift_p05.toFixed(2)} · ${n} mẫu gần nhất · ` +
    'IoU tự nhất quán (không phải độ chính xác)'
}

/** FPS phát để hiển thị: ưu tiên số do CHÍNH worker đo (nguồn của mọi số trong báo cáo). */
export function shownFps(status: Pick<LiveStatus, 'measured_fps' | 'display_fps'> | null | undefined): number {
  if (!status) return 0
  return status.display_fps > 0 ? status.display_fps : status.measured_fps
}
