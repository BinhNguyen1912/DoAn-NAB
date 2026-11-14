/**
 * api.ts — toàn bộ lời gọi HTTP tới backend FastAPI ở MỘT chỗ.
 *
 * Chức năng: khai báo kiểu dữ liệu (khớp src/api/schemas.py) + hàm gọi từng endpoint.
 * Input  : dữ liệu từ UI (file video, bbox).
 * Output : Promise trả dữ liệu đã parse; ném Error có message tiếng Việt khi lỗi.
 * Lưu ý  : dev dùng đường dẫn tương đối '/api/...' và Vite proxy sang cổng 8000
 *          (xem vite.config.ts) — không hardcode host để build xong nhúng vào FastAPI vẫn chạy.
 */

export type JobState = 'uploaded' | 'queued' | 'running' | 'done' | 'error'

export interface BBox {
  x: number
  y: number
  w: number
  h: number
}

export interface JobSummary {
  total_frames?: number
  mean_latency_ms?: number
  p95_latency_ms?: number
  effective_fps?: number
  mean_score?: number
  /** Tên khoá PHẢI khớp `MetricsLogger._summary_core()` (xem tests/test_api_routes.py). */
  lost_count?: number
  lost_ratio?: number
  frozen_frames?: number
  reacquiring_frames?: number
  reacquired_count?: number
}

export interface JobStatus {
  job_id: string
  state: JobState
  progress: number
  message: string
  created_at: string
  bbox: number[] | null
  artifacts: Record<string, string>
  summary: JobSummary | null
}

export interface UploadOptions {
  image_size?: number
  max_frames?: number
  max_trajectory?: number
  reid?: boolean
  cue?: 'face' | 'object' | 'both'
}

/** Đọc lỗi từ response và ném Error có message người đọc được. */
async function _error(res: Response): Promise<never> {
  let detail = `HTTP ${res.status}`
  try {
    const body = (await res.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') detail = body.detail
  } catch {
    // body không phải JSON — giữ message mặc định
  }
  throw new Error(detail)
}

/** Upload video và tạo job. Trả job_id. */
export async function createJob(file: File, opts: UploadOptions = {}): Promise<string> {
  const form = new FormData()
  form.append('file', file)
  if (opts.image_size !== undefined) form.append('image_size', String(opts.image_size))
  if (opts.max_frames !== undefined) form.append('max_frames', String(opts.max_frames))
  if (opts.max_trajectory !== undefined) form.append('max_trajectory', String(opts.max_trajectory))
  if (opts.reid !== undefined) form.append('reid', String(opts.reid))
  if (opts.cue !== undefined) form.append('cue', opts.cue)

  const res = await fetch('/api/jobs', { method: 'POST', body: form })
  if (!res.ok) await _error(res)
  const body = (await res.json()) as { job_id: string }
  return body.job_id
}

/** Lấy trạng thái + tiến trình + kết quả của job. */
export async function getJob(jobId: string): Promise<JobStatus> {
  const res = await fetch(`/api/jobs/${jobId}`)
  if (!res.ok) await _error(res)
  return (await res.json()) as JobStatus
}

/** Gửi ô chọn đối tượng để bắt đầu bám. */
export async function selectObject(jobId: string, bbox: BBox): Promise<void> {
  const res = await fetch(`/api/jobs/${jobId}/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bbox }),
  })
  if (!res.ok) await _error(res)
}

/** URL ảnh frame đầu để vẽ lên canvas chọn đối tượng. */
export function previewUrl(jobId: string, index = 0): string {
  return `/api/jobs/${jobId}/preview?index=${index}`
}

/** URL video kết quả / file CSV (lấy từ `artifacts`). */
export function artifactUrl(jobId: string, name: string): string {
  return `/api/jobs/${jobId}/artifacts/${name}`
}

/** Kiểm tra backend sống. */
export async function health(): Promise<boolean> {
  try {
    const res = await fetch('/health')
    return res.ok
  } catch {
    return false
  }
}


// --------------------------------------------------------------------------- live

export type LiveState = 'stopped' | 'loading' | 'running' | 'error'

export interface LiveStatus {
  state: LiveState
  source: string
  /** thiết bị model THẬT SỰ chạy: 'cpu' | 'cuda'; '' = chưa biết (chế độ raw / worker bản cũ) */
  device: string
  frames: number
  /** FPS PHÁT (frame hình/giây) — không phải nhịp mask */
  measured_fps: number
  /** FPS phát do CHÍNH worker đo (0 khi nguồn không báo) — số dùng trong báo cáo */
  display_fps: number
  /** nhịp MASK MỚI (số lần model chạy/giây); 0 khi chế độ raw hoặc nguồn không báo */
  mask_fps: number
  /** `null` = CHƯA ĐO (xem `stability_n`), khác `0` = đo được 0 / đang mất dấu */
  stability: number | null
  stability_n: number
  /** độ trễ suy luận gần nhất (ms) */
  latency_ms: number
  /** số lần model trả mask RỖNG (mất dấu thật) từ đầu phiên — bộ đếm TRỌN ĐỜI, không giảm */
  empty_runs: number
  /** tỉ lệ mất dấu trong 200 lần chạy GẦN NHẤT (null = chưa đủ mẫu) */
  empty_frac_window: number | null
  /** số mẫu của cửa sổ trên (0 = chưa có số) */
  empty_window_n: number
  /** phân vị 5 % của IoU(ô bao đã phát, ô bao VOS sửa lại) trên tối đa 200 MẪU DRIFT gần nhất
   * — ĐỘ TỰ NHẤT QUÁN, không phải độ chính xác; `null` khi chưa đủ mẫu */
  drift_p05: number | null
  /** số mẫu drift (0 ⇒ chưa đo, KHÔNG phải "drift = 0") */
  drift_n: number
  /** tuổi dữ liệu ảnh của mask ĐANG HIỂN THỊ (ms, queue+pre+vos+post+age của mẫu cuối);
   *  `null` = CHƯA ĐO (worker bản cũ) — khác `0` = mask tươi tuyệt đối */
  mask_age_total_ms: number | null
  /** phân vị 95 tuổi dữ liệu trên cửa sổ `age_n` mẫu; `null` khi chưa đủ mẫu */
  mask_age_p95: number | null
  /** số mẫu của cửa sổ tuổi dữ liệu (0 ⇒ chưa đo) */
  age_n: number
  message: string
}

export interface LiveStartOptions {
  /** raw = chỉ phát khung hình · track = bám đối tượng bằng model (cần bbox) */
  mode?: 'raw' | 'track'
  bbox?: BBox
  image_size?: number
  /** chạy model mỗi N frame; phần còn lại nội suy bằng LK (mặc định worker: 3) */
  vos_every?: number
}

/** Một nguồn frame backend DÒ được (kèm cờ đã kiểm bằng thử thật). */
export interface LiveSourceCandidate {
  source: string
  label: string
  kind: 'camera' | 'relay' | 'file'
  /** backend đã THỬ và dùng được LÚC DÒ — KHÔNG phải "đang chạy" (chỉ phiên live nói được điều đó) */
  available: boolean
  /** bằng chứng đã kiểm (vd 'nhận được ảnh JPEG') — hiện lên UI thay cho chữ "đã kiểm" */
  check: string
  /** thời gian dò nguồn này (ms) */
  latency_ms: number
  note: string
}

export interface LiveSources {
  /** nguồn NÊN dùng ngay ('' = không dò được) — UI tự điền vào ô "Nguồn frame" */
  suggested: string
  /** 'camera' | 'relay' | 'file' — rỗng khi không có gợi ý (gợi ý video ≠ gợi ý camera) */
  suggested_kind: string
  /** thời điểm dò (giờ máy chủ) — dò cũ ≠ dò mới */
  checked_at: string
  /** ngân sách thời gian của một lần dò (ms) */
  budget_ms: number
  candidates: LiveSourceCandidate[]
}

/** Dò nguồn frame backend dùng được (webcam / relay / video demo) để UI tự điền. */
export async function getLiveSources(): Promise<LiveSources> {
  const res = await fetch('/api/live/sources')
  if (!res.ok) await _error(res)
  return (await res.json()) as LiveSources
}

/** Bắt đầu phát trực tiếp từ nguồn frame (webcam/RTSP/snapshot/video file). */
export async function startLive(source: string, options: LiveStartOptions = {}): Promise<LiveStatus> {
  const res = await fetch('/api/live/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source, ...options }),
  })
  if (!res.ok) await _error(res)
  return (await res.json()) as LiveStatus
}

/** Dừng phát và giải phóng nguồn (webcam). */
export async function stopLive(): Promise<LiveStatus> {
  const res = await fetch('/api/live/stop', { method: 'POST' })
  if (!res.ok) await _error(res)
  return (await res.json()) as LiveStatus
}

/** Trạng thái phiên live (số frame + FPS thực đo). */
export async function getLiveStatus(): Promise<LiveStatus> {
  const res = await fetch('/api/live/status')
  if (!res.ok) await _error(res)
  return (await res.json()) as LiveStatus
}

/** Luồng MJPEG — dùng trực tiếp trong <img src>. */
export const LIVE_STREAM_URL = '/api/live/stream'

/** Frame JPEG mới nhất — dùng để đóng băng ảnh và kéo chuột chọn đối tượng. */
export const LIVE_FRAME_URL = '/api/live/frame'
