# Ngày 22-10-2026 — Chạy Colab GPU lấy số liệu thật + sửa 2 lỗi chặn Colab

> Mục đích: sau khi thêm tái nhận diện (`src/*.py` đổi), phải chạy lại Colab để số GPU khớp code
> (quy ước trong `README.md` mục 3: số liệu GPU là sản phẩm tĩnh, chỉ tạo lại khi code/tham số đổi).

## 🎯 Mục tiêu
- Push code mới lên GitHub.
- Chạy lại Colab T4 để có `gpu_metrics.csv` / `gpu_summary.json` / `gpu_run_info.json` / `out_gpu.mp4` đúng commit.
- Sửa mọi lỗi khiến Colab không chạy được.

## 📥 Input
- Code sau khi thêm re-ID (commit `46a5f96`).
- Notebook `notebooks/colab_gpu_evaluation.ipynb` (cell 2 = "CHẠY TẤT CẢ").
- Log lỗi thật từ Colab (người dùng dán): `ModuleNotFoundError: No module named 'src'`.

## 🔨 Công việc đã thực hiện

1. **Push code** lên `github.com/BinhNguyen1912/DoAn-NAB` (nhánh `main`), 2 commit:
   - `46a5f96` feat(reid) — tái nhận diện khuôn mặt + fix `switch` UnboundLocalError + defer import sam2.
   - Không commit `docs/DoAnCameraAI.docx` (đề cương người dùng đang sửa).
2. **Rà lỗi chặn Colab trước khi chạy** — tìm ra và sửa 2 lỗi:
   - **Thiếu `scipy`**: `scripts/colab_run_all.py` và cell 3 của notebook chỉ cài `loguru`.
     `sam2/utils/kalman_filter.py` (phần SAMURAI thêm) `import scipy.linalg`, mà `setup.py` của
     sam2 **không** khai báo → crash ngay khi tạo predictor. Sửa thành `loguru scipy` ở cả 2 chỗ (`a80af51`).
   - **Thiếu `sys.path`**: chạy `python scripts/colab_run_all.py` thì `sys.path[0] = scripts/` nên
     `from src.synthetic_video import ...` báo `ModuleNotFoundError: No module named 'src'`
     (crash **sau khi đã tải xong checkpoint 156 MB**). Sửa: chèn `REPO_ROOT` vào `sys.path` — cùng
     pattern các script khác (`8d64d59`). Lỗi này tái hiện được trên máy bằng
     `--video data/__khong_ton_tai.mp4` (ép nhánh sinh video tổng hợp); máy không lộ ra vì đã có `data/input.mp4`.
3. **Mở ngoại lệ `.gitignore`** cho `data/*_summary.json`, `data/*_metrics.csv`, `data/*_run_info.json`
   để số liệu đo nằm trong Git (hội đồng đối chiếu được số trong báo cáo — ADR-0002).
4. **Thêm link mở notebook 1-click** vào README mục 3 + quy trình 5 bước lấy & commit số liệu.
5. **Chạy Colab T4** (người dùng bấm; agent không có tài khoản Google): 60 frame, image_size 512,
   `--reanchor-every 10`, video tổng hợp 720p, `git_rev=8d64d59`.
6. **Tính lại số đúng** (phát hiện `p95 < mean` = có outlier warmup) và **cập nhật tài liệu**.

## 📤 Output / Kết quả

### Số liệu GPU T4 (thật, commit `8d64d59`)

| Cách tính | mean | p95 | min | max | FPS |
|---|---|---|---|---|---|
| Thô 60 frame | **100,8 ms** | 72,6 | 42,1 | **2 954,5** (frame 0 warmup CUDA) | 9,92 |
| Bỏ 1 frame | 52,4 ms | 62,4 | 42,1 | 147,8 | 19,08 |
| **Bỏ 5 frame (steady)** | **49,6 ms** | **56,9** | 42,1 | 61,3 | **20,15** |

- Mất dấu: **0/60**, `mean_score` 9,38.
- Kết luận phải nói khi báo cáo: *"mean thô 100,8 ms là do frame 0 warmup CUDA 2 954 ms; tốc độ ổn định
  49,6 ms/frame ≈ **20,15 FPS**"*.
- So với CPU laptop: 5 047 ms (image_size 1024) → GPU nhanh **~13×**; so cấu hình tối ưu hai bên
  (49,6 ms vs 445 ms) → **~9×**. (Trước đây tài liệu ghi "78×" là so 65 ms vs 5 047 ms — đã sửa cho đúng.)
- T4 là Turing (SM 7.5) → **không bật được FlashAttention** ⇒ 20,15 FPS là **cận dưới**.

### File thay đổi
- `scripts/colab_run_all.py` — thêm `scipy`; thêm `sys.path.insert(0, REPO_ROOT)`.
- `notebooks/colab_gpu_evaluation.ipynb` — cell 3 thêm `scipy`.
- `.gitignore` — ngoại lệ cho file số liệu nhỏ.
- `README.md` — link Colab 1-click, quy trình lấy số liệu, bảng hiệu năng mục 7 (số mới + cảnh báo warmup).
- `docs/tom-tat-do-an.md`, `docs/team-contribution.md`, `docs/giai-thich-do-an.md` — đồng bộ 20,15 FPS.
- **Mới trong repo**: `data/gpu_metrics.csv`, `data/gpu_summary.json`, `data/gpu_run_info.json`,
  `data/gui_metrics.csv`, `data/gui_summary.json`, `data/smooth_metrics.csv`, `data/smooth_summary.json`.
- Sinh lại `data/charts/{gpu_*,smooth_*,so_sanh_latency}.png` (không commit — `data/charts/` bị ignore).

## 🐞 Vấn đề gặp phải & cách xử lý
- **`p95 < mean`** lúc đầu tưởng lỗi đo → thực ra là frame 0 warmup 2 954 ms kéo mean lên. Đã tính lại
  theo `--skip-warmup` và ghi rõ cả 2 số vào tài liệu.
- **`scripts/plot_metrics.py --skip-warmup 5` → IndexError**: cờ áp cho **mọi** file, file
  `smooth_metrics.csv` chỉ có 5 dòng nên mảng rỗng. Tạm dùng `--skip-warmup 1`. **Chưa sửa code**
  để giữ `git_rev` khớp số GPU.
- **`tools/run_live.py` in "image_size=512 (nhanh hơn trên CPU)" cả khi `--device cuda`** — lỗi chữ,
  không ảnh hưởng số. Chưa sửa cùng lý do trên.
- **Colab không tự chạy được từ agent** (cần tài khoản Google + GPU); agent chỉ chuẩn bị notebook
  1-click + sửa lỗi chặn, người dùng bấm chạy.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Sửa `scripts/plot_metrics.py`: `--skip-warmup` phải an toàn với file ít frame (bỏ qua hoặc báo rõ)
      → làm **sau** khi không cần chạy lại Colab nữa.
- [ ] Sửa câu log `image_size=... (nhanh hơn trên CPU)` thành theo `device`.
- [ ] Nếu muốn số GPU cho **re-ID**: upload `models/face/*.onnx` (39 MB) lên Colab rồi thêm `--reid`.
- [ ] Chạy lại `./run demo` trên máy (có webcam) để thay `data/smooth_*` bằng lần chạy đầy đủ
      (số cũ 445 ms / 2,25 FPS) — hiện file là kết quả `./run demo5` 5 frame.

## 📚 Tài liệu tham khảo
- `README.md` mục 3 (quy trình Colab) + mục 7 (bảng hiệu năng).
- `docs/adr/0002` (báo cáo trung thực, Colab cho số GPU).
- `docs/adr/0003` (tái nhận diện — lý do phải chạy lại Colab).
