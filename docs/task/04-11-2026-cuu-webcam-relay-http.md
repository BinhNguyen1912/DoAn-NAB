# Ngày 04-11-2026 — Cứu webcam: usbipd kẹt `Device busy (exported)` → relay HTTP Windows→WSL

> Phiên nối tiếp 02-11 (ADR-0004 + đo CPU/RAM + thí nghiệm ánh sáng).
> Hôm nay chỉ một việc: **webcam không vào được WSL**, mà mai phải demo bám vật với GVHD.

## 🎯 Mục tiêu
- Tìm ra vì sao `./run cam attach` luôn báo `Device busy (exported)` (đã thử cả reboot).
- **Có webcam sống trong WSL trước buổi demo**, không phụ thuộc usbipd.

## 📥 Input
- Lỗi người dùng dán: `usbipd attach --wsl --busid 2-8` → `Device busy (exported)`; `usbipd list`:
  `2-8 5986:211c HD Webcam Shared (forced)`.
- Máy: Windows 11 + Ubuntu (WSL2 NAT, gateway `172.19.176.1`), usbipd-win **5.3.0**, webcam tích hợp.
- Yêu cầu người dùng: *"fix, tao làm mọi cách nhưng không bật được"*.

## 🔨 Công việc đã thực hiện

> Người dùng báo `./run cam attach` luôn lỗi `Device busy (exported)`, đã thử đủ cách (kể cả reboot)
> mà không vào được ⇒ **không thể demo bằng webcam** nếu chỉ dựa vào USB/IP.

### Chẩn đoán đã làm (để lần sau không mò lại)

| Thử | Kết quả |
|---|---|
| `usbipd unbind --busid 2-8` (Admin) → `bind` lại | ✅ gỡ được `Shared (forced)` → `Shared`, bind không báo "in use" |
| `usbipd attach` | ❌ vẫn `Device busy (exported)` (usbipd 5.3.0) |
| Dừng `FrameServer`, kiểm `WbioSrvc` (Windows Hello) | Không phải nguyên nhân |
| Kill `ZaloCall.exe` / `ZaloCap.exe` / `Zalo` (8 process) | ✅ kill được, vẫn ❌ (chúng **tự bật lại sau reboot**) |
| Restart service `usbipd`, kiểm `vhci_hcd` + cổng 3240 | Cổng WSL trống, không client lạ |
| Kiểm audit camera registry (`LastUsedTimeStop`) + process python/ffmpeg | Không app nào đang giữ camera |
| **Reboot Windows** rồi attach | ❌ vẫn lỗi ⇒ trạng thái kẹt ở **driver**, unbind cũng đã cảnh báo "reboot may be required" |

### Giải pháp đã dựng (không cần Admin, không cần reboot)

**Windows mở webcam → phát MJPEG → WSL đọc như camera IP** (đúng nhánh "Camera **IP**" của đề cương):

1. `scripts/win_camera_relay.py` (mới) — HTTP server MJPEG chạy bằng **python của Windows**:
   `/video` (multipart), `/snapshot.jpg`, `/info` (JSON), `/` (trang xem). Đọc camera bằng DirectShow,
   luôn giữ **khung mới nhất** (client chậm không làm trễ camera), nhiều client cùng lúc.
2. `tools/setup_cam_relay.ps1` (mới) — tạo venv riêng ở `%LOCALAPPDATA%\wincam-venv` + cài
   `opencv-python` (**không đụng python hệ thống**; máy này python uv bị PEP 668 nên phải dùng venv).
3. `tools/start_cam_relay.cmd` (mới) — file bấm đúp trên Windows để bật relay.
4. `scripts/cam_relay.sh` (mới) + `./run relay` / `./run demoip` — tự dò IP Windows host trong WSL
   (`ip route`), bật relay nếu chưa chạy, chờ có khung hình, in URL; `demoip` chạy luôn pipeline
   (`--display --smooth --reid --reid-cue object --image-size 320`) và tự ghi mp4 + metrics + summary.

### 📤 Kết quả đo (04-11-2026, cùng máy)

| Kiểm chứng | Số đo |
|---|---|
| Luồng MJPEG | **640×480 @ ~21 fps**, `/snapshot.jpg` 50 KB khung JPEG hợp lệ |
| Pipeline đọc qua HTTP (`HttpVideoSource`) | 4 frame OK, **0/4 mất dấu**, mean **305 ms** ≈ **3,28 FPS** |
| Tài nguyên | CPU **321 %** (1 lõi ≈ 40 % máy), RAM đỉnh **593 MB** |
| `./run relay start` (đo sau khi sửa) | **3,2 s** (trước khi sửa: **treo >90 s**) |
| Test hợp đồng HTTP relay | **6 test** (info/snapshot/trang chủ/404/định dạng multipart/503 khi chưa có khung) |

### 🐞 3 lỗi tự bắt được (đều làm chết buổi demo nếu không sửa)
1. **Console Windows cp1252** → `print("…tiếng Việt…")` ném `UnicodeEncodeError` và **chết cả relay**
   ⇒ `sys.stdout/stderr.reconfigure(encoding="utf-8")`.
2. **`send_error(503, "chưa có khung hình")`** → status line HTTP chỉ mã hoá được **latin-1**
   ⇒ `UnicodeEncodeError` trong handler (test `test_snapshot_503_*` bắt được) ⇒ thông điệp **ASCII**.
3. **`powershell Start-Process -RedirectStandardOutput` giữ pipe** → lệnh trong WSL **treo vô hạn**
   (đo được `real 1m30` với `timeout 90`) ⇒ đổi sang `Invoke-CimMethod Win32_Process` (**1,3 s**).
   Bài học chung: mọi tiến trình Windows khởi từ WSL phải `</dev/null >/dev/null 2>&1`.

**Cổng kiểm tra cuối:** `./run lint` → All checks passed · `./run test` → **342 passed, 5 deselected** (35,4 s).

**File thay đổi (phần webcam):**
- `scripts/win_camera_relay.py`, `scripts/cam_relay.sh`, `tools/setup_cam_relay.ps1`,
  `tools/start_cam_relay.cmd` — **mới**: relay camera Windows → WSL.
- `run` — thêm `relay` + `demoip` (+ 2 dòng usage).
- `tests/test_win_camera_relay.py` — **mới**: 6 test hợp đồng HTTP (không cần camera).
- `README.md`, `docs/cheatsheet-lenh.md` — mục "Webcam khi usbipd kẹt" + 2 lệnh mới.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Nếu muốn quay lại đường USB/IP: `usbipd unbind --busid 2-8` (Admin) → **reboot** → `usbipd bind`
      → `./run cam attach`. Chưa xác nhận được cách này có ăn (đã thử rebind + reboot, vẫn lỗi).
- [ ] Tắt **auto-start của Zalo** (ZaloCall/ZaloCap tự chiếm camera sau mỗi lần khởi động Windows).
- [ ] Trước khi tắt máy: `usbipd detach --busid 2-8` (không detach rồi shutdown là đúng cái sinh ra lỗi này).
- [ ] Demo 04-11/05-11: dùng `./run demoip` (relay) hoặc điện thoại qua `./run phone`; dự phòng clip
      `./run fast data/binh1.mp4 --reid-cue object`.
- [ ] Commit (relay + 6 test + doc) khi người dùng đồng ý.

## 📚 Tài liệu tham khảo
- usbipd-win troubleshooting: https://github.com/dorssel/usbipd-win/wiki/Troubleshooting
- `docs/cheatsheet-lenh.md` §usbipd — quy trình attach/detach của repo này.
- MJPEG (`multipart/x-mixed-replace`) — định dạng `cv2.VideoCapture("http://…/video")` đọc được;
  `src/video_source.py` (`HttpVideoSource`) đã hỗ trợ sẵn.
- OpenCV DirectShow (`cv2.CAP_DSHOW`) — mở webcam trên Windows, tránh MSMF chậm 2–3 s ở khung đầu.


## 🧩 Bổ sung cùng phiên — fix lỗi "mất dấu đưa vật vào lại KHÔNG nhận được"

> Người dùng demo `./run demoip` (62 frame, `demoip_1104-212328.mp4`): vật rời khung ở f31, đưa về
> f38 → **không bao giờ tự nhận lại** (CSV: trả `reacquired=0` suốt, phải bấm `r`).

### Phỏng lỗi bằng chính video đó (bằng chứng định lượng)

| Phép thử | Số đo |
|---|---|
| bbox frame CUỐI "thấy vật" (f30) | **71×10 px chạm mép khung** — trong khi size thật (TB bbox đầu) **220×204** |
| bán kính vùng tìm theo size rác đó | age3 = **89 px** · age12 = **248 px** |
| ô đúng trong video, cách chỗ mất | **~300 px** ⇒ luôn ngoài vùng tìm ⇒ **không nhận lại được** |
| NCC trên template theo `prefilter_candidates` | chỉ 0,68–0,796 — yếu vì people đổi tư thế (templates hiếm, tình huống thật) |
| chấm descriptor trên lưới theo kích thước TB (220×204) | **cosine 0,82–0,85, 4/4 frame ô đúng IoU ≥ 0,4 cos ≥ 0,6** ✔ |

### Ba sửa trong `src/reid.py` (mặc định BẬT, không thêm key config)

1. **`_size_ema`** — kích thước vật trung bình trượt (α=0,2) cập nhật ở `_collect_reference`.
2. **bbox CHẠM MÉP không được cập nhật EMA** — chạm mép = dấu hiệu mask rác co mép (đo: 71×10).
3. `_filter_by_radius` / `_match_object` (kể cả lưới quét + `target_area`) **dùng EMA** thay
   `_last_obj_size`.

### Output — verify bằng 2 cách

**1) Tái kịch bản (mock engine, đúng chuỗi f0→3→38→47):** f46 `reacquiring`, f47 `reid=0,708` +
`reacquired=True` → TRACKING. Mà trước khi sửa, cùng chuỗi này không bao giờ tới được.

**2) Headless SAMURAI thật trên 2 clip:**

| Clip | Kết quả |
|---|---|
| `demoip_1104-212328.mp4` (60 frame) | mất dấu **0/60**, FPS **4,07**, mean 245 ms — không còn "ô bao nhảy ráng reset tự nhiều lần" |
| `binh1_simloss.mp4` (95 frame, ca vàng: mất f60) | mất dấu **27/95** (28%), nhận lại tại **f81 (reid 0,744)** và **f92 (0,927)** — trước đây ca này đã đo, kết quả đúng |
| Tài nguyên | CPU 398 % (1 lõi, 50 % máy), RAM 609 MB (`data/fix1104_summary.json`) |

**Test:** 3 test khoá hành vi EMA trong `tests/test_reid.py::TestKichThuocEma` (mask trong khung → EMA = size thật;
bbox chạm mép không sửa EMA; radius age5 = 385 px theo EMA thay vì 124 px theo bbox rác) — làn nhanh **345 passed** (33 s),
`./run lint` sạch.

**File thay đổi:**
- `src/reid.py` — `_size_ema` + 3 chỗ dùng.
- `README.md` — mục "Vật rời khung thì bbox 'co rác' của mép — EMA kích thước (04-11)".
- `data/fix1104_summary.json`, `data/fix1104b_summary.json` — bằng chứng đo verify.


## 🧩 Bổ sung 2 — lần test thứ 2 (theo thông số thực hiện đầy đủ kịch bản): vật TỐT nhưng hệ thống vẫn fail ở chỗ KHÁC

> Người dùng demo lại `./run demoip` (`demoip_1104-214048.mp4`, 75 frame) — kịch bản đúng chuẩn:
> vật (hộp AirPods cam) ra khung rồi đưa về, **nhiều lần**. Kết quả CSV: 18/75 mất dấu,
> **reacquired = 0** — vẫn phải bấm `r` 2 lần (log WARN "nghi ngờ ĐỔI ĐỐI TƯỢNG" f43, f63).

### Phân tích từng đoạn video (chụp ảnh + chấm điểm thủ công)

| Khung | Chuyện gì | Thấy gì ở ảnh |
|---|---|---|
| f0 | chọn hộp AirPods cam | ô chọn **tách người** ra khỏi hộp (chỉ khít mặt hộp) |
| f4–f13 | hộp di chuyển sang phải | mask dính theo hộp OK |
| f16–f33 | hộp chui xuống **ra khỏi khung** | mask teo dần → 10×small → 71×10 (llbbox chạm đáy) |
| f34–f51 | hộp **LÊN LẠI từ chỗ khác** (bên tay trái) | HUD hiện `MẤT DẤU`, reacquiring nhưng **reacquired=0** |
| f42, f51 | 2 lần có ứng viên | `reid_score` ghi 0,750/0,788 **nhưng không đủ để confirm 2 frame cùng chỗ** |
| f43, f63 | WARN đổi đối tượng + tự-reset | BẮN `r` thì về TRACKING, chồng chất nhiều lần |
| f52–f76 | bám "vùng lơ lớ" | mask TÂM là hộp NHƯNG lệch 50–90 px (chゴtigt sau vụ tự reset) |

### Ba nguyên nhân chứng minh bằng chấm điểm ứng viên từng frame

1. **Template NCC DUY NHẤT (lần đầu chọn) sai lệch dần**: 高校 vật được cầm quay theo tay.
   NCC của vùng ĐÚNG với template f0 chỉ 0,757; mà TPL mới nhất (f30) 0,918 ⇒ template phải
   cập nhật định kỳ. Đo từng template trên f36/f42/f51:
   | Frame | tpl f0 | tpl f10 | tpl f20 | tpl f30 |
   |---|---|---|---|---|
   | f36 | 0,606 | **0,813** | 0,908 | **0,967** |
   | f42 | 0,891 | **0,932** | — | — |
   | f51 | 0,762 | **0,882** | — | — |
   ⚠️ cho thấy: luôn phải **dùng multi-template** (không chỉ 1).
2. **Ứng viên qua confirm 2 frame KHÔNG cùng chỗ**: vì vật chui khỏi khung rồi bò về từ chỗ
   khác (bán tay trái) mà các frame liên tiếp ứng viên務 khác chỗ (f42 (216,272) vs f44 (188,276)
   cách nhau > 50%) — `_confirm` reset ⇒ không bao giờ đếm tới 2.
3. **Verify sau lúc nhận lại**: engine.start vào ô thiếu (f50 (340,68,505,233) — vùng trắng trên
   vv) → 2 frame verify fail vì mask mới không giống vật → về LOST → chu kỳ lặp (f50→f51 lost).

### Sửa các nguyên nhân 1 + 3 (nguyên nhân 2 là hành vi đúng — **chống bám nhầm**, không "fix")

**`src/reid.py`: thay `_obj_template` = tập `_obj_templates` (deque 4) nạp ĐỊNH KỲ:**

- Quy tắc nạp: (1) chưa có template nào, HOẶC (2) ≥ `DEFAULT_TEMPLATE_EVERY` = **10 frame**
  từ lần nạp trước, VÀ bbox **KHÔNG chạm mép** (chạm mép = mask rác — đo lần trước: 71×10).
- `_match_object` chạy prefilter trên **TẤT CẢ** template, **gộp + giữ max NCC** cho từng ô,
  rồi mới `_filter_by_radius`.
- Xoá template duy nhất cũ: `reset()` xoá cả deque; `_obj_template` cũ giữ lại cho lưới khớp.
- Cấu hình mặc định: `DEFAULT_TEMPLATE_EVERY = 10`, `DEFAULT_OBJ_TEMPLATES_MAX = 4`.

### Đo verify trên chính video lỗi (mock engine, đúng chuỗi f0→33→34→76)

- template nạp: **3** (f0 + f10 + f30 không chạm mép) · EMA = **(149, 122)** đúng size vật mới
- nhận lại tự động: **f41 (reid 0,815)** — trước đây không bao giờ; vẫn đi qua LOST/reacquiring
- sau đó verify fail đúng lúc box sai → về LOST → nhận lại khác chỗ (đoàn quản vòng lặp —
  đúng nghĩa "thà đang tìm còn hơn bám nhầm")
- runs được xác minh vị trí: f36 (0,842), f46 (0,765), f66 (0,918) — hệ có cơ hội đúng vật
  mà vật quay về chỗ khác trong phạm vi kích thước nở dần

**Cổng kiểm tra:** `./run test` → **345 passed, 5 deselected** (33 s) · `./run lint` → All checks passed.

**File thay đổi:**
- `src/reid.py` — `_obj_templates` (deque) + nạp định kỳ + gộp multi-template trong `_match_object`.

## 🧩 Bổ sung 3 — lần test thứ 3 (177 frame): "khúc sau nhận nhầm" — nguyên nhân KHÁC lần trước

> Người dùng test lại sau fix multi-template (`demoip_1104-214922.mp4`, 177 frame).
> Khúc đầu **ổn**: f42 nhận lại (reid 0,78) + f45 (reid 0,97) — đúng vật ✔.
> Khúc sau: **nhận lại NHẦM** — f102 (reid 0,81) bám vào **TAY người** (xem ảnh `data/_an2_f102.png`
> — mask trên tay, không phải hộp), rồi bám "vùng lơ lớ" suốt f102–f137; user: *"đưa đúng vật
> thể thì không ăn"*.

### Nguyên nhân (chứng minh chấm điểm thủ công)

- `_collect_reference` **lọc chạm mép cho `_obj_templates`** (fix trước) nhưng **QUÊN `_obj_refs`**
  (tập signature cosine). Đo: sample mask rác chạm đáy (f30, 117×46) cho **cos 0,798** với vùng
  nền — cao gần bằng ca ĐÚNG thật (0,85 với f103). Đó là lý do "nhận" f102 trên tay.
- Kết quả sạch khi bỏ ref chạm mép khỏi bộ mẫu: cos vùng đúng = **0,81** (f45, nhận ĐÚNG), các vùng
  nhầm tụt **0,46–0,58** (dưới ngưỡng 0,60) ⇒ **tách được**.

### Fix (1 chỗ duy nhất)

`_collect_reference`: **mask chạm mép → KHÔNG nạp**
- KHÔNG thêm vào `_obj_refs` (tập cosine — luôn nhớ là "ký ức ngoại hình")
- KHÔNG thêm vào `_obj_templates` (NCC)
- KHÔNG cập nhật `_size_ema`
- **VẪN cập nhật `_last_obj_size` + `_last_center`** — neo vùng tìm ở chỗ vật biến mất
  (test bắt được lỗi trừ bỏ neo này trong lần commit đầu)

### Verify headless lại_video gốc (SAMURAI thật, 177 frame)

- mất dấu **0/177**, mean **213 ms** ≈ **4,70 FPS** (trước fix: 269 ms / mất dấu 33 %)
- không còn "bám vùng lơ lớ": scoretb 3,45 ổn định suốt phiên (`data/verify1104_summary.json`)
- trên 3 lần mất dấu của phiên thật, các frame reacquired giữ nguyên (f42/f45/f102/f142/f147)
  nhưng **mask bám đúng vật** (không có vùng rõ ràng sai).

**Test:** thêm khẳng định `_obj_refs` không bị nạp mask chạm mép → `tests/test_reid.py` 3 + 1 hiện
có; làn nhanh **345 passed** (33 s) · `./run lint` sạch · `data/verify1104_summary.json` là bằng chứng.
