/**
 * App — composition root của frontend: lắp hook + component, giữ state dùng chung.
 *
 * Chức năng: kiểm tra backend, upload video, giữ bbox đang chọn, nối kết quả poll vào UI.
 * Input  : thao tác người dùng (chọn file, kéo chuột, bấm nút).
 * Output : giao diện 3 bước.
 * Lưu ý  : KHÔNG gọi fetch ở đây (đi qua api.ts), KHÔNG tự đặt interval (đi qua useJobPolling).
 *          Muốn đổi backend/API chỉ sửa api.ts; muốn đổi nhịp poll chỉ sửa hook.
 */

import { useEffect, useState } from 'react'
import { createJob, health, previewUrl, selectObject, type BBox, type UploadOptions } from './api'
import { ResultPanel } from './components/ResultPanel'
import { SelectionCanvas } from './components/SelectionCanvas'
import { UploadForm } from './components/UploadForm'
import { useJobPolling } from './hooks/useJobPolling'

function HealthBadge(): JSX.Element {
  const [online, setOnline] = useState<boolean | null>(null)

  useEffect(() => {
    let cancelled = false
    void health().then((ok) => {
      if (!cancelled) setOnline(ok)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const text =
    online === null
      ? 'Đang kiểm tra backend…'
      : online
        ? 'Backend sẵn sàng'
        : 'Không kết nối được backend — chạy ./run api'
  return <p className={online === false ? 'status bad' : 'status ok'}>{text}</p>
}

export default function App(): JSX.Element {
  const [jobId, setJobId] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [box, setBox] = useState<BBox | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { job, error: pollError, refresh } = useJobPolling(jobId)

  useEffect(() => {
    if (pollError) setError(pollError)
  }, [pollError])

  const onUpload = async (file: File, opts: UploadOptions): Promise<void> => {
    setError(null)
    setBox(null)
    setJobId(null)
    setUploading(true)
    try {
      setJobId(await createJob(file, opts))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setUploading(false)
    }
  }

  const onStart = async (): Promise<void> => {
    if (!jobId || !box) return
    setError(null)
    try {
      await selectObject(jobId, box)
      await refresh()          // cập nhật ngay, không chờ nhịp poll kế tiếp
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const busy = job?.state === 'running' || job?.state === 'queued'
  const done = job?.state === 'done'

  return (
    <main className="page">
      <header>
        <h1>Camera AI — bám bắt đối tượng</h1>
        <p className="sub">
          SAM 2 + Motion Memory: chọn vật thể, hệ thống phân đoạn và bám theo, xuất video HUD
          kèm số liệu đo thật (FPS, độ trễ, số lần mất dấu).
        </p>
        <HealthBadge />
      </header>

      {error && <p className="error">Lỗi: {error}</p>}

      <UploadForm onUpload={onUpload} uploading={uploading} jobId={jobId} />

      {jobId && (
        <section className="card">
          <h2>2. Chọn đối tượng</h2>
          <SelectionCanvas src={previewUrl(jobId)} value={box} onChange={setBox} />
          <button type="button" onClick={() => void onStart()} disabled={!box || busy || done}>
            Bắt đầu bám
          </button>
        </section>
      )}

      {jobId && job && <ResultPanel jobId={jobId} job={job} />}
    </main>
  )
}
