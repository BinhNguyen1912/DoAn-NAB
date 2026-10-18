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

---

## Bổ sung 5 — webcam thật qua usbipd: 3 fix backend + format, tool quét LAN sai subnet

**Bối cảnh:** người dùng gắn webcam laptop (`HD Webcam`, usbipd BUSID `1-8`) vào WSL. Sau khi `sudo usermod -aG video $USER` thì `/dev/video0` mở được nhưng **read() luôn False**. Đồng thời `find_phone_camera.py` tự đoán subnet ra `172.19.177.x` (NAT của WSL) → quét nhầm dải.

**Đo thật (4 tổ hợp mở webcam)**:

| Cấu hình | read() đầu tiên |
|---|---|
| backend mặc định (obsensor) | False (dù `isOpened()=True`) |
| `CAP_V4L2`, không set format, đọc ngay | False |
| `CAP_V4L2`, chờ 1s | False |
| `CAP_V4L2`, retry 10×200ms | False |
| `CAP_V4L2` + `FOURCC=MJPG` + 640×480 | **True** |

**Đã sửa (TDD):**
1. `CameraVideoSource._create_capture` — Linux: ưu tiên `CAP_V4L2` (fallback `CAP_ANY`) và **ép MJPG + 640×480** sau khi mở; Windows giữ backend mặc định. Test: 3 case backend order + 2 case format.
2. `tools/find_phone_camera.py` — `pick_lan_ip()` (ưu tiên 192.168.*/10.*, loại loopback/link-local/172.16-31) + `windows_lan_ips()` đọc IP LAN của Windows host qua `powershell.exe` interop; chỉ fallback về IP của chính máy khi không lấy được. Test: 3 case `pick_lan_ip`.

**Verify thật sau fix:**
- `check_video_source --source 0 --num 10` → `CameraVideoSource | (640,480) | FPS 30` + đọc 10 frame @35ms.
- `run_live.py --source 0 --max-frames 2` → `[kết quả] 2 frame | mean=2780 ms`.
- `find_phone_camera.py --ports 1` → in `[quet] subnet 192.168.1.1-254` (đúng LAN).

**Ticket 03 → 4/4 resolved.** Test: làn nhanh 103 passed; ruff sạch.

**Ghi chú môi trường (cho lần sau):** webcam đang attach vào WSL → Windows không dùng được camera cho đến khi `usbipd detach --busid 1-8`.

---

## Bổ sung 6 — chậm dần khi chạy lâu: chẩn đoán + `--reanchor-every`

**Người dùng báo:** demo webcam 640×480, ms tăng dần `1852 → 6378` rồi bão hoà; hỏi có cách tối ưu nhanh hơn.

**Chẩn đoán (đo thật):**

| Phép đo | Kết quả |
|---|---|
| Thu nhận 1 frame webcam (MJPG 640×480) | 32 ms |
| `process()` frame 1 → frame 8 → frame 15 | 3353 → 8314 → 6438 ms |
| `len(non_cond_frame_outputs)` tương ứng | 1 → 8 → 15 |
| Giảm camera xuống 320×240 | 3969 → 3576 ms (**−10%**) |
| `torch.set_num_threads(8)` thay 4 | 3708 → 3410 ms (**−8%**) |
| Cắt bớt `non_cond_frame_outputs` (giữ 2–4) | ❌ `KeyError: 2` — SAM 2 tham chiếu frame cũ |

→ Nút cổ chai: **chi phí propagate tăng theo số frame lưu trong state**, không phải độ phân giải/thread.

**Đã làm:** `_maybe_reanchor()` trong `src/live_pipeline.py` + tuỳ chọn `reanchor_every` cho cả
`run_tracking`/`run_interactive`, key `reanchor_every` trong `configs/default.yaml`, flag CLI
`--reanchor-every N` (mặc định tắt). Cách hoạt động: mỗi N frame → `engine.reset()` rồi
`engine.start(frame, last_bbox)` (chọn lại chính bbox dự đoán gần nhất).

**Đo hiệu quả (fixture 20 frame, ô vuông + bị che 5 frame):**

| Chế độ | ms/frame | FPS | IoU sau che | Frame mất dấu |
|---|---|---|---|---|
| baseline | 5340 | 0.16–0.19 | 0.981 | 5/19 |
| re-anchor 6 | 3577 | 0.29 | 0.969 | 1/19 |
| **re-anchor 3** | **3053** | **0.34** | 0.969 | **0/19** |

Xác nhận qua CLI thật (12 frame, video test): `5346 ms → 3662 ms`.

**Test:** +2 (reanchor đúng nhịp + bbox cuối; mặc định không reanchor) + 3 config test; README mục
"Tối ưu tốc độ trên CPU" có bảng số liệu và đánh đổi; ruff sạch; full suite 111 passed.

---

## Bổ sung 7 — webcam realtime: giảm `image_size` của model (nhanh 5,4×)

**Bối cảnh:** người dùng nhấn mạnh sản phẩm là **webcam realtime** (video file chỉ để test). Nên tối ưu
phải nhắm vào độ trễ webcam.

**Thử nghiệm (build predictor với `++model.image_size=N`), fixture 20 frame, ô vuông 60px + che 5 frame:**

| image_size | ms/frame | FPS | IoU sau che | Mất dấu |
|---|---|---|---|---|
| 1024 (mặc định) | 5492 | 0.18 | 0.981 | 5/19 |
| 768 | 1645 | 0.61 | 0.993 | — |
| 512 | 733 | 1.36 | 0.988 | 5/19 |
| **512 + re-anchor 3** | **558** | **1.79** | 0.977 | **0/19** |
| 512 + re-anchor 5 | 578 | 1.73 | 0.978 | 4/19 |

**Đã làm:** `TrackerEngine.build_overrides(image_size)` (pure, 2 test) + `build_default(..., image_size=None)`;
key `image_size` trong config (validate int) + `configs/default.yaml`; flag CLI `--image-size N`
in cảnh báo khi bật. Mặc định vẫn 1024 (trung thực, không tự ý hạ chất lượng).

**Verify trên webcam thật:** mặc định `3080 ms` (0.32 FPS) → `--image-size 512 --reanchor-every 3`
= `569 ms` (**1.76 FPS**), nhanh 5,4×. Lệnh demo khuyến nghị đã ghi vào README.

**Cảnh báo trung thực:** hạ image_size làm ảnh downsample mạnh hơn → vật thể NHỎ trong ảnh thật có thể
kém chính xác; cần đo lại trên video thật trước khi chốt số cho báo cáo.

**Test:** +2 build_overrides + 2 config; full suite 115 passed; ruff sạch.

---

## Bổ sung 8 — "lag quá, di chuyển 1 phút sau mới thấy": bộ đệm camera + mức image_size

**Chẩn đoán:** driver V4L2 đệm **4 frame** (đọc liên tiếp 10 frame mất 675 ms → toàn frame cũ trong
queue). Cộng với suy luận 3–8 s/frame (mặc định) ⇒ cảm giác trễ hàng chục giây.

**Đã sửa:** `CameraVideoSource` ép `CAP_PROP_BUFFERSIZE = 1` (test riêng; verify driver báo 1.0) →
luôn đọc frame mới nhất, chỉ trễ 1 frame (~33 ms) cộng thời gian suy luận.

**Đo thêm các mức image_size (fixture 14 frame, che 3 frame, re-anchor 3):**

| image_size | ms/frame | FPS | IoU TB |
|---|---|---|---|
| 512 | 882 | 1.13 | 0.509 ⚠️ |
| 384 | 435 | **2.30** | 0.861 |
| 256 | 239 | 4.19 | 0.791 |

**Phát hiện quan trọng (sửa lại kết luận trước):** `--reanchor-every` **không ổn định khi có che
khuất** — nếu reset đúng lúc đối tượng bị che, nó "chọn lại" vào nền và bám sai (IoU 0.509). Kết quả
tốt trước đó (0.977) là do mẫu che khác. ⇒ Khuyến nghị: demo có che khuất thì **bỏ** re-anchor, chỉ
dùng `--image-size`; README đã ghi rõ.

**Test:** +1 buffer (16 test video_source); full suite 116 passed; ruff sạch.

---

## Bổ sung 9 — chuẩn bị Colab GPU: `--device cuda` + notebook chạy sẵn

**Người dùng chốt:** Colab là nơi chạy trước để lấy video + số liệu GPU (30 phút là thời gian cài đặt
một lần, không phải thời gian chờ mỗi lần demo).

**Đã làm:**
1. `--device {cpu,cuda}` trong `run_live.py` (đè được bằng config key `device`), kiểm tra
   `torch.cuda.is_available()` trước khi build → báo lỗi rõ nếu chưa bật GPU trên Colab; in tên GPU khi dùng cuda.
2. `notebooks/colab_gpu_demo.ipynb` (6 code cell): kiểm GPU → clone repo + SAMURAI + tải checkpoint +
   pip install → sinh video test nếu chưa có input → chạy headless `--device cuda` → in `gpu_summary.json`
   + xem mp4 trong notebook → tải 3 file về máy.
3. `docs/colab-gpu.md`: thời gian từng bước (cài 8–15 phút/lần, chạy video 20–40 giây), cách quay video nguồn,
   câu trả lời cho hội đồng, và ghi chú Colab free sẽ ngắt phiên.
4. README mục 3 trỏ tới notebook + `docs/colab-gpu.md`.

**Kiểm chứng trên máy dev (CPU):** lệnh y như cell 4 (đổi `--device cpu`) → ra mp4 + CSV + JSON;
`--device cuda` không có GPU → `[LOI] --device cuda nhưng máy không có GPU CUDA (kiểm tra: Colab → …)`.

**Test:** +3 config test (device default/cuda/giá trị lạ); full suite 119 passed; ruff sạch.

---

## Bổ sung 10 — LÀM LẠI phần demo: chế độ hiển thị MƯỢT (tách 3 luồng)

**Yêu cầu người dùng:** "hạn chế bỏ demo, đây là dự án đồ án của tôi… làm lại" — cần demo webcam
realtime thật, không phải workaround.

**Thiết kế (`src/smooth_display.py` mới):**
1. `LatestFrameSource` — luồng capture: đọc liên tục, giữ **frame mới nhất** + mốc thời gian, không xếp hàng.
2. `InferenceWorker` — luồng suy luận: lấy frame mới nhất → `engine.start/process`; `set_bbox()` để chọn/đổi
   đối tượng (reset + start), `clear()` khi bấm `r`; không có bbox thì **không chạy model**.
3. `run_smooth_display()` — vòng lặp hiển thị (main thread): vẽ frame mới nhất ~30 FPS + overlay của lần
   suy luận gần nhất; HUD thêm dòng `Overlay: N ms trước`; mỗi kết quả chỉ `consume()` 1 lần.

**Refactor `Visualizer`:** tách `update()` = `consume()` + `render()`.
`consume(result)` cập nhật quỹ đạo/latency/bộ đếm mất dấu (mỗi lần suy luận 1 lần);
`render(frame, result, overlay_age_ms, display_fps)` chỉ vẽ. Nhờ vậy vẽ 30 frame cho cùng 1 kết quả
không nhân đôi điểm quỹ đạo.

**Lỗi gặp khi làm:**
- `import torch` **trong luồng nền** (test fake engine) → kẹt import lock, thread đứng im. Sửa: import
  `TrackingResult` ở main thread trước khi start thread (ghi chú trong test).
- `summary.processed` ban đầu chỉ tăng khi có `visualizer` → sửa để không phụ thuộc visualizer.
- Fixture test vượt khung (30 frame × vận tốc 4 px trên khung 160px) → giảm còn 20 frame/khung 200px.

**Đo trên webcam thật (image_size 384, 8,3 s):** **159 frame hiển thị = 19,0 FPS**; **16 lần suy luận
= 1,92 FPS**; tuổi overlay TB **~522 ms**.

**CLI:** `--smooth` (+ config key `smooth_display`), dùng chung `--record/--metrics-csv/--metrics-summary`
(ghi mp4 theo luồng hiển thị 19 FPS). **Test:** +8 (2 nguồn/worker, 3 worker, 2 visualizer, 1 tích hợp
"vẽ nhiều hơn suy luận"); full suite 127 passed; ruff sạch.

---

## Bổ sung 11 — sửa 2 bug người dùng gặp khi chạy `--smooth`

**Người dùng báo (log thật):** sau ~38 frame xuất hiện `[LOI] suy luận thất bại: TypeError:
'NoneType' object is not subscriptable`, rồi lặp mãi `[f38] …`, và **phím `r` không chọn lại được**.

**Hai nguyên nhân (đều là bug của bản `--smooth` vừa thêm):**
1. **Race trên engine** — phím `r` gọi `engine.reset()` ngay ở luồng hiển thị trong khi luồng suy luận
   đang chạy model → `inference_state` bị xoá giữa chừng → `TypeError: 'NoneType' object is not
   subscriptable`; state hỏng nên các lần sau trả mãi frame cũ f38.
2. **`clear()` không xoá kết quả cũ** — vòng hiển thị vẫn thấy overlay cũ nên ở lại chế độ `track`,
   không vẽ lại con trỏ chọn ⇒ người dùng không kéo được ô mới. Thêm nữa, khi không có `visualizer`
   thì biến `mode` bị gán lại thành `select` dù đang track.

**Đã sửa:**
- `InferenceWorker` — **mọi thao tác engine chỉ diễn ra trong luồng suy luận**; `set_bbox()`/`clear()`
  từ main thread chỉ ghi `_pending` ("start"/"clear"), worker thực hiện `engine.reset()` rồi start.
- `clear()` xoá `_stamped` (về chế độ chọn), thêm `is_tracking()`; vòng hiển thị dựa vào
  `is_tracking()` thay vì kết quả cũ.
- Khi suy luận lỗi: in **1 lần** kèm hướng dẫn "bấm r để chọn lại", reset engine, về chế độ chọn
  (không lặp lỗi vô hạn như trước).
- Vòng hiển thị giữ đúng `mode = "track"` kể cả khi không có `visualizer`.

**Test:** +4 (`TestThreadSafety`: set_bbox không chạm engine ở main thread; clear xoá kết quả và ngừng
suy luận; lỗi chỉ báo 1 lần và về chế độ chọn; `r` rồi kéo ô mới thì start lại) — 12 test smooth_display,
full suite **131 passed**, ruff sạch.

**Verify trên webcam thật:** chạy → sau 2 lần suy luận bấm `r` → kéo ô mới `(180,120,460,400)` →
bám tiếp 5 lần suy luận, **42 frame vẽ**, quỹ đạo reset đúng, **không có `[LOI]`**.

---

## Bổ sung 12 — bảng đóng góp + biểu đồ báo cáo

**Người dùng hỏi:** "mình đang làm cho mình, chứ không dùng sẵn đúng không, vì đây là đồ án" →
cần tài liệu phân định rõ phần tự làm vs có sẵn.

**Đã làm:**
1. **`docs/team-contribution.md`** — bảng 12 thành phần (TrackerEngine streaming, VideoSource 4 adapter,
   PromptSelector, Visualizer, MetricsLogger, pipeline + smooth 3 luồng, config/CLI, fixture, tool phụ trợ,
   guardrail CI, tài liệu/ADR/log, số liệu đo) với cột *Nguồn / Em làm gì / Bằng chứng (file-commit-test)*;
   mục "không tự viết" (SAM 2, SAMURAI, thư viện, Colab) kèm lý do hợp lệ theo ADR-0001; mục "kết quả gốc";
   mục cách hội đồng tự kiểm chứng + câu trả lời mẫu. Số liệu thật: **2 424 dòng code**, **131 test**, 25 commit.
   README thêm mục 4 trỏ tới file này.
2. **`scripts/plot_metrics.py`** — vẽ PNG từ CSV MetricsLogger: `*_latency.png` (độ trễ + trung bình),
   `*_trajectory.png` (quỹ đạo tâm, trục y đảo đúng toạ độ ảnh), `*_lost.png` (frame mất dấu), và
   `so_sanh_latency.png` (so sánh nhiều lần đo, thang log). Thêm `matplotlib` vào requirements + 3 test
   cho phần đọc/tính (`tests/test_plot_metrics.py`).
3. **CI bắt lỗi của chính mình:** ruff lint cả code trong notebook → job đỏ ở commit 8f3121b; sửa bằng
   `extend-exclude = ["notebooks/"]` trong `ruff.toml` + tách import trong cell Colab → xanh (`dc19b68`).

**Verify:** `python scripts/plot_metrics.py data/smooth_metrics.csv data/gui_metrics.csv` →
7 PNG trong `data/charts/`; bảng in ra: smooth 55 frame mean 445 ms (2,25 FPS); gui 15 frame mean 5 047 ms
(0,20 FPS) → hình so sánh cho thấy chênh ~11 lần.

**Test:** +3 (plot_metrics), full suite 134 passed, ruff sạch.

---

## Bổ sung 13 — chạy Colab T4 thật: 3 lỗi môi trường + số liệu GPU

**Lỗi gặp khi chạy trên Colab (đều đã sửa vào repo):**
1. **Checkpoint 0 byte** — URL `.../092823/sam2.1_hiera_tiny.pt` trả **403** (Meta đổi mã ngày).
   Đúng: `.../092824/...` (200, 156 008 466 bytes). Notebook đổi sang **urllib Python thuần** + `assert`
   `>100MB` (chạy được ở mọi cell, không phụ thuộc `!wget`).
2. **`ModuleNotFoundError: No module named 'loguru'`** — SAMURAI sửa `sam2/modeling/sam2_base.py` để dùng
   `loguru`, gói này **không** nằm trong `install_requires` của sam2. Thêm `pip install loguru` vào
   notebook/README/`docs/samurai-setup.md`.
3. **`INTERNAL ASSERT FAILED ... inputs must be a CUDA tensor`** (từ `fill_holes_in_mask_scores`) — trên Colab
   extension C `_C.so` **có** nhưng nhận tensor CPU. Sửa: `build_default(apply_postprocessing=False)`
   (mặc định tắt) + cờ `--postprocess`; đồng thời làm số đo CPU/GPU **so sánh được** với nhau
   (trên CPU trước đây bước này luôn bị bỏ qua).
4. Dòng kết luận hard-code "máy CPU laptop" → đổi thành `_device_note(device)` in đúng thiết bị.

**Số liệu GPU thật (T4, video test 720p 60 frame, ô vuông):**

| Cấu hình | mean ms | p95 ms | FPS |
|---|---|---|---|
| image_size 1024 (mặc định) | 380 | 362 | 2,63 |
| **image_size 512 + reanchor 10** | **65** | **74** | **15,28** |

Đối chiếu CPU cùng máy: 5 047 ms (0,20 FPS) ở 1024; 445 ms (2,25 FPS) ở 384+smooth.
→ GPU nhanh ~13× ở 1024 và ~78× khi cả hai tối ưu. Ghi chú trung thực: T4 là Turing (SM 7.5) nên
**FlashAttention bị tắt** → số GPU là cận dưới; Ampere/Ada sẽ nhanh hơn.

**Còn lại:** người dùng tải `gpu_metrics2.csv` về `data/` để vẽ biểu đồ so sánh CPU vs GPU bằng
`scripts/plot_metrics.py`.
