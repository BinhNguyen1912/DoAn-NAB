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

- `src/video_source.py` — 1 interface cho 3 nguồn: webcam index, RTSP, video file.
- `src/tracker_engine.py` — seam trung tâm: `start(bbox)` → `process(frame)` mỗi frame →
  mask + bbox + điểm tin cậy + ms. Đóng gói SAMURAI nguyên bản (Kalman + memory bank).
- `src/prompt_selector.py` — máy trạng thái kéo-thả chọn ô; phím **r** chọn lại đối tượng.
- `src/visualizer.py` — HUD: mask alpha + ô bao + quỹ đạo (deque giới hạn) + FPS/độ trễ
  nhãn tiếng Việt (PIL font TTF) + ghi mp4.
- `src/metrics_logger.py` — hàm thuần: CSV từng frame + summary mean/p95/tỷ lệ mất dấu.
- Cấu hình YAML: `configs/default.yaml` (checkpoint, nguồn, ghi mp4, metrics).

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
wget https://dl.fbaipublicfiles.com/segment_anything_2/092823/sam2.1_hiera_tiny.pt
cd ../../..

# 5) cài package sam2 của SAMURAI
pip install -e samurai/sam2        # hoặc theo hướng dẫn samurai/README

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

1. Đẩy repo (kèm `samurai/` clone + checkpoint) lên Drive/clone trực tiếp trong notebook.
2. Trên Colab: `!pip install -r requirements.txt && pip install -e samurai/sam2`
   (torch CUDA đã có sẵn).
3. Chạy `!python tools/run_live.py --source data/video.mp4 --bbox "..." \
   --record data/colab_gpu.mp4 --metrics-csv data/colab_metrics.csv --metrics-summary data/colab_summary.json`
4. Số liệu trong `summary.json` **là số đo GPU thật** — dùng cho mục "Đánh giá hiệu năng"
   của báo cáo, đặt cạnh số liệu CPU laptop để đối chiếu trung thực.

## 4. Cấu trúc repo

```
src/            mã nguồn chính (video_source, tracker_engine, prompt_selector,
                visualizer, metrics_logger, live_pipeline, config)
tools/          CLI chạy (run_live.py), benchmark, demo scripts
configs/        default.yaml + config SAMURAI
tests/          pytest (fixture synthetic, không commit dữ liệu nặng)
docs/           đề cương, ADR, log công việc theo ngày (docs/task/)
data/           video demo + bbox frame 0 (KHÔNG commit file nặng)
```

## 5. Đánh giá hiệu năng (đang có)

| Môi trường | Pipeline (mean ms/frame) | FPS hiệu dụng | Nguồn số liệu |
|---|---|---|---|
| Laptop CPU (tiny) | ~3200–3600 | ~0.28–0.31 | smoke test ticket 05–08 |

Chi tiết từng phiên chạy: `docs/task/`; số liệu mẫu:
`[metrics] mean=3441 ms | p95=4123 ms | FPS hiệu dụng ≈ 0.29 | mất dấu 0/5`.

## 6. Kiến thức nền

- **SAMURAI**: https://github.com/yangchris11/samurai (motion-aware memory + Kalman)
- **SAM 2**: https://github.com/facebookresearch/sam2 (streaming memory propagation)
- ADR: `docs/adr/0001` (chọn backbone SAM 2.1 + tự tối ưu), `docs/adr/0002`
  (demo live CPU trung thực, job nặng qua Colab GPU).