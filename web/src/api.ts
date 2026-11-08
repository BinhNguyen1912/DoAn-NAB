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

export type LiveState = 'stopped' | 'running' | 'error'

export interface LiveStatus {
  state: LiveState
  source: string
  frames: number
  measured_fps: number
  message: string
}

/** Bắt đầu phát trực tiếp từ nguồn frame (webcam/RTSP/snapshot/video file). */
export async function startLive(source: string): Promise<LiveStatus> {
  const res = await fetch('/api/live/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source }),
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
