/**
 * useJobPolling — side-effect duy nhất của trang: hỏi trạng thái job theo nhịp.
 *
 * Chức năng: poll `GET /api/jobs/{id}` mỗi `intervalMs` cho tới khi job done/error.
 * Input  : jobId (null = không poll), intervalMs (mặc định 1000).
 * Output : { job, error, refresh } — job mới nhất và lỗi mạng (nếu có).
 * Lưu ý  : interval PHẢI được clear khi jobId đổi, khi job kết thúc và khi unmount —
 *          nếu không sẽ gọi API mãi mãi (đã từng gặp khi poll trong App).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { getJob, type JobStatus } from '../api'

const POLL_MS = 1000

interface Polling<T> {
  job: T | null
  error: string | null
  refresh: () => Promise<void>
}

export function useJobPolling(jobId: string | null, intervalMs: number = POLL_MS): Polling<JobStatus> {
  const [job, setJob] = useState<JobStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)

  const stop = useCallback((): void => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const refresh = useCallback(async (): Promise<void> => {
    if (!jobId) return
    try {
      const status = await getJob(jobId)
      setJob(status)
      if (status.state === 'done' || status.state === 'error') stop()
    } catch (err) {
      setError((err as Error).message)
    }
  }, [jobId, stop])

  useEffect(() => {
    // Đổi job → bỏ kết quả cũ, tránh hiện nhầm kết quả của job trước
    setJob(null)
    setError(null)
    if (!jobId) return undefined

    void refresh()
    timerRef.current = window.setInterval(() => {
      void refresh()
    }, intervalMs)
    return () => stop()
  }, [jobId, intervalMs, refresh, stop])

  return { job, error, refresh }
}
