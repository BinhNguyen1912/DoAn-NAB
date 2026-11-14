/**
 * Câu chữ cho phần "nhịp mask" của chế độ live (tách khỏi component để test headless được).
 *
 * Vì sao cần: khi chạy hybrid, FPS phát (~30) KHÔNG phải nhịp mask (~8,5). UI phải nói rõ hai
 * con số, nếu không người xem báo cáo sẽ tưởng mask được suy luận 30 lần/giây.
 */
import type { LiveStatus } from './api'

type Rhythm = Pick<LiveStatus, 'mask_fps' | 'stability' | 'stability_n' | 'latency_ms' | 'empty_runs'
  | 'empty_frac_window' | 'empty_window_n'>

/** Dòng mô tả nhịp mask; `null` khi nguồn không báo (chế độ raw / webcam thường).
 *
 * Ba chỗ từng gây hiểu sai (review 09-11):
 *  - "độ ổn định N%" ⇒ `stability` là IoU giữa hai mask **liên tiếp**, chỉ đo **nhấp nháy**.
 *  - Nhãn "nhấp nháy N%" mà in thẳng `stability × 100` là **ĐẢO CHIỀU SỐ**: `stability = 1.0` mới là
 *    *không* nhấp nháy, nên phải in `100 − stability`. Tệ hơn, `stability = 0` vừa là "chưa đo"
 *    (default) vừa bị gán 0 khi mask RỖNG ⇒ in "nhấp nháy 0 %" = "êm tuyệt đối" đúng lúc model rơi
 *    vật. Từ 10-11 backend phân biệt được (`stability = null` + `stability_n = 0` = chưa đo;
 *    `0,0` + `stability_n > 0` = ĐO ĐƯỢC), nên UI chỉ in số khi `stability_n > 0`.
 *  - "mất dấu: N lần" ⇒ `empty_runs` là bộ đếm **trọn đời, không bao giờ giảm**; ưu tiên tỉ lệ theo
 *    **cửa sổ 200 lần chạy gần nhất** (`empty_frac_window`).
 */
export function maskRhythmLine(status: Rhythm | null | undefined): string | null {
  if (!status || !(status.mask_fps > 0)) return null
  const fps = status.mask_fps.toFixed(1)
  // `stability` giờ có encoding "chưa đo": `null` (+ `stability_n = 0`). `0` là số ĐO ĐƯỢC
  // (hai mask rời nhau) ⇒ phải in "nhấp nháy 100 %", không được nói "chưa đo" (ticket 18).
  const soOnDinh = status.stability
  const coSoOnDinh = Number.isFinite(soOnDinh) && (soOnDinh as number) >= 0
    && (status.stability_n ?? 0) > 0
  const flicker = coSoOnDinh
    ? `nhấp nháy mask: ${100 - Math.round((soOnDinh as number) * 100)}%`
    : 'nhấp nháy mask: chưa đo'
  const latency = Math.round(status.latency_ms)
  let lost = ''
  const windowN = status.empty_window_n ?? 0
  const windowFrac = status.empty_frac_window
  if (windowN > 0 && windowFrac != null) {
    lost = ` · mất dấu: ${Math.round(windowFrac * 100)}% của ${windowN} lần chạy gần nhất`
  } else if (status.empty_runs > 0) {
    lost = ` · mất dấu (cả phiên): ${status.empty_runs} lần`
  }
  return `Mask mới: ${fps} lần/giây · ${flicker} · độ trễ model: ${latency} ms${lost}`
}

type MaskAge = Pick<LiveStatus, 'mask_age_total_ms' | 'mask_age_p95' | 'age_n'>

/** Ngưỡng coi mask là "CŨ" (ms). Đo trên máy này: tuổi dữ liệu THẬT p95 = 268–301 ms ở
 * `image_size 192` (`data/chu_ky_chai_binh1_*_metrics.json`). 1500 ms ≈ 5× mức bình thường ⇒ lúc đó
 * vật đã đi chỗ khác và mask đang chỉ vào chỗ cũ, phải nói to chứ không chỉ in số. */
export const MASK_AGE_CANH_BAO_MS = 1500

/** Dòng "mask đang hiển thị cũ bao nhiêu" — `null` khi chỉ số CHƯA ĐO.
 *
 * Vì sao phải hiện: HUD báo 30 FPS nhưng mask chỉ mới ~8–9 lần/giây, nên ảnh người xem thấy là dữ
 * liệu cũ cỡ 0,2–0,3 s (`mask_age_total_ms`). Không in ra thì người xem (và người viết báo cáo) sẽ
 * hiểu "mask 30 FPS". `null` KHÁC `0`: `0` là mask tươi tuyệt đối, `null` là worker bản cũ chưa ghi.
 */
export function maskAgeLine(status: MaskAge | null | undefined): string | null {
  if (!status) return null
  const total = status.mask_age_total_ms
  if (total == null || !Number.isFinite(total) || total < 0) return null
  const coP95 = status.age_n > 0 && status.mask_age_p95 != null
  const p95 = coP95 ? ` · p95 ${Math.round(status.mask_age_p95 as number)} ms của ${status.age_n} mẫu` : ''
  if (total >= MASK_AGE_CANH_BAO_MS) {
    return `Mask CŨ: ${(total / 1000).toFixed(1)} s (vật có thể đã di chuyển)${p95}`
  }
  return `Mask đang hiển thị: ${Math.round(total)} ms tuổi${p95}`
}

/** Có nên tô cảnh báo cho dòng mask age không (dùng cho class CSS/role alert). */
export function maskAgeIsStale(status: MaskAge | null | undefined): boolean {
  const total = status?.mask_age_total_ms
  return total != null && Number.isFinite(total) && total >= MASK_AGE_CANH_BAO_MS
}

type Drift = Pick<LiveStatus, 'mask_fps' | 'drift_p05' | 'drift_n'>

/** Dòng chẩn đoán "ô bao đang hiển thị khớp lần VOS kế tiếp bao nhiêu"; `null` khi không có model.
 *
 * Hai điều bắt buộc:
 *  - **Ngưỡng mẫu lấy từ backend** (`drift_p05 == null` khi < 30 mẫu) — KHÔNG nhân bản hằng số ở
 *    đây, nếu backend nâng ngưỡng thì UI sẽ in "chưa đo được (35/30 mẫu)".
 *  - **Không gọi là "lệch"**: `drift_p05` là IoU (cao = tốt); ca xấu nhất là `0.00`, viết "LK lệch
 *    0.00" sẽ đọc thành "không lệch" (review 09-11, P2). Nói đúng đại lượng + nhãn "không phải độ
 *    chính xác" (AGENTS §6).
 */
export function driftLine(status: Drift | null | undefined): string | null {
  if (!status || !(status.mask_fps > 0)) return null
  const n = status.drift_n ?? 0
  if (status.drift_p05 == null) {
    return `IoU tự nhất quán (LK↔VOS): chưa đo được (${n} mẫu) — không kết luận`
  }
  return `IoU tự nhất quán p05 (LK↔VOS): ${status.drift_p05.toFixed(2)} · ${n} mẫu gần nhất · ` +
    'không phải độ chính xác'
}

/** FPS phát để hiển thị: ưu tiên số do CHÍNH worker đo (nguồn của mọi số trong báo cáo). */
export function shownFps(status: Pick<LiveStatus, 'measured_fps' | 'display_fps'> | null | undefined): number {
  if (!status) return 0
  return status.display_fps > 0 ? status.display_fps : status.measured_fps
}

/** Dòng "model chạy trên thiết bị nào"; `null` khi nguồn không báo (chế độ raw / worker bản cũ).
 *
 * Vì sao phải hiện: mọi con số FPS/độ trễ chỉ đúng cho MỘT thiết bị. Cùng mã nguồn cho 97 ms @192
 * trên CPU laptop này và 49,6 ms/frame (~20,15 FPS) trên GPU T4 (`docs/task/22-10-2026-colab-gpu-
 * so-lieu-va-fix.md`) — không nói thiết bị thì người xem báo cáo không tái lập được
 * (ticket 21; AGENTS §6). `''` (chưa biết) KHÔNG được in thành "cpu".
 */
export function deviceLine(status: Pick<LiveStatus, 'device'> | null | undefined): string | null {
  const device = (status?.device ?? '').trim()
  if (!device) return null
  const nhan = device === 'cuda' ? 'cuda (GPU)' : device === 'cpu' ? 'cpu (CPU)' : device
  return `Thiết bị chạy model: ${nhan} — FPS/độ trễ chỉ đúng cho thiết bị này`
}

/** Câu chữ cho "ảnh có đứng không" — suy từ `frames` KHÔNG tăng, không phải từ `state`.
 *
 * Vì sao cần (review 13-11, góc nhìn chất lượng): relay giữ frame CUỐI khi camera hỏng
 * (`scripts/win_camera_relay.py`), nên `/snapshot.jpg` vẫn 200 và `state` vẫn `running` trong khi
 * ảnh trên màn hình đứng im. Tín hiệu trung thực duy nhất là `frames`: backend chỉ đếm khi NỘI DUNG
 * frame đổi (`src/api/live.py`), nên ảnh đứng ⇒ `frames` đứng và `measured_fps → 0`.
 *
 * Cấm viết "nguồn đã chết": cảnh tĩnh (người ngồi im) cũng làm `frames` đứng — chỉ được nói
 * "không có frame mới trong N s".
 *
 * @param stalledSeconds số giây liên tiếp `frames` không đổi (0 = vừa đổi)
 */
export function stallLine(
  status: Pick<LiveStatus, 'state' | 'frames' | 'measured_fps'> | null | undefined,
  stalledSeconds: number,
): string | null {
  if (!status || status.state !== 'running') return null
  if (!(stalledSeconds >= 3)) return null
  return (
    `Không có frame mới trong ${stalledSeconds.toFixed(1)} s` +
    ` (frame đứng ở ${status.frames}, FPS đo được ${status.measured_fps.toFixed(1)})` +
    ' — cảnh có thể tĩnh, hoặc camera/relay đã ngừng trả ảnh mới; bấm "Dò lại" rồi "Bật phát" để kiểm.'
  )
}

/** Nhãn nguồn gợi ý kèm BẰNG CHỨNG đo được — thay cho chữ "đã kiểm" trống rỗng.
 *
 * `available` chỉ có nghĩa "thử được lúc `checked_at`"; nó KHÔNG chứng minh nguồn đang chạy và
 * cũng KHÔNG chứng minh ảnh còn mới (relay phục vụ lại frame cũ). Vì vậy nhãn phải nói rõ:
 * dò lúc mấy giờ, kiểm bằng gì, mất bao lâu.
 */
export function sourceCheckLine(
  candidate: { check?: string; latency_ms?: number } | null | undefined,
  checkedAt?: string | null,
): string {
  if (!candidate) return 'chưa dò nguồn'
  const gio = checkedAt ? checkedAt.slice(11, 19) : ''
  const bangChung = candidate.check || 'không có bằng chứng'
  const ms = candidate.latency_ms ?? 0
  return `dò lúc ${gio || '—'} · ${bangChung} · ${ms} ms`
}
