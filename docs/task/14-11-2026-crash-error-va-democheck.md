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
10. `./run lint` xanh; `./run test` = **1037 passed**, 5 deselected. Test mới: `tests/test_live_crash.py`
    (18 test), `tests/test_demo_preflight.py` (41 test).
11. **Hai lần diễn tập thật** (`--full`, nguồn `data/binh1.mp4`, bbox 300,275,150,410, mẫu 12 s):

## 📤 Output / Kết quả

**Diễn tập `--full` (CPU, image_size mặc định, `binh1.mp4`):**

| Lần | frame thêm / 12 s | mask (VOS) | tổng kết 10 mục | mã thoát |
|---|---|---|---|---|
| 1 | **+357** (~29,8 FPS hiển thị) | **8,8 FPS** | 8 OK · 2 cảnh báo · 0 LỖI | 0 |
| 2 | **+330** | **9,0 FPS** | 8 OK · 2 cảnh báo · 0 LỖI | 0 |

Hai cảnh báo đúng như thiết kế: `mã nguồn` (cây bẩn khi đang phát triển) và `tệp phiên cũ` (lần 2 thấy
`bbox.json` còn lại từ lần 1 — đúng thứ cần dọn trước khi demo).

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
- `tests/test_live_crash.py`, `tests/test_demo_preflight.py` — **mới** (59 test).
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
- **Review độc lập (§9.1) — agent `reviewer`, nhánh `b94e0c5` so với `main`:** kết quả ghi ở mục dưới khi
  agent trả về; P0 = ? (xem "Kết quả review").

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Đóng các mục P0/P1 của review độc lập (nếu có) **trong cùng nhánh này**.
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
