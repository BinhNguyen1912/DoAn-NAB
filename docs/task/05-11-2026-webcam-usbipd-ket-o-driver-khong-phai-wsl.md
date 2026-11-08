# Ngày 05-11-2026 — Webcam: chứng minh `Device busy (exported)` kẹt ở **driver usbipd**, không phải WSL

> Nối tiếp log [04-11-2026](04-11-2026-cuu-webcam-relay-http.md) (dựng relay HTTP để demo).
> Hôm nay: người dùng `wsl --shutdown` rồi `./run cam attach` **vẫn** lỗi ⇒ phải xác định cho xong
> nguyên nhân và sửa những chỗ tài liệu/gợi ý đang chỉ sai đường.

## 🎯 Mục tiêu
- Kiểm chứng: reset WSL (`wsl --shutdown`) có cứu được `usbipd attach` không (gợi ý cũ trong repo nói có).
- Loại trừ nghi vấn "relay đang giữ camera nên usbipd báo busy".
- Sửa mọi gợi ý sai + lỗ hổng trong đường dự phòng (relay) để lần sau không mất thời gian.

## 📥 Input
- Người dùng dán nguyên văn (sau khi đã `wsl --shutdown`, mở lại Ubuntu):
  `./run cam attach` → `WSL usbip: error: Attach Request for 2-8 failed - Device busy (exported)`
  + `usbipd: warning: The device appears to be used by Windows` + `Failed to attach device with busid '2-8'`.
- Máy: Windows 11 + Ubuntu WSL2 (NAT, gateway `172.19.176.1`), usbipd-win **5.3.0**, webcam tích hợp
  `2-8  5986:211c  HD Webcam`.
- Kết quả điều tra cũ (04-11) trong `docs/task/04-11-2026-cuu-webcam-relay-http.md`.

## 🔨 Công việc đã thực hiện

### 1. Chẩn đoán (đo trên máy, 05-11 ~07:45–07:55)

| Phép thử | Kết quả | Kết luận |
|---|---|---|
| `usbipd list` | `2-8 … HD Webcam  Shared` (không `--force`) | Thiết bị *đã* bind, không phải lỗi bind |
| `usbipd state` (JSON) | **mọi** `ClientIPAddress: null`, `StubInstanceId: null` | usbipd **không** giữ export nào ⇒ "exported" là trạng thái kẹt nội bộ |
| `/sys/devices/platform/vhci_hcd.0/status` (WSL) | 8 port `sta 004` = `VDEV_ST_NULL`, `sockfd 000000` | Phía Linux **trống**, không kẹt cổng |
| `dmesg \| grep usbip` | chỉ có 2 dòng khởi tạo `vhci_hcd`, không có lần attach lỗi nào | WSL không nhận được yêu cầu attach |
| Cổng 3240 (usbipd) | `Listen` pid 5688 + 1 `TimeWait` (chính là lần attach vừa fail) | Không có client lạ |
| **Tắt relay rồi attach lại** | `./run relay stop` → `curl /info` chết → `usbipd attach --wsl --busid 2-8` → **vẫn** `Device busy (exported)` | ❌ **Bác bỏ** giả thuyết "relay giữ camera" |
| `Get-PnpDevice` HD Webcam | `Status OK`, `USB\VID_5986&PID_211C\…&0&8` | Driver Windows báo khoẻ, không có mã lỗi |
| `usbipd --version` vs GitHub API release mới nhất | 5.3.0 vs **v5.3.0** (2025-10-11) | Không có bản vá để nâng cấp |

⇒ Nguyên nhân đúng: **cờ "exported" kẹt ở tầng driver usbipd-win**; WSL, relay, app Windows đều không liên quan.
Đúng như kết luận 04-11 (reboot cũng không khỏi) — nhưng lần này có thêm bằng chứng `usbipd state` + `vhci` để
không ai phải mò lại.

### 2. Sửa chỗ chỉ sai đường + vá đường dự phòng
1. `scripts/usbipd_helper.py` — sau khi attach fail, in đúng sự thật (kẹt driver, `wsl --shutdown`/reboot
   đã thử không khỏi) + 2 lệnh chạy được ngay (`./run relay`, `./run demoip`) + đường quay lại USB/IP
   (`usbipd unbind` → reboot → `bind`), thay cho gợi ý "reset WSL rồi attach lại".
2. `run` (khối `./run cam`) — cùng nội dung, thêm nhắc `usbipd detach` trước khi tắt máy.
3. `scripts/cam_relay.sh` — thêm `streaming()` (yêu cầu `"w" > 0`, tức **có khung hình thật**):
   - `start`: trước đây chỉ chờ `"serving": true` ⇒ báo `OK` cả khi camera chưa mở được frame nào
     (đo được ngay sau start: `{"w": 0, "h": 0, "fps": 0.0, "serving": true}`). Nay chờ tối đa 20 s
     cho tới khi có frame; hết hạn ⇒ báo rõ "relay sống nhưng KHÔNG có khung hình ⇒ app Windows đang giữ camera".
   - `status`: phân biệt "đang chạy + có frame" vs "server sống nhưng chưa có frame" (exit 1).
   - `start` khi relay đã sống nhưng 0 frame ⇒ không im lặng cho qua, chỉ cách `stop && start`.
4. `docs/cheatsheet-lenh.md` — sửa dòng troubleshooting `Device busy (exported)` (bỏ "reset WSL" sai),
   và đổi các ví dụ `--busid 1-8` cứng → `--busid <BUSID>` (BUSID đổi sau mỗi lần khởi động lại).

## 📤 Output / Kết quả
- **Webcam vẫn dùng được ngay để demo** qua relay (đo 05-11 07:48–08:00):
  - `/info` → `{"w": 640, "h": 480, "fps": 9,2–15,9, "camera": 0, "serving": true}`
  - `/snapshot.jpg` → **HTTP 200**, **24 756–33 412 B**, JPEG 640×480 hợp lệ (xem ảnh: khung hình thật, không đen)
  - `./run relay stop && ./run relay start` → sống lại có frame sau **9,0 s**
  - Lệnh demo: `./run demoip`
- Cổng kiểm tra: `./run lint` → **All checks passed!** · `./run test` → **345 passed, 5 deselected** (34,7 s)
- File thay đổi:
  - `scripts/usbipd_helper.py` — gợi ý sau attach fail: kẹt driver usbipd, trỏ sang relay
  - `scripts/cam_relay.sh` — thêm `streaming()`, `start`/`status` chỉ OK khi có frame thật
  - `run` — khối `./run cam` nói đúng nguyên nhân + chỉ `./run relay` / `./run demoip`
  - `docs/cheatsheet-lenh.md` — sửa dòng troubleshooting sai + `--busid <BUSID>`

## 🐞 Vấn đề gặp phải & cách xử lý
- **Giả thuyết sai tự bắt được:** "2 tiến trình python cùng chạy relay ⇒ tranh camera ⇒ usbipd busy".
  Đo lại: `PID 2580` (python của venv `wincam-venv`) là **trampoline** của venv tạo bằng `uv`, nó
  spawn `PID 23704` (CPython 3.12 của uv) — **một relay, hai tiến trình**, không phải hai relay.
  Hệ quả: không sửa `stop` (giết theo `$_.Path -like '*wincam-venv*'` là đủ, đã kiểm: stop → 0 tiến trình,
  cổng 8090 đóng) — nếu không đo lại thì đã "sửa" một bug không tồn tại.
- **Không sửa được bằng phần mềm thường:** `usbipd` 5.3.0 là bản mới nhất; `unbind/rebind`, restart service,
  tắt app giữ camera, reset WSL, reboot (04-11) đều không xoá được cờ exported ⇒ coi như **hỏng tầng driver**,
  chỉ có thể chờ bản usbipd mới hoặc cài lại driver (chưa thử, cần Admin + reboot).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Trước khi tắt máy: `usbipd detach --busid <BUSID>` — không detach rồi shutdown là đúng cái sinh ra lỗi này.
- [ ] Tắt auto-start **Zalo** (ZaloCall/ZaloCap tự chiếm camera sau mỗi lần khởi động Windows).
- [ ] (Tuỳ chọn, cần Admin) thử `usbipd unbind --busid 2-8` → **reboot** → `usbipd bind --busid 2-8` → `./run cam attach`;
      nếu vẫn lỗi thì cài lại usbipd-win (gỡ + `winget install dorssel.usbipd-win`) rồi thử tiếp.
- [ ] Demo: dùng `./run demoip` (relay), dự phòng `./run phone` / `./run video`.

## 📚 Tài liệu tham khảo
- `docs/task/04-11-2026-cuu-webcam-relay-http.md` — dựng relay, các phép thử 04-11.
- usbipd-win (dorssel) — trạng thái export & `usbipd state`: https://github.com/dorssel/usbipd-win
- usbip status codes (`ST_DEV_BUSY` = "Device busy (exported)"): kernel `tools/usb/usbip`.
