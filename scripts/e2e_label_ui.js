/**
 * e2e_label_ui.js — E2E TRÌNH DUYỆT THẬT cho UI gán nhãn (`tools/label_ui.html` + `tools/label_ui.py`).
 *
 * Vì sao cần (cùng bài học AGENTS §5.4 / CODING_STANDARDS): unit test Python không thấy lỗi JS. Ba thứ
 * chỉ lộ khi lái trình duyệt thật:
 *   1. trang có tải được và **không có `pageerror`** không (một lỗi cú pháp JS ⇒ nút bấm chết mà
 *      `curl /` vẫn 200);
 *   2. `<video>` có **tua được** bằng Range request không (thiếu 206 ⇒ `currentTime` không nhảy ⇒
 *      "nhảy tới bước VOS kế" là nút chết);
 *   3. bấm phím `1` có **ghi thật** vào `data/nhan/<phiên>.jsonl` và **ô vẽ** có lưu `bbox_dung` không.
 *
 * Chạy: ./run labeluie2e   (tự bật server trên cổng riêng + tự xoá nhãn e2e sau khi xong)
 * Biến môi trường: BASE (mặc định http://127.0.0.1:8772), PHIEN (mặc định demoip_1125-121456).
 */
const fs = require('fs')
const path = require('path')

function loadPlaywright() {
  for (const c of ['playwright', path.join(__dirname, '..', 'web', 'node_modules', 'playwright')]) {
    try { return require(c) } catch (err) { /* thử đường kế */ }
  }
  throw new Error('Thiếu playwright — chạy: cd web && npm i -D playwright')
}

const { chromium } = loadPlaywright()
const BASE = process.env.BASE || 'http://127.0.0.1:8772'
const PHIEN = process.env.PHIEN || 'demoip_1125-121456'
// Server e2e ghi nhãn vào thư mục TẠM (`LABELUI_NHAN_DIR`) ⇒ script phải trỏ đúng chỗ đó.
const FILE_NHAN = path.join(process.env.LABELUI_NHAN_DIR || path.join('data', 'nhan'), `${PHIEN}.jsonl`)
const NGUOI = 'e2e'

let hong = 0
function kiem(ok, moTa, chiTiet) {
  console.log(`${ok ? '✓' : '✗'} ${moTa}${chiTiet ? ' — ' + chiTiet : ''}`)
  if (!ok) hong++
}
async function choFile(p, soLan = 20) {
  for (let i = 0; i < soLan; i++) {
    if (fs.existsSync(p)) return true
    await new Promise(r => setTimeout(r, 150))
  }
  return false
}
function docNhan() {
  if (!fs.existsSync(FILE_NHAN)) return []
  return fs.readFileSync(FILE_NHAN, 'utf8').split('\n').filter(Boolean).map(s => JSON.parse(s))
}

;(async () => {
  // `channel: 'chrome'` = dùng Chrome CÀI SẴN trên Windows (giống e2e_web.js / e2e_gt_painter.js);
  // bản chromium tải riêng chưa chắc có trên máy ⇒ launch() trần sẽ ném.
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  const page = await browser.newPage()
  const loi = []
  page.on('pageerror', e => loi.push('pageerror: ' + e.message))
  page.on('console', m => { if (m.type() === 'error') loi.push('console: ' + m.text()) })

  await page.goto(BASE, { waitUntil: 'domcontentloaded' })

  // 1) chọn phiên + nhập tên người gán
  // `<option>` trong <select> đóng KHÔNG 'visible' theo Playwright ⇒ phải chờ `attached`
  await page.waitForSelector('#phien option', { state: 'attached', timeout: 15000 })
  const soPhien = await page.$$eval('#phien option', os => os.length)
  kiem(soPhien > 0, 'danh sách phiên có dữ liệu', `${soPhien} phiên`)
  await page.selectOption('#phien', PHIEN)
  await page.fill('#nguoi', NGUOI)
  await page.dispatchEvent('#nguoi', 'change')
  kiem(true, 'chọn phiên + nhập người gán')

  // 2) video tải được metadata (Range request phải chạy)
  const okMeta = await page.evaluate(() => new Promise(res => {
    const v = document.getElementById('v')
    if (v.readyState >= 1) return res(true)
    const t = setTimeout(() => res(false), 15000)
    v.addEventListener('loadedmetadata', () => { clearTimeout(t); res(true) }, { once: true })
    v.addEventListener('error', () => { clearTimeout(t); res(false) }, { once: true })
  }))
  kiem(okMeta, '<video> tải được metadata (Range/206 hoạt động)')
  const dur = await page.evaluate(() => document.getElementById('v').duration || 0)
  kiem(dur > 5, 'video có thời lượng', `${dur.toFixed(1)} s`)

  // 3) "bước sau" phải TUA được (bắt bug Range/seek)
  const t0 = await page.evaluate(() => document.getElementById('v').currentTime)
  await page.click('#next')
  await page.waitForTimeout(900)
  const t1 = await page.evaluate(() => document.getElementById('v').currentTime)
  kiem(Math.abs(t1 - t0) > 0.05, 'nút "bước sau" tua được video', `${t0.toFixed(2)} → ${t1.toFixed(2)} s`)
  const vos = await page.$eval('#fVos', el => el.textContent)
  kiem(/^#\d+$/.test(vos.trim()), 'panel bước VOS cập nhật', vos)

  // 4) phím 1 ⇒ ghi nhãn ĐÚNG vào đĩa
  const truoc = docNhan().length
  await page.keyboard.press('1')
  const coFile = await choFile(FILE_NHAN)
  kiem(coFile, 'file nhãn được tạo', FILE_NHAN)
  const sau1 = docNhan()
  kiem(sau1.length === truoc + 1, 'phím 1 ghi ĐÚNG 1 nhãn', `${truoc} → ${sau1.length}`)
  const rec = sau1[sau1.length - 1] || {}
  kiem(rec.nhan === 'dung', 'nhãn ghi đúng giá trị', rec.nhan)
  kiem(rec.nguoi_gan === NGUOI, 'nhãn ghi đúng người gán', rec.nguoi_gan)
  kiem(typeof rec.t_video === 'number' && rec.t_video >= 0, 'nhãn có t_video thật', String(rec.t_video))
  kiem('git_rev' in rec && 'do_luc' in rec, 'nhãn có provenance (git_rev, do_luc)')

  // 5) vẽ ô (b) + phím 2 ⇒ nhãn SAI kèm bbox_dung
  await page.keyboard.press('b')
  const box = await page.$eval('#c', el => {
    const r = el.getBoundingClientRect()
    return { x: r.x, y: r.y, w: r.width, h: r.height }
  })
  await page.mouse.move(box.x + box.w * 0.3, box.y + box.h * 0.3)
  await page.mouse.down()
  await page.mouse.move(box.x + box.w * 0.6, box.y + box.h * 0.7, { steps: 6 })
  await page.mouse.up()
  await page.keyboard.press('2')
  await page.waitForTimeout(600)
  const sau2 = docNhan()
  const rec2 = sau2[sau2.length - 1] || {}
  kiem(sau2.length === sau1.length + 1, 'phím 2 ghi thêm 1 nhãn')
  kiem(rec2.nhan === 'sai', 'nhãn thứ hai là SAI', rec2.nhan)
  kiem(Array.isArray(rec2.bbox_dung) && rec2.bbox_dung.length === 4
       && rec2.bbox_dung[2] > rec2.bbox_dung[0], 'ô vẽ lưu thành bbox_dung',
       JSON.stringify(rec2.bbox_dung))

  // 6) bảng + bộ đếm cập nhật trên giao diện
  const dem = await page.$eval('#demNguoi', el => el.textContent)
  kiem(Number(dem) === 2, 'bộ đếm "đã dán" cập nhật', dem)
  const soDong = await page.$$eval('#bang tr', tr => tr.length)
  kiem(soDong >= 2, 'bảng nhãn gần nhất có dòng', `${soDong} dòng`)

  // 7) nhãn của NGƯỜI KHÁC bị ẩn (để dán độc lập)
  const khac = await page.$eval('#demKhac', el => el.textContent)
  kiem(!khac || /người khác/.test(khac), 'khu vực nhãn người khác không lộ giá trị', khac || '(trống)')

  // 8) không có lỗi JS nào (bắt P0 "nút chết" kiểu gt_painter)
  kiem(loi.length === 0, 'không có pageerror/console.error', loi.join(' | ') || '(sạch)')

  await browser.close()
  console.log(hong === 0 ? '\nLABELUI E2E: PASS' : `\nLABELUI E2E: ${hong} mục HỎNG`)
  process.exit(hong === 0 ? 0 : 1)
})().catch(e => { console.error('LỖI E2E:', e.message); process.exit(1) })
