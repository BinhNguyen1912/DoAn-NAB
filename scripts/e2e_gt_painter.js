/**
 * e2e_gt_painter.js — E2E THẬT cho trình tô GT (`scripts/gt_painter.html` + `gt_gan_nhanh.py`).
 *
 * Vì sao có file này: PR #49 từng có **2 P0 trong JS** mà 24 unit test Python không bắt được:
 *   - `ve(null, …)` ⇒ `drawImage(null)` ném TypeError ⇒ **người tô vẽ mù** (nét vẫn lưu, nhưng không
 *     thấy gì trên màn hình);
 *   - `demPhu()` đọc `d.data` trên `.data` ⇒ TypeError ngay lần vẽ đầu ⇒ dòng trạng thái không bao giờ
 *     hiện.
 * Cả hai chỉ lộ khi **lái trình duyệt thật**. Đây đúng bài học AGENTS §5.4 (e2e đã bắt 3 bug thật).
 *
 * Kiểm gì:
 *   1. trang tải được, KHÔNG có `pageerror`/`console.error`
 *   2. canvas đúng kích thước frame gốc (720×1280 — bẫy canvas mặc định 300×150)
 *   3. "Nhận gợi ý" + phím A ⇒ % diện tích vật > 0 và **canvas hiển thị đổi thật** (bắt P0 "vẽ mù")
 *   4. kéo chuột ⇒ % diện tích TĂNG (bắt P0 `demPhu`)
 *   5. bấm "Lưu & tiếp" ⇒ file `gt_000057.png` có trên đĩa (kiểm bằng fs từ Windows) và trang sang
 *      frame kế, **không** có hộp thoại "chưa lưu" (bắt P2 confirm sai)
 *   6. "Không có vật" ⇒ ghi GT toàn đen + `?rong=1` được server nhận, `index.json` có `gt_rong`
 *
 * Chạy: `./run gte2e` (tự dựng bộ GT `_e2e_gt` + bật server). Biến môi trường: BASE, TEN.
 */
const fs = require('fs')
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
const BASE = process.env.BASE || 'http://localhost:8766'
const TEN = process.env.TEN || '_e2e_gt'
const GT_DIR = path.join('docs', 'gt', TEN)

let hong = 0

// Windows đọc file do WSL ghi qua 9p có thể trễ vài trăm ms ⇒ chờ ngắn thay vì kết luận "không có file"
async function choFile(p, soLan = 20) {
  for (let i = 0; i < soLan; i++) {
    if (fs.existsSync(p)) return true
    await new Promise(r => setTimeout(r, 150))
  }
  return false
}
function kiem(ok, moTa, chiTiet) {
  if (ok) {
    console.log(`✓ ${moTa}${chiTiet ? ' — ' + chiTiet : ''}`)
  } else {
    hong++
    console.log(`✗ ${moTa}${chiTiet ? ' — ' + chiTiet : ''}`)
  }
}

async function phanTramTrang(page) {
  return page.evaluate(() => {
    const cv = document.getElementById('cv')
    const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data
    let tong = 0
    for (let p = 0; p < d.length; p += 4) tong += d[p] + d[p + 1] + d[p + 2]
    return tong                                  // "khối lượng sáng" — đổi khi có mask hoặc nét mới
  })
}

async function demPixelMask(page) {
  return page.evaluate(() => {
    // `% diện tích vật` in ra từ chính mask ⇒ đọc số trên HUD thay vì đoán từ ảnh
    const t = document.getElementById('tt').textContent || ''
    const m = t.match(/([\d.]+)\s*%/)
    return m ? parseFloat(m[1]) : null
  })
}

;(async () => {
  // `channel: 'chrome'` = dùng Chrome/Edge CÀI SẴN trên Windows (giống `e2e_web.js`); bản headless
  // shell của Playwright không phải lúc nào cũng được tải về máy này.
  const browser = await chromium.launch({ channel: 'chrome', headless: true })
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } })
  const loiJs = []
  const hopThoai = []
  page.on('pageerror', e => loiJs.push('pageerror: ' + e.message))
  page.on('console', m => { if (m.type() === 'error') loiJs.push('console: ' + m.text()) })
  page.on('response', r => { if (r.status() >= 400) loiJs.push(`${r.status()} ${r.url()}`) })
  page.on('dialog', async d => { hopThoai.push(d.message()); await d.dismiss() })

  try {
    await page.goto(BASE + '/', { waitUntil: 'load' })
    await page.waitForSelector('#cv', { timeout: 15000 })
    await page.waitForFunction(() => (document.getElementById('tt').textContent || '').includes('frame'),
      null, { timeout: 15000 })

    const kt = await page.evaluate(() => {
      const cv = document.getElementById('cv')
      return { w: cv.width, h: cv.height }
    })
    kiem(kt.w === 720 && kt.h === 1280, 'canvas đúng kích thước frame gốc', `${kt.w}×${kt.h}`)

    const truoc = await phanTramTrang(page)
    await page.click('#nhan')
    await page.waitForTimeout(400)
    const sauGoiY = await phanTramTrang(page)
    const ptGoiY = await demPixelMask(page)
    kiem(sauGoiY !== truoc, 'nhận gợi ý ⇒ canvas hiển thị ĐỔI (không "vẽ mù")')
    kiem(ptGoiY !== null && ptGoiY > 0, 'HUD hiện % diện tích vật', `${ptGoiY} %`)

    // Kéo chuột 1 nét ở góc dưới-trái (ngoài chai) ⇒ diện tích phải tăng
    // Canvas 720×1280 cao hơn viewport (bị `max-width:100%` co lại) ⇒ kéo ở vùng NHÌN THẤY, nếu dùng
    // `box.height - 60` thì toạ độ rơi ngoài màn hình và chuột không chạm canvas (test đỏ oan).
    await page.locator('#cv').scrollIntoViewIfNeeded()
    const box = await page.locator('#cv').boundingBox()
    const y = box.y + Math.min(120, box.height / 2)
    await page.mouse.move(box.x + 40, y)
    await page.mouse.down()
    await page.mouse.move(box.x + 160, y, { steps: 12 })
    await page.mouse.up()
    await page.waitForTimeout(300)
    const ptSauVe = await demPixelMask(page)
    kiem(ptSauVe !== null && ptGoiY !== null && ptSauVe > ptGoiY,
      'kéo chuột ⇒ % diện tích TĂNG (đọc được mask thật)',
      `${ptGoiY} % → ${ptSauVe} %`)

    // Lưu & tiếp
    const fileTruoc = path.join(GT_DIR, 'gt_000057.png')
    if (fs.existsSync(fileTruoc)) fs.unlinkSync(fileTruoc)
    await page.click('#luu')
    await page.waitForFunction(() => (document.getElementById('canh').textContent || '').includes('đã lưu'),
      null, { timeout: 15000 })
    kiem(await choFile(fileTruoc), 'GT ghi THẲNG vào docs/gt/<ten>/', fileTruoc)
    // Bắt buộc: "Lưu & tiếp" KHÔNG được khai rỗng (từng bị: `onclick = luu` truyền MouseEvent vào
    // tham số `khaiRong` ⇒ mask bị xoá trắng + index ghi `gt_rong` trong khi người dùng vừa tô).
    const indexSauLuu = JSON.parse(fs.readFileSync(path.join(GT_DIR, 'index.json'), 'utf8'))
    kiem(!(indexSauLuu.gt_rong || []).includes(57),
      'lưu thường KHÔNG bị hiểu thành "không có vật"', JSON.stringify(indexSauLuu.gt_rong || []))
    await page.waitForTimeout(500)
    const daSang = await page.evaluate(() => (document.getElementById('tt').textContent || '').includes('frame 90'))
    kiem(daSang, 'sau khi lưu tự sang frame kế')
    kiem(hopThoai.length === 0, 'không có hộp thoại "chưa lưu" sai sự thật', hopThoai.join(' | '))

    // "Không có vật" trên frame 90
    await page.click('#rong')
    await page.waitForFunction(() => (document.getElementById('canh').textContent || '').includes('KHÔNG có vật'),
      null, { timeout: 15000 })
    const fileRong = path.join(GT_DIR, 'gt_000090.png')
    kiem(await choFile(fileRong), 'khai "Không có vật" ⇒ có file GT', fileRong)
    const index = JSON.parse(fs.readFileSync(path.join(GT_DIR, 'index.json'), 'utf8'))
    kiem(Array.isArray(index.gt_rong) && index.gt_rong.includes(90),
      'index.json ghi gt_rong (score_miou sẽ KHÔNG chấm frame này)', JSON.stringify(index.gt_rong))
    kiem(Array.isArray(index.frame_hw) && index.frame_hw.length === 2,
      'index.json có frame_hw (cổng kích thước GT mới chạy được)', JSON.stringify(index.frame_hw))

    kiem(loiJs.length === 0, 'không có lỗi JS trên trang', loiJs.slice(0, 3).join(' | '))

    await page.screenshot({ path: path.join('data', 'e2e_gt_painter.png'), fullPage: false })
  } catch (err) {
    hong++
    console.log('✗ ngoại lệ khi lái trình duyệt: ' + err.message)
  } finally {
    await browser.close()
  }

  console.log(`\nẢnh chụp: data${path.sep}e2e_gt_painter.png`)
  console.log(hong === 0 ? 'KẾT LUẬN: PASS' : `KẾT LUẬN: FAIL (${hong} mục)`)
  process.exit(hong === 0 ? 0 : 1)
})()
