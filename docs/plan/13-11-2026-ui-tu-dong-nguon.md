# Plan 13-11-2026 — Tự dò nguồn frame + làm lại UI

> Theo `AGENTS.md` §9.2: việc lớn (> ~4 h, đổi hợp đồng API) phải qua 3 góc nhìn độc lập + 1 vòng
> phản biện rồi mới chốt. Ba agent chạy **song song, không biết đề xuất của nhau** (vòng 1); phần
> tranh chấp dưới đây là chỗ các đề xuất **mâu thuẫn nhau** và cách tôi chốt.

## 🎯 Câu hỏi cần quyết
Người dùng yêu cầu: *"UI xấu quá, `./run api` tự kết nối rồi dán vào luôn cho gọn, làm lại UI cho
đẹp luôn"*. Máy WSL **không có webcam** (`/dev/video0` không tồn tại) nên nguồn thật là relay Windows
`http://<IP-Windows>:8090/snapshot.jpg`, và IP đó **đổi sau mỗi lần restart WSL**.

Câu hỏi: **làm cách nào để mở web là có nguồn dùng được ngay, mà không biến tính năng "tự kết nối"
thành nguồn lỗi mới (treo API, giành webcam, hoặc nói dối người xem)?**
Ràng buộc: `./run lint|test|webtest|e2e` phải xanh; không thêm thư viện UI; không đổi hợp đồng cũ
(chỉ thêm endpoint); watchdog/hằng số của `src/api/live.py` **không được đụng**.

## 🧭 Ba góc nhìn (vòng 1 — độc lập)

### A. Chất lượng & số đo
- Endpoint dò dùng được, nhưng `available` + nhãn "đã kiểm" **nói quá**: chỉ chứng minh "lấy được 4
  byte JPEG lúc dò", không chứng minh ảnh còn mới (relay phục vụ frame cũ vô hạn). Đề nghị:
  `check`/`latency_ms`/`checked_at`/`suggested_kind`; UI in *"dò lúc 22:41:03 · ảnh JPEG 6 ms"*.
- `camera_ok` phải dò bằng **đúng đường mở** của phiên live (`open_video_source`), không `cv2` trần
  (webcam UVC-qua-usbipd `isOpened()=True` mà `read()` False ⇒ dò sai).
- Chặn ngân sách: HTTP 0,8 s/URL, webcam 0,6 s, tổng ≤ ~1,6 s; 10 tab = 1 lần mở thiết bị.
- Thêm đồng hồ "không có frame mới trong N s" (relay giữ frame cuối ⇒ `state` vẫn `running`).
- **Đo**: `/info` relay tự báo 16,26 FPS nhưng nhịp đổi thật ~19,9/s ⇒ **cấm** đưa `fps` của relay
  lên HUD; chỉ `measured_fps`/`display_fps` của API/worker là số dùng được.

### B. Sản phẩm & bằng chứng bảo vệ
- Lỗ hổng lớn nhất không phải CSS: suốt 20–60 s **nạp model** màn hình chỉ có một dòng chữ ⇒ hội
  đồng thấy "treo". Đề nghị overlay đếm giây + giữ frame cuối.
- Số liệu 1,12rem (≈18 px) **không đọc được từ ghế thứ 3** ⇒ mất luôn "yêu cầu 6" của đề cương:
  phải ≥ 30 px, tách ô "mask mới" khỏi "FPS hình", có ô **mất dấu**.
- Nguy cơ nói dối: khi relay tắt, backend gợi ý **video mẫu** trong `data/` ⇒ phải có pill
  *"ĐANG PHÁT VIDEO MẪU (không phải camera)"*.
- Không auto-start (banner đỏ trước hội đồng + `LiveBusy` cho tab 2); badge LIVE phải tránh góc
  trên-trái vì worker vẽ HUD ở đó; bỏ `aspect-ratio 4:3` cứng (video 16:9 bị viền đen).

### C. Độ bền & hiệu năng
- **Không dò ở `create_app()`/import/lifespan** (`app = create_app()` chạy mỗi lần import ⇒ phá CI,
  và `--reload` biến mỗi lần lưu file thành một lần mở webcam).
- Route phải là `def` (threadpool), có cache + single-flight, `Cache-Control: no-store`.
- `live_busy` phải gồm **cả `LOADING`** (worker `track` nạp model rồi sẽ mở đúng thiết bị đó).
- Không probe URL tuỳ ý từ query (SSRF); không `sleep` trong test; E2E phải chạy 3 lần liên tiếp.
- Tách PR UI khỏi PR backend nếu diff > ~400 dòng.

## ⚔️ Tranh chấp (vòng 2 — phản biện chéo)

| Điểm tranh chấp | A (chất lượng) | B (sản phẩm) | C (độ bền) | Chốt |
|---|---|---|---|---|
| Làm gì trước | đồng hồ "ảnh đứng" | stage sống trong lúc nạp model | single-flight + cache | **Làm cả ba** — chúng không đụng nhau: A/B nằm ở UI, C ở adapter. Thứ tự thực thi: C (nền) → B (thấy được) → A (trung thực) |
| Có tự bật phiên khi mở trang? | không nói | **không** (banner đỏ) | **không** (`LiveBusy`, chiếm webcam) | **Không auto-start**; chỉ tự điền nguồn (1 click) |
| Backend có được "gợi ý" thứ tự ưu tiên? | để UI xếp hạng, backend trả `kind` | cần nhãn THẬT/MẪU ngay | backend không biết ý người dùng | Backend trả `kind` + `suggested`; **UI** quyết nhãn/hành vi |
| Có tách PR UI riêng? | — | — | **nên** (diff lớn che lỗi hành vi) | **Không tách** trong lần này: người dùng cần chạy được ngay, và E2E chạy 4 lần đều xanh; đổi lại tôi review theo từng file + log ghi rõ 3 vòng sửa |
| Sửa `src/api/live.py`/watchdog? | — | — | **cấm** | **Không đụng** (`STALE_S/MISS_MIN/WARMUP_S` đã qua 2 vòng review) |
| Thư viện UI (Tailwind/MUI)? | — | không | không | **Không**; chỉ CSS thuần, bundle vẫn < 200 kB |

## ✅ Quyết định
- **Chọn**: endpoint mới `GET /api/live/sources` (adapter `SourceProbe`, dò webcam → relay → video
  demo, cache 5 s, deadline cứng, `live_busy` gồm `RUNNING|LOADING`) + UI tự điền nguồn
  (`touchedRef` chống đè) + làm lại giao diện CSS thuần.
- **Vì sao**: đây là cách duy nhất đáp đúng yêu cầu *"đỡ phải dán"* mà không phải hardcode URL của
  một máy; dò ở adapter giữ được ADR-0005 (routes không biết cv2/HTTP) và test được không cần thiết bị.
  Số đo trên máy: dò lần đầu **74 ms**, cache **3 ms**, relay `available` với bằng chứng
  *"nhận được ảnh JPEG · 6 ms"*; E2E có check mới xác nhận ô nguồn = `suggested` của backend.
- **Bác**:
  1. **Hardcode URL relay vào UI** — bác vì IP đổi sau mỗi lần restart WSL, và máy khác sẽ thấy URL sai.
  2. **Auto-start phiên live khi mở trang** (hấp dẫn nhất về UX) — bác vì chiếm webcam dù không ai
     xem, và tab thứ hai/E2E nhận `LiveBusy` 409 (banner đỏ đúng lúc demo).
  3. **Dò trong `create_app()` để "dán vào luôn" sớm hơn** — bác vì `app = create_app()` chạy mỗi
     lần import ⇒ CI (ubuntu không có webcam) chậm/flaky và `--reload` mở webcam mỗi lần lưu file.
  4. **Dùng `fps` của relay cho HUD** — bác: đo được relay tự khai 16,26 FPS trong khi nhịp đổi thật
     ~19,9/s; số dùng được là `measured_fps`/`display_fps` (AGENTS §6).
  5. **Thêm thư viện UI / dark-light toggle / i18n** — bác: bundle + rủi ro vỡ toàn bộ `getByRole`
     của E2E, không có điểm nào cho đồ án.
- **Tiêu chí nghiệm thu (có SỐ)**:
  - [x] `./run lint` xanh · `./run test` **901 passed** · `npm test` **41 passed** · `npm run build` OK
  - [x] `./run e2e` **PASS** với 1 check mới `nguồn frame tự điền theo kết quả dò của backend`
  - [x] Dò nguồn: lần đầu **74 ms**, trong cache **3 ms**; `budget_ms = 1400`; `Cache-Control: no-store`
  - [x] Bundle JS **161,38 kB** (gzip 52,54) — không thêm dependency (`web/package.json` không đổi)
  - [x] Số liệu HUD ≥ **32 px** (`.stat .v = 2rem`), nhãn **13,6 px** không uppercase
  - [x] Dò webcam bị bỏ khi phiên live `RUNNING` **hoặc** `LOADING` (test `TestDangBanThietBi`)

## 📌 Việc tách ra ticket / Next steps
- Đường dẫn tuyệt đối của `data/` trong response (API chạy VPS cần rà lại) — log + Next steps.
- `image_size`/`vos_every` vào `LiveStatusResponse` để HUD in đúng provenance (live 192 vs form 256).
- Card "tổng kết phiên" + giữ frame cuối sau khi Dừng; ô "mất dấu" thành KPI riêng.
- `scripts/measure_live_sources.py` (p95 gọi đầu ≤ 500 ms, cache-hit ≤ 50 ms, first-frame ≤ 1500 ms)
  + LCP/CLS trong E2E.

## 📚 Tham chiếu
- `docs/task/13-11-2026-ui-moi-va-tu-dong-do-nguon.md` (log chi tiết, kể cả 2 ca E2E đỏ phải sửa).
- `AGENTS.md` §6 (số §6 đã đo, luật "0/None ≠ đã đo"), §9.1 (review độc lập), §9.2 (plan này).
- `docs/adr/0005-*` (ports & adapters — vì sao `SourceProbe` là adapter, tiêm ở `create_app`).
- Review độc lập nhánh `feat/ui-tu-dong-do-nguon`: 0 P0 · 1 P1 code (đã sửa trước khi review đọc:
  `live_busy` gồm `LOADING`) · 1 P1 tài liệu (plan này + bullet §6) · P2/P3 đã xử lý hoặc lên Next steps.
