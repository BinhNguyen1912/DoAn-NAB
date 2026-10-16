# Ngày 16-10-2026 — Implement ticket 08: Chế độ headless + config YAML + README (đóng gói)

## 🎯 Mục tiêu
- Ticket 08: đóng gói sản phẩm — 1 lệnh headless (mp4 + CSV + summary), tham số hoá qua YAML trong `configs/`, README cài đặt tái tạo từ clone mới + ghi nhận Colab GPU (story 19–22, ADR-0002).

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/08-...md` (claimed sau khi resolve 01/02/04/05/06/07 — tracker mở khoá).
- pyyaml 6.0.3 có sẵn trong env `samurai`; cấu trúc hydra của SAM 2 (`sam2/__init__.py` init `initialize_config_module("sam2")`).
- Mọi module đã làm ở ticket 05–07 (visualizer/metrics/prompt selector/run_interactive).

## 🔨 Công việc đã thực hiện
1. TDD (RED → GREEN): `src/config.py` — `DEFAULTS` (checkpoint/model_cfg/source/max_trajectory/record_*/metrics_*/max_frames), `load_config(path)` (None → defaults; key lạ → ValueError nêu tên; sai kiểu số → ValueError), `merge_cli_overrides` (CLI khác None mới đè YAML), `resolve_checkpoint` (tương đối → tuyệt theo REPO_ROOT; thiếu file → FileNotFoundError kèm hướng dẫn tải). 13 test loader thuần.
2. `configs/default.yaml` — mẫu cấu hình có chú thích từng key (tiếng Việt).
3. `TrackerEngine.build_default(..., model_cfg=MODEL_CFG)` — cho phép đè model_cfg từ YAML.
4. `run_live.py` `main()` — hợp nhất `defaults < YAML (--config) < CLI (--flag)`; `--source` giờ tuỳ chọn (mặc định lấy config); bật ghi khi `record_enabled: true` trong YAML hoặc `--record`; `--ckpt` đè checkpoint; engine build bằng checkpoint đã resolve + model_cfg của config.
5. README.md (mới, tiếng Việt): kiến trúc 5 module + sơ đồ, cài đặt 6 bước từ clone (conda samurai, requirements, clone SAMURAI — không vendor, copy config hydra, tải checkpoint tiny + link chính thức, pip install -e), 3 cách chạy (live chuột / RTSP / headless 1 lệnh), YAML config, **mục Colab GPU** — lệnh headless đúng của repo làm video minh hoạ 15–25 FPS theo ADR-0002, bảng hiệu năng hiện có + tham chiếu ADR/hardware.
6. Kiểm tra: **75/75 passed** (62 cũ + 13 config; 1:40). Smoke thật: `python tools/run_live.py --config configs/_smoke8.yaml --bbox "60,60,40,40"` → mp4 4 frame + CSV 4 dòng + summary JSON (mean=3067 ms, FPS≈0.30, mất dấu 0/4); checkpoint sai trong YAML → FileNotFoundError thân thiện (không crash khó hiểu).

## 📤 Output / Kết quả
- Ticket 08: **4/4 tiêu chí ticked**. Toàn bộ 8 ticket của spec đã xong (03 còn 1 mục webcam xác nhận thủ công — không làm được dưới WSL).
- File thay đổi:
  - `src/config.py` — config loader YAML + hợp nhất CLI (mới)
  - `configs/default.yaml` — mẫu cấu hình (mới)
  - `src/tracker_engine.py` — build_default nhận model_cfg (sửa)
  - `tools/run_live.py` -- --config + hợp nhất 3 lớp (sửa)
  - `README.md` — cài đặt + chạy + Colab (mới)
  - `requirements.txt` — + pyyaml>=6.0 (sửa)
  - `tests/test_config.py` — 13 test (mới)

## 🐞 Vấn đề gặp phải & cách xử lý
- Bug validation: `source` trong `_INT_KEYS` làm YAML `source: data/video.mp4` báo sai ("phải là số nguyên") — source hợp lệ int (webcam) lẫn str (file/RTSP) → bỏ khỏi _INT_KEYS, thêm test chốt.
- Negative test checkpoint đầu tiên vô tác dụng: sed trên yaml KHÔNG có key `checkpoint` → tưởng đã test, thực ra cfg lấy DEFAULTS. Sửa: tạo yaml có key checkpoint; phát hiện nhờ đối chiếu `cfg["checkpoint"]` in ra.
- Điều tra cơ chế hydra SAM 2: `compose(config_name="configs/samurai/sam2.1_hiera_t.yaml")` compose thành công nhờ `sam2/__init__.py` tự `initialize_config_module("sam2")` — README ghi rõ giữ nguyên value `model_cfg` trong default.yaml và chỉ đổi checkpoint khi cần.
- WSL smoke YAML đầu chứa key `bbox` → loader từ chối đúng thiết kế (key lạ báo rõ); bbox là tham số mỗi lần chạy → truyền CLI.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Kiểm thủ công các đường GUI trên máy có màn hình/camera: --display (kéo chuột, r, q/ESC), webcam adapter (ticket 03), --record trực tiếp.
- [ ] Chạy trên Colab GPU: video minh hoạ GPU thật + số liệu đối chiếu CPU (ADR-0002) đưa vào báo cáo.
- [ ] Vẽ biểu đồ quỹ độ/latency từ CSV MetricsLogger phục vụ mục "Đánh giá hiệu năng" của báo cáo.

## 📚 Tài liệu tham khảo
- `/implement`, `/tdd`; spec + ticket 08 (stories 18–22); ADR-0001, ADR-0002; docs Hydra (`initialize_config_module`), docs SAM 2 INSTALL.md (link checkpoint).