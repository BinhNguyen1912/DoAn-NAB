/**
 * LivePanel — phát trực tiếp nguồn frame (webcam / RTSP / snapshot relay / video file lặp).
 *
 * Chức năng: bật–dừng phiên live ở backend, hiển thị luồng MJPEG bằng <img>, poll trạng thái
 *            để hiên số frame + FPS THỰC ĐO (không phải target).
 * Input  : nguồn (chuỗi) do người dùng nhập.
 * Output : JSX; side-effect chỉ là gọi api.ts và một interval tự clear khi unmount.
 * Lưu ý  : <img src> của MJPEG là một kết nối HTTP dài — phải đổi `key` mỗi lần bật lại,
 *          nếu không trình duyệt giữ kết nối cũ và hiện khung hình đã dừng.
 *          Dùng video file làm nguồn (backend tự lặp) để demo live KHÔNG cần webcam thật.
 */

import { useEffect, useRef, useState } from 'react'
import { getLiveStatus, LIVE_STREAM_URL, startLive, stopLive, type LiveStatus } from '../api'

const POLL_MS = 1000

export function LivePanel(): JSX.Element {
  const [source, setSource] = useState('0')
  const [status, setStatus] = useState<LiveStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sessionKey, setSessionKey] = useState(0)
  const timerRef = useRef<number | null>(null)

  const stopPolling = (): void => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  useEffect(() => stopPolling, []) // dọn interval khi unmount

  const poll = async (): Promise<void> => {
    try {
      setStatus(await getLiveStatus())
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const onStart = async (): Promise<void> => {
    setError(null)
    try {
      setStatus(await startLive(source))
      setSessionKey((value) => value + 1)
      stopPolling()
      timerRef.current = window.setInterval(() => {
        void poll()
      }, POLL_MS)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const onStop = async (): Promise<void> => {
    stopPolling()
    try {
      setStatus(await stopLive())
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const running = status?.state === 'running'

  return (
    <section className="card">
      <h2>4. Phát trực tiếp (thử nghiệm — chưa bám đối tượng)</h2>
      <p className="hint">
        0 = webcam · rtsp://IP:554/stream · http://127.0.0.1:8080/snapshot.jpg (relay) ·
        đường dẫn video (backend tự lặp lại để demo không cần camera)
      </p>

      <div className="row">
        <label>
          Nguồn frame
          <input
            type="text"
            value={source}
            onChange={(event) => setSource(event.target.value)}
            disabled={running}
            style={{ minWidth: '320px' }}
          />
        </label>
        <button type="button" onClick={() => void onStart()} disabled={running || !source.trim()}>
          Bật phát
        </button>
        <button type="button" className="button ghost" onClick={() => void onStop()} disabled={!running}>
          Dừng
        </button>
      </div>

      {error && <p className="error">Lỗi: {error}</p>}

      {status && (
        <p className="hint" data-testid="live-status">
          Trạng thái: <strong>{status.state}</strong> · {status.message} · frame: {status.frames} · FPS
          đo được: {status.measured_fps}
        </p>
      )}

      {running && (
        <img
          key={sessionKey}
          className="live-frame"
          src={`${LIVE_STREAM_URL}?session=${sessionKey}`}
          alt="Luồng camera trực tiếp"
        />
      )}
    </section>
  )
}
