# Ngày 21-11-2026 — `./run relay start` không có khung hình: chẩn đoán sai 1 lần, sửa bằng "thử MỞ camera"

## 🎯 Mục tiêu
Người dùng chạy `./run relay start` và nhận *"relay sống nhưng KHÔNG có khung hình sau 20s ⇒ camera đang bị
app Windows giữ"*, rồi hỏi "ủa là sao". Mục tiêu: tìm nguyên nhân **thật**, làm relay chạy lại, và sửa để
thông báo không chỉ sai đường nữa.

## 📥 Input
- Log người dùng (05:47): `[LOI] relay sống nhưng KHÔNG có khung hình sau 20s`.
- Người dùng nói: *"HD cam, tôi vào camera bình thường mà, đã tắt rồi"* (đã đóng app Camera).
- Máy: MSI, camera trong máy `HD Webcam` (VID_5986) + webcam rời `PC Camera` (VID_058F) từng cắm.

## 🔨 Công việc đã thực hiện (theo thứ tự, gồm cả một lần SAI)
1. `curl /info` → `{"w":0,"h":0,"fps":0.0,"serving":true}`; `/snapshot.jpg` không trả gì ⇒ relay sống,
   camera không ra khung.
2. `data/_relay.log`: `cv::VideoCapture::open VIDEOIO(DSHOW): … can't be used to capture by index`
   ⇒ **lúc 05:47 relay KHÔNG mở được camera** (đúng ca "app giữ cam": app Camera đang mở).
3. **SAI (đã bác bỏ):** tôi kết luận "Windows không thấy camera nào đang cắm" từ
   `Get-PnpDevice -PresentOnly -Class Camera` = rỗng. Lúc đó thiết bị đúng là `Present=False`, nhưng
   **không đủ** để nói "không có camera": sau đó cùng truy vấn trả `OK Camera HD Webcam`, và
   `pnputil /scan-devices` từ WSL thì `Access is denied` (cần admin) nên không tự khắc phục được.
4. **Đo quyết định:** chạy `scripts/win_cam_probe.py` trên Windows (bằng đúng
   `%LOCALAPPDATA%\wincam-venv\Scripts\python.exe`) thử mở index 0..2 với 3 backend:
   `ANY idx=0 open=True read=True 640x480`, `DSHOW idx=0 open=True read=True`,
   `MSMF idx=0 open=True read=True`, `idx=2 open=False` ⇒ **camera mở được**, thiết bị không hỏng.
   ⇒ thủ phạm còn lại: **tiến trình relay cũ giữ thiết bị với handle đã chết** (server vẫn `serving`,
   `w=0`).
5. `./run relay stop && ./run relay start` ⇒ **`{"w":640,"h":480,"fps":20.0,"serving":true}`**,
   `/snapshot.jpg` = 22 166 byte trong **2,5 ms**, ảnh 480×640 độ sáng tb 123,6 (không đen).

## 📤 Output / Kết quả
- **Relay chạy lại bình thường** (640×480 @ 20 FPS, snapshot 22 KB).
- **Công cụ mới** `scripts/win_cam_probe.py` (chạy trên Windows, in `OK idx=0 640x480` | `FAIL`):
  thử **đúng việc relay sẽ làm** thay vì suy đoán từ PnP.
- **`scripts/cam_relay.sh`**: thay `cam_present()` (PnP) bằng `cam_probe()` dùng script trên; ba chỗ báo
  lỗi (`status`, `start` khi server đã chạy, `start` sau 20 s) nay phân biệt được **ba** trạng thái:
  - camera **mở được** ⇒ *"tiến trình relay đang cũ/kẹt ⇒ `./run relay stop && ./run relay start`"*;
  - camera **không mở được** ⇒ *"app khác đang giữ cam (Camera/Zalo/Discord/Chrome) hoặc thiết bị bị tắt"*;
  - không gọi được python Windows ⇒ giữ thông báo cũ (app giữ cam / firewall).
- Kiểm sau khi sửa: `./run relay status` in *"NHƯNG Windows MỞ ĐƯỢC camera (idx=0 640x480) ⇒ tiến trình
  relay đang cũ/kẹt"* — đúng ca đang gặp, không còn chỉ người dùng đi cắm lại dây.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Một triệu chứng (`serving=true`, `w=0`) không phân biệt được 3 nguyên nhân**: (a) app khác giữ cam,
  (b) tiến trình relay cũ giữ handle chết, (c) không có thiết bị. Bản vá đầu tiên của tôi chỉ kiểm (c)
  bằng PnP ⇒ **kết luận sai, làm người dùng mất thời gian cắm lại dây**. Cách đúng: kiểm **hành vi**
  (mở được camera hay không), không kiểm **danh sách thiết bị**.
- Bài học chung cho repo: khi thông báo lỗi nêu một **giả thuyết**, phải kèm bước kiểm chứng giả thuyết đó
  — hoặc nói rõ "có thể do X hoặc Y". Đã áp dụng: mọi nhánh nay in cả kết quả probe.
- `pnputil /scan-devices` từ WSL **không chạy được** (Access denied) — đừng đưa vào script như bước tự sửa.

## 📌 Việc cần làm tiếp
- [ ] Người dùng chạy lại `./run demoip --image-size 192` với **vật khác tông màu da** (xem log
      `21-11-2026-demo-webcam-lan-1-nhan-lai-sai-vao-mat.md`).
- [ ] Nếu gặp lại `w=0`: chạy `./run relay status` — nó nói ngay nên `stop && start` hay nên đóng app.
- [ ] Ticket #11: vẫn cần clip chai đen + ≥ 3 ca sai đa dạng để chốt `ncc_min` (`max_bad` nay 0,545).

## 📚 Tài liệu tham khảo
- `scripts/win_cam_probe.py` (mới), `scripts/cam_relay.sh` (`cam_probe()`), `scripts/win_camera_relay.py:65`
  (`cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)`), `data/_relay.log`
- `AGENTS.md` §6 (relay `/snapshot.jpg` là đường demo web; không dùng `/video` cho demo web)
