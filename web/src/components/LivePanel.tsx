/**
 * LivePanel — phát trực tiếp nguồn frame và (tuỳ chọn) BÁM ĐỐI TƯỢNG bằng model.
 *
 * Chức năng: bật/dừng phiên live; chế độ "raw" phát khung hình gốc, chế độ "track" chạy worker
 *            model ở tiến trình riêng rồi phát frame đã vẽ mask + ô bao + quỹ đạo.
 * Input  : nguồn (0 | rtsp:// | http://snapshot | đường dẫn video) + ô chọn đối tượng.
 * Output : JSX; side-effect chỉ là gọi api.ts và một interval tự clear khi unmount.
 * Lưu ý  : muốn bám đối tượng phải có ô chọn → luồng là: bật "raw" → đóng băng 1 frame →
 *          kéo chuột trên canvas → bấm "Bám đối tượng" (khởi động lại phiên ở mode=track).
 *          <img> MJPEG phải đổi `key` mỗi phiên, nếu không trình duyệt giữ kết nối cũ.
 */

import { useEffect, useRef, useState } from 'react'
import {
  getLiveStatus,
  LIVE_FRAME_URL,
  LIVE_STREAM_URL,
  startLive,
  stopLive,
  type BBox,
  type LiveStatus,
} from '../api'
import { deviceLine, driftLine, maskRhythmLine, shownFps } from '../live'
import { SelectionCanvas } from './SelectionCanvas'

const POLL_MS = 1000

export function LivePanel(): JSX.Element {
  const [source, setSource] = useState('0')
  const [mode, setMode] = useState<'raw' | 'track'>('raw')
  const [status, setStatus] = useState<LiveStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sessionKey, setSessionKey] = useState(0)
  const [picking, setPicking] = useState(false)
  const [frozenFrame, setFrozenFrame] = useState<string | null>(null)
  const [box, setBox] = useState<BBox | null>(null)
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

  const beginPolling = (): void => {
    stopPolling()
    timerRef.current = window.setInterval(() => {
      void poll()
    }, POLL_MS)
  }

  const onStart = async (): Promise<void> => {
    setError(null)
    setPicking(false)
    setBox(null)
    setMode('raw')
    try {
      setStatus(await startLive(source, { mode: 'raw' }))
      setSessionKey((value) => value + 1)
      beginPolling()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const onPickObject = (): void => {
    // Đóng băng khung hình hiện tại để kéo chuột (ảnh tĩnh dễ chọn hơn luồng đang chạy)
    setFrozenFrame(`${LIVE_FRAME_URL}?t=${Date.now()}`)
    setBox(null)
    setPicking(true)
  }

  const onTrack = async (): Promise<void> => {
    if (!box) return
    setError(null)
    try {
      const next = await startLive(source, { mode: 'track', bbox: box })
      setStatus(next)
      setMode('track')
      setPicking(false)
      setFrozenFrame(null)
      setSessionKey((value) => value + 1)
      beginPolling()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const onStop = async (): Promise<void> => {
    stopPolling()
    setPicking(false)
    setFrozenFrame(null)
    setMode('raw')
    try {
      setStatus(await stopLive())
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const running = status?.state === 'running'
  // Đang nạp nguồn (worker `track` 20–240 s): nút "Dừng" PHẢI bấm được (backend huỷ được giữa lúc
  // nạp — `src/api/live.py`), và "Bật phát" phải tắt (bấm nữa chỉ nhận 409 `LiveBusy`, hiện banner
  // lỗi trong lúc đang nạp bình thường — ticket 16).
  const loading = status?.state === 'loading'
  const maskLine = maskRhythmLine(status)
  const driftText = driftLine(status)
  const deviceText = deviceLine(status)
  const displayFps = shownFps(status)

  return (
    <section className="card">
      <h2>4. Phát trực tiếp {mode === 'track' ? '— ĐANG BÁM ĐỐI TƯỢNG' : ''}</h2>
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
            disabled={running || loading || picking}
            style={{ minWidth: '320px' }}
          />
        </label>
        <button type="button" onClick={() => void onStart()}
                disabled={running || loading || picking || !source.trim()}>
          Bật phát
        </button>
        <button
          type="button"
          className="button ghost"
          onClick={onPickObject}
          disabled={!running || picking || mode === 'track'}
        >
          Chọn đối tượng để bám
        </button>
        <button type="button" className="button ghost" onClick={() => void onStop()}
                disabled={!running && !picking && !loading}>
          Dừng
        </button>
      </div>

      {error && <p className="error">Lỗi: {error}</p>}

      {status && (
        // `error`: worker chết/treo giữa phiên (watchdog ở backend) — dòng chữ này là thứ DUY NHẤT
        // nói cho người vận hành biết ảnh đang đứng vì lỗi, không phải vì camera chậm.
        <p className={status.state === 'error' ? 'error' : 'hint'} data-testid="live-status"
           role={status.state === 'error' ? 'alert' : undefined}>
          Trạng thái:{' '}
          <strong>{status.state === 'loading' ? 'đang mở…' : status.state}</strong> · {status.message} ·
          frame: {status.frames} · FPS đo được: {displayFps}
        </p>
      )}

      {maskLine && (
        // Hai nhịp tách rời: hình 30 FPS là nhờ nội suy, MASK chỉ mới ở nhịp model chạy.
        // Hiện cả hai để không ai đọc nhầm "30 FPS" thành "mask 30 FPS".
        <p className="hint" data-testid="mask-rhythm">
          {maskLine}
        </p>
      )}

      {driftText && (
        // Chẩn đoán, KHÔNG phải cảnh báo đỏ: hiện cả số nền (số mẫu) để người xem biết đây là
        // dụng cụ đo; "chưa đo được" không bao giờ được hiện thành "tốt".
        <p className="hint" data-testid="drift-line">
          {driftText}
        </p>
      )}

      {deviceText && (
        // Thiết bị là NGỮ CẢNH của mọi số ở trên: cùng mã cho 97 ms @192 trên CPU và nhanh hơn
        // nhiều lần trên GPU — không nói thiết bị thì không ai tái lập được số trong báo cáo.
        <p className="hint" data-testid="device-line">
          {deviceText}
        </p>
      )}

      {picking && frozenFrame && (
        <>
          <SelectionCanvas src={frozenFrame} value={box} onChange={setBox} />
          <div className="row">
            <button type="button" onClick={() => void onTrack()} disabled={!box}>
              Bám đối tượng
            </button>
            <button type="button" className="button ghost" onClick={() => { setPicking(false); setFrozenFrame(null); setBox(null) }}>
              Huỷ
            </button>
          </div>
        </>
      )}

      {running && !picking && (
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
