/**
 * e2e_web.js — E2E thật: Chrome/Edge headless (Windows) lái giao diện, server FastAPI trong WSL.
 *
 * Kiểm gì:
 *   1. trang tải được + frontend kết nối backend (/health)
 *   2. upload sai định dạng → UI báo lỗi tiếng Việt (không phải crash)
 *   3. upload video thật → tạo job
 *   4. canvas có đúng kích thước video gốc (không phải khung mặc định 300×150)
 *   5. KÉO CHUỘT chọn bbox → toạ độ quy đổi ĐÚNG tỉ lệ (so với kỳ vọng tính tay)
 *   6. bấm "Bắt đầu bám" → job chạy → done
 *   7. có player video kết quả + bảng 7 dòng số liệu
 *   8. tải được metrics.csv, artifact ngoài whitelist bị 404
 *   9. không có lỗi JS trên trang
 *
 * Chạy: `./run e2e` (tự bật server + sinh fixture). Cần Chrome/Edge trên Windows và
 *        playwright trong web/node_modules (`cd web && npm i -D playwright`).
 * Biến môi trường: BASE (mặc định http://localhost:8013), SHOT (đường dẫn ảnh chụp).
 */
const path = require('path')

function loadPlaywright() {
  const candidates = [
    'playwright',
    path.join(__dirname, '..', 'web', 'node_modules', 'playwright'),
  ]
  for (const candidate of candidates) {
    try {
      return require(candidate)
    } catch (err) {
      // thử đường dẫn kế tiếp
    }
  }
  throw new Error('Thiếu playwright — chạy: cd web && npm i -D playwright')
}

const { chromium } = loadPlaywright()

const BASE = process.env.BASE || 'http://localhost:8013'
const VIDEO = process.env.VIDEO || path.join('data', 'e2e_web.mp4')
const BAD_FILE = process.env.BAD_FILE || path.join('data', 'e2e_bad.txt')
const SHOT = process.env.SHOT || path.join('data', 'e2e_web.png')
// Nguồn cho chế độ live là đường dẫn PHÍA SERVER (Linux) → phải dùng dấu '/' .
// (đường dẫn Windows chỉ dùng cho setInputFiles vì trình duyệt tự đọc file rồi upload)
const LIVE_SOURCE = process.env.LIVE_SOURCE || 'data/e2e_web.mp4'

// Kỳ vọng tính tay cho video 160×120 khi kéo chuột 10–40% ngang, 30–70% dọc
const EXPECTED = { x: 16, y: 36, w: 48, h: 48 }
const TOLERANCE_PX = 3

const failures = []

function check(name, ok, detail = '') {
  console.log(`${ok ? '✓' : '✗'} ${name}${detail ? ' — ' + detail : ''}`)
  if (!ok) failures.push(name)
}

async function waitJobState(page, wanted, timeout = 240000) {
  await page.waitForFunction(
    (states) => {
      const p = [...document.querySelectorAll('p')].find((element) =>
        element.textContent.trim().startsWith('Trạng thái:'),
      )
      return p && states.some((state) => p.textContent.includes(state))
    },
    wanted,
    { timeout, polling: 500 },
  )
}

;(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  const page = await browser.newPage({ viewport: { width: 1100, height: 1000 } })
  const pageErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  // 1. tải trang
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await page.getByText('Backend sẵn sàng').waitFor({ timeout: 20000 })
  check('trang tải được + frontend kết nối backend', true)
  check('tiêu đề đúng', (await page.locator('h1').innerText()).includes('Camera AI'))

  // 2. nhánh lỗi: upload file sai định dạng
  await page.setInputFiles('input[type=file]', BAD_FILE)
  await page.getByRole('button', { name: 'Tải lên và tạo job' }).click()
  await page.locator('p.error').waitFor({ timeout: 20000 })
  const errText = await page.locator('p.error').innerText()
  check('upload sai định dạng bị chặn + báo lỗi tiếng Việt', errText.includes('định dạng'),
    errText.slice(0, 70))

  // 3. upload video thật
  await page.setInputFiles('input[type=file]', VIDEO)
  await page.getByLabel('Giới hạn frame').fill('5')
  await page.getByRole('button', { name: 'Tải lên và tạo job' }).click()
  await page.getByText(/Mã job:/).waitFor({ timeout: 60000 })
  const jobId = (await page.getByText(/Mã job:/).innerText()).split(':')[1].trim()
  check('upload video + tạo job', /^\d{8}-\d{6}-[0-9a-f]{6}$/.test(jobId), jobId)

  // 4. canvas phải có kích thước video gốc và đã load xong ảnh
  await page.waitForSelector('canvas', { timeout: 30000 })
  await page.waitForFunction(
    () => {
      const canvas = document.querySelector('canvas')
      const stillLoading = document.body.innerText.includes('Đang tải khung hình')
      return canvas && canvas.width > 0 && canvas.height > 0 && !stillLoading
    },
    null,
    { timeout: 30000 },
  )
  const size = await page.evaluate(() => {
    const canvas = document.querySelector('canvas')
    return { w: canvas.width, h: canvas.height }
  })
  check('canvas đúng kích thước video gốc', size.w === 160 && size.h === 120, JSON.stringify(size))

  // 5. kéo chuột chọn bbox
  const rect = await page.locator('canvas').boundingBox()
  const at = (fx, fy) => ({ x: rect.x + rect.width * fx, y: rect.y + rect.height * fy })
  const start = at(0.1, 0.3)
  const end = at(0.4, 0.7)
  await page.mouse.move(start.x, start.y)
  await page.mouse.down()
  await page.mouse.move((start.x + end.x) / 2, (start.y + end.y) / 2, { steps: 5 })
  await page.mouse.move(end.x, end.y, { steps: 5 })
  await page.mouse.up()

  const hint = await page.getByTestId('bbox-hint').innerText()
  const nums = hint.match(/(\d+),\s*(\d+),\s*(\d+)×(\d+)/)
  check('kéo chuột sinh ra bbox hợp lệ', Boolean(nums), nums ? nums.slice(1).join(',') : hint)
  if (nums) {
    const [x, y, w, h] = nums.slice(1).map(Number)
    const near = (value, expected) => Math.abs(value - expected) <= TOLERANCE_PX
    check(
      'quy đổi canvas → pixel video ĐÚNG tỉ lệ',
      near(x, EXPECTED.x) && near(y, EXPECTED.y) && near(w, EXPECTED.w) && near(h, EXPECTED.h),
      `nhận ${x},${y},${w}×${h} — kỳ vọng ${EXPECTED.x},${EXPECTED.y},${EXPECTED.w}×${EXPECTED.h}`,
    )
  }

  // 6. bắt đầu bám → chờ done
  await page.getByRole('button', { name: 'Bắt đầu bám' }).click()
  await waitJobState(page, ['running', 'done'])
  check('bấm "Bắt đầu bám" → job chạy', true)

  const startedAt = Date.now()
  await waitJobState(page, ['done'], 240000)
  check('job kết thúc done', true, `${((Date.now() - startedAt) / 1000).toFixed(1)} s`)

  // 7. kết quả
  await page.locator('video').waitFor({ timeout: 30000 })
  const videoSrc = await page.locator('video').getAttribute('src')
  check('có player video kết quả', Boolean(videoSrc && videoSrc.includes('out_web.mp4')), videoSrc)

  // Bằng chứng mạnh nhất: trình duyệt GIẢI MÃ được video (bản mp4v của OpenCV thì không)
  const decode = await page.evaluate(async () => {
    const video = document.querySelector('video')
    const deadline = Date.now() + 10000
    while (Date.now() < deadline && video.readyState < 1) {
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    return {
      readyState: video.readyState,
      decoded: video.videoWidth > 0 && video.videoHeight > 0,
      w: video.videoWidth,
      h: video.videoHeight,
      codecLoi: video.error ? video.error.code : null,
    }
  })
  check('trình duyệt GIẢI MÃ được video kết quả (H.264)', decode.w > 0 && decode.h > 0,
    JSON.stringify(decode))

  const rows = await page.locator('table.summary tr').allInnerTexts()
  check('bảng số liệu có 7 dòng', rows.length === 7, `${rows.length} dòng`)
  const meanRow = rows.find((row) => row.includes('Độ trễ trung bình')) || ''
  const meanValue = Number((meanRow.match(/([\d.]+)\s*ms/) || [])[1])
  check('độ trễ trung bình là số dương', meanValue > 0, meanRow.replace(/\s+/g, ' ').trim())
  const fpsRow = rows.find((row) => row.includes('FPS hiệu dụng')) || ''
  check('có dòng FPS hiệu dụng', /\d/.test(fpsRow), fpsRow.replace(/\s+/g, ' ').trim())

  // 8. tải CSV + chặn whitelist
  const csvHref = await page.locator('a[href$="metrics.csv"]').getAttribute('href')
  const csv = await page.request.get(BASE + csvHref)
  const csvText = await csv.text()
  check('tải được metrics.csv', csv.ok() && csvText.split('\n')[0].includes('frame_idx'),
    `${csv.status()} · ${csvText.trim().split('\n').length - 1} dòng dữ liệu`)

  const blocked = await page.request.get(`${BASE}/api/jobs/${jobId}/artifacts/job.json`)
  check('artifact ngoài whitelist bị chặn 404', blocked.status() === 404, String(blocked.status()))

  // 9. live: dùng chính video file làm nguồn (backend lặp lại) — không cần webcam thật
  await page.getByLabel('Nguồn frame').fill(LIVE_SOURCE)
  await page.getByRole('button', { name: 'Bật phát' }).click()
  try {
    await page.getByTestId('live-status').waitFor({ timeout: 20000 })
  } catch (err) {
    const banner = await page.locator('p.error').last().innerText().catch(() => '(không có banner lỗi)')
    throw new Error(`live không khởi động được — UI báo: ${banner}`)
  }
  const liveFrame = await page.evaluate(async () => {
    const deadline = Date.now() + 15000
    while (Date.now() < deadline) {
      const img = document.querySelector('img.live-frame')
      if (img && img.naturalWidth > 0) return { w: img.naturalWidth, h: img.naturalHeight }
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    return null
  })
  check('luồng MJPEG hiện được frame trong trình duyệt', Boolean(liveFrame),
    JSON.stringify(liveFrame))

  await page.waitForFunction(
    () => {
      const el = document.querySelector('[data-testid="live-status"]')
      return el && /FPS đo được: [1-9]/.test(el.textContent)
    },
    null,
    { timeout: 15000 },
  )
  const liveText = await page.getByTestId('live-status').innerText()
  check('FPS live đo được > 0', /FPS đo được: [1-9]/.test(liveText), liveText.replace(/\s+/g, ' '))

  // 9b. UI chọn đối tượng trên LIVE: đóng băng frame → kéo chuột → gửi mode=track + bbox.
  //      Chặn (route) lời gọi /api/live/start để KHÔNG phải nạp model 20–60 s trong E2E, nhưng
  //      vẫn kiểm được payload thật mà UI gửi đi.
  // Trang có 2 khối canvas (job + live) → phải SCOPE vào card live, nếu không sẽ kéo nhầm canvas
  const liveCard = page.locator('section').filter({ hasText: 'Phát trực tiếp' })
  await liveCard.getByRole('button', { name: 'Chọn đối tượng để bám' }).click()
  await liveCard.locator('canvas').waitFor({ timeout: 20000 })
  // BẮT BUỘC: page.mouse dùng toạ độ VIEWPORT — card live nằm dưới màn hình thì phải cuộn tới,
  // nếu không chuột rơi ra ngoài canvas và không có sự kiện nào được bắn (bug gặp 08-11).
  await liveCard.locator('canvas').scrollIntoViewIfNeeded()
  const liveCanvas = await liveCard.locator('canvas').boundingBox()
  await page.mouse.move(liveCanvas.x + liveCanvas.width * 0.2, liveCanvas.y + liveCanvas.height * 0.3)
  await page.mouse.down()
  await page.mouse.move(liveCanvas.x + liveCanvas.width * 0.5, liveCanvas.y + liveCanvas.height * 0.7, { steps: 5 })
  await page.mouse.up()

  let trackPayload = null
  await page.route('**/api/live/start', async (route) => {
    trackPayload = JSON.parse(route.request().postData() || '{}')
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ state: 'running', source: 'stub', frames: 0, measured_fps: 0,
                             device: 'cuda', message: 'stub' }) })
  })
  await liveCard.getByRole('button', { name: 'Bám đối tượng' }).click()
  await page.waitForTimeout(300)

  // Thiết bị phải đi hết chuỗi status.json → LiveTelemetry → schema → api.ts → HUD (ticket 21).
  // Chặn CẢ /api/live/status: sau khi bắt đầu bám, component poll mỗi 1 s và ghi đè status bằng
  // phản hồi THẬT (mode raw: `device = ""` ⇒ không có dòng thiết bị), nên chỉ stub `/start`
  // thì dòng thiết bị chỉ sống < 1 s — kiểm tra sẽ chập chờn.
  await page.route('**/api/live/status', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ state: 'running', source: 'stub', frames: 0, measured_fps: 0,
                             device: 'cuda', message: 'stub' }) })
  })
  const deviceText = await liveCard.getByTestId('device-line').innerText({ timeout: 8000 })
    .catch(() => '')
  check('HUD hiện thiết bị model (cuda) lấy từ /api/live/status', /cuda/.test(deviceText),
    deviceText.replace(/\s+/g, ' ') || '(không thấy dòng thiết bị)')
  await page.unroute('**/api/live/status')
  await page.unroute('**/api/live/start')

  check('UI gửi mode=track kèm bbox khi bấm "Bám đối tượng"',
    Boolean(trackPayload && trackPayload.mode === 'track' && trackPayload.bbox),
    JSON.stringify(trackPayload))
  if (trackPayload && trackPayload.bbox) {
    const live = trackPayload.bbox
    check('bbox gửi đi nằm trong khung video live',
      live.w > 0 && live.h > 0 && live.x + live.w <= 160 && live.y + live.h <= 120,
      JSON.stringify(live))
  }

  // quay lại "Dừng" để kiểm nhánh dừng (dùng lại nút ở panel live)
  await liveCard.getByRole('button', { name: 'Dừng' }).click()
  await page.waitForFunction(
    () => {
      const el = document.querySelector('[data-testid="live-status"]')
      return el && el.textContent.includes('stopped')
    },
    null,
    { timeout: 10000 },
  )
  check('dừng phát sạch (state=stopped)', true)

  // 10. log lỗi JS
  check('không có lỗi JS trên trang', pageErrors.length === 0, pageErrors.join(' | '))

  await page.screenshot({ path: SHOT, fullPage: true })
  console.log(`\nẢnh chụp giao diện: ${SHOT}`)
  await browser.close()

  console.log(
    failures.length === 0 ? '\nKẾT LUẬN: PASS' : `\nKẾT LUẬN: FAIL (${failures.join(', ')})`,
  )
  process.exit(failures.length === 0 ? 0 : 1)
})().catch((error) => {
  console.error('LỖI E2E:', error.message)
  process.exit(2)
})
