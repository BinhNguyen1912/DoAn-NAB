# Ngày 18-10-2026 — Kiểm GUI thật (WSLg) + fix Ctrl+C làm mất metrics

## 🎯 Mục tiêu
- Kiểm thủ công đường GUI (kéo chuột chọn đối tượng, ghi mp4, metrics) trên máy thật — hạng mục treo từ ticket 03/05/06/07.
- Sửa mọi lỗi phát hiện được trong lúc kiểm.

## 📥 Input
- Kết quả kiểm của người dùng: Windows không có Python/conda; WSLg có (`DISPLAY=:0`) nhưng Qt thiếu `libICE.so.6`/`libSM.so.6` → `cv2.namedWindow` abort.
- Video demo cũ `data/samurai_cpu_demo_dog.mp4` **hỏng** (`moov atom not found`).
- Lệnh kiểm: `python tools/run_live.py --source data/_gui_test.mp4 --display [--record … --metrics-csv …]`.

## 🔨 Công việc đã thực hiện
1. Chẩn đoán bằng `ldd` trên `cv2/qt/plugins/platforms/libqxcb.so` → đúng 2 lib thiếu; người dùng cài `sudo apt-get install -y libice6 libsm6` → GUI chạy.
2. Tạo video test mới `data/_gui_test.mp4` (640×360, 30 frame, ô vuông cam 60px đi `(+8,+4)/frame`, 5 fps) bằng `src/synthetic_video.py` — thay video demo hỏng. (File nằm trong `data/` nên bị `.gitignore`, không commit.)
3. **Kiểm GUI thật — KẾT QUẢ ĐẠT:** kéo chuột chọn ô → bbox f0 `(79,80,142,142)` ≈ ô thật `(80,80)–(140,140)`; bám đúng quỹ đạo tới `(184,132,244,192)` ở f13 (khớp `+8x,+4y`/frame); thoát `q` in `[kết quả] 14 frame đã track`. Ghi mp4: `data/gui_hud.mp4` mở được, 9 frame, 640×360.
4. **Phát hiện bug thật:** thoát bằng **Ctrl+C** → `data/gui_metrics.csv` + `gui_summary.json` KHÔNG được ghi (mp4 vẫn có). Nguyên nhân: `_finish_metrics` nằm sau `try`, bị `SystemExit(0)` bỏ qua. Người dùng demo hay dừng bằng Ctrl+C → mất toàn bộ số liệu "đánh giá hiệu năng".
5. TDD fix: 2 test đỏ trong `tests/test_run_live_cli.py::TestCtrlCFlush` (headless + display, engine giả ném `KeyboardInterrupt` ở process thứ 2, assert CSV/JSON vẫn có + exit code 0) → sửa `_run_headless`/`_run_display`: cờ `interrupted`, flush metrics + `close_recorder()` **trong `finally`**; `_finish_metrics` bỏ tham số `total` không dùng. GREEN 9/9 test CLI.
6. Dứt tiếng ồn Qt (5 dòng `QFontDatabase: Cannot find font directory …cv2/qt/fonts`) bằng cách tạo thư mục đó + copy `DejaVuSans.ttf` → **0 cảnh báo**. Đã thử `QT_QPA_FONTDIR` trước (KHÔNG ăn với Qt5). Ghi vào README mục "Sự cố thường gặp khi chạy GUI" (kèm bảng: thiếu lib Qt, không mở được camera, HUD ô `?`, warning `_C` của SAM 2 là bình thường).
7. Verify: `ruff check .` sạch; full suite **84 passed (127s)**.

## 📤 Output / Kết quả
- Đường GUI + chọn đối tượng + ghi video: **đã kiểm chứng thật** (không chỉ test headless).
- Bug Ctrl+C mất metrics: **đã sửa + có regression test** (2 test mới).
- File thay đổi:
  - `tools/run_live.py` — flush metrics/recorder trong `finally` (cả headless + display), `_finish_metrics` gọn hơn
  - `tests/test_run_live_cli.py` — +2 test `TestCtrlCFlush`, helper `_write_cfg` dùng `textwrap.dedent`
  - `README.md` — mục "Sự cố thường gặp khi chạy GUI" + lệnh dứt cảnh báo font Qt
- Artefact kiểm (không commit): `data/_gui_test.mp4`, `data/gui_hud.mp4`.

## 🐞 Vấn đề gặp phải & cách xử lý
- Qt xcb thiếu lib → `ldd` chỉ đúng 2 gói, sửa bằng apt (không cần cài Python/conda bên Windows).
- `QT_QPA_FONTDIR` không có tác dụng với Qt5 của OpenCV → tạo đúng thư mục `cv2/qt/fonts` + TTF.
- Video demo cũ hỏng nên không dùng được cho demo lẫn test → sinh video test bằng code.
- Test YAML trong file test viết sai (mẹo `.replace` thụt lề) → chuyển helper sang `textwrap.dedent`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Kiểm **phím r** (chọn lại đối tượng thứ 2) trên GUI thật — chưa xác nhận.
- [ ] Chạy lại lệnh metrics + **Ctrl+C** để xác nhận CSV/JSON đã có (bản sửa).
- [ ] Webcam: WSL không thấy camera → dùng RTSP/HTTP từ điện thoại (kiểm adapter nguồn mạng) hoặc cài Miniconda trên Windows (`winget install -e --id Anaconda.Miniconda3`).
- [ ] Colab GPU + biểu đồ báo cáo (phase mới).

## 📚 Tài liệu tham khảo
- WSLg (`/mnt/wslg`, `DISPLAY=:0`), OpenCV Qt5 xcb plugin, `ldd`; `docs/samurai-setup.md`; ADR-0002 (số liệu trung thực — lý do Ctrl+C phải giữ metrics).

---

## Bổ sung cùng ngày — "chọn vùng nền mà vẫn chạy" (phản hồi của người dùng)

**Hiện tượng người dùng báo:** bấm `r` chọn lại rồi kéo ô vào **vùng nền trống** (không có ô vuông cam) → hệ thống vẫn bám.

**Chẩn đoán bằng đo thật** (`TrackerEngine.start` trên frame 0 của `data/_gui_test.mp4`):

| Trường hợp chọn | Mask | Score (logit) |
|---|---|---|
| A. đúng đối tượng (80,80,140,140) | 3618 px (**1.6%** khung) | **22.64** |
| B. nền trống nhỏ (520,260,580,320) | 2825 px (1.2%) | 17.81 |
| C. nền trống nhỏ (10,10,60,60) | 2883 px (1.3%) | 19.24 |
| D. nền trống ô lớn 200×200 | 32256 px (13.9%) | 14.74 |
| E. ô phủ gần cả khung | 224870 px (**97.6%**) | 18.77 |
| F. ô nửa đối tượng nửa nền | 3618 px (1.6%) | 15.74 |

**Kết luận:** đây **không phải bug** — SAM 2 là *promptable segmentation*, luôn trả mask cho bất kỳ ô nào được vẽ (kể cả nền). Ô nền nhỏ cho mask ≈ đúng ô đó nên **không phân biệt được** với đối tượng thật qua diện tích/score. Chỉ trường hợp mask phủ gần cả khung (E: 97.6%) mới phát hiện chắc chắn.

**Đã làm (TDD):**
1. `Visualizer.hud_lines(score, fps, ms)` — HUD thêm **dòng 3: `Điểm tin cậy: x.x`** (hàm thuần, test 2 case) để người dùng so sánh giữa các lần chọn.
2. `live_pipeline.warn_if_bad_selection(result)` + hằng `MASK_FRAME_WARN_RATIO = 0.6`, gọi ngay sau `engine.start` ở **cả 2 vòng lặp**: mask rỗng → `[WARN] ô chọn không phân đoạn được đối tượng (mask rỗng) — bấm r để chọn lại`; mask > 60% khung → `[WARN] mask phủ N% khung — ô chọn có thể quá lớn hoặc không chứa đối tượng`.
3. Verify thật: `--bbox "0,0,639,359"` → in `[WARN] mask phủ 98% khung`; `--bbox "80,80,60,60"` → không cảnh báo.
4. README: hàng mới trong bảng sự cố, nêu bản chất + 3 dấu hiệu nhận biết + cách xử lý (bấm r).

**Test:** 5 test mới (2 HUD + 3 cảnh báo); ruff sạch; full suite 89 passed.

---

## Bổ sung 2 — phản hồi "chọn nền thì vẫn chạy" và "mất dấu im lặng"

**Người dùng báo (log thật):**
- Lần 1: chọn bbox `(243,75,301,133)` **không nằm trên ô cam** → bám đúng vùng nền đó rồi **từ f7 liên tục `bbox=(0,0,0,0)`** (mask rỗng = mất dấu, chỉ thỉnh thoảng bắt lại).
- Lần 2: bấm `r`, chọn `(271,176,332,236)` = đúng vị trí ô cam lúc đó (ô đã đi tới `80+24·8, 80+24·4`) → bám đúng `(+8,+4)`/frame.

**Kết luận:** cả hai là hành vi đúng (promptable segmentation); thiếu sót là **không có phản hồi khi mất dấu**.

**Đã làm (TDD, 4 test mới trong `tests/test_visualizer.py`):**
1. `Visualizer.lost_frames` (tổng) + `consecutive_lost` (chuỗi liên tiếp); reset cả hai trong `reset()` (phím r).
2. Banner đỏ **`MẤT DẤU — bấm r chọn lại`** căn giữa khung khi mask rỗng; helper `_centered_org` (PIL, đo bằng font thật) / `_centered_org_cv` (fallback), màu `_COLOR_LOST`.
3. Verify end-to-end bằng model thật (bbox `243,75,301,133`, 10 frame): metrics `lost=[0,0,0,0,0,1,0,0,0,0]` ↔ pixel đỏ dải banner `[181,213,180,180,180,689,217,…]` → **mọi frame lost=1 có banner (689 px), mọi frame lost=0 không có (<217 px)**. Ảnh bằng chứng: `data/_banner_evidence.png` (HUD `FPS: 0.3`, `Độ trễ: 3333 ms/frame`, `Điểm tin cậy: -1.0` + banner giữa khung).
4. README: mô tả Visualizer nêu banner; bảng sự cố giải thích chọn-nền + 3 dấu hiệu nhận biết.

**Test:** full suite 93 passed; ruff sạch.

---

## Bổ sung 3 — nguồn camera điện thoại qua HTTP (fix theo phản hồi người dùng)

**Người dùng báo:** `--source "http://192.168.x.x:8080/video"` →
`FileNotFoundError: Không mở được video file` + lỗi DNS. Hai nguyên nhân: (a) dùng đúng chuỗi **placeholder** `192.168.x.x`; (b) **`http://` bị factory coi là video FILE** → thông báo sai đường.

**Đã sửa (TDD, 5 test mới trong `tests/test_video_source.py::TestHttpSource`):**
1. `HttpVideoSource` (mới) — MJPEG qua HTTP: thử `CAP_FFMPEG` rồi fallback `CAP_ANY`, timeout mở/đọc 5s, cùng lớp `_CaptureSource`.
2. `open_video_source` định tuyến `http://`/`https://` → `HttpVideoSource` (trước đây rơi vào `FileVideoSource`).
3. Thông báo lỗi mới nêu 4 việc cần kiểm (IP thật + cùng Wi-Fi, Start server, đúng `/video`, app chỉ RTSP) và **cảnh báo sớm khi URL còn placeholder** (`x.x`, `<`).
4. `tools/check_video_source.py` + README: mục "Camera điện thoại (iPhone/Android)" — 2 dạng URL, lệnh kiểm nguồn trước khi chạy pipeline, checklist 5 bước.

**Verify thật (không cần điện thoại):** dựng MJPEG-over-HTTP server local từ `data/_gui_test.mp4` (`/tmp/mjpeg_server.py`) rồi chạy đúng code repo:
- `check_video_source --source http://127.0.0.1:8099/video --num 5` → `HttpVideoSource | (640,360) | FPS 25 | 3.0 ms/frame`.
- `run_live.py --source http://127.0.0.1:8099/video --bbox 80,80,60,60 --max-frames 2` → `[kết quả] 2 frame | mean=2539 ms` (model thật, bám đúng ô vuông trên luồng mạng).
- Ghi chú: 2 lần chạy đầu fail vì server nền bị bash tool dọn giữa các lệnh (`Connection refused`) — lỗi harness, không phải code; chạy server + test trong cùng 1 lệnh thì OK.

**Test:** 94 passed (làn nhanh), ruff sạch.

---

## Bổ sung 4 — tool tìm camera trong LAN (người dùng không biết IP thật)

**Vấn đề:** người dùng chạy `--source "http://192.168.1.25:8080/video"` — đó là IP *ví dụ* trong hướng dẫn, không phải IP điện thoại → không tìm được host.

**Đã thêm:** `tools/find_phone_camera.py` — quét subnet /24 của máy trên các cổng thường dùng của app camera (`8080, 4747, 8081, 8088, 5000`), thử mở từng ứng viên như luồng MJPEG (`/video`, `/videofeed`, `/mjpegfeed`), in URL đọc được frame + lệnh pipeline gợi ý. Chỉ quét mạng cục bộ của máy, không cần model nên chạy vài giây.

**Verify:** dựng MJPEG server local (`/tmp/mjpeg_server.py`, port 8099) rồi chạy:
```
python tools/find_phone_camera.py --subnet 127.0.0 --ports 8099 --timeout 0.15
→ [OK] http://127.0.0.1:8099/video → 640x360
→ python tools/run_live.py --source "http://127.0.0.1:8099/video" --display
```
README: thêm mục "Không biết IP/URL của điện thoại? Quét mạng LAN".

**Lưu ý:** iPhone không có app "IP Webcam" (Android-only) — nếu app không hiện URL (DroidCam/Iriun chỉ tạo virtual camera cho Windows) thì phải dùng env Windows cho webcam; tool quét chỉ có ích khi app thật sự phát MJPEG/RTSP.
