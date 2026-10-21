# Cheat-sheet lệnh — giải thích từng lệnh

> Mỗi lệnh ghi rõ: **làm gì** → **kỳ vọng thấy gì** → **khi nào dùng**.
> Chạy trong **terminal WSL (Ubuntu)**, trừ khi ghi "(Windows)".

---

## 0a. Chạy ở ĐÂU? — mở đúng terminal trước đã

`run` là **script Linux (bash)**, không phải chương trình Windows:

- ❌ **Đừng double-click** file `run` trong Explorer (Windows sẽ hỏi "mở bằng app nào" — đóng hộp thoại đó).
- ❌ **Đừng mở bằng VS Code/IDE** như một tài liệu.
- ✅ Phải **gõ trong terminal WSL (Ubuntu)**.

### 3 cách mở đúng terminal

| Cách | Làm thế nào |
|---|---|
| **1. App Ubuntu** | Bấm Start → gõ `Ubuntu` → mở app → cửa sổ đen hiện ra |
| **2. Windows Terminal** | Mở Windows Terminal → bấm mũi tên cạnh dấu `+` → chọn **Ubuntu** |
| **3. VS Code** (nếu đang dùng) | Mở repo → menu **Terminal → New Terminal** → ở ô chọn shell (bên phải dấu `+`) chọn **Ubuntu (WSL)**, KHÔNG chọn PowerShell |

### Nhìn prompt để biết đã đúng chưa

| Đúng ✅ | Sai ❌ |
|---|---|
| `msi@NGUYEN-ANH-BINH:/mnt/d/DOAN-NAB$` | `PS D:\DOAN-NAB>` ← đây là PowerShell (Windows), `./run` sẽ không chạy |
| có dòng chữ `(samurai)` sau khi `./run` tự bật môi trường | `C:\Users\MSI>` ← cmd của Windows |

### Đứng ở đâu để gõ

```bash
cd /mnt/d/DOAN-NAB     # đứng trong thư mục repo (nơi có file 'run')
./run help             # rồi mới gõ ./run ...
```

### Cách khỏi gõ gì cả: double-click trên Windows

File **`start-demo.cmd`** trong `D:\DOAN-NAB` — double-click là nó tự mở WSL, vào repo, chạy demo:

| Double-click | Tác dụng |
|---|---|
| `start-demo.cmd` | chạy `./run demo` (demo webcam) |
| `start-demo.cmd test` (chuột phải → Edit rồi sửa, hoặc gõ trong cmd) | chạy `./run test` |

> Nếu double-click `start-demo.cmd` mà cửa sổ loé lên rồi tắt: mở PowerShell, chạy
> `D:\DOAN-NAB\start-demo.cmd` để thấy thông báo lỗi (script có `pause` khi lỗi).

---

## 0b. Gõ tắt bằng `./run` (khuyến nghị)

Trong thư mục repo, gõ **`./run <lệnh>`** — script tự bật môi trường conda, không cần
`source ... && conda activate` nữa:

| Lệnh | Tác dụng |
|---|---|
| `./run demo` | Demo webcam mượt + ghi `data/webcam_smooth.mp4` + CSV + JSON |
| `./run demo5` | Demo 5 khung rồi tự thoát (kiểm môi trường ~20 giây) |
| `./run view` | Chỉ mở cửa sổ xem, không ghi file |
| `./run video [file]` | Demo trên video file (mặc định `data/_gui_test.mp4`) |
| `./run fast` | Demo bản nhanh (image_size 256 + reanchor 3) |
| `./run check 0` | Kiểm nguồn camera 5 giây (0 = webcam) |
| `./run phone` | Quét LAN tìm URL camera điện thoại |
| `./run cam` | Xem trạng thái webcam + **BUSID hiện tại** (BUSID đổi sau mỗi lần khởi động lại!) |
| `./run cam attach` | **Tự dò BUSID rồi gắn webcam vào WSL** (không cần Admin) |
| `./run test` | Test nhanh (~10 giây, 140+ test) |
| `./run testall` | Toàn bộ test (~2 phút, cần checkpoint) |
| `./run lint` | `ruff check .` |
| `./run charts [csv…]` | Vẽ biểu đồ báo cáo (mặc định `data/smooth_metrics.csv`) |
| `./run summary` | In tóm tắt mọi file `*_summary.json` |
| `./run gpu` | In link Colab + cách đo GPU |
| `./run env` | In trạng thái: python, torch, opencv, webcam, GUI |
| `./run help` | Bảng lệnh |

**Gõ còn ngắn hơn nữa (alias):**
```bash
./run aliases --install     # thêm alias vào ~/.bashrc (chỉ 1 lần)
source ~/.bashrc            # hoặc mở terminal mới
```
Sau đó chỉ cần: `demo` · `demo5` · `view` · `camcheck` · `testfast` · `charts` · `camenv`

`./run aliases` (không có `--install`) chỉ **in** khối alias để bạn tự dán nếu muốn.

---

## 0c. Cách thủ công (khi không dùng `./run`) — chạy 2 dòng mỗi khi mở terminal

```bash
cd /mnt/d/DOAN-NAB
source ~/miniconda3/etc/profile.d/conda.sh && conda activate samurai
```
- **Làm gì:** vào thư mục dự án + bật môi trường Python đã cài sẵn (torch, opencv, sam2).
- **Kỳ vọng:** prompt có chữ `(samurai)` ở đầu.
- **Khi nào:** **luôn luôn**, trước mọi lệnh khác. Quên bước này sẽ gặp `python: command not found`
  hoặc `ModuleNotFoundError`.

---

## 1. Demo webcam (việc chính khi bảo vệ)

### 1.1. Demo đầy đủ — mượt + ghi video + ghi số liệu
```bash
bash scripts/demo_webcam.sh
```
- **Làm gì:** mở cửa sổ webcam ở **chế độ mượt** (`--smooth`, `--image-size 384`), đồng thời ghi
  `data/webcam_smooth.mp4`, `data/smooth_metrics.csv`, `data/smooth_summary.json`.
- **Kỳ vọng:** video mượt ~19 FPS, HUD 4 dòng; kéo chuột để chọn đối tượng.
- **Khi nào:** khi cần vừa demo vừa có video + số liệu cho báo cáo.

### 1.2. Chạy thử nhanh 5 khung (không cần ngồi chờ)
```bash
bash scripts/demo_webcam.sh --max-frames 5
```
- **Làm gì:** chỉ xử lý 5 khung rồi tự thoát (vẫn ghi file).
- **Khi nào:** kiểm tra môi trường/webcam còn hoạt động không (~20 giây).

### 1.3. Chỉ xem, không ghi file
```bash
python tools/run_live.py --source 0 --display --smooth --image-size 384
```
- **Làm gì:** mở cửa sổ demo, **không** tạo file.
- **Khi nào:** demo nhanh, hoặc đang thử chỉnh tham số.

### 1.4. Các tham số hay dùng (thêm vào cuối lệnh 1.1/1.3)

| Tham số | Tác dụng | Khi nào |
|---|---|---|
| `--image-size 384` | model thu nhỏ ảnh về 384 → **nhanh ~5–7×** so với 1024 | mặc định cho demo |
| `--image-size 256` | nhanh hơn nữa (~4 FPS) nhưng **kém chi tiết** vật nhỏ | khi cần mask cập nhật dày |
| `--reanchor-every 3` | reset bộ nhớ mỗi 3 khung → **độ trễ không tăng dần** | demo không có che khuất |
| `--record-fps 1` | ghi video 1 khung/giây → phát lại gần đúng tốc độ CPU thật | khi làm video minh chứng trung thực |
| `--max-trajectory 50` | giới hạn số điểm quỹ đạo | video dài |
| `--hide-trajectory` | **KHÔNG vẽ đường quỹ đạo (màu tím)** — chỉ còn mặt nạ + ô bao + HUD | khi thấy rối mắt |
| `--postprocess` | bật bước vá lỗ hổng mặt nạ của SAM 2 | khi cần mask mịn hơn (mặc định tắt) |

### 1.5. Phím trong cửa sổ (phải **click vào cửa sổ** trước)

| Phím | Tác dụng |
|---|---|
| Kéo chuột | vẽ ô chọn đối tượng; thả chuột → bắt đầu bám |
| `r` | dừng bám, quay về chế độ chọn lại trên khung hiện tại |
| `q` hoặc `ESC` | thoát sạch (ghi nốt số liệu + đóng video) |
| `Ctrl+C` (trong terminal) | thoát sạch tương đương `q` (vẫn ghi số liệu) |

---

## 2. Nguồn video khác webcam

### 2.1. Chạy trên một video file (demo lặp lại được)
```bash
python tools/run_live.py --source data/_gui_test.mp4 --display --smooth --image-size 384
```
- **Làm gì:** mở cửa sổ với video có sẵn thay vì webcam.
- **Khi nào:** phòng thi không có camera, hoặc cần demo giống hệt nhau nhiều lần.

### 2.2. Kiểm tra một nguồn trước khi chạy (5 giây, không cần model)
```bash
python tools/check_video_source.py --source 0 --num 10            # webcam
python tools/check_video_source.py --source "rtsp://IP:554/s" --num 10   # camera IP
python tools/check_video_source.py --source "http://IP:8080/video" --num 10  # điện thoại MJPEG
```
- **Kỳ vọng:** in loại nguồn, kích thước khung, FPS nguồn, số khung đọc được.
- **Khi nào:** **luôn kiểm trước** khi chạy pipeline với nguồn mới.

### 2.3. Camera điện thoại — tìm URL tự động
```bash
python tools/find_phone_camera.py                      # tự đoán subnet LAN (192.168.x)
python tools/find_phone_camera.py --subnet 192.168.1   # chỉ định subnet
```
- **Làm gì:** quét mạng LAN tìm app camera đang phát (MJPEG/HTTP).
- **Kỳ vọng:** `[OK] http://192.168.1.7:8080/video → 640x480` + lệnh pipeline gợi ý.
- **Khi nào:** không biết IP/URL của điện thoại.

### 2.4. Chế độ headless (không cửa sổ — dùng cho server/Colab)
```bash
python tools/run_live.py --source data/input.mp4 --bbox "200,200,120,120" \
  --record data/out.mp4 --metrics-csv data/m.csv --metrics-summary data/s.json
```
- **Làm gì:** chạy toàn bộ video, xuất mp4 + CSV + JSON, **không mở cửa sổ**.
- **Khi nào:** chạy trên Colab/máy không màn hình, hoặc cần xuất hàng loạt.
- **Lưu ý:** `--bbox` là ô chọn ở khung đầu `x,y,w,h`; bỏ đi thì lấy ô giữa khung.

---

## 3. Cấu hình bằng file YAML (không sửa code)

```bash
python tools/run_live.py --config configs/my.yaml
```
- **Làm gì:** đọc checkpoint, nguồn mặc định, bật/tắt ghi video, metrics, image_size… từ file YAML.
- **Ưu tiên:** `giá trị mặc định < file YAML < tham số dòng lệnh` (CLI thắng).
- **Khi nào:** đổi model/máy/tham số mà không muốn gõ lệnh dài.

Sửa file: `configs/default.yaml` (có chú thích từng dòng).

---

## 4. Kiểm tra chất lượng code (trước khi commit/nộp)

```bash
python -m pytest -m "not slow"     # làn NHANH ~10 giây: 140 test, KHÔNG cần checkpoint
python -m pytest                    # full ~2 phút: gồm test chạy model thật (cần checkpoint)
ruff check .                        # lint: import thừa, biến thừa, tên chưa định nghĩa
```
- **Khi nào:** sau mỗi lần sửa code; trước khi `git push` (CI chạy đúng 2 lệnh đầu).

---

## 5. Số liệu và biểu đồ cho báo cáo

```bash
python scripts/plot_metrics.py data/smooth_metrics.csv
python scripts/plot_metrics.py data/smooth_metrics.csv data/gpu_metrics2.csv
python scripts/plot_metrics.py data/gpu_metrics.csv --skip-warmup 1
```
- **Làm gì:** vẽ PNG (độ trễ theo khung, quỹ đạo tâm, khung mất dấu, so sánh nhiều lần đo)
  vào `data/charts/` + in bảng tóm tắt (mean/p95/FPS/tỷ lệ mất dấu).
- **`--skip-warmup 1`:** bỏ khung đầu (trên GPU khung đầu là "khởi động" ~3 giây → làm sai mean).
- **Khi nào:** mỗi khi có CSV mới cần đưa vào báo cáo.

---

## 6. Colab GPU (đo số liệu + làm video đẹp)

```
Mở: https://colab.research.google.com/github/BinhNguyen1912/DoAn-NAB/blob/main/notebooks/colab_gpu_evaluation.ipynb
→ Runtime → Change runtime type → T4 GPU → Save → chạy cell "⚡ CHẠY TẤT CẢ"
```
Hoặc trong Colab gõ 1 lệnh:
```python
!python scripts/colab_run_all.py
```
- **Làm gì:** tự clone repo, cài `sam2`+`loguru`, tải checkpoint (kiểm tra >100 MB), tạo/nhận video,
  chạy pipeline GPU (`image_size 512` + `reanchor 10`), in số liệu, đóng gói `data/colab_gpu_results.zip`.
- **Kỳ vọng:** `mean≈65 ms | FPS≈15,3` (Tesla T4).
- **Nhớ:** **tải file kết quả về máy** — Colab xoá sạch `/content` khi đóng phiên.

---

## 7. Webcam trong WSL (chỉ cần khi máy khởi động lại)

```powershell
usbipd list                        # (Windows) tìm "HD Webcam", ghi BUSID (VD 1-8)
usbipd attach --wsl --busid 1-8    # (Windows) gắn webcam vào WSL
```
```bash
ls /dev/video0                     # phải thấy mới dùng được webcam trong WSL
```
- **Khi nào:** sau mỗi lần khởi động lại WSL (`usbipd bind` chỉ cần làm 1 lần, `attach` cần mỗi phiên).
- **Trả camera lại Windows:** `usbipd detach --busid 1-8`.

---

## 8. Bảng tra nhanh "tôi muốn X → gõ lệnh nào"

| Tôi muốn… | Lệnh |
|---|---|
| Demo webcam mượt + ghi video/số liệu | `bash scripts/demo_webcam.sh` |
| Demo nhanh 5 khung để kiểm tra | `bash scripts/demo_webcam.sh --max-frames 5` |
| Chỉ xem, không ghi file | `python tools/run_live.py --source 0 --display --smooth --image-size 384` |
| Chạy trên video file | `python tools/run_live.py --source data/_gui_test.mp4 --display` |
| Kiểm nguồn camera có sống không | `python tools/check_video_source.py --source 0 --num 10` |
| Tìm camera điện thoại trong LAN | `python tools/find_phone_camera.py` |
| Chạy không màn hình, xuất mp4+CSV | `python tools/run_live.py --source data/in.mp4 --bbox "x,y,w,h" --record data/out.mp4 --metrics-csv data/m.csv --metrics-summary data/s.json` |
| Đổi model/tham số bằng file | sửa `configs/default.yaml` rồi `python tools/run_live.py --config configs/default.yaml` |
| Test nhanh sau khi sửa code | `python -m pytest -m "not slow"` |
| Kiểm lint | `ruff check .` |
| Vẽ biểu đồ báo cáo | `python scripts/plot_metrics.py data/smooth_metrics.csv` |
| Đo trên GPU | mở notebook Colab → cell "⚡ CHẠY TẤT CẢ" |
| Cấp lại webcam cho WSL | `usbipd attach --wsl --busid 1-8` (Windows) |

---

## 9. Lỗi thường gặp — 10 giây xử lý

| Triệu chứng | Nguyên nhân | Lệnh sửa |
|---|---|---|
| `python: command not found` | chưa bật môi trường | `source ~/miniconda3/etc/profile.d/conda.sh && conda activate samurai` |
| `ModuleNotFoundError: No module named 'sam2'` | chưa cài sam2 | `pip install -e samurai/sam2` |
| `ModuleNotFoundError: No module named 'loguru'` | thiếu phụ thuộc SAMURAI | `pip install loguru` |
| `Không mở được camera index 0` | WSL chưa thấy webcam / Windows đang giữ | Windows: `usbipd attach --wsl --busid 1-8`; đóng Teams/Camera app |
| Cửa sổ không hiện / process abort | thiếu 2 thư viện Qt | `sudo apt install -y libice6 libsm6` |
| HUD hiện ô `?` thay vì dấu tiếng Việt | không tìm được font | `export CAMAI_FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` |
| Lệnh dài bị `expected one argument` | copy-paste làm vỡ dòng | dùng `./run demo` thay vì gõ tay |
| `RuntimeError: Không mở được camera index 0` | webcam chưa `attach` vào WSL (thường sau khi khởi động lại) | (Windows, Admin) `usbipd attach --wsl --busid 1-8` → `./run check 0` |
| Demo không có webcam mà vẫn muốn thử | — | `./run video` (chạy trên video file) |
| `usbipd: error: Failed to attach ... Device busy (exported)` (lặp lại dù đã `--force`) | Cổng USB/IP trong kernel Linux kẹt ở trạng thái lỗi. Kiểm: `cat /sys/devices/platform/vhci_hcd.0/status` → các port `sta 004` | Reset hẳn WSL: (PowerShell) `wsl --shutdown` → mở Ubuntu → `usbipd attach --wsl --busid 1-8` |
| Muốn tránh lỗi trên lần sau | Tắt WSL khi camera còn attach sẽ để lại trạng thái kẹt | Trước khi tắt máy/`wsl --shutdown`: (PowerShell) `usbipd detach --busid 1-8` |
| Mất số liệu khi tắt máy | tắt WSL đột ngột | bấm `q` trong cửa sổ trước khi `wsl --shutdown` |
