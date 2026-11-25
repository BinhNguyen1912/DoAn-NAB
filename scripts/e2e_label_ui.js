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
const PHIEN = process.env.PHIEN || 'e2e_labelui'
// Bộ dữ liệu + thư mục nhãn do `./run labeluie2e` dựng trong TMP (data/* bị gitignore) ⇒ đọc từ env,
// mặc định vẫn trỏ data/ cho ai chạy tay.
const DATA_DIR = process.env.LABELUI_DATA_DIR || path.join('data')
// Server e2e ghi nhãn vào thư mục TẠM (`LABELUI_NHAN_DIR`) ⇒ script phải trỏ đúng chỗ đó.
const FILE_NHAN = path.join(process.env.LABELUI_NHAN_DIR || path.join(DATA_DIR, 'nhan'),
                            `${PHIEN}.jsonl`)
// CỐ Ý khác tên server (`--nguoi-gan e2e`): nếu trùng thì không phân biệt được "tên lấy từ UI" với
// "tên lấy từ cờ CLI" (review vòng 2, P1-A: assertion cũ xanh kể cả khi UI bị bỏ qua hoàn toàn).
const NGUOI = 'nguoi-tu-ui'

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
  kiem(await page.$eval('#nguoi', el => el.value) === NGUOI, 'ô người gán nhận tên đã nhập', NGUOI)
  kiem(await page.$eval('#dangDan', el => el.textContent) === NGUOI, 'header hiện người ĐANG dán', NGUOI)

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
  kiem(dur > 3, 'video có thời lượng', `${dur.toFixed(1)} s`)

  // 3) "bước sau" phải TUA được (bắt bug Range/seek)
  const t0 = await page.evaluate(() => document.getElementById('v').currentTime)
  await page.click('#next')
  await page.waitForTimeout(900)
  const t1 = await page.evaluate(() => document.getElementById('v').currentTime)
  kiem(Math.abs(t1 - t0) > 0.05, 'nút "bước sau" tua được video', `${t0.toFixed(2)} → ${t1.toFixed(2)} s`)
  const vos = await page.$eval('#fVos', el => el.textContent)
  kiem(/^#\d+$/.test(vos.trim()), 'panel bước VOS cập nhật', vos)

  // 2b) Enter ở ô tên = nhả focus (không gõ ký tự nào vào tên)
  await page.click('#nguoi')
  await page.keyboard.press('Enter')
  const tenSauEnter = await page.$eval('#nguoi', el => el.value)
  kiem(tenSauEnter === NGUOI, 'Enter ở ô tên KHÔNG gõ ký tự vào tên', tenSauEnter)

  // 3b) hệ số bù đã áp: video 98,0 s vs tổng latency 94,76 s ⇒ hệ số ≈ 1,034 (nếu KHÔNG bù thì cuối
  //     video lệch ~3 s và nhãn rơi sang bước khác)
  const heSo = await page.evaluate(() => (window.__labelui || {}).heSo)
  const tongLat = await page.evaluate(async ph => {
    const r = await fetch('/api/frames?phien=' + encodeURIComponent(ph))
    return (await r.json()).tong_latency_s
  }, PHIEN)
  const kyVong = Math.min(2, Math.max(0.5, dur / tongLat))
  kiem(typeof heSo === 'number' && Math.abs(heSo - kyVong) < 0.01 && Math.abs(heSo - 1) > 0.01,
       'hệ số bù = thời lượng video / tổng latency (khác 1 nghĩa là THẬT SỰ có bù)',
       `heSo ${heSo.toFixed(3)}, kỳ vọng ${kyVong.toFixed(3)} (video ${dur.toFixed(1)} s / ${tongLat} s)`)

  // 3c) tua vào GIỮA hai bước xa nhau nhất (bước 197 có 1771 ms) ⇒ phải hiện cảnh báo LỆCH
  const giua = await page.evaluate(() => {
    const s = window.__labelui, m = s.mapT || []
    let best = 0, gapMax = 0
    for (let i = 1; i < m.length; i++) {
      const g = m[i] - m[i - 1]
      if (g > gapMax) { gapMax = g; best = i }
    }
    return { t: (m[best] + m[best - 1]) / 2, gap: gapMax }
  })
  await page.evaluate(t => { document.getElementById('v').currentTime = t }, giua.t)
  await page.waitForTimeout(800)
  const coCanhBao = await page.evaluate(() => !!document.getElementById('lech'))
  kiem(coCanhBao, 'cảnh báo LỆCH hiện khi đứng giữa 2 bước xa nhau',
       `giữa 2 bước cách ${giua.gap.toFixed(2)} s, ở ${giua.t.toFixed(2)} s`)
  await page.click('#prev')                      // về bước gần nhất ⇒ cảnh báo phải tắt
  await page.waitForTimeout(800)
  const hetCanhBao = await page.evaluate(() => !document.getElementById('lech'))
  kiem(hetCanhBao, 'cảnh báo lệch TẮT sau khi bấm ←')

  // 4) P1-1: phím 1 khi con trỏ VẪN Ở Ô TÊN ⇒ phải ghi nhãn (bản cũ gõ "1" vào tên, không ghi gì và
  //    mọi nhãn sau mang tên "Binh1" ⇒ `tong_hop` bịa ra "2 người")
  await page.click('#nguoi')                  // con trỏ Ở TRONG ô tên, KHÔNG Enter
  const truoc = docNhan().length
  await page.keyboard.press('1')
  const coFile = await choFile(FILE_NHAN)
  kiem(coFile, 'file nhãn được tạo', FILE_NHAN)
  const sau1 = docNhan()
  kiem(sau1.length === truoc + 1, 'phím 1 ghi ĐÚNG 1 nhãn', `${truoc} → ${sau1.length}`)
  const rec = sau1[sau1.length - 1] || {}
  kiem(rec.nhan === 'dung', 'nhãn ghi đúng giá trị', rec.nhan)
  kiem(rec.nguoi_gan === NGUOI, 'nhãn ghi TÊN GÕ TRONG UI (không phải cờ --nguoi-gan)', rec.nguoi_gan)
  const tenTrongO = await page.$eval('#nguoi', el => el.value)
  kiem(tenTrongO === NGUOI, 'phím số KHÔNG lọt vào ô tên', tenTrongO)
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
  // 30%→60% ngang, 30%→70% dọc của 320×240 ⇒ (96,72,192,168) ±4 px. Sai tỉ lệ là mục này đỏ:
  // bản cũ chỉ kiểm `x2>x1` nên lỗi scale canvas→video vẫn PASS (review độc lập P2-5).
  const b = rec2.bbox_dung || []
  const dungToaDo = b.length === 4 && Math.abs(b[0] - 96) <= 4 && Math.abs(b[1] - 72) <= 4
    && Math.abs(b[2] - 192) <= 4 && Math.abs(b[3] - 168) <= 4
  kiem(dungToaDo, 'ô vẽ lưu ĐÚNG toạ độ video (30%..60% × 30%..70%)', JSON.stringify(b))

  // 5b) P1-2: vẽ ô ở bước này rồi sang bước kế ⇒ nhãn phải KHÔNG còn ô (ô của bước trước)
  await page.keyboard.press('b')
  await page.mouse.move(box.x + box.w * 0.2, box.y + box.h * 0.2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.w * 0.5, box.y + box.h * 0.5, { steps: 5 })
  await page.mouse.up()
  await page.click('#next')
  await page.waitForTimeout(900)
  await page.keyboard.press('3')
  await page.waitForTimeout(600)
  const sau3 = docNhan()
  const rec3 = sau3[sau3.length - 1] || {}
  kiem(rec3.nhan === 'mat_dau' && rec3.bbox_dung === null,
       'ô vẽ bị XOÁ khi sang bước khác (không lưu ô của bước trước)', JSON.stringify(rec3.bbox_dung))

  // 6) bảng + bộ đếm cập nhật trên giao diện
  const dem = await page.$eval('#demNguoi', el => el.textContent)
  // 3 dòng nhãn nhưng chỉ 2 BƯỚC (hai nhãn đầu cùng một bước) ⇒ bộ đếm theo bước phải là 2.
  kiem(Number(dem) === 2, 'bộ đếm đếm theo BƯỚC đã dán, không phải số dòng nhãn', dem)
  const soDong = await page.$$eval('#bang tr', tr => tr.length)
  kiem(soDong >= 2, 'bảng nhãn gần nhất có dòng', `${soDong} dòng`)

  // 7) nhãn của NGƯỜI KHÁC: ghi thẳng vào file một nhãn của "nguoi_khac" rồi tải lại trang ⇒ phải thấy
  //    SỐ LƯỢNG nhưng KHÔNG thấy nội dung (bản cũ assert `!khac || …` nên PASS cả khi xoá tính năng).
  const fsx = require('fs')
  fsx.appendFileSync(FILE_NHAN, JSON.stringify({
    phien: PHIEN, frame_vos: 99, t_video: 1, t_uoc_luong: 1, nhan: 'sai',
    bbox_dung: [1, 2, 3, 4], nguoi_gan: 'nguoi_khac', git_rev: 'e2e', do_luc: 'e2e'
  }) + '\n')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('#phien option', { state: 'attached', timeout: 15000 })
  await page.selectOption('#phien', PHIEN)
  await page.fill('#nguoi', NGUOI)
  await page.dispatchEvent('#nguoi', 'change')
  await page.waitForTimeout(800)
  const khac = await page.$eval('#demKhac', el => el.textContent)
  kiem(/1 nhãn của người khác/.test(khac), 'thấy SỐ LƯỢNG nhãn người khác', khac)
  const coNoiDung = await page.evaluate(() => document.body.innerText.includes('nguoi_khac')
    ? document.getElementById('demKhac').textContent.includes('nguoi_khac') : false)
  kiem(coNoiDung, 'chỉ nêu TÊN người khác, không nêu nhãn/toạ độ của họ')
  const bangCo99 = await page.$$eval('#bang tr', tr => tr.some(r => r.textContent.includes('99')))
  kiem(!bangCo99, 'bảng nhãn KHÔNG hiện bước 99 của người khác')

  // 8) không có lỗi JS nào (bắt P0 "nút chết" kiểu gt_painter)
  kiem(loi.length === 0, 'không có pageerror/console.error', loi.join(' | ') || '(sạch)')

  await browser.close()
  console.log(hong === 0 ? '\nLABELUI E2E: PASS' : `\nLABELUI E2E: ${hong} mục HỎNG`)
  process.exit(hong === 0 ? 0 : 1)
})().catch(e => { console.error('LỖI E2E:', e.message); process.exit(1) })
