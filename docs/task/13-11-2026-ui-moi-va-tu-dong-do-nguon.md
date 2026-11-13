# Ngày 13-11-2026 — UI mới + backend tự dò nguồn frame

## 🎯 Mục tiêu
- Bỏ bước thủ công "dán URL relay" mỗi lần mở web: `./run api` xong là UI đã có nguồn dùng được.
- Làm lại giao diện cho gọn/đẹp, số liệu đọc được từ xa khi chiếu máy chiếu, **không** thêm thư viện UI.

## 📥 Input
- Yêu cầu người dùng: "Ui xấu quá, ./run api tự kết nối rồi dán vào luôn cho gọn đở vào dán, tao cực
  quá. Làm lại UI cho đẹp luôn".
- Hiện trạng: `web/src` ~800 dòng React + `styles.css` tối giản; ô "Nguồn frame" mặc định `0` và **không
  lưu**, trong khi máy WSL không có webcam (`/dev/video0` không tồn tại) ⇒ mỗi lần `F5` phải dán lại
  `http://172.19.176.1:8090/snapshot.jpg` (IP đổi sau mỗi lần restart WSL).
- Ràng buộc: `AGENTS.md` §5 (lint/test/webtest/build/e2e), §9.1 (review độc lập), §9.2 (plan 3 góc nhìn
  cho việc lớn), ADR-0005 (ports & adapters), E2E Playwright đang chạy phải giữ xanh.

## 🔨 Công việc đã thực hiện
### 1. Backend: dò nguồn frame (endpoint mới, additive)
- `src/api/adapters/source_probe.py` (**mới**): `SourceProbe` dò theo thứ tự
  **webcam 0..2 → relay → video demo trong `data/`**, mỗi ứng viên có cờ `available` là kết quả **thử thật**
  (`cv2.VideoCapture(i)` đọc 1 frame; `GET` ảnh và kiểm magic `FF D8`), trả thêm `suggested`.
  - Relay lấy từ `CAM_RELAY_URL` nếu có, nếu không thì IP gateway (`/proc/net/route`) ở port 8090 —
    đúng đường WSL2 → Windows.
  - **Cache 5 s** dưới `threading.Lock`: 10 tab gọi cùng lúc không mở webcam 10 lần.
  - **Không dò webcam khi đang có phiên live** (`live_busy`) — mở thêm thiết bị sẽ tranh với chính phiên đang chạy.
  - Mọi lỗi dò bị nuốt (`_safe`) ⇒ endpoint không bao giờ 500 vì driver/mạng.
- `src/api/schemas.py`: `LiveSourceCandidate`, `LiveSourcesResponse`.
- `src/api/routes.py`: `GET /api/live/sources` (bọc try/except → 200 với danh sách rỗng).
- `src/api/main.py`: `create_app(..., sources=...)`; mặc định dựng `SourceProbe(REPO_ROOT, live_busy=...)`
  ở composition root (routes không biết cv2/HTTP).

### 2. Frontend: tự điền nguồn + giao diện mới
- `web/src/api.ts`: `getLiveSources()` + type `LiveSources`/`LiveSourceCandidate`.
- `LivePanel.tsx`: khi mở trang gọi `/api/live/sources` → **tự điền** ô "Nguồn frame" (`touchedRef` chặn
  việc đè lên chữ người dùng đã gõ/dán); thêm ô **"Nguồn gợi ý"** (chọn theo nhãn, không phải theo URL);
  dải **số liệu** (trạng thái, frame, FPS phát, nhịp mask, độ trễ); khung `.stage` có badge **LIVE** và
  placeholder hướng dẫn khi chưa phát.
- `App.tsx`: topbar (brand + tình trạng backend) + hero + layout 2 cột (live bên trái, upload/chọn/kết quả
  bên phải; dưới 1080 px thì xếp dọc).
- `UploadForm.tsx` / `ResultPanel.tsx`: đầu thẻ có số bước, file input kiểu dashed, mã job dạng `kbd`.
- `styles.css`: viết lại toàn bộ (biến màu, nền gradient nhẹ, thẻ số liệu `tabular-nums`, nút có trạng thái,
  focus ring) — **không thêm dependency** nào.
- Giữ nguyên 100 % label/testid mà E2E đang dùng (`Nguồn frame`, `Bật phát`, `Dừng`, `Chọn đối tượng để bám`,
  `Bám đối tượng`, `live-status`, `mask-rhythm`, `drift-line`, `device-line`, `img.live-frame`, `p.error`).

### 3. Test
- `tests/test_api_live_sources.py` (**mới**, 14 test): đọc gateway từ bảng định tuyến giả, thứ tự ưu tiên
  (camera/relay/video/không có gì), `CAM_RELAY_URL` thắng dò gateway, **không mở webcam khi đang live**,
  cache (2 lần gọi = 1 lần dò), lỗi dò không nổ, endpoint trả JSON đúng/lỗi → 200 rỗng, nguồn gợi ý phải
  là đường dẫn thật dùng được.
- `tests/test_api_routes.py`: khai endpoint mới trong danh sách hợp đồng OpenAPI (test này cố tình bắt
  mọi endpoint chưa khai báo — đã đỏ trước khi khai, đúng thiết kế).

## 📤 Output / Kết quả
- **Trước**: mở web → ô nguồn `0` → bấm "Bật phát" → `Không mở được camera index 0`; phải `Ctrl+A`, dán URL
  relay bằng tay mỗi lần tải trang.
  **Sau**: mở web → ô nguồn đã là `http://172.19.176.1:8090/snapshot.jpg` (kèm nhãn "Relay webcam Windows
  (snapshot JPEG)" + tag "đã kiểm") → bấm "Bật phát" là có hình.
- Đo trên máy này (relay đang chạy, camera Windows 640×480):
  - `GET /api/live/sources` lần đầu: **0,09 s**, `suggested = http://172.19.176.1:8090/snapshot.jpg`
    (webcam 0/1/2 = `available: false`), video demo `binh1/binh2/_gui_test.mp4` = `true`.
  - Trong trình duyệt thật (Playwright, Chrome headless): ô nguồn tự điền đúng URL;
    `live-status` = `Trạng thái: running · frame: 33 · FPS đo được: 16.5`.
  - Ảnh chụp: `data/_ui_top.png` (chưa phát, có placeholder) và `data/_ui_live.png` (đang phát 16,7 FPS).
- Kích thước bundle: JS **158,97 kB** (gzip 51,69 kB), CSS **7,66 kB** (gzip 2,44 kB) — không đổi công nghệ.
- Kiểm tra: `./run lint` xanh · `./run test` **893 passed, 5 deselected** · `npm test` **36 passed** ·
  `npm run build` OK · `./run e2e` **PASS** (24 check).

## 🐞 Vấn đề gặp phải & cách xử lý
- **E2E đỏ 1**: dòng `live-status` ban đầu bị tách trạng thái ra thẻ số liệu ⇒ mất chuỗi `stopped` mà E2E
  chờ (`waitForFunction` sau khi bấm Dừng). Sửa: giữ `Trạng thái: <state>` **trong** dòng đó (vừa để E2E
  đọc, vừa để trình đọc màn hình có ngữ cảnh).
- **E2E đỏ 2**: đổi `<h1>` thành "Bám bắt đối tượng theo thời gian thực" ⇒ mất chữ "Camera AI" mà check
  tiêu đề yêu cầu. Sửa: `Camera AI — bám bắt đối tượng thời gian thực` (giữ cả hai).
- **Bẫy thiết kế của test gateway**: tôi tự nghĩ giá trị hex nên test đỏ (`172.188.118.1`); `/proc/net/route`
  thật trên máy là `01B013AC` ⇒ phải đọc file thật để viết fixture. Ghi lại để lần sau không đoán.
- **`create_app(sources=None)` là "dùng bộ dò THẬT"**, không phải "không dò" ⇒ test phải tiêm bộ dò rỗng
  (`lambda: {}`). Đã ghi trong docstring để không ai hiểu nhầm.

## 📌 Next steps
- [ ] Review độc lập §9.1 cho nhánh `feat/ui-tu-dong-do-nguon` → sửa P0/P1 → merge.
- [ ] Cân nhắc nhớ nguồn gần nhất (`localStorage`) — hiện chỉ tự điền theo kết quả dò.
- [ ] Ticket P2-5 (từ log trước): relay báo khoẻ khi camera chết giữa phiên (`age_ms` + `streaming()`).
- [ ] Nếu API chạy trên VPS công khai: rà lại việc `/api/live/sources` trả đường dẫn tuyệt đối của `data/`
      (đang trả, phục vụ demo nội bộ).

## 📚 Tài liệu tham khảo
- `AGENTS.md` §1 (yêu cầu sản phẩm), §5 (checklist), §6 (số đo), §9.1/§9.2.
- `docs/adr/0005-*` (ports & adapters — lý do `SourceProbe` là adapter, tiêm ở `create_app`).
- `docs/task/13-11-2026-live-webcam-nguon-0-tu-web.md` (bug nguồn `"0"` + relay nhịp phát, cùng ngày).
- `docs/task/_template.md` (khuôn log này).
