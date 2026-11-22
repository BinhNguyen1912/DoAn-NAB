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
  // SCOPE vào thẻ kết quả của JOB: panel live cũng có dòng bắt đầu bằng "Trạng thái:" và nó đứng
  // TRƯỚC trong DOM ⇒ bắt "<p> đầu tiên" sẽ đọc nhầm ngay khi có phiên live (review 13-11, P3).
  await page.waitForFunction(
    (states) => {
      const p = document.querySelector('[data-testid="job-status"]')
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
  // Cỡ mẫu phải hiện trên DOM: `summary.test.ts` canh hàm thuần, nhưng nó KHÔNG canh dây nối
  // component → `summaryRows` (revert component về in số trực tiếp thì vitest vẫn xanh). Repo không có
  // jsdom ⇒ e2e là nơi DUY NHẤT bắt được hồi quy đó (P2 review độc lập 17-11).
  check('p95 in kèm cỡ mẫu (n=…)', /\(n=\d+\)/.test(meanRow), meanRow.replace(/\s+/g, ' ').trim())
  const p95Row = rows.find((row) => row.includes('Độ trễ p95')) || ''
  check('p95 có cỡ mẫu hoặc nói "chưa đo"', /\(n=\d+\)|0 mẫu/.test(p95Row),
    p95Row.replace(/\s+/g, ' ').trim())
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

  // 8b. TỰ ĐIỀN NGUỒN: backend dò nguồn (webcam/relay/video) và UI phải điền sẵn.
  //     Chấp nhận mọi kết quả dò (máy CI không có webcam/relay) — chỉ đòi: có gợi ý thì ô nguồn
  //     phải bằng đúng gợi ý đó; không có gợi ý thì ô giữ nguyên.
  const goiY = await page.request.get(`${BASE}/api/live/sources`)
  const duLieuGoiY = await goiY.json().catch(() => ({ suggested: '' }))
  const nguonTrongO = await page.getByLabel('Nguồn frame').inputValue()
  check(
    'nguồn frame tự điền theo kết quả dò của backend',
    duLieuGoiY.suggested ? nguonTrongO === duLieuGoiY.suggested : true,
    `gợi ý=${JSON.stringify(duLieuGoiY.suggested)} · ô=${JSON.stringify(nguonTrongO)} · ` +
      `kind=${JSON.stringify(duLieuGoiY.suggested_kind)} · checked_at=${JSON.stringify(duLieuGoiY.checked_at)}`,
  )

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
  // Dùng `\s` chứ không phải khoảng trắng thường: `innerText` chèn xuống dòng khi HUD xuống dòng.
  check('FPS live đo được > 0', /FPS\s+đo\s+được:\s*[1-9]/.test(liveText), liveText.replace(/\s+/g, ' '))

  // 9a-bis. Cờ #14 phải có mặt trên ĐƯỜNG THẬT (không mock).
  // ⚠ THỨ TỰ LÀ MỘT PHẦN CỦA PHÉP KIỂM: khối này PHẢI nằm TRƯỚC mọi `page.route('**/api/live/status')`
  // bên dưới. Nếu ai chuyển nó xuống dưới, fetch sẽ đi qua route mock và mục này lại thành "kiểm
  // component" — đúng lỗi P0 đã xảy ra ở PR #54 (HUD thật không hiện vì DTO thiếu khoá, e2e vẫn xanh).: bản đầu chỉ nối tới `status.json`, DTO →
  // route dựng từng field nên thiếu khoá ⇒ HUD không bao giờ hiện, mà e2e vẫn xanh vì nó MOCK route
  // (review độc lập PR #54, P0). Ở đây hỏi thẳng API thật khi phiên đang chạy.
  const thatStatus = await page.evaluate(async (base) => {
    const r = await fetch(`${base}/api/live/status`)
    return r.ok ? await r.json() : null
  }, BASE)
  check('API THẬT trả khoá suc_khoe (không chỉ status.json)',
    Boolean(thatStatus) && Object.prototype.hasOwnProperty.call(thatStatus, 'suc_khoe')
      && Object.prototype.hasOwnProperty.call(thatStatus, 'suc_khoe_cau'),
    thatStatus ? `suc_khoe=${JSON.stringify(thatStatus.suc_khoe)} · cau=${thatStatus.suc_khoe_cau}` : 'không gọi được /api/live/status')

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

  // 9c. ĐIỂM PROMPT dương/âm (khôi phục 22-11): ca vật be trơn bám sang cửa/tường be cùng tông
  //     KHÔNG chữa được bằng ngưỡng cos hay đổi model (AGENTS §6) — phải cho người dùng chỉ vùng SAI.
  //     Ctrl+Click = điểm ÂM (ngoài ô, vùng bám sai) · Click thường = điểm DƯƠNG (trong vật).
  const hintDiem = await liveCard.getByTestId('points-hint').innerText().catch(() => '')
  check('canvas có gợi ý điểm dương/âm', /dương/.test(hintDiem) && /âm/.test(hintDiem),
    hintDiem.replace(/\s+/g, ' ') || '(không thấy gợi ý)')

  const boxTruoc = (await liveCard.getByTestId('bbox-hint').innerText()).replace(/\s+/g, ' ')

  // P0 (review 22-11): ngưỡng click/kéo phải ở KHÔNG GIAN NGƯỜI DÙNG. Nhấn-nhả lệch 2 CSS px là
  // thao tác click bình thường của tay người; trước đây nó bị coi là KÉO ⇒ xoá/thay ô.
  await page.mouse.move(liveCanvas.x + liveCanvas.width * 0.3, liveCanvas.y + liveCanvas.height * 0.2)
  await page.mouse.down()
  await page.mouse.move(liveCanvas.x + liveCanvas.width * 0.3 + 2, liveCanvas.y + liveCanvas.height * 0.2)
  await page.mouse.up()
  await page.waitForTimeout(150)
  const boxSauRung = (await liveCard.getByTestId('bbox-hint').innerText()).replace(/\s+/g, ' ')
  check('nhấn-nhả rung 2 px KHÔNG làm đổi/xoá ô đang chọn (P0)', boxSauRung === boxTruoc,
    `trước="${boxTruoc}" sau="${boxSauRung}"`)
  // Cú "rung 2 px" là một CLICK hợp lệ ⇒ nó ĐÃ thêm 1 điểm dương (đúng ngữ nghĩa). Dọn lại để các
  // phép đếm bên dưới tất định — nếu không, test sẽ đỏ vì lý do của chính test, không phải của code.
  if ((await liveCard.getByTestId('undo-point').count()) === 1) {
    await liveCard.getByTestId('undo-point').click()
    await page.waitForTimeout(120)
  }
  const sauDonDep = (await liveCard.getByTestId('points-hint').innerText().catch(() => '')).replace(/\s+/g, ' ')
  check('dọn điểm của cú rung xong ⇒ về "chưa có điểm nào"', /chưa có điểm nào/.test(sauDonDep), sauDonDep)

  // Chuột PHẢI là thao tác huỷ/ngữ cảnh — không được đặt điểm.
  const demTruoc = await liveCard.getByTestId('points-hint').innerText().catch(() => '')
  await page.mouse.click(liveCanvas.x + liveCanvas.width * 0.7, liveCanvas.y + liveCanvas.height * 0.6,
    { button: 'right' })
  await page.waitForTimeout(150)
  const sauChuotPhai = await liveCard.getByTestId('points-hint').innerText().catch(() => '')
  check('click chuột PHẢI không đặt điểm nào', sauChuotPhai === demTruoc,
    `trước="${demTruoc.replace(/\s+/g, ' ')}" sau="${sauChuotPhai.replace(/\s+/g, ' ')}"`)

  await page.keyboard.down('Control')
  await page.mouse.click(liveCanvas.x + liveCanvas.width * 0.85, liveCanvas.y + liveCanvas.height * 0.15)
  await page.keyboard.up('Control')
  await page.waitForTimeout(150)
  const sauAm = (await liveCard.getByTestId('points-hint').innerText().catch(() => '')).replace(/\s+/g, ' ')
  const boxConDo = (await liveCard.getByTestId('bbox-hint').innerText()).replace(/\s+/g, ' ')
  check('Ctrl+Click đặt 1 điểm ÂM và ô đang chọn KHÔNG ĐỔI (so chuỗi)',
    /1 điểm âm/.test(sauAm) && boxConDo === boxTruoc, `${sauAm} · trước="${boxTruoc}" sau="${boxConDo}"`)

  await page.mouse.click(liveCanvas.x + liveCanvas.width * 0.35, liveCanvas.y + liveCanvas.height * 0.5)
  await page.waitForTimeout(150)
  const sauDuong = (await liveCard.getByTestId('points-hint').innerText().catch(() => '')).replace(/\s+/g, ' ')
  check('Click thường đặt thêm 1 điểm DƯƠNG (tổng 1 dương + 1 âm)',
    /1 điểm dương/.test(sauDuong) && /1 điểm âm/.test(sauDuong), sauDuong)

  const nhanUndo = (await liveCard.getByTestId('undo-point').innerText().catch(() => '')).replace(/\s+/g, ' ')
  check('nút xoá điểm cuối hiện kèm SỐ ĐIỂM đang có', /2/.test(nhanUndo), nhanUndo || '(không thấy nút)')
  await liveCard.getByTestId('undo-point').click()
  await page.waitForTimeout(150)
  const sauUndo = (await liveCard.getByTestId('points-hint').innerText().catch(() => '')).replace(/\s+/g, ' ')
  // Thứ tự đặt là [âm, dương] ⇒ "xoá điểm cuối" bỏ ĐIỂM DƯƠNG, còn lại 1 âm.
  check('bấm "Xoá điểm cuối" thật sự bỏ điểm VỪA ĐẶT (còn 0 dương, 1 âm)',
    /0 điểm dương/.test(sauUndo) && /1 điểm âm/.test(sauUndo), sauUndo)
  // Đặt lại điểm DƯƠNG (click thường ở chỗ khác) để payload bên dưới có đủ cả hai loại.
  await page.mouse.click(liveCanvas.x + liveCanvas.width * 0.35, liveCanvas.y + liveCanvas.height * 0.5)
  await page.waitForTimeout(150)
  const sauDatLai = (await liveCard.getByTestId('points-hint').innerText().catch(() => '')).replace(/\s+/g, ' ')
  check('đặt lại được điểm dương sau khi xoá (1 dương + 1 âm)',
    /1 điểm dương/.test(sauDatLai) && /1 điểm âm/.test(sauDatLai), sauDatLai)

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
                             device: 'cuda', message: 'stub',
                             // Tuổi dữ liệu ảnh (việc #8): 2,6 s = vượt ngưỡng ⇒ HUD phải nói TO
                             mask_age_total_ms: 2600, mask_age_p95: 900, age_n: 40,
                             // Cấu hình lệch (15-11): model chạy 1024 trong khi yêu cầu 192 ⇒ mọi số
                             // trên HUD gắn với cấu hình khác ⇒ HUD phải cảnh báo, không im lặng.
                             cau_hinh_lech: ['image_size'], image_size_hieu_luc: 1024 }) })
  })
  const deviceText = await liveCard.getByTestId('device-line').innerText({ timeout: 8000 })
    .catch(() => '')
  check('HUD hiện thiết bị model (cuda) lấy từ /api/live/status', /cuda/.test(deviceText),
    deviceText.replace(/\s+/g, ' ') || '(không thấy dòng thiết bị)')
  // Cùng lý do với dòng thiết bị: phải đi hết chuỗi status.json → telemetry → schema → HUD.
  const ageText = await liveCard.getByTestId('mask-age').innerText({ timeout: 8000 })
    .catch(() => '')
  check('HUD cảnh báo MASK CŨ khi tuổi dữ liệu vượt ngưỡng',
    /Mask CŨ: 2\.6 s/.test(ageText), ageText.replace(/\s+/g, ' ') || '(không thấy dòng tuổi mask)')
  // "Nói TO" là yêu cầu a11y, không phải trang trí: kiểm `role=alert` thì mới chặn được hồi quy làm
  // cảnh báo thành chữ thường (review độc lập 14-11, P2 — bản trước chỉ so chữ).
  const ageRole = await liveCard.getByTestId('mask-age').getAttribute('role').catch(() => null)
  check('cảnh báo mask cũ có role=alert (screen reader đọc ngay)',
    ageRole === 'alert', `role=${ageRole}`)
  // Cấu hình lệch phải đi hết chuỗi status.json → LiveTelemetry → schema → api.ts → HUD (15-11).
  const cfgText = await liveCard.getByTestId('config-mismatch').innerText({ timeout: 8000 })
    .catch(() => '')
  check('HUD cảnh báo CẤU HÌNH LỆCH (model đang chạy 1024 px)',
    /CẤU HÌNH LỆCH/.test(cfgText) && /1024/.test(cfgText),
    cfgText.replace(/\s+/g, ' ') || '(không thấy dòng cấu hình)')
  const cfgRole = await liveCard.getByTestId('config-mismatch').getAttribute('role').catch(() => null)
  check('cảnh báo cấu hình lệch có role=alert (screen reader đọc ngay)',
    cfgRole === 'alert', `role=${cfgRole}`)
  // Ca ÂM (review 15-11, P3-9): đã kiểm và KHỚP thì KHÔNG được hiện dòng nào — một hồi quy kiểu
  // `lech.length >= 0` sẽ render khung rỗng và không ai bắt.
  await page.unroute('**/api/live/status')
  await page.route('**/api/live/status', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ state: 'running', source: 'stub', frames: 0, measured_fps: 0,
                             device: 'cuda', message: 'stub',
                             cau_hinh_lech: [], image_size_hieu_luc: 192 }) })
  })
  await page.waitForTimeout(1300)                    // > 1 chu kỳ poll status (1 s)
  check('cấu hình KHỚP ([]) thì HUD không hiện dòng cấu hình (không báo oan)',
    await liveCard.getByTestId('config-mismatch').count() === 0,
    `số dòng = ${await liveCard.getByTestId('config-mismatch').count()}`)
  // Cờ PHÁN QUYẾT chất lượng bám (ticket #14): phải phân biệt được "model mất vật" với "ô hiển thị
  // lệch ô VOS" — hai nguyên nhân khác hẳn nhau; ghép sai thì báo cáo nói sai thứ đang hỏng.
  for (const [co, cau, phai] of [
    ['drift_trend', 'Chất lượng bám: ô hiển thị lệch ô VOS (p05 0.00, mask rỗng thấp)', /lệch ô VOS/],
    ['model_lost', 'Chất lượng bám: model MẤT VẬT (p05 0.00, mask rỗng 11 % cửa sổ)', /MẤT VẬT/],
  ]) {
    await page.unroute('**/api/live/status')
    await page.route('**/api/live/status', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ state: 'running', source: 'stub', frames: 0, measured_fps: 0,
          mask_fps: 8.5, device: 'cpu', message: 'stub', cau_hinh_lech: [],
          image_size_hieu_luc: 192, suc_khoe: { co, p05: 0, n: 40, empty_frac: co === 'model_lost' ? 0.11 : 0.0,
            cua_so: 30, nguong_vao: 0.3, nguong_ra: 0.45 }, suc_khoe_cau: cau }) })
    })
    await page.waitForTimeout(1300)
    const chu = ((await liveCard.getByTestId('suc-khoe-line').textContent().catch(() => '')) || '')
      .replace(/\s+/g, ' ')
    check(`HUD hiện cờ chất lượng bám (${co})`, phai.test(chu), chu || '(không thấy dòng nào)')
    const lop = await liveCard.getByTestId('suc-khoe-line').getAttribute('class').catch(() => '')
    check(`cờ ${co} là CẢNH BÁO (đổi màu), không phải dòng chẩn đoán thường)`,
      String(lop).includes('hint-warn'), `class=${lop}`)
  }
  // Ca ÂM: `ok` ⇒ KHÔNG hiện dòng nào (worker báo "ổn" thì HUD phải im).
  await page.unroute('**/api/live/status')
  await page.route('**/api/live/status', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ state: 'running', source: 'stub', frames: 0, measured_fps: 0,
        mask_fps: 8.5, device: 'cpu', message: 'stub', cau_hinh_lech: [], image_size_hieu_luc: 192,
        suc_khoe: { co: 'ok', p05: 0.82, n: 40, empty_frac: 0, cua_so: 30,
          nguong_vao: 0.3, nguong_ra: 0.45 }, suc_khoe_cau: null }) })
  })
  await page.waitForTimeout(1300)
  check('cờ chất lượng bám = ok thì HUD KHÔNG hiện dòng nào (không báo oan)',
    await liveCard.getByTestId('suc-khoe-line').count() === 0,
    `số dòng = ${await liveCard.getByTestId('suc-khoe-line').count()}`)

  // Cổng nhảy CÓ NHỚ "nghi đổi đối tượng" (21-11): worker ẩn ô khi nghi bám sang vật khác, và UI
  // phải cho người dùng ĐƯỜNG TIẾP TỤC (`POST /api/live/confirm`) — thiếu nút thì một lần báo nhầm
  // làm buổi demo đứng im. Mock route chỉ chứng minh phần HIỂN THỊ + việc gọi đúng endpoint; phần
  // worker (latch, ẩn ô, xoá file `confirm.json`) có test Python riêng.
  {
    await page.unroute('**/api/live/status')
    await page.route('**/api/live/status', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ state: 'running', source: 'stub', frames: 0, measured_fps: 0,
          mask_fps: 8.5, device: 'cpu', message: 'stub', cau_hinh_lech: [],
          image_size_hieu_luc: 192, suc_khoe: null, suc_khoe_cau: null,
          bam: 'nghi_doi_tuong', bam_ly_do: 'o_nhay', bam_no_evidence_n: 0,
          nghi_doi_tuong: true, nghi_doi_tuong_n: 12 }) })
    })
    let goiConfirm = false
    await page.route('**/api/live/confirm', async (route) => {
      goiConfirm = true
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ state: 'running', source: 'stub', frames: 0, measured_fps: 0,
          mask_fps: 8.5, device: 'cpu', message: 'da xac nhan', cau_hinh_lech: [],
          image_size_hieu_luc: 192, suc_khoe: null, suc_khoe_cau: null, bam: 'tracking',
          bam_ly_do: null, bam_no_evidence_n: 0, nghi_doi_tuong: false, nghi_doi_tuong_n: 0 }) })
    })
    await page.waitForTimeout(1300)
    const chu = ((await liveCard.getByTestId('bam-no-evidence').textContent().catch(() => '')) || '')
      .replace(/\s+/g, ' ')
    check('HUD báo NGHI ĐỔI ĐỐI TƯỢNG + nói rõ 2 lựa chọn khi bam=nghi_doi_tuong',
      /ĐỐI TƯỢNG KHÁC/.test(chu) && /12 frame đã ẩn/.test(chu), chu || '(không thấy dòng nào)')
    const nut = liveCard.getByTestId('live-confirm-object')
    check('có nút "Vẫn đúng, tiếp tục" để tiếp tục mà không phải chọn lại ô',
      await nut.count() === 1)
    await nut.click()
    await page.waitForTimeout(400)
    check('bấm nút gọi ĐÚNG endpoint /api/live/confirm', goiConfirm === true,
      `goiConfirm=${goiConfirm}`)
    await page.unroute('**/api/live/confirm')
  }

  // "Có bằng chứng về vật" (21-11, plan P4): `state` = running KHÔNG có nghĩa là đang bám. Ba trạng
  // thái phải phân biệt được trên trình duyệt thật — mock route chỉ chứng minh được phần HIỂN THỊ,
  // phần DTO đã có test Python riêng (`TestBamXuyenTang`) vì e2e mock `**/api/live/status`.
  for (const [bam, lyDo, phaiHien, phaiCo] of [
    ['no_evidence', 'mask_rong', true, /Không có bằng chứng/],
    ['tracking', null, false, null],
  ]) {
    await page.unroute('**/api/live/status')
    await page.route('**/api/live/status', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ state: 'running', source: 'stub', frames: 0, measured_fps: 0,
          mask_fps: 8.5, device: 'cpu', message: 'stub', cau_hinh_lech: [],
          image_size_hieu_luc: 192, suc_khoe: { co: 'ok', p05: 0.82, n: 40, empty_frac: 0,
            cua_so: 30, nguong_vao: 0.3, nguong_ra: 0.45 }, suc_khoe_cau: null,
          bam, bam_ly_do: lyDo, bam_no_evidence_n: bam === 'no_evidence' ? 67 : 0 }) })
    })
    await page.waitForTimeout(1300)
    const so = await liveCard.getByTestId('bam-no-evidence').count()
    if (phaiHien) {
      const chu = ((await liveCard.getByTestId('bam-no-evidence').textContent().catch(() => '')) || '')
        .replace(/\s+/g, ' ')
      check('HUD báo "không có bằng chứng về vật" khi bam=no_evidence', so === 1 && phaiCo.test(chu),
        chu || '(không thấy dòng nào)')
      const lop = await liveCard.getByTestId('bam-no-evidence').getAttribute('class').catch(() => '')
      check('dòng "không có bằng chứng" là CẢNH BÁO (role=alert), không phải gợi ý',
        String(lop).includes('error'), `class=${lop}`)
    } else {
      check('bam=tracking ⇒ KHÔNG hiện dòng "không có bằng chứng" (không báo oan)', so === 0,
        `số dòng = ${so}`)
    }
  }

  await page.unroute('**/api/live/status')
  await page.unroute('**/api/live/start')

  const soGoiYDiemTrenTrangJob = await page.getByTestId('points-hint').count()
  check('trang JOB offline KHÔNG hiện gợi ý điểm (nó bỏ im lặng points — ticket #05)',
    soGoiYDiemTrenTrangJob <= 1,
    `số khối points-hint trên cả trang = ${soGoiYDiemTrenTrangJob} (chỉ khối của LIVE là đúng)`)

  check('UI gửi mode=track kèm bbox khi bấm "Bám đối tượng"',
    Boolean(trackPayload && trackPayload.mode === 'track' && trackPayload.bbox),
    JSON.stringify(trackPayload))
  check('payload /api/live/start có ĐIỂM kèm bbox (điểm âm đi được hết chuỗi UI → API)',
    Array.isArray(trackPayload && trackPayload.points) && trackPayload.points.length === 2
      && trackPayload.points.some((p) => p.label === 0) && trackPayload.points.some((p) => p.label === 1),
    JSON.stringify(trackPayload && trackPayload.points))
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

  // 9c. Nguồn mặc định "0" (chuỗi UI gửi đi) phải được hiểu là WEBCAM INDEX.
  //     Bug thật 13-11-2026: backend coi chuỗi "0" là ĐƯỜNG DẪN FILE ⇒ /api/live/start trả
  //     "Không mở được video file: '0'" — người dùng chọn webcam mà bị báo lỗi file.
  //     Máy chạy E2E có thể KHÔNG có webcam ⇒ chấp nhận "không có camera" hoặc chạy được;
  //     điều bị cấm là báo lỗi "video file".
  await liveCard.getByLabel('Nguồn frame').fill('0')
  await liveCard.getByRole('button', { name: 'Bật phát' }).click()
  const zeroMsg = await page.waitForFunction(
    () => {
      // SCOPE vào card live: trang có banner lỗi của khối JOB (`App.tsx`) đứng TRƯỚC panel live
      // ⇒ `document.querySelector('p.error')` có thể đọc nhầm banner khác (review 13-11, P3).
      const card = [...document.querySelectorAll('section')]
        .find((el) => el.textContent.includes('Phát trực tiếp'))
      const err = card?.querySelector('p.error')?.textContent || ''
      const st = card?.querySelector('[data-testid="live-status"]')?.textContent || ''
      if (err.includes('Không mở được')) return err
      if (st.includes('running')) return 'running'
      return null
    },
    null,
    { timeout: 20000 },
  ).then((handle) => handle.jsonValue()).catch(() => '(không có phản hồi)')
  check('nguồn "0" là webcam index, không phải file tên "0"',
    zeroMsg === 'running' || /camera index/.test(zeroMsg),
    String(zeroMsg).replace(/\s+/g, ' '))
  if (zeroMsg === 'running') {                 // máy có webcam thật ⇒ đóng phiên cho sạch
    await liveCard.getByRole('button', { name: 'Dừng' }).click()
    await page.waitForFunction(
      () => (document.querySelector('[data-testid="live-status"]')?.textContent || '')
        .includes('stopped'),
      null,
      { timeout: 10000 },
    )
  }

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
