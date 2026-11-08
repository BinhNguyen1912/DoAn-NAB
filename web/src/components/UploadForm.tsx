/**
 * UploadForm — bước 1: chọn file video + tham số track, rồi gọi callback upload.
 *
 * Chức năng: quản lý state của form; KHÔNG gọi API trực tiếp (do App truyền `onUpload` vào).
 * Input  : onUpload(file, opts), uploading (cờ đang gửi), jobId (để hiện mã job).
 * Output : JSX form.
 * Lưu ý  : tách khỏi App để đổi UI không phải chạm logic upload/polling.
 */

import { useState } from 'react'
import type { UploadOptions } from '../api'

interface Props {
  onUpload: (file: File, opts: UploadOptions) => Promise<void>
  uploading: boolean
  jobId: string | null
}

const IMAGE_SIZE_OPTIONS: Array<[number, string]> = [
  [192, '192 — nhanh nhất (~10 FPS)'],
  [256, '256 — cân bằng (~6,5 FPS)'],
  [320, '320 — chi tiết vật nhỏ (chậm)'],
]

const DEFAULT_OPTIONS: UploadOptions = { image_size: 256, reid: true, cue: 'object' }

export function UploadForm({ onUpload, uploading, jobId }: Props): JSX.Element {
  const [file, setFile] = useState<File | null>(null)
  const [opts, setOpts] = useState<UploadOptions>(DEFAULT_OPTIONS)

  return (
    <section className="card">
      <h2>1. Chọn video</h2>
      <input
        type="file"
        accept="video/mp4,video/x-msvideo,video/quicktime,video/x-matroska"
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
      />

      <div className="row">
        <label>
          Độ phân giải model
          <select
            value={opts.image_size ?? 256}
            onChange={(event) => setOpts({ ...opts, image_size: Number(event.target.value) })}
          >
            {IMAGE_SIZE_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="inline">
          <input
            type="checkbox"
            checked={opts.reid ?? false}
            onChange={(event) => setOpts({ ...opts, reid: event.target.checked })}
          />
          Bật tái nhận diện khi mất dấu
        </label>

        <label>
          Giới hạn frame
          <input
            type="number"
            min={1}
            placeholder="tất cả"
            onChange={(event) => {
              const raw = event.target.value
              setOpts({ ...opts, max_frames: raw === '' ? undefined : Number(raw) })
            }}
          />
        </label>
      </div>

      <button
        type="button"
        onClick={() => {
          if (file) void onUpload(file, opts)
        }}
        disabled={!file || uploading}
      >
        {uploading ? 'Đang tải lên…' : 'Tải lên và tạo job'}
      </button>

      {jobId && <p className="hint">Mã job: {jobId}</p>}
    </section>
  )
}
