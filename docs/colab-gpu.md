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

## Các bước

1. Mở https://colab.research.google.com → **Upload** file `notebooks/colab_gpu_demo.ipynb` (hoặc mở từ GitHub:
   *File → Open notebook → GitHub → `BinhNguyen1912/DoAn-NAB` → `notebooks/colab_gpu_demo.ipynb`*).
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
