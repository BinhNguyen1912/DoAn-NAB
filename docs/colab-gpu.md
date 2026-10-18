# Colab GPU — chạy headless để lấy video + số liệu GPU (ADR-0002)

Mục đích: laptop CPU chỉ đạt ~0.2–2 FPS, nên **video minh hoạ tốc độ thật** và **số FPS GPU** lấy từ Colab T4.
Sản phẩm chính (demo live webcam) **vẫn chạy trên laptop** — Colab chỉ là nơi đo/ làm video.

## Thời gian (quan trọng)

| Giai đoạn | Thời gian |
|---|---|
| Cài đặt **một lần mỗi phiên Colab** (clone repo + SAMURAI + tải checkpoint 156 MB + pip install) | **~8–15 phút** |
| Chạy 1 video 10–15 giây (~250–375 frame) trên T4 | **~20–40 giây** |
| Lúc bảo vệ | mở file `out_gpu.mp4` — không chờ gì |

Colab free sẽ **ngắt phiên** sau một thời gian rảnh → lần sau phải chạy lại cell cài đặt (checkpoint tải lại).
Muốn tránh: lưu checkpoint vào Google Drive và copy sang (tuỳ chọn).

## Cách nhanh nhất — 1 cell duy nhất

Mở notebook, bật **Runtime → Change runtime type → T4 GPU**, rồi chạy **cell "⚡ CHẠY TẤT CẢ"**
(ngay sau cell kiểm GPU). Cell đó chạy `scripts/colab_run_all.py`, tự làm: clone/pull repo → cài
`sam2` + `loguru` → tải checkpoint (kiểm tra >100 MB) → tạo video test (nếu chưa có `data/input.mp4`)
→ chạy pipeline GPU với `--image-size 512 --reanchor-every 10` → in số liệu → đóng gói
`data/colab_gpu_results.zip`.

Muốn dùng **video thật**: kéo video vào panel Files tại `/content/DoAn-NAB/data/input.mp4` **trước**
khi chạy cell, và truyền `--bbox` đúng:
```python
!python scripts/colab_run_all.py --bbox "x,y,w,h"        # hoặc --max-frames 300
```

## Các bước thủ công (nếu muốn chạy từng cell)

1. Mở https://colab.research.google.com → **Upload** file `notebooks/colab_gpu_evaluation.ipynb` (hoặc mở từ GitHub:
   *File → Open notebook → GitHub → `BinhNguyen1912/DoAn-NAB` → `notebooks/colab_gpu_evaluation.ipynb`*).
2. **Runtime → Change runtime type → T4 GPU → Save**.
3. Chạy lần lượt các cell (Shift+Enter):
   - Cell 1: kiểm tra GPU (`Tesla T4`, `CUDA sẵn sàng: True`).
   - Cell 2: clone repo + SAMURAI + checkpoint + pip install (~8–15 phút).
   - Cell 3b: nếu chưa có video, sinh video test (ô vuông di chuyển).
   - Cell 4: chạy pipeline `--device cuda` → ra mp4 + CSV + JSON.
   - Cell 5: in số liệu + xem video ngay trong notebook.
   - Cell 6: tải 3 file về máy.
4. Đưa video vào slide; đưa số GPU vào báo cáo mục "Đánh giá hiệu năng", **cạnh** số CPU laptop.

## Video nguồn nên quay thế nào

- 10–15 giây, 720p, **một đối tượng chuyển động** (người đi qua khung, tay vẫy, con vật…).
- Quay bằng điện thoại rồi kéo file vào panel **Files** của Colab, đặt tên `data/input.mp4`.
- Chọn `--bbox "x,y,w,h"` đúng vị trí đối tượng ở **frame 0** (mở video trong máy để xem toạ độ ước lượng;
  hoặc bỏ `--bbox` để dùng ô giữa khung).

## Câu trả lời cho hội đồng

> Hệ thống **real-time-capable trên GPU**: đo thật trên T4 được `X FPS` (xem `gpu_summary.json`).
> Trên laptop CPU (không GPU NVIDIA) chỉ đạt `0.2–2 FPS` nên demo live là **slideshow có chủ đích**,
> số liệu công bố trung thực theo ADR-0002.

## Kiểm chứng đã làm trên máy dev (CPU)

- Lệnh y như cell 4 (đổi `--device cpu`) chạy đúng: ra mp4 + CSV + JSON.
- `--device cuda` khi không có GPU → báo lỗi rõ: *"kiểm tra: Colab → Runtime → Change runtime type → GPU"*.

## Sau khi đã có số liệu — có phải chạy lại không?

**Không.** Video + CSV + JSON là **sản phẩm tĩnh**: tạo một lần, dùng cho báo cáo/slide mãi.
Lúc bảo vệ chỉ cần **mở file mp4** — không cần Colab, không cần GPU, không mạng.

| Việc bạn làm | Cần chạy lại Colab? |
|---|---|
| Soạn báo cáo, làm slide, trả lời phản biện | ❌ Không |
| Demo live bằng webcam laptop | ❌ Không (đó là CPU, dùng `scripts/demo_webcam.sh`) |
| Sửa `src/tracker_engine.py`, `visualizer.py`, `live_pipeline.py`, `metrics_logger.py` | ✅ Có — số liệu cũ không còn đúng với code mới |
| Đổi video nguồn / `--bbox` / `--image-size` / `--reanchor-every` | ✅ Có |
| Muốn thêm kịch bản (video dài hơn, cảnh che khuất) | ✅ Có |

**Cách biết số liệu đã cũ:** mỗi lần chạy, `data/gpu_run_info.json` được ghi kèm `git_rev`:

```bash
cat data/gpu_run_info.json     # {"git_rev": "e45d87f", "image_size": 512, ...}
git log -1 --oneline           # so rev ở đây với git_rev
```
- Hai rev **giống nhau** → số liệu còn đúng, dùng tiếp.
- Khác nhau **và** commit mới có đụng `src/` hoặc tham số đo → chạy lại Colab (~10 phút, gồm tải checkpoint).

> ⚠️ Colab **xoá toàn bộ `/content`** khi phiên kết thúc (đóng tab, hết 90 phút, hết quota).
> Vì vậy phải **tải `colab_gpu_results.zip` về máy** (hoặc copy sang Google Drive) ngay sau khi chạy —
> đừng dựa vào việc “lần sau mở lại vẫn còn”.
