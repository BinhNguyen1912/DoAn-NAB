# Ngày 21-11-2026 — `./run relay start` báo sai nguyên nhân: KHÔNG có camera đang cắm

## 🎯 Mục tiêu
Người dùng chạy `./run relay start` và nhận: *"relay sống nhưng KHÔNG có khung hình sau 20s ⇒ camera đang bị
app Windows giữ"*. Tìm nguyên nhân thật và sửa chẩn đoán để lần sau không chỉ sai đường.

## 📥 Input
- Log người dùng: `[LOI] relay sống nhưng KHÔNG có khung hình sau 20s` (lúc 05:47).
- Trạng thái relay hiện tại + Windows (WSL gọi `powershell.exe`).

## 🔨 Công việc đã thực hiện (đo, không đoán)
1. `curl /info` → `{"w": 0, "h": 0, "fps": 0.0, "camera": 0, "serving": true}`; `/snapshot.jpg` → **không trả gì**
   (`http=000`, hết 6 s) ⇒ server sống, camera **không ra khung**.
2. `data/_relay.log` chỉ một dòng: `cv::VideoCapture::open VIDEOIO(DSHOW): ... can't be used to capture by index`.
3. Tiến trình Windows: **2** `python.exe` chạy `win_camera_relay.py` — nhưng `ParentProcessId` cho thấy
   tiến trình `wincam-venv\python.exe` (23812) **sinh ra** tiến trình `uv\python` (8588) ⇒ **một** relay
   (trampoline), không phải hai bản chạy tranh nhau. Port 8090 do PID 8588 giữ.
4. **`Get-PnpDevice -PresentOnly | Where InstanceId -like '*VID_058F*'` → RỖNG**; thiết bị `PC Camera`
   (`USB\VID_058F&PID_3841&MI_00`) ở trạng thái **Unknown** (không present). Có **2** instance composite
   (`&6&2E04BE9A`, `&6&523A538`) = dấu vết webcam bị rớt/re-enumerate.
5. `./run relay stop` → cả 2 tiến trình mất, port 8090 trống ⇒ **stop không có lỗi** (nghi vấn ban đầu sai).

## 📤 Output / Kết quả
- **Nguyên nhân thật: Windows KHÔNG thấy camera nào đang cắm** (rút dây / USB rớt sau sleep / thiết bị bị
  disable). Không phải Zalo/Discord/Chrome giữ camera — đóng chúng **không** giúp gì.
- **Sửa chẩn đoán** (`scripts/cam_relay.sh`): thêm `cam_present()` hỏi PnP `PresentOnly -Class Camera`;
  ba chỗ (`status`, `start` khi server đã chạy, `start` sau 20 s) nay phân biệt:
  - **không có thiết bị** ⇒ "cắm lại webcam / thử cổng USB khác … đóng app KHÔNG giúp gì", kèm gợi ý
    `./run view data/binh2.mp4` khi cần demo mà chưa có camera;
  - **có thiết bị mà vẫn `w = 0`** ⇒ mới là "app khác giữ camera" (thông báo cũ).
- Kiểm: `bash -n` OK; `./run relay status` nay in đúng "NGUYÊN NHÂN: Windows KHÔNG thấy camera nào đang cắm".

## 🐞 Vấn đề gặp phải & cách xử lý
- Thông báo cũ **đoán** nguyên nhân từ một triệu chứng duy nhất (`serving=true` + `w=0`) và chỉ nêu giả
  thuyết "app giữ camera" ⇒ người dùng mất thời gian đóng app. Bài học: khi chỉ có một triệu chứng, phải
  **hỏi thêm nguồn sự thật** (ở đây là PnP) trước khi khuyến nghị hành động.
- Nghi vấn "2 relay tranh camera" **sai** — đã kiểm `ParentProcessId` và bác bỏ trước khi báo.

## 📌 Việc cần làm tiếp
- [ ] Người dùng cắm lại webcam (hoặc thử cổng USB khác) → `./run relay stop && ./run relay start`.
- [ ] Nếu `Get-PnpDevice -PresentOnly -Class Camera` vẫn rỗng khi dây đã cắm: Device Manager → quét lại
      (`pnputil /scan-devices`) hoặc gỡ thiết bị + rescan; kiểm camera có bị disable bằng phím Fn/khoá cứng.
- [ ] Trong lúc chờ: demo bằng clip — `./run view data/binh2.mp4` (hoặc `./run fast <clip>`), không cần webcam.

## 📚 Tài liệu tham khảo
- `scripts/cam_relay.sh` (mới: `cam_present()`), `data/_relay.log`, `scripts/win_camera_relay.py`
- `AGENTS.md` §6 (relay là đường duy nhất khi usbipd kẹt; demo web dùng `/snapshot.jpg`)
