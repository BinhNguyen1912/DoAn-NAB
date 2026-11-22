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

export interface PointPrompt {
  x: number
  y: number
  /**
   * 1 = positive (vật thể), 0 = negative (nền/vùng bám sai).
   * BẮT BUỘC: để tuỳ chọn thì payload quên `label` bị backend mặc định thành **dương** trong im
   * lặng (review độc lập 22-11, P3) — đúng loại "gửi mà không ai nhận biết".
   */
  label: 0 | 1
}

export interface JobSummary {
  total_frames?: number
  /** `0,0` khi chưa có mẫu (hợp đồng `effective_fps = 1000/mean`) — đọc `mean_latency_ms_n` trước. */
  mean_latency_ms?: number
  /** Số mẫu của `mean_latency_ms` (`0` ⇒ `0,0` là "chưa đo", không phải "xử lý tức thì"). */
  mean_latency_ms_n?: number
  /** `null` = CHƯA ĐO (phiên rỗng / toàn frame đóng băng), khác `0` = đo được 0 ms (ticket #32). */
  p95_latency_ms?: number | null
  /** Số mẫu của `p95_latency_ms` — phải hiện kèm con số, `n` nhỏ thì "p95" ≈ frame xấu nhất. */
  p95_latency_ms_n?: number
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
  /** khoá mà model chạy KHÁC cấu hình đã yêu cầu (vd ['image_size']);
   *  `null` = CHƯA BIẾT (worker bản cũ / khoá null) — null KHÔNG phải "khớp";
   *  `[]` = không khoá nào lệch, NHƯNG `[]` + `image_size_hieu_luc == null` = CHƯA KIỂM ĐƯỢC */
  cau_hinh_lech: string[] | null
  /** `image_size` model THẬT SỰ dùng; `null` = CHƯA kiểm được (khi đó `[]` ở trên không chứng
   *  minh model chạy đúng cấu hình) */
  image_size_hieu_luc: number | null
  message: string
  /** cờ phán quyết chất lượng bám (ticket #14); `null` = worker bản cũ CHƯA có cờ
   *  (KHÔNG được đọc thành "ok"). `co`: ok | model_lost | drift_trend | not_measured */
  suc_khoe: {
    co: 'ok' | 'model_lost' | 'drift_trend' | 'not_measured'
    ly_do: string
    /** p05 của cửa sổ `cua_so` mẫu gần nhất; `null` = chưa đủ mẫu */
    /** p05 của `cua_so` mẫu gần nhất — KHÁC `drift_p05` (200 mẫu); `null` = chưa đủ mẫu */
    p05: number | null
    n: number
    /** tỉ lệ mask rỗng trong CÙNG cửa sổ mẫu với `p05`; `null` = chưa đo (hoặc hai dãy lệch độ dài) */
    empty_frac: number | null
    /** số mẫu rỗng thật trong cửa sổ (`model_lost` đòi ≥ `empty_min_mau`) */
    empty_so_mau?: number
    empty_min_mau?: number
    cua_so: number
    nguong_vao: number
    nguong_ra: number
  } | null
  /** câu tiếng Việt cho HUD (`null` khi `ok` — không chiếm chỗ) */
  suc_khoe_cau: string | null
  /**
   * CÓ BẰNG CHỨNG về vật hay không — KHÁC `state` (state chỉ là tiến trình: running/stopped…).
   * `null` = CHƯA BIẾT (worker bản cũ / frame đầu), KHÔNG được đọc thành `'tracking'`.
   */
  bam: 'tracking' | 'no_evidence' | 'nghi_doi_tuong' | null
  /** `'mask_rong' | 'o_nhay'` | null */
  bam_ly_do: string | null
  /** số frame ĐÃ PHÁT ở trạng thái `no_evidence` */
  bam_no_evidence_n: number
  /**
   * Cổng nhảy CÓ NHỚ: `true` = worker ĐANG NGHI đã bám sang đối tượng khác và ĐÃ ẨN mask/ô.
   * UI phải hiện banner + nút "vẫn đúng" (`confirmLive`) — im lặng thì người xem tưởng hệ hỏng.
   */
  nghi_doi_tuong?: boolean
  /** số frame ĐÃ PHÁT trong trạng thái nghi (`0` = chưa từng nghi) */
  nghi_doi_tuong_n?: number
}

export interface LiveStartOptions {
  /** raw = chỉ phát khung hình · track = bám đối tượng bằng model (cần bbox) */
  mode?: 'raw' | 'track'
  bbox?: BBox
  points?: PointPrompt[]
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

/**
 * Xác nhận "vẫn đúng đối tượng" ⇒ worker xoá trạng thái nghi đổi đối tượng và VẼ LẠI mask/ô.
 *
 * Dùng khi banner `nghi_doi_tuong` hiện ra mà người dùng thấy vẫn đúng: không cần chọn lại ô.
 * (21-11: đo được `track_cos` KHÔNG phân biệt được vùng sai cùng tông ⇒ hệ không tự phán quyết
 * được, phải hỏi người.)
 */
export async function confirmLive(): Promise<LiveStatus> {
  const res = await fetch('/api/live/confirm', { method: 'POST' })
  if (!res.ok) await _error(res)
  return (await res.json()) as LiveStatus
}

/** Chọn hoặc chọn lại đối tượng cho phiên live đang chạy (kèm điểm âm/dương tuỳ chọn). */
export async function selectLive(bbox: BBox, points?: PointPrompt[]): Promise<LiveStatus> {
  const res = await fetch('/api/live/select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bbox, points }),
  })
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
