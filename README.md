# Camera AI — Bám bắt đối tượng theo thời gian thực (SAMURAI streaming)

Hệ thống nhận diện, phân đoạn và bám bắt đối tượng trong video real-time, xây dựng trên
**SAM 2.1 (config SAMURAI)** ở chế độ streaming từng frame — khớp 7 yêu cầu của đề cương
"Xây dựng hệ thống Camera AI bám bắt đối tượng theo thời gian thực".

> ⚠️ **Trung thực về hiệu năng (ADR-0002):** demo live chạy trên laptop CPU (không có GPU
> NVIDIA) đạt **~0.2–0.3 FPS** (~3–5 giây/frame) — là "slideshow có chủ đích", mọi số liệu
> được đo và in/GHI RA FILE trung thực. Video minh hoạ tốc độ GPU sẽ chạy headless trên Colab.

## Kiến trúc (5 module)

```
VideoSource ──► TrackerEngine ──► Visualizer (HUD)
(webcam/RTSP/     (SAM 2.1 tiny,        │
 file)            streaming per-frame)  ├─► PromptSelector (kéo chuột chọn/r chọn lại)
                                        ├─► MetricsLogger (CSV + summary JSON)
                                        └─► cửa sổ OpenCV / video out mp4
```

- `src/video_source.py` — 1 interface cho 4 nguồn: webcam index, RTSP, video file, **thư mục ảnh** (frames).
- `src/tracker_engine.py` — seam trung tâm: `start(bbox)` → `process(frame)` mỗi frame →
  mask + bbox + điểm tin cậy + ms. Đóng gói SAMURAI nguyên bản (Kalman + memory bank).
- `src/prompt_selector.py` — máy trạng thái kéo-thả chọn ô; phím **r** chọn lại đối tượng.
- `src/visualizer.py` — HUD: mask alpha + ô bao + quỹ đạo (deque giới hạn) + 3 dòng
  FPS/độ trễ/**điểm tin cậy** (nhãn tiếng Việt qua PIL font TTF) + banner đỏ
  `MẤT DẤU — bấm r chọn lại` khi mask rỗng + ghi mp4.
- `src/metrics_logger.py` — hàm thuần: CSV từng frame + summary mean/p95/tỷ lệ mất dấu.
- Cấu hình YAML: `configs/default.yaml` (checkpoint, nguồn, ghi mp4, metrics).

## 0. Gõ tắt — `./run`

```bash
./run demo      # demo webcam mượt + ghi video/số liệu (tự bật môi trường conda)
./run test      # test nhanh ~10 giây
./run help      # xem tất cả lệnh tắt
./run aliases --install   # (tuỳ chọn) tạo alias ngắn hơn: demo, testfast, charts…
```
Danh sách đầy đủ + giải thích từng lệnh: `docs/cheatsheet-lenh.md`.

## 0b. Chưa biết thuật ngữ? Đọc file này trước

**`docs/cheatsheet-lenh.md`** — mọi lệnh cần dùng, mỗi lệnh có giải thích "làm gì → kỳ vọng → khi nào dùng".
**`docs/giai-thich-do-an.md`** — giải thích toàn bộ đồ án bằng ngôn ngữ đời thường: từ điển thuật ngữ
(AI, mô hình, mask, FPS, GPU…), hệ thống hoạt động ra sao, Colab là gì và vì sao cần, thiết bị của bạn
mạnh/yếu chỗ nào, bảng "bị gì → cần gì → đã làm gì", và 8 câu trả lời mẫu cho hội đồng.

## 1. Cài đặt từ clone mới (tái tạo được)

```bash
# 0) python 3.10+ + conda
conda create -n samurai python=3.10 -y
conda activate samurai

# 1) dependencies của repo
pip install -r requirements.txt          # numpy, opencv, pytest, pyyaml, pillow
pip install torch torchvision            # CPU: mặc định; Colab: đã có sẵn CUDA

# 2) clone SAMURAI vào thư mục repo (không vendor trong Git)
git clone https://github.com/yangchris11/samurai.git samurai

# 3) config SAM 2 của SAMURAI — nằm sẵn trong package, không cần copy vào repo:
#    `samurai/sam2/sam2/configs/` (hydra tìm theo package; giữ nguyên value
#    `model_cfg` trong configs/default.yaml nếu không rõ về hydra search path)

# 4) tải checkpoint SAM 2.1 tiny
mkdir -p samurai/sam2/checkpoints
cd samurai/sam2/checkpoints
wget https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt
cd ../../..

# 5) cài package sam2 của SAMURAI + phụ thuộc riêng của SAMURAI
pip install -e samurai/sam2
pip install loguru                 # SAMURAI import loguru trong sam2/modeling/sam2_base.py

# 6) chạy test (không cần camera; test "slow" cần checkpoint)
python -m pytest tests/ -m "not slow"
python -m pytest tests/                # full suite
```

> SAMURAI dùng SAM 2 làm backbone — tham chiếu config: `configs/samurai/sam2.1_hiera_t.yaml`
> (đây là yaml gốc SAMURAI, giữ nguyên; đổi checkpoint/tham số chỉ nằm trong
> `configs/default.yaml` của repo này).

## 2. Chạy

```bash
conda activate samurai
```

### Live + chọn đối tượng bằng chuột (máy có camera + màn hình)

```bash
python tools/run_live.py --source 0 --display        # webcam tích hợp
python tools/run_live.py --source 1 --display        # camera USB rời
python tools/run_live.py --source rtsp://IP:554/stream --display   # camera điện thoại/IP
```

Kéo chuột vẽ ô quanh đối tượng → thả chuột → bám; **r** chọn lại trên frame hiện tại,
**q/ESC** thoát.

### Camera điện thoại (iPhone / Android) — nguồn mạng

Repo hỗ trợ **2 dạng URL** (chỉ cần app hiện đúng 1 trong 2):

| Dạng | Ví dụ | Adapter |
|---|---|---|
| MJPEG qua HTTP | `http://192.168.1.25:8080/video` | `HttpVideoSource` |
| RTSP | `rtsp://192.168.1.25:554/stream` | `RtspVideoSource` |

**Không biết IP/URL của điện thoại?** Quét mạng LAN để tìm:
```bash
python tools/find_phone_camera.py                       # tự đoán subnet của máy
python tools/find_phone_camera.py --subnet 192.168.1    # hoặc chỉ định
# → [OK] http://192.168.1.7:8080/video → 640x480
# → python tools/run_live.py --source "http://192.168.1.7:8080/video" --display
```

**Kiểm nguồn trước khi chạy pipeline** (nhanh, không cần model):
```bash
python tools/check_video_source.py --source "http://192.168.1.25:8080/video" --num 10
# → [nguồn] '...' → HttpVideoSource | kích thước (W,H)=(640, 360) | FPS nguồn=25.0
```
Rồi:
```bash
python tools/run_live.py --source "http://192.168.1.25:8080/video" --display
```

Checklist khi không kết nối được:
1. **IP thật** hiện trên app (chuỗi `192.168.x.x` chỉ là ví dụ — dùng đúng IP như `192.168.1.25`).
2. Điện thoại và máy tính **cùng một mạng Wi-Fi**; app đã bấm **Start server**.
3. Đúng **đường dẫn stream**: nhiều app MJPEG dùng `/video` (có app dùng `/videofeed`).
4. App chỉ phát **RTSP** → dùng `rtsp://…` thay vì `http://…`.
5. WSL2 ra được mạng LAN, nhưng nếu vẫn lỗi: thử từ Windows bằng env Windows (xem mục cài đặt).

#### Riêng iPhone — 3 điều hay làm sai

1. **Cấp quyền "Local Network"** (iOS 14+): app camera server cần quyền này để máy tính truy cập
   được. Vào **Settings → Privacy & Security → Local Network** → bật cho app. Nếu lúc mở app có
   hộp thoại hỏi → bấm **Allow** (bấm Don't Allow là mất kết nối, phải vào Settings bật lại).
2. **Giữ app ở foreground + khoá tự động TẮT**: iOS dừng server khi app xuống nền hoặc màn hình tắt.
   Đặt **Settings → Display & Brightness → Auto-Lock = Never** trong lúc demo, và không chuyển app.
3. **Đúng loại app**: app phải là **server** (hiện URL) chứ không phải app *xem* camera. Dấu hiệu đúng:
   màn hình app có dòng `http://192.168.x.x:PORT/...` hoặc `rtsp://...`. App chỉ tạo "virtual webcam"
   cho Windows (DroidCam/Iriun/EpocCam) **không dùng được** với repo này.

Nếu app hiện URL mà dạng đường dẫn lạ, quét rộng hơn:
```bash
python tools/find_phone_camera.py --ports 8080,8081,8082,8088,8090,4747,5000 \
  --paths /video,/videofeed,/mjpegfeed,/stream
```

### Headless — 1 lệnh trên video file (server/Colab, không màn hình)

```bash
python tools/run_live.py \
  --source data/video.mp4 \
  --bbox "120,80,60,60" \
  --record data/ket_qua.mp4 \
  --metrics-csv data/metrics.csv \
  --metrics-summary data/summary.json
```

→ Xuất: `data/ket_qua.mp4` (mask + ô bao + quỹ đạo + HUD), `data/metrics.csv` (tâm, ms,
score, cờ mất dấu từng frame — vẽ quỹ đạo cho báo cáo), `data/summary.json`
(mean/p95 latency, FPS hiệu dụng, tỷ lệ mất dấu).

### Đổi model/tham số qua file YAML (không sửa code)

Sửa `configs/default.yaml` (hoặc tạo file riêng):

```yaml
checkpoint: samurai/sam2/checkpoints/sam2.1_hiera_small.pt   # đổi checkpoint
source: data/video_demo.mp4                                  # nguồn mặc định
record_enabled: true                                         # bật ghi khi chạy lệnh
```

```bash
python tools/run_live.py --config configs/my.yaml            # CLI flag vẫn đè được YAML
```

## 3. Colab GPU — video minh hoạ tốc độ thật (ADR-0002)

Máy laptop CPU không đủ để demo FPS cao; theo **ADR-0002** phần "video minh hoạ 15–25 FPS"
chạy offline trên **Colab GPU** bằng chính lệnh headless trên:

**Chạy lại khi nào?** Số liệu/video GPU là **sản phẩm tĩnh** — tạo 1 lần, dùng mãi.
Chỉ chạy lại Colab khi **code đổi** (`src/*.py` ảnh hưởng tracking/HUD/metrics) hoặc **đổi tham số**
(video, bbox, image_size). Mỗi lần chạy, `scripts/colab_run_all.py` ghi `data/gpu_run_info.json`
chứa `git_rev` + tham số → so với `git log -1` là biết số liệu còn đúng hay đã cũ.

**Notebook có sẵn:** `notebooks/colab_gpu_evaluation.ipynb` — mở trên Colab (Runtime → T4 GPU) rồi chạy
lần lượt; hướng dẫn chi tiết + thời gian từng bước: `docs/colab-gpu.md`.

1. Đẩy repo (kèm `samurai/` clone + checkpoint) lên Drive/clone trực tiếp trong notebook.
2. Trên Colab: `!pip install -r requirements.txt && pip install -e samurai/sam2`
   (torch CUDA đã có sẵn).
3. Chạy `!python tools/run_live.py --source data/video.mp4 --bbox "..." --device cuda \
   --record data/colab_gpu.mp4 --metrics-csv data/colab_metrics.csv --metrics-summary data/colab_summary.json`
4. Số liệu trong `summary.json` **là số đo GPU thật** — dùng cho mục "Đánh giá hiệu năng"
   của báo cáo, đặt cạnh số liệu CPU laptop để đối chiếu trung thực.

## 4. Đóng góp của sinh viên vs thành phần có sẵn

Bảng chi tiết phần nào tự viết, phần nào dùng có sẵn (SAM 2/SAMURAI theo ADR-0001) và bằng chứng
(commit/file/số liệu): **`docs/team-contribution.md`** — dùng khi bảo vệ.

## 5. Cấu trúc repo

```
src/            mã nguồn chính (video_source, tracker_engine, prompt_selector,
                visualizer, metrics_logger, live_pipeline, config)
tools/          CLI chạy (run_live.py), benchmark, demo scripts
configs/        default.yaml + config SAMURAI
tests/          pytest (fixture synthetic, không commit dữ liệu nặng)
docs/           đề cương, ADR, log công việc theo ngày (docs/task/)
data/           video demo + bbox frame 0 (KHÔNG commit file nặng)
```

## 6. Kiểm tra chất lượng (guardrail)

```bash
python -m pytest -m "not slow"     # làn nhanh ~10s (UI/logic/config) — bỏ test cần checkpoint
ruff check .                       # lint: import/biến thừa, tên chưa định nghĩa (config: ruff.toml)
python -m pytest                   # full suite ~2 phút (cần checkpoint SAM 2)
```

CI (`.github/workflows/checks.yml`) chạy `ruff` + làn nhanh trên mọi push/PR vào `main`.
`pytest.ini` đặt `--timeout=120` để test treo không treo cả phiên.
Chuẩn code chi tiết: `CODING_STANDARDS.md`. Quy ước làm việc: `AGENTS.md`.

### Sự cố thường gặp khi chạy GUI

| Hiện tượng | Cách xử lý |
|---|---|
| `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` rồi `Aborted` | Thiếu thư viện Qt (WSL/Linux): `sudo apt-get install -y libice6 libsm6` |
| 5 dòng `QFontDatabase: Cannot find font directory …cv2/qt/fonts` mỗi lần mở cửa sổ | Bản OpenCV Qt không kèm font — tạo thư mục + copy 1 TTF: xem lệnh dưới |
| `Không mở được camera index 0` | Windows: Settings → Privacy → Camera (bật); đóng Teams/Zoom; thử `--source 1`. WSL không thấy webcam → dùng RTSP/HTTP từ điện thoại |
| HUD hiện ô `?` thay vì dấu tiếng Việt | `export CAMAI_FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` (Linux) hoặc `C:\\Windows\\Fonts\\segoeui.ttf` (Windows) |
| `UserWarning: cannot import name '_C' from 'sam2'` | Bình thường — SAM 2 không build extension C, chỉ mất post-processing `fill_holes` (không ảnh hưởng kết quả demo) |
| **Chọn ô vào vùng nền mà hệ thống vẫn bám** | Bản chất *promptable segmentation*: SAM 2 luôn trả mask cho bất kỳ ô nào được vẽ (đo thật: ô nền nhỏ → mask 1.2% khung, score 17.8; đối tượng thật → 1.6%, score 22.6). Dấu hiệu để nhận biết: **dòng thứ 3 HUD `Điểm tin cậy:`** thấp hơn hẳn, mask/đường quỹ đạo không khớp vật thể, hoặc console in `[WARN] mask phủ …% khung` khi ô quá lớn. Cách xử lý: bấm **r** chọn lại |

```bash
# Dứt cảnh báo QFontDatabase (Linux/WSL) — copy 1 TTF vào thư mục font OpenCV tự tìm
FONTDIR="$(python -c 'import cv2, os; print(os.path.join(os.path.dirname(cv2.__file__), "qt", "fonts"))')"
mkdir -p "$FONTDIR" && cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf "$FONTDIR/"
```

## 7. Đánh giá hiệu năng (đang có)

| Môi trường | Cấu hình | mean ms/frame | FPS hiệu dụng | Nguồn số liệu |
|---|---|---|---|---|
| Laptop CPU (i5, không GPU rời) | 720p, image_size 1024 | 5 047 | **0,20** | `data/gui_summary.json` |
| Laptop CPU + tối ưu | 720p, image_size 384, `--smooth` | 445 | **2,25** | `data/smooth_summary.json` |
| **Colab GPU Tesla T4** | 720p, image_size 1024 | 380 (bỏ frame warmup: **337**) | **2,63** (steady **2,97**) | `data/gpu_summary.json` |
| **Colab GPU Tesla T4 + tối ưu** | 720p, image_size 512, `--reanchor-every 10` | **65** | **15,28** | `data/gpu_summary2.json` |

→ GPU (T4) nhanh hơn CPU laptop **~13×** ở cùng độ phân giải, và **~78×** khi cả hai đã tối ưu.
Lưu ý trung thực: T4 là kiến trúc **Turing (SM 7.5)** nên **không bật được FlashAttention**
(SAM 2 cảnh báo `Flash Attention is disabled as it requires a GPU with Ampere (8.0)`) → số FPS trên
T4 là **cận dưới**; GPU Ampere/Ada (A100, RTX 30/40) sẽ nhanh hơn nữa.

Chi tiết từng phiên chạy: `docs/task/`; số liệu mẫu:
`[metrics] mean=3441 ms | p95=4123 ms | FPS hiệu dụng ≈ 0.29 | mất dấu 0/5`.

### Chọn `--image-size` nào? (đo trên laptop này, cùng một nguồn 720p)

Nhịp cập nhật **khung đỏ + mặt nạ** = 1000 / ms mỗi lần suy luận (video vẫn mượt 19 FPS nhờ `--smooth`).

| `--image-size` | ms/lần | Khung đỏ cập nhật | Chất lượng biên | Dùng khi |
|---|---|---|---|---|
| 1024 (mặc định) | 3 700–5 000 | 0,2–0,27 lần/s | tốt nhất | xuất ảnh cho báo cáo (headless, không cần realtime) |
| **512** | **572** | **1,75 lần/s** | tốt | khi đứng yên, cần biên nét |
| **384** | **316** | **3,2 lần/s** | khá | demo hiện tại (cân bằng) |
| **320** | **236** | **4,2 lần/s** | trung bình | ⭐ demo CPU: khung đỏ phản hồi tốt hơn |
| **256** | **161** | **6,2 lần/s** | giảm rõ (IoU 0,79 khi có che) | cần khung đỏ nhanh nhất trên CPU |
| GPU T4 (512 + reanchor) | 65 | 15,4 lần/s | tốt | video minh hoạ + số liệu GPU |

**Ngưỡng "đủ" theo cảm nhận:**
- Khung đỏ **< 2 lần/s** → giật, khó theo dõi
- **5–10 lần/s** → dùng được (mắt thấy cập nhật đều)
- **≥ 10 lần/s** → mượt (chỉ đạt trên GPU với cấu hình này)
- Video hiển thị **≥ 15 FPS** → mượt (chế độ `--smooth` đang cho ~19 FPS)

### Chế độ MƯỢT cho demo webcam (`--smooth`) — đo thật

Vấn đề: nếu đọc → suy luận → hiển thị tuần tự thì cửa sổ chỉ cập nhật bằng tốc độ model
(0.3–2 FPS) → "di chuyển mãi mới nhích". Chế độ `--smooth` **tách 3 luồng**:

1. **capture** — luôn giữ frame mới nhất từ webcam (không xếp hàng frame cũ);
2. **inference** — lấy frame mới nhất đem `engine.start/process`, xong thì ghi kết quả + mốc thời gian;
3. **display** (main thread — OpenCV chỉ cho 1 luồng dùng GUI) — vẽ frame mới nhất ở ~30 FPS kèm
   overlay của lần suy luận gần nhất, HUD ghi rõ **`Overlay: N ms trước`**.

**Đo trên webcam thật (image_size 384, 8,3 giây):**

| Chỉ số | Kết quả |
|---|---|
| Frame **hiển thị** | 159 frame → **19,0 FPS** (video mượt) |
| Lần **suy luận** | 16 lần → **1,92 FPS** |
| Tuổi overlay trung bình | **~522 ms** (mask cập nhật 2 lần/giây) |

→ Video mượt như camera thường; mask/ô bao/quỹ đạo cập nhật 2 lần/giây và **tuổi overlay luôn
hiện trên HUD** (trung thực theo ADR-0002 — không giả vờ 19 FPS là tốc độ model).

**Cách chạy ngắn nhất** (tránh lỗi copy-paste làm vỡ dòng lệnh):
```bash
bash scripts/demo_webcam.sh          # demo mượt + xuất mp4/CSV/JSON vào data/
bash scripts/demo_webcam.sh --max-frames 5    # chạy thử 5 frame
```

Hoặc gõ đầy đủ (một dòng, đừng để xuống hàng giữa tham số):
```bash
python tools/run_live.py --source 0 --display --smooth --image-size 320
```

Muốn **ẩn đường quỹ đạo** (màu tím) cho gọn mắt: thêm `--hide-trajectory`
(hoặc `show_trajectory: false` trong `configs/default.yaml`).
Ghi video minh chứng (ghi đúng luồng hiển thị 19 FPS):
```bash
python tools/run_live.py --source 0 --display --smooth --image-size 384 --record data/webcam_smooth.mp4 --metrics-csv data/smooth_metrics.csv --metrics-summary data/smooth_summary.json
```

### Thí nghiệm che khuất một phần (bằng chứng cho tên đề tài)

```bash
python scripts/experiment_occlusion.py --image-size 320   # → data/charts/occlusion_iou_320.png
```
Đo IoU theo từng khung khi đối tượng bị che **50%** và **100%** (khung 12–17), rồi hiện lại:
-che 50%: IoU 0,97 → **0,53** (không mất dấu) → **0,967 ngay khung đầu sau che**
-che 100%: IoU 0,98 → 0,00 (mất dấu 6/6) → **0,984 ngay khung đầu sau che**, mất dấu 0/12
Chi tiết: `docs/giai-thich-do-an.md` mục 13.

### Biểu đồ cho báo cáo (từ CSV của MetricsLogger)

```bash
python scripts/plot_metrics.py data/smooth_metrics.csv            # 3 hình: latency / quỹ đạo / mất dấu
python scripts/plot_metrics.py data/smooth_metrics.csv data/gpu_metrics.csv   # + hình so sánh CPU vs GPU
# → data/charts/*.png  + bảng tóm tắt (mean/p95/min/max ms, FPS hiệu dụng, tỷ lệ mất dấu)
```
`so_sanh_latency.png` dùng thang log để thấy rõ chênh lệch CPU (~500–5000 ms) vs GPU (~70–350 ms).
Frame 0 trên GPU gồm **warmup CUDA (~3 s)** nên làm lệch mean — dùng `--skip-warmup 1` để lấy số ổn định:
```bash
python scripts/plot_metrics.py data/gpu_metrics.csv --skip-warmup 1
```

### Tối ưu tốc độ trên CPU (đo thật trên laptop này, 18-10-2026)

Độ trễ **tăng dần** khi chạy lâu vì chi phí propagate của SAMURAI tỉ lệ với số frame lưu trong
`output_dict["non_cond_frame_outputs"]` (đo: 3.4 s khi lưu 1 frame → 8.3 s khi lưu 8 frame).

| Cấu hình | mean ms/frame | FPS hiệu dụng | Ghi chú |
|---|---|---|---|
| Mặc định (`image_size=1024`, memory đầy đủ) | 5346 (12 frame), tăng tới ~6.3 s | 0.19 | chậm dần rồi bão hoà |
| `--reanchor-every 3` | 3662 | 0.27 | nhanh ~1.5× (12 frame), ~2.2× ổn định |
| `--image-size 512` | 733 | 1.36 | nhanh ~5–7× |
| `--image-size 512 --reanchor-every 3` | 558 | 1.79 | ⭐ cấu hình demo khuyến nghị |
| `--image-size 384` (+ reanchor 3) | 435 | **2.30** | mượt hơn nữa, chất lượng giảm nhẹ |
| `--image-size 256` (+ reanchor 3) | 239 | 4.19 | nhanh nhất, chất lượng giảm rõ (IoU 0.79) |
| Giảm camera 320×240 | −10% | | SAM 2 tự resize đầu vào → gần như không lợi |
| 8 thread thay 4 | −8% | | model-bound |
| Cắt bớt `non_cond_frame_outputs` | ❌ `KeyError` | | SAM 2 tham chiếu frame cũ → không khả thi |

Xác nhận trên **webcam thật** (5 frame): mặc định `3080 ms` (0.32 FPS) → `--image-size 512
--reanchor-every 3` = **`569 ms` (1.76 FPS)**, tức **nhanh 5,4×**.

Lệnh demo khuyến nghị cho webcam realtime:
```bash
python tools/run_live.py --source 0 --display --image-size 512 --reanchor-every 3
```

⚖️ **Đánh đổi của `--image-size`:** ảnh bị downsample mạnh hơn nên **đối tượng nhỏ** kém chính xác;
384/256 còn làm IoU giảm rõ (fixture có che khuất: 384 → 0.861; 256 → 0.791). Với ảnh thật cần đo lại.

⚠️ **`--reanchor-every` không ổn định khi có che khuất:** reset state đúng lúc đối tượng bị che sẽ
"chọn lại" vào nền → bám sai (đo được IoU 0.509 ở image_size 512, che 3 frame). Khi demo có che khuất:
**bỏ** `--reanchor-every`, chỉ dùng `--image-size`.

🔧 **Bộ đệm camera:** driver V4L2 mặc định giữ **4 frame**; sau mỗi lần suy luận 0.5–3 s, hàng đợi toàn
frame cũ nên người dùng thấy "di chuyển rồi lâu mới hiện". `CameraVideoSource` ép
`CAP_PROP_BUFFERSIZE = 1` → luôn đọc frame mới nhất (chỉ trễ đúng 1 frame).

**Đánh đổi của `--reanchor-every`** (reset state + chọn lại bbox hiện tại): đo trên fixture 20 frame
có che khuất 5 frame — baseline IoU sau che **0.981**, mất dấu 5/19; re-anchor 3: IoU **0.969**,
mất dấu **0/19**. Tức là nhanh hơn và trên fixture còn ít mất dấu hơn, nhưng **mất bộ nhớ dài hạn**
(che khuất dài hơn N frame sẽ kém hơn) → mặc định **tắt**, bật khi cần demo mượt.

Nút cổ chai thật là suy luận model trên CPU: thu nhận frame chỉ 32 ms, xử lý 3000–6000 ms.
Muốn 15–25 FPS thật → chạy headless trên **Colab GPU** (mục 3).

## 8. Kiến thức nền

- **SAMURAI**: https://github.com/yangchris11/samurai (motion-aware memory + Kalman)
- **SAM 2**: https://github.com/facebookresearch/sam2 (streaming memory propagation)
- ADR: `docs/adr/0001` (chọn backbone SAM 2.1 + tự tối ưu), `docs/adr/0002`
  (demo live CPU trung thực, job nặng qua Colab GPU).