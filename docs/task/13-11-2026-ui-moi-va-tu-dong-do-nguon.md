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

## 🔧 Siết sau 2 góc nhìn plan (§9.2) — phần "không được nói dối"

Góc nhìn **chất lượng & đo** và **độ bền** bắt đúng các chỗ tính năng dễ nói quá; đã sửa hết phần rẻ:

| Vấn đề được bắt | Đã sửa | Bằng chứng |
|---|---|---|
| `available` + chữ "đã kiểm" chỉ chứng minh "lấy được 4 byte JPEG", không nói ảnh còn mới | Mỗi ứng viên giờ có `check` (bằng chứng), `latency_ms`, và response có `checked_at` + `budget_ms` + `suggested_kind`; UI in **"dò lúc 23:21:05 · nhận được ảnh JPEG · 6 ms"** thay cho "đã kiểm" | `GET /api/live/sources` trên máy: `kind=relay`, `checked_at=2026-11-13T23:21:05`, relay `6 ms` |
| `camera_ok` gọi `cv2.VideoCapture` trần ⇒ khác đường mở thật (webcam UVC-usbipd `isOpened()=True` mà `read()` False) | Dùng đúng `open_video_source(str(index)).open()/read()/close()` — cùng đường với "Bật phát" | `tests/test_api_live_sources.py::TestNganSachThoiGian` |
| Không có deadline: driver Windows (DSHOW) có thể block 1–3 s/thiết bị | `_timed()` chạy trong thread + `join(budget)`: webcam **0,6 s**, HTTP **0,8 s**; quá hạn ⇒ `available=false` + `check="quá hạn … ms"` | `CAMERA_BUDGET_S`/`HTTP_BUDGET_S`, `budget_ms=1400` trong response |
| Gợi ý `_gui_test.mp4` (160×120, 14 KB) và `e2e_web.mp4` làm demo trông "hỏng"; `_PREFERRED_VIDEOS` còn tên file không tồn tại (`simloss.mp4`) | Bỏ tên `_*`/`e2e_*` và file < 100 KB; sửa danh sách ưu tiên thành `binh1/binh2/binh1_simloss` | test `test_bo_clip_tam_va_clip_qua_nho`; response thật chỉ còn `binh1/binh2` (2915/3108/4533 KB) |
| Relay giữ frame CUỐI khi camera hỏng ⇒ `state` vẫn `running`, ảnh đứng, HUD vẫn ghi "live" | Thêm `stallLine()` (web/src/live.ts) + `data-testid="stall-line"`: **"Không có frame mới trong 3,4 s (frame đứng ở 120 …)"** — cấm chữ "nguồn đã chết" (cảnh tĩnh cũng đứng) | 3 test vitest + 2 test cho nhãn nguồn |
| `--reload` làm mất cache mỗi lần lưu file | Đã ghi trong docstring adapter; ngân sách 1,4 s nên chấp nhận được | — |

Góc nhìn **sản phẩm & bằng chứng bảo vệ** (demo trước hội đồng) bổ 4 việc rẻ, đã làm:

| Việc | Đã làm | Vì sao |
|---|---|---|
| Nhãn THẬT/MẪU | `<pill>` xanh **"CAMERA THẬT"** khi nguồn là `camera`/`relay`; vàng **"ĐANG PHÁT VIDEO MẪU (không phải camera)"** khi relay tắt và backend gợi ý video trong `data/` | Không có nhãn này, hội đồng vẫy tay vào video lặp = mất điểm nặng nhất |
| Số liệu đọc được từ máy chiếu | `.stat .v` 1,12rem → **2rem (32 px)**, `.stat .k` 0,72rem uppercase → 0,85rem thường | Ở 1280×720 từ ghế thứ 3, cỡ cũ (18 px) không đọc được ⇒ "yêu cầu 6" của đề cương vô hình |
| Lúc NẠP MODEL không còn màn hình trống | thêm overlay **"Đang nạp model… N s"** (đồng hồ client, đếm mỗi giây) + nút "Dừng" bấm được | 20–60 s nạp model là lúc hội đồng đang nhìn; trước đó chỉ có một dòng chữ tiếng Anh |
| Chẩn đoán khi dò trượt | một dòng liệt kê nguồn ✗ + việc cần làm (`bật relay trên Windows: ./run relay (rồi bấm "Dò lại")`) | Trước hội đồng không ai phải mò nguyên nhân |
| Badge LIVE + tỉ lệ khung | badge sang **góc trên-phải** (worker vẽ HUD ở góc trên-trái: `cv2.putText(..., (8, 28))`); bỏ `aspect-ratio: 4/3` cứng (video demo 16:9 từng bị viền đen); giảm vignette 90px → 40px | Badge cũ che đúng dòng FPS/VOS/LK của chính hệ thống; viền tối làm mất mask ở mép khung (case "vật chạm mép" của đề cương) |
| Bỏ số "Bước 4" trên card live | đổi thành icon ▶ | Live giờ đứng ĐẦU trang, đánh số 4 thì hội đồng hỏi "bước 1 2 3 đâu" |

Không làm (đưa vào Next steps): script đo `scripts/measure_live_sources.py` (p95 gọi đầu ≤ 500 ms, cache-hit ≤ 50 ms,
first-frame ≤ 1500 ms) và đo LCP/CLS trong E2E — cần thêm thời gian, chưa chặn merge.

## 🔍 Kết quả review độc lập (§9.1) — vòng 3
- **Ai review**: agent `reviewer` qua tool `task` (chỉ đọc). Kết luận: **0 P0**, 1 P1 code, 1 P1 tài liệu;
  kiến trúc ADR-0005 **đạt** (`SourceProbe` không rò vào domain/routes/service), hợp đồng API cũ không đổi,
  luồng chọn đối tượng và tỉ lệ canvas **không bị phá** (E2E `16,36,48×48` vẫn xanh).
- **P1 code — `live_busy` phải gồm `LOADING`**: reviewer đọc bản trước commit `8f70f1c`; bản hiện tại đã
  sửa, và tôi tách `live_uses_device()` ở `main.py` để **test được** (`TestDangBanThietBi`: RUNNING/LOADING
  ⇒ True, STOPPED/ERROR ⇒ False).
- **P1 tài liệu**: thiếu `docs/plan/…` và bullet `AGENTS.md` §6 → đã viết
  `docs/plan/13-11-2026-ui-tu-dong-nguon.md` (3 góc nhìn + tranh chấp + 5 phương án bị bác) và thêm bullet
  §6 (dò nguồn chỉ lúc có request; `available` ≠ "đang chạy"; cấm dùng `fps` của relay).
- **P2/P3 đã sửa trong PR**:
  - `touchedRef` chưa set khi bấm "Bật phát" ⇒ kết quả dò về muộn có thể đổi nguồn giữa phiên: đã set.
  - `CAM_RELAY_URL` sai **chặn luôn** dò gateway (IP WSL2 đổi sau restart) ⇒ luôn thử gateway sau env;
    test `test_env_sai_van_thu_gateway`.
  - Dò lại sau "Dừng" (lúc đang live, webcam bị bỏ khỏi danh sách) + F5 giữa phiên giờ lấy trạng thái
    thật thay vì hiện "Chưa phát"; poll tự dừng khi `stopped|error`; lỗi mạng thoáng qua được xoá khi
    đọc lại được trạng thái.
  - Dựng DTO nằm **trong** `try` ⇒ một dict ứng viên hỏng không thành 500 (test `..._giua_chung_van_tra_200`).
  - Ứng viên `file`: chữ "đã kiểm" → **"có sẵn · N KB (chưa mở thử)"** (đúng thứ đã kiểm).
  - E2E: thêm check **"nguồn frame tự điền theo kết quả dò của backend"** (đây là lỗ hổng *bằng chứng*
    reviewer bắt được: trước đó không có test nào phủ tính năng chính) và `waitJobState` scope vào
    `[data-testid="job-status"]` (panel live cũng có dòng "Trạng thái:", đứng trước trong DOM).
  - A11y: file input có `<label>`, `p.error` có `role="alert"`, dòng trạng thái `aria-live="polite"`,
    `prefers-reduced-motion` tắt nhấp nháy badge; cột live sticky có `max-height` + `overflow:auto`.
- **Còn nợ (Next steps)**: đường dẫn tuyệt đối `data/` trong response (API chạy VPS cần rà), `image_size`
  trong `LiveStatusResponse`, card tổng kết phiên, `scripts/measure_live_sources.py`, TTL riêng cho kết quả
  dò âm, và follower của `suggest()` vẫn chiếm 1 thread threadpool khi phải chờ (chưa đo ca xấu).

## 📌 Next steps
- [ ] Review độc lập §9.1 cho nhánh `feat/ui-tu-dong-do-nguon` → sửa P0/P1 → merge.
- [ ] Cân nhắc nhớ nguồn gần nhất (`localStorage`) — hiện chỉ tự điền theo kết quả dò.
- [ ] `scripts/measure_live_sources.py`: p95 gọi đầu ≤ 500 ms, cache-hit ≤ 50 ms, first-frame ≤ 1500 ms
      (artifact có `git_rev`/`lenh`/`do_luc`/`git_dirty_code`), và LCP ≤ 1500 ms / CLS ≤ 0,1 đo trong E2E.
- [ ] Auto-fill nguồn cũng nên chạy lại sau `Dừng` và sau `start` lỗi (hiện chỉ lúc mount + nút "Dò lại").
- [ ] Thêm `image_size`/`vos_every` vào `LiveStatusResponse` để UI in đúng "provenance" (live = 192, form
      upload = 256 — hai số này lệch nhau và rất dễ bị hỏi trong buổi bảo vệ).
- [ ] Card "tổng kết phiên" + giữ frame cuối sau khi bấm Dừng (hội đồng thường hỏi đúng lúc đó).
- [ ] Ô "mất dấu" thành ô KPI riêng (hiện nằm trong dòng `mask-rhythm`), và `p95` độ trễ chỉ có khi đọc CSV
      từ worker — chưa hứa trên HUD.
- [ ] Ticket P2-5 (từ log trước): relay báo khoẻ khi camera chết giữa phiên (`age_ms` + `streaming()`).
- [ ] Nếu API chạy trên VPS công khai: rà lại việc `/api/live/sources` trả đường dẫn tuyệt đối của `data/`
      (đang trả, phục vụ demo nội bộ).

## 📚 Tài liệu tham khảo
- `AGENTS.md` §1 (yêu cầu sản phẩm), §5 (checklist), §6 (số đo), §9.1/§9.2.
- `docs/adr/0005-*` (ports & adapters — lý do `SourceProbe` là adapter, tiêm ở `create_app`).
- `docs/task/13-11-2026-live-webcam-nguon-0-tu-web.md` (bug nguồn `"0"` + relay nhịp phát, cùng ngày).
- `docs/task/_template.md` (khuôn log này).
