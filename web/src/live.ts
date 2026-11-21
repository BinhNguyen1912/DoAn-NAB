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

/** Ba trường của `/api/live/status` cần cho dòng cấu hình; `state` để KHÔNG báo "chưa kiểm được"
 * trong lúc worker còn đang nạp model (20–240 s) — đó là bình thường, không phải bất thường. */
type CauHinh = {
  cau_hinh_lech?: string[] | null
  image_size_hieu_luc?: number | null
  state?: string
}

/** Dòng cảnh báo "model chạy KHÁC cấu hình đã yêu cầu" — `null` khi không có gì để nói.
 *
 * Vì sao phải hiện: `--image-size 192` chỉ là **yêu cầu**; nếu override không được áp thì model chạy
 * 1024 và mọi số của phiên (FPS, độ trễ, tuổi mask) gắn với một cấu hình KHÁC cấu hình người dùng
 * chọn (15-11). Trước đây cảnh báo chỉ nằm trong `worker.log` ⇒ người ngồi xem không biết.
 *
 * Bốn trạng thái KHÔNG được gộp (AGENTS §6):
 *  - `cau_hinh_lech == null` ⇒ **CHƯA BIẾT** (worker bản cũ) → không in gì, KHÔNG in "đã khớp";
 *  - `[]` + `image_size_hieu_luc` có số ⇒ đã kiểm và khớp → không in gì;
 *  - `[]` + `image_size_hieu_luc == null` ⇒ **CHƯA KIỂM ĐƯỢC** (`so_khop_cau_hinh` trả `[]` cả khi
 *    không đọc được `image_size` của predictor) → hint, KHÔNG phải "đã khớp" (review 15-11, P2);
 *  - có phần tử ⇒ cảnh báo đỏ, kèm giá trị thật nếu biết.
 */
export function configMismatchLine(status: CauHinh | null | undefined): string | null {
  const lech = status?.cau_hinh_lech
  if (!Array.isArray(lech)) return null
  const thuc = status?.image_size_hieu_luc
  const bietThuc = thuc != null && Number.isFinite(thuc)
  if (lech.length === 0) {
    // "Không khoá nào lệch" ≠ "đã kiểm": giai đoạn `loading` và ca predictor không khai báo
    // `image_size` đều rơi vào đây.
    if (bietThuc || status?.state !== 'running') return null
    return 'Cấu hình: CHƯA kiểm được model chạy ở độ phân giải nào — đừng coi là đã khớp yêu cầu'
  }
  const khoa = lech.join(', ')
  const con = bietThuc ? ` (model đang chạy ${thuc} px)` : ''
  return `CẤU HÌNH LỆCH (${khoa})${con}: số của phiên này gắn với cấu hình KHÁC cấu hình đã chọn — ` +
    'dừng và bật lại với đúng tham số trước khi trích số'
}

/** Có nên tô cảnh báo (role="alert") cho dòng cấu hình không: chỉ khi LỆCH thật. */
export function configMismatchIsAlert(status: CauHinh | null | undefined): boolean {
  const lech = status?.cau_hinh_lech
  return Array.isArray(lech) && lech.length > 0
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

type SucKhoe = Pick<LiveStatus, 'suc_khoe' | 'suc_khoe_cau' | 'mask_fps'>

/** Câu "chất lượng bám" cho HUD — `null` khi ổn, khi chế độ raw, hoặc khi worker bản cũ.
 *
 * Vì sao cần một câu thay vì bắt người xem tự ghép hai con số: `drift_p05` thấp có HAI nguyên nhân
 * khác hẳn nhau — model mất vật (mask rỗng nhiều) hay ô hiển thị lệch ô VOS (mask vẫn có). Ghép sai
 * thì báo cáo nói sai thứ đang hỏng (ticket #14; trước 19-11 chưa tách được vì p05 tính cả phiên).
 *
 * `suc_khoe == null` ⇒ worker bản cũ: trả `null` chứ KHÔNG in "chất lượng tốt".
 */
export function sucKhoeLine(status: SucKhoe | null | undefined): string | null {
  if (!status || !(status.mask_fps > 0)) return null
  const sk = status.suc_khoe
  if (!sk) return null
  if (sk.co === 'ok') return null
  const cau = status.suc_khoe_cau
  if (cau) return cau
  // Dự phòng khi backend bản cũ có `suc_khoe` mà thiếu câu chữ.
  if (sk.co === 'model_lost') return 'Chất lượng bám: model MẤT VẬT (mask rỗng nhiều)'
  if (sk.co === 'drift_trend') return 'Chất lượng bám: ô hiển thị lệch ô VOS (mask không rỗng)'
  return `Chất lượng bám: chưa đo được (${sk.n} mẫu)`
}

/** Cờ này có phải CẢNH BÁO (đổi màu) hay chỉ là thông tin (`not_measured`). */
export function sucKhoeIsAlert(status: SucKhoe | null | undefined): boolean {
  const co = status?.suc_khoe?.co
  return co === 'model_lost' || co === 'drift_trend'
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

/**
 * Câu chữ cho "CÓ BẰNG CHỨNG về vật" (plan 21-11 P4) — `null` khi đang bám bình thường.
 *
 * Vì sao phải có: `LiveStatus.state` chỉ là **tiến trình** (`running`), nên panel in "Trạng thái:
 * running" đúng lúc worker đã ẨN ô vì không có bằng chứng nào. Ba trạng thái phải phân biệt:
 *  - `bam === null` ⇒ **chưa xác định** (worker bản cũ / frame đầu) — cấm in "đang bám";
 *  - `bam === 'no_evidence'` ⇒ nói rõ lý do, kèm số frame đã mất bằng chứng (đếm được);
 *  - `bam === 'tracking'` ⇒ `null` (không chiếm chỗ trên HUD).
 */
export function bamLine(status: { bam?: string | null; bam_ly_do?: string | null
  bam_no_evidence_n?: number; nghi_doi_tuong?: boolean
  nghi_doi_tuong_n?: number } | null | undefined): string | null {
  if (!status) return null
  // Cổng nhảy CÓ NHỚ (21-11). Đo trên phiên thật: cổng báo đúng 1 lần (bám sang cửa/tường be cùng
  // tông) rồi hệ vẽ mask SAI 65 frame vì chuyển động sau đó lại mượt. Nay worker ẩn ô và HỎI người
  // dùng — câu này phải nói rõ 2 lựa chọn, không chỉ "đã ẩn".
  if (status.nghi_doi_tuong === true || status.bam === 'nghi_doi_tuong') {
    const n = status.nghi_doi_tuong_n ?? 0
    const dem = n > 0 ? ` · ${n} frame đã ẩn` : ''
    return 'Nghi đã bám sang ĐỐI TƯỢNG KHÁC (ô bao nhảy vô lý) — ô đã được ẩn khỏi ảnh. '
      + 'Bấm "Vẫn đúng, tiếp tục" nếu vẫn là vật đã chọn, hoặc chọn lại ô.' + dem
  }
  if (status.bam == null) return null
  if (status.bam === 'tracking') return null
  // HIỆN CHỈ có `mask_rong`: `lk_tu_choi` từng có trong bản nháp và đã bị bỏ vì ĐO ĐƯỢC nó báo oan
  // 296/400 frame (LK từ chối ⇒ vẫn hiển thị ô VOS THẬT của lần VOS gần nhất). Đừng thêm lại nhánh đó
  // nếu backend không phát giá trị ấy (review 21-11, P2).
  const lyDo = status.bam_ly_do === 'mask_rong' ? 'model không thấy vật' : 'không rõ lý do'
  const n = status.bam_no_evidence_n ?? 0
  const dem = n > 0 ? ` · ${n} frame mất bằng chứng` : ''
  return `Không có bằng chứng về vật (${lyDo}) — ô đã được ẩn khỏi ảnh để không vẽ ô suy diễn`
    + dem
}
