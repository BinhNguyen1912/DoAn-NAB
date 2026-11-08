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
  const hasVideo = done && Boolean(job.artifacts['out.mp4'])

  return (
    <section className="card">
      <h2>3. Kết quả</h2>
      <p>
        Trạng thái: <strong>{job.state}</strong> — {job.message}
      </p>

      <div className="progress">
        <div className="bar" style={{ width: `${job.progress}%` }} />
      </div>
      <p className="hint">{job.progress}%</p>

      {hasVideo && (
        <>
          <video controls src={artifactUrl(jobId, 'out.mp4')} />
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
          </p>
        </>
      )}
    </section>
  )
}
