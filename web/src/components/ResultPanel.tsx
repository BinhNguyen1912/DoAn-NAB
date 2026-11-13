/**
 * ResultPanel — bước 3: tiến trình, video kết quả, bảng số liệu, nút tải.
 *
 * Chức năng: trình bày JobStatus (đã poll ở hook) — thuần hiển thị, không gọi API.
 * Input  : jobId, job (trạng thái mới nhất).
 * Output : JSX.
 * Lưu ý  : chỉ hiện player khi state = done và artifact out.mp4 tồn tại; job error thì
 *          hiện message của backend (nguyên văn tiếng Việt) để người dùng biết xem worker.log.
 */

import { artifactUrl, type JobStatus } from '../api'
import { SummaryTable } from './SummaryTable'

export function ResultPanel({ jobId, job }: { jobId: string; job: JobStatus }): JSX.Element {
  const done = job.state === 'done'
  // Ưu tiên bản H.264 (out_web.mp4) — Chrome KHÔNG giải mã được bản mp4v của OpenCV.
  const webVideo = job.artifacts['out_web.mp4']
  const rawVideo = job.artifacts['out.mp4']
  const hasVideo = done && Boolean(webVideo || rawVideo)

  return (
    <section className="card">
      <div className="card-head">
        <span className="step">3</span>
        <h2>Kết quả</h2>
      </div>
      <p>
        Trạng thái: <strong>{job.state}</strong> — {job.message}
      </p>

      <div className="progress">
        <div className="bar" style={{ width: `${job.progress}%` }} />
      </div>
      <p className="hint">{job.progress}%</p>

      {hasVideo && (
        <>
          <video controls preload="metadata" src={artifactUrl(jobId, webVideo ? 'out_web.mp4' : 'out.mp4')} />
          {!webVideo && (
            <p className="hint">
              Chưa có bản H.264 (máy thiếu ffmpeg) — trình duyệt có thể không phát được video.
              Vẫn tải được bản gốc bên dưới để xem bằng VLC.
            </p>
          )}
          {job.summary && <SummaryTable summary={job.summary} />}
          <p className="row">
            <a className="button" href={artifactUrl(jobId, 'metrics.csv')}>
              Tải số liệu từng frame (CSV)
            </a>
            {job.artifacts['summary.json'] && (
              <a className="button ghost" href={artifactUrl(jobId, 'summary.json')}>
                Tải summary (JSON)
              </a>
            )}
            {job.artifacts['out.mp4'] && (
              <a className="button ghost" href={artifactUrl(jobId, 'out.mp4')}>
                Tải video gốc (mp4v)
              </a>
            )}
          </p>
        </>
      )}
    </section>
  )
}
