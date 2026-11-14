# Ngày 14-11-2026 — Crash thành `error` thật + `./run democheck` (việc #2, #7 của plan)

> Nhánh `fix/live-crash-va-democheck`, commit `b94e0c5`, nối tiếp plan `docs/plan/14-11-2026-plan-toi-uu-va-audit-bbox.md`
> (đã merge xong #1/#3/#4/#10). Đây là hai việc **an toàn cho buổi demo** còn lại.

## 🎯 Mục tiêu
- **#2** — Ca tệ nhất trước hội đồng: tiến trình **crash mà trông y như "thầy bấm Dừng"**. Làm crash thành
  `state=error` đọc được lý do, và chặn mọi đường tự mở lại thiết bị giữa phiên.
- **#7** — `./run democheck`: soi trước buổi demo 9 thứ đã từng làm hỏng demo (hoặc từng làm "demo chạy được"
  thành lời nói suông), **không nạp model**, ≤ 120 s; kèm `--full --bbox x,y,w,h` để **diễn tập thật**.

## 📥 Input
- `docs/plan/14-11-2026-plan-toi-uu-va-audit-bbox.md` (việc #2, #7 + ước lượng giờ + lý do).
- `AGENTS.md` §6 (kết luận đã đo: model nạp 20–240 s; ngưỡng treo; "Device busy" của webcam WSL; `source`
  là chuỗi "0" = webcam) và §9.1 (review độc lập bắt buộc).
- Code: `src/live_tracking.py` (`run()`, `_rewind()`, `_on_worker_error`), `tools/live_worker.py`,
  `src/api/adapters/worker_source.py` (`health()`), `src/api/adapters/opencv_source.py` (`_looks_like_file`),
  `src/video_source.py` (`open_video_source`).
- Dữ liệu: `data/binh1.mp4` (720×1280, 333 frame), bbox đã biết `300,275,150,410`.

## 🔨 Công việc đã thực hiện

### #2 — Crash phải thành `error`
1. **`src/live_tracking.py` — ngoại lệ ở luồng chính** (mở nguồn, `engine.start()` với ô chọn xấu, `read()`
   ném, `_annotate`): bọc `try/except Exception` quanh thân vòng lặp ⇒ `_on_loop_error(exc)` ⇒
   `state=error` + `message = "lỗi trong vòng lặp chính: <exc>"`. Trước đây ngoại lệ thoát ra ngoài rồi
   `finally` ghi `stopped` ⇒ API trả "worker đã kết thúc phiên", không ai phân biệt được với việc bấm Dừng.
   Tách `_set_error()` để chỉ có **một** nơi ghi `state = error`; message của luồng VOS giữ nguyên
   ("model lỗi trong luồng VOS") để đọc `status.json` là biết lỗi từ đâu.
2. **`.open()` chuyển VÀO trong `try`**: trước đây nằm ngoài nên ném ở đó ⇒ **không ai ghi trạng thái**,
   `status.json` kẹt `loading` trong khi tiến trình đã chết (người vận hành tưởng model còn đang nạp).
3. **`src/api/adapters/worker_source.py::health()`**: `state == "stopped"` chỉ được đọc là STOPPED khi **mã
   thoát == 0**; mã ≠ 0 ⇒ ERROR nêu mã + đường dẫn `worker.log`. (Chính crash cũng đi qua nhánh `stopped`
   do `finally` ghi ⇒ thiếu điều kiện này thì mọi crash vẫn "bình thường".)
4. **`session_exit_code(stats)`** (mới, `src/live_tracking.py`): `1` khi `state == error`, ngược lại `0`;
   `tools/live_worker.py` trả mã này (`if error: print [LOI] ...; return session_exit_code(stats)`).
   Trước đây worker **luôn** trả 0, nên mã thoát — tín hiệu cuối cùng còn lại cho systemd/runner/test —
   không nói được gì.
5. **`_rewind()` chỉ mở lại nguồn CÓ điểm kết thúc**: helper mới **`looks_like_file()`** trong
   `src/video_source.py` (int/chuỗi số ⇒ webcam ⇒ False; `rtsp://`/`http(s)://` ⇒ False; `.mp4/.avi/.mov/.mkv`,
   file, thư mục ảnh ⇒ True). Đường `raw` (`opencv_source._looks_like_file`) nay **dùng lại** helper này
   thay vì bản sao — trước 14-11 hai đường lệch chuẩn nhau. Lý do: webcam/RTSP/HTTP mà `read()` trả None
   thì mở lại thiết bị là bắn vào chân (relay/`usbipd` còn giữ ⇒ "Device busy", AGENTS §6).

### #7 — `./run democheck`
6. **`scripts/demo_preflight.py`** (mới) — 9 mục, mỗi mục một hàm nhận **tham số tiêm được** (`http_json`,
   `read_frames`, `provenance`) để test không cần mạng/webcam:

   | Mục | Vì sao có mặt |
   |---|---|
   | checkpoint SAM 2 | thiếu file là chết ngay giây đầu |
   | clip demo (mở được + ≥ 100 frame + in kích thước) | codec/đường dẫn sai |
   | `web/dist` không cũ hơn `web/src` | dist cũ ⇒ demo chạy mã cũ (bẫy đã gặp 12-11) |
   | API `/health` | quên `./run api` |
   | cổng API | API cũ/á quân đang giữ cổng |
   | tệp phiên cũ (`bbox.json`, `status.json` còn `running`) | phiên mới bám sai vật ngay frame đầu |
   | nguồn đọc được `n` frame trong `timeout` | webcam bận/relay chết |
   | **frame có ĐỔI** | nguồn đứng hình vẫn "đọc được" ⇒ demo là ảnh chết (bẫy "0/None ≠ đã đo") |
   | `git_rev` (+ bẩn trong `data/`) | mọi số buổi demo phải truy được về một commit |

   Mục **cảnh báo** (git bẩn, dist cũ, cổng bận, frame đứng, clip quá ngắn) **không** làm đỏ — nếu mọi thứ
   đều bắt buộc thì lệnh đỏ vĩnh viễn và không ai đọc nữa. `verdict()` là hàm thuần: `1` khi có mục **bắt buộc**
   không đạt.
7. **Nguồn chỉ đọc MỘT lần** (`probe_source`) rồi dùng cho cả mục "đọc được" lẫn "frame có đổi": hai lần mở
   riêng là tự sinh ra "Device busy" mà preflight định phát hiện.
8. **`--full --bbox x,y,w,h`** = diễn tập thật: tự dựng API nếu chưa chạy (log `data/democheck_server.log`),
   `POST /api/live/start` (mode=track, bbox dạng `{x,y,w,h}` — hợp đồng `LiveStartRequest`), chờ `running`
   (≤ 260 s), lấy mẫu `frames`/`mask_fps`, rồi `POST /api/live/stop`. **Bắt buộc `--bbox`**: hộp mặc định hay
   rơi vào nền ⇒ phiên "chạy được" mà bám sai (AGENTS §6, ca Colab 13-11).
9. **`run`** — thêm case `democheck` + 2 dòng help; **`AGENTS.md` §5** — thêm gạch đầu dòng bắt buộc chạy
   `./run democheck` trước buổi demo, kèm cảnh báo "OK ở mục nguồn ≠ bám đúng" và "--full bắt buộc --bbox".

### Kiểm tra & diễn tập
10. `./run lint` xanh; `./run test` = **1054 passed**, 5 deselected. Test mới: `tests/test_live_crash.py`
    (21 test), `tests/test_demo_preflight.py` (55 test).
11. **Hai lần diễn tập thật** (`--full`, nguồn `data/binh1.mp4`, bbox 300,275,150,410, mẫu 12 s):

## 📤 Output / Kết quả

**Diễn tập `--full` (CPU, image_size mặc định, `binh1.mp4`):**

| Lần | frame thêm / 12 s | mask (VOS) | tổng kết 10 mục | mã thoát |
|---|---|---|---|---|
| 1 | **+357** (~29,8 FPS hiển thị) | **8,8 FPS** | 8 OK · 2 cảnh báo · 0 LỖI | 0 |
| 2 | **+330** | **9,0 FPS** | 8 OK · 2 cảnh báo · 0 LỖI | 0 |
| 3 (sau khi sửa P0) | **+355** | **9,1 FPS** | **9 OK · 1 cảnh báo** · 0 LỖI | 0 |

Cảnh báo `mã nguồn` (cây bẩn khi đang phát triển) là cảnh báo **đúng như thiết kế**. Cảnh báo
`tệp phiên cũ` ở lần 2 (thấy `bbox.json` còn lại của lần 1) hoá ra là **nhiễu**: `_prepare_dir()` xoá
`bbox.json` trước mỗi lần start nên nó không bao giờ làm phiên sau bám sai — **đã bỏ cảnh báo đó ở
`219b792`** và thay bằng kiểm `worker.pid` còn sống (worker mồ côi mới thật sự giữ webcam).

**`./run democheck` trên nguồn webcam (máy này):** `nguồn video` = **LỖI** "Không mở được camera index 0
(bận hoặc không tồn tại)" và `frame có đổi` = LỖI "cần ≥ 2 frame để so" ⇒ verdict `CHƯA DEMO ĐƯỢC`.
Đây là hành vi **đúng** (WSL không có `/dev/video0`; đường demo là relay — xem AGENTS §6). Nó cũng chứng
minh preflight bắt được đúng ca "mở webcam hỏng" mà không nạp model.

**File thay đổi:**
- `src/live_tracking.py` — `try/except` quanh thân vòng lặp, `_on_loop_error`/`_set_error`, `.open()` vào
  trong `try`, `_rewind()` qua `looks_like_file`, hàm `session_exit_code`.
- `src/video_source.py` — helper `looks_like_file()` (một định nghĩa duy nhất) + `Path` import.
- `src/api/adapters/opencv_source.py` — dùng lại `looks_like_file` (xoá bản sao).
- `src/api/adapters/worker_source.py` — `health()` phân biệt mã thoát 0 / ≠ 0.
- `tools/live_worker.py` — trả `session_exit_code(stats)` + in `[LOI]` khi phiên lỗi.
- `scripts/demo_preflight.py` — **mới**: 9 mục + `--full` + 3 bước tay in ở cuối.
- `run` — case `democheck` + help.
- `AGENTS.md` §5 — bắt buộc `./run democheck` trước buổi demo.
- `tests/test_live_crash.py`, `tests/test_demo_preflight.py` — **mới** (76 test).
- `docs/task/14-11-2026-crash-error-va-democheck.md` — log này.

## 🐞 Vấn đề gặp phải & cách xử lý
- **`health()` không đủ để kết luận** khi chỉ nhìn `state`: crash cũng đi qua `finally` ghi `stopped`.
  ⇒ Phải **kèm mã thoát**; kéo theo việc worker phải trả mã đúng (`session_exit_code`), nếu không thì
  điều kiện mới không bao giờ kích hoạt (ban đầu worker luôn `return 0`).
- **`_on_worker_error` viết message "model lỗi trong luồng VOS"** — dùng lại cho lỗi luồng chính là nói sai
  chỗ hỏng ⇒ tách `_set_error(exc, where)` với hai câu khác nhau.
- **`_start_api` tự dựng API**: bản đầu tôi để người dùng tự `./run api` trước, nhưng diễn tập mà phải mở
  terminal thứ hai thì thực tế người ta sẽ **bỏ qua đúng bước cần nhất** ⇒ tự dựng + tự `terminate` (kèm đóng
  file log để không rò fd).
- **Cảnh báo "cổng 8010 đang bận" báo oan chính mình** (vì `--full` vừa dựng API trên cổng đó) ⇒ thêm cờ
  `port_owned`.
- **`--full` với bbox mặc định che giấu rủi ro thật**: hộp rơi vào nền cho `mask_fps > 0` mà bám sai
  (AGENTS §6 đã ghi đúng ca này ở Colab 13-11) ⇒ **bắt buộc** truyền `--bbox`, từ chối chạy nếu thiếu.
- **cv2 in cảnh báo `Camera index out of range` ra stderr** khi dò webcam — giữ nguyên (thông tin thật, và
  mục `nguồn video` đã nói lại bằng tiếng Việt kèm gợi ý index khác).
- **Review độc lập (§9.1) — agent `reviewer`, commit `b94e0c5` so với `main`:** verdict đầu
  "chưa merge được", **1 P0 + 2 P1 + 6 P2 + 6 P3**. Reviewer **không có shell** nên chỉ đọc mã (nó nói
  rõ điều này). Đã sửa **toàn bộ P0/P1/P2 + 7 P3** trong cùng nhánh:

| Mức | Phát hiện | Cách xử lý (đã làm) |
|---|---|---|
| **P0** | `POST /api/live/start` **chặn tới khi model nạp xong** (`routes.py:190` → `live.start()` → `WorkerFrameSource.start()` → `_wait_first_frame()`), trong khi `_http_post` mặc định **timeout 5 s** ⇒ `--full` báo hỏng oan **và** để phiên sống tiếp phía server (không ai gửi stop) | **Đo lại: POST chặn 3,4–4,1 s** với checkpoint tiny trên máy này (biên chỉ ~1 s!) ⇒ timeout nay `max(30 s, --full-timeout)`; khi POST hỏng vẫn gửi `/api/live/stop` **best-effort** + in `HTTP <code>: <detail>` |
| **P1** | `_rehearsal` không kiểm `state` **sau** khi lấy mẫu: phiên chết trong 10 s vẫn "OK" vì `frames`/`mask_fps` là số dính từ trước khi chết | kiểm `state != running` ⇒ LỖI kèm `message`; test `test_phien_chet_trong_luc_lay_mau_thi_khong_bao_ok` |
| **P1** | 2 test ghim "hợp đồng không có thật" (start trả dict tức thì; "start lỗi thì không stop") | viết lại theo hợp đồng thật (`_posts` giả ghi `(url, timeout)`); thêm test **timeout ≥ 30 s** và test **start lỗi vẫn stop** |
| **P2** | `_start_api` nằm **ngoài** `try/finally` ⇒ Ctrl-C/ngoại lệ để uvicorn mồ côi | bọc cả đoạn dựng API trong `try` |
| **P2** | `_http_post` nuốt **thân lỗi HTTP** ⇒ ca hỏng thật chỉ in "POST thất bại", mất đúng lý do | trả `(body, lỗi)`, giữ `HTTP 400: detail` cho `start` |
| **P2** | `check_stale_state` cảnh báo `bbox.json` cũ — **sai**: `_prepare_dir()` xoá nó trước mỗi lần start ⇒ sau mỗi buổi demo luôn có 1 cảnh báo vô nghĩa; đồng thời bỏ sót `worker.pid` (worker mồ côi giữ webcam) | bỏ cảnh báo bbox; thêm **pidfile còn sống** (`os.kill(pid, 0)`) + state `loading`; test 4 ca |
| **P2** | Thiếu test cho ngoại lệ **có chủ đích** của `looks_like_file`: chuỗi số khi CÓ file/thư mục thật trùng tên | test mới (`monkeypatch.chdir`, tạo file `0`) |
| **P2** | `_is_clip` khai lại danh sách đuôi video; `opencv_source._FILE_SUFFIXES` thành **chết** | export `FILE_SUFFIXES` từ `src/video_source.py`, dùng ở cả hai nơi |
| **P3** | `check_port` báo "cổng bận" đúng lúc API của ta **đang chạy** (trạng thái chuẩn bị demo) | chỉ cảnh báo khi cổng bận **và** `/health` không trả lời |
| **P3** | `check_source_moving` cho **đạt** khi hai frame **khác kích thước** | thành cảnh báo "nguồn đang đổi cấu hình" |
| **P3** | `check_webbuild` "đạt" khi **không có** `web/src` để so | cảnh báo "không so được" |
| **P3** | `_set_error` để lỗi sau ghi đè lỗi trước ⇒ `status.json` nêu sai nguồn gốc | **lỗi đầu tiên thắng** (+ test) |
| **P3** | `_default_checkpoint()` hardcode `tiny` trong khi `configs/default.yaml` là nguồn sự thật | đọc config, `tiny` chỉ là fallback |
| **P3** | Worker chết lúc đang nạp ⇒ message đọc như "đang nạp bình thường" | thêm tiền tố `status cuối:` |
| **P3** | Assert theo chuỗi thông điệp trong test | **giữ nguyên** (reviewer cũng ghi "chấp nhận được"): mục đích của hai test đó là *hai nguồn lỗi phải phân biệt được* |
| Note | đếm test sai (41 → 43) | log đã sửa thành số đếm thật (48 + 20) |

Reviewer cũng **xác nhận không phải lỗi** 9 nghi vấn của phiên cha (SIGTERM/Ctrl-C không bị báo ERROR oan,
worker chết không kịp ghi status vẫn ERROR, `_rewind` không phá hành vi cũ, `--full` đã dọn phiên khi ném
giữa đường…) — chi tiết ở báo cáo review trong phiên.

### Review vòng 2 (commit `219b792` → sửa tiếp)

**Kết luận: ĐỒNG Ý MERGE.** P0 + 2 P1 của vòng 1 **đã đóng đúng** (reviewer đối chiếu 14/14 mục đề xuất);
phát sinh **2 P2 + 10 P3**, đã sửa tiếp trong cùng nhánh:

| Mức | Phát hiện vòng 2 | Cách xử lý |
|---|---|---|
| **P2** | Khi POST start trả 4xx (**409 đang bận**, **422 bbox sai**) thì server **chưa chạm phiên nào**, nhưng `finally`/best-effort của tôi vẫn gửi `/api/live/stop` ⇒ **giết phiên đang chạy của người khác** | chỉ gửi stop khi kết cục **không xác định** (lỗi mạng/timeout, không phải `HTTP 4xx`); thêm chặn sớm: `GET /api/live/status` thấy `running` / `loading` ⇒ **từ chối diễn tập** (vì `live.start()` luôn `_stop_locked()` ⇒ `--full` sẽ cướp phiên) |
| **P2** | `_pid_alive` bằng `os.kill(pid, 0)`: trên **Windows** đó là `TerminateProcess` ⇒ "phép dò" **giết** tiến trình (và test tự giết pytest) | dùng lại helper của adapter: `_read_pid` (chặn pid ≤ 0) + `_pid_alive` (zombie = chết) + `_is_our_live_worker` (argv có `--out-dir` đúng thư mục) |
| P3 | `--full-timeout 60` ⇒ POST timeout 60 s < trần nạp model của server (240 s) ⇒ hỏng oan | `timeout = max(MODEL_LOAD_TIMEOUT_S, --full-timeout)` |
| P3 | Nhánh `HTTPError` của `_http_post` **không có test** | 3 test mới (400 + `detail`, 500 thân không phải JSON, `URLError`) |
| P3 | stop trong `finally` timeout 5 s < `LiveStreamService.stop()` (~7 s) | `timeout=15 s` |
| P3 | `_start_api`: `Popen` ném ⇒ rò fd file log | `try/except OSError: handle.close(); raise` |
| P3 | pidfile: pid âm / pid tái chế / zombie bị báo oan | đã đóng bằng cách dùng helper adapter (P2 ở trên) + 3 test |
| P3 | `--port 8011` mà `--base-url` hardcode 8010 ⇒ "cổng bận" được báo **đạt** (âm tính giả) | `--base-url` mặc định suy từ `--port` |
| P3 | Tiền tố `status cuối:` không có test | test mới (`status.json` còn "Đang nạp model…") |
| P3 | "Thiếu `web/src`" trả `ok=True` ⇒ in đạt cho thứ chưa so | thành **cảnh báo** + test |
| P3 | di vật comment trong `opencv_source.py`, import tách rời trong `_is_clip` | đã dọn |
| P3 | Log mâu thuẫn (khen cảnh báo `bbox.json`) + header thiếu commit sau review | đã sửa (mục "Output" + header) |

## 📌 Việc cần làm tiếp (Next steps)
- [x] Đóng các mục P0/P1 của review độc lập **trong cùng nhánh này** (vòng 1: P0/P1/P2 + 7 P3; vòng 2: 2 P2 + 9 P3 — xem hai bảng trên).
- [ ] Đo `--full` với **webcam/relay thật** (`source: 0` / `http://…/snapshot.jpg`) — rủi ro "Device busy"
      do `probe_source` mở/đóng nguồn ngay trước worker (review 14-11 nêu, chưa đo được trên máy này).
- [ ] Việc còn lại của plan: **#5** bảng cấu hình, **#6** thước đo "bám đúng", **#8** HUD, **#9** media, **#11** A/B.
- [ ] **2 lần diễn tập trên CAMERA THẬT** (relay Windows → `/snapshot.jpg`) + **kéo chuột trên web**: script
      không tự làm được, đã in 3 bước tay ở cuối `democheck`. Hiện chỉ mới diễn tập trên clip `binh1.mp4`.
- [ ] Đoạn video demo **liên tục ≥ 20 s** (hiện dài nhất 3,7–5,3 s) — điều kiện để demo bằng file thay vì webcam.
- [ ] Chốt phạm vi với GVHD bằng văn bản (re-ID bắt buộc? dataset chuẩn? "real-time" định nghĩa sao?).
- [ ] Ticket treo (không chặn demo): port re-ID vào đường live · fixture "vật cản đi ngang" có texture ·
      `pre_ms` 12–13 ms → `cv2.cvtColor`/`cv2.resize` (phải đo chất lượng) · `score` vào `status.json`/CSV.

## 📚 Tài liệu tham khảo
- `docs/plan/14-11-2026-plan-toi-uu-va-audit-bbox.md` — plan gốc (việc #2, #7 + ước lượng giờ).
- `AGENTS.md` §6 (kết luận đã đo: "Device busy", ngưỡng treo, `source` chuỗi "0") và §9.1 (review độc lập).
- `docs/task/09-11-2026-watchdog-live-va-nhanh-raw.md` — nguồn gốc `health()`/watchdog.
- `docs/task/13-11-2026-colab-t4-lan-2-so-gpu-nhung-bbox-sai.md` — ca `ket_qua = true` mà bbox trỏ vào nền
  (lý do `--full` bắt buộc `--bbox`).
- `docs/task/12-11-2026-ticket-21-thiet-bi-live-xuyen-chuoi-api-hud.md` — bẫy `web/dist` cũ làm e2e
  "PASS" trên mã cũ (cùng lý do mục `web/dist` trong `democheck`).
