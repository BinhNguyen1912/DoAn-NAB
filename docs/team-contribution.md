# Đóng góp của sinh viên vs thành phần có sẵn

> Tài liệu để trả lời hội đồng: **phần nào em tự làm, phần nào dùng có sẵn (và dùng theo đúng
> phạm vi đề cương cho phép)**. Số liệu lấy từ chính repo (commit, file, test, log đo) — không
> phải tự khai.

## 1. Tóm tắt một câu

Đồ án **không huấn luyện lại model** (đề cương + ADR-0001 chốt backbone SAM 2.1 + config SAMURAI);
phần **em tự xây là toàn bộ hệ thống** chạy quanh model: streaming per-frame, chọn đối tượng, HUD
tiếng Việt, quỹ đạo, đo hiệu năng, cấu hình, chế độ headless, chế độ hiển thị mượt, test + CI —
tổng **2 424 dòng code** và **131 test tự động**.

## 2. Bảng đóng góp

| # | Thành phần | Nguồn | Em làm gì trên đó | Bằng chứng |
|---|---|---|---|---|
| 1 | **`TrackerEngine`** (streaming per-frame) | SAM 2 của Meta (backbone) + SAMURAI (Kalman/memory) | **Adapt SAM 2 offline → streaming**: thay `inference_state["images"]` bằng `_StreamingImages`, nạp frame vô hạn, giải phóng tensor đã dùng, `start/process/reset`, đo ms/frame, đọc `object_score_logits` | `src/tracker_engine.py` (236 dòng), `tests/test_tracker_engine.py` (5 test, IoU ≥ 0.5 trên fixture), commit `d219590` |
| 2 | **`VideoSource`** (3 nguồn + HTTP) | OpenCV `VideoCapture` | Viết factory + 4 adapter (webcam / RTSP / file / **MJPEG-HTTP**), timeout, thông báo lỗi tiếng Việt có hướng dẫn; **fix backend V4L2 + MJPG/640×480** cho webcam UVC; **fix đệm 1 frame** (BUFFERSIZE) | `src/video_source.py` (239 dòng), `tests/test_video_source.py` (16 test), commits `6bb3060`, `328bc8d`, `d44d82e`, `0e3805f` |
| 3 | **`PromptSelector`** | — | **Tự viết**: máy trạng thái kéo-thả chuột (idle→dragging→done), chuẩn hoá bbox, min-size, `r` chọn lại, vẽ rubber-band | `src/prompt_selector.py` (106 dòng), `tests/test_prompt_selector.py` (12 test), commit `ac5893d` |
| 4 | **`Visualizer`** (HUD) | OpenCV + PIL | **Tự viết**: mask alpha, ô bao, **quỹ đạo deque**, HUD 4 dòng tiếng Việt (font TTF), **banner MẤT DẤU**, điểm tin cậy, ghi mp4, tách `consume()/render()` | `src/visualizer.py` (284 dòng), `tests/test_visualizer.py` (21 test), commits `dfbfd88`, `907247d`, `0fddfdf`, `025a547` |
| 5 | **`MetricsLogger`** | — | **Tự viết** (hàm thuần): CSV từng frame (ms, score, tâm x/y, cờ mất dấu), summary mean/p95/FPS/tỷ lệ mất dấu, JSON | `src/metrics_logger.py` (100 dòng), `tests/test_metrics_logger.py` (14 test), commit `89ca85f` |
| 6 | **Pipeline** (`run_tracking`/`run_interactive`/`run_smooth_display`) | — | **Tự viết**: vòng lặp headless, vòng lặp tương tác (chọn → track → r → thoát), **chế độ mượt 3 luồng** (capture / inference / display), `--reanchor-every`, xử lý Ctrl+C | `src/live_pipeline.py` (269), `src/smooth_display.py` (286), `tests/test_live_pipeline.py` (3), `tests/test_interactive_loop.py` (10), `tests/test_smooth_display.py` (12), commits `bb7626f`, `025a547`, `b733795` |
| 7 | **Config YAML + CLI** | PyYAML | **Tự viết**: defaults < YAML < CLI, validate kiểu, `resolve_checkpoint` lỗi thân thiện, `--device cuda` cho Colab, `--image-size`, `--smooth` | `src/config.py` (95), `tools/run_live.py` (337), `configs/default.yaml`, `tests/test_config.py` (21), `tests/test_run_live_cli.py` (9), commits `db8ad09`, `1244638` |
| 8 | **Fixture giả lập** (test không cần dữ liệu nặng) | — | **Tự viết**: sinh chuỗi frame ô vuông di chuyển + **chế độ che khuất** + bbox đáp án | `src/synthetic_video.py` (73), `tests/test_synthetic_video.py` (5), commit `f11233e` |
| 9 | **Tool phụ trợ** | — | **Tự viết**: `check_video_source.py` (kiểm nguồn nhanh), `find_phone_camera.py` (quét LAN tìm camera điện thoại, sửa nhận diện subnet WSL), `scripts/demo_webcam.sh` | `tools/` (409 dòng), `tests/test_find_phone_camera.py` (3) |
| 10 | **Guardrail kỹ thuật** | — | **Tự dựng**: 131 test, `pytest-timeout`, `ruff.toml` ghim rule, **CI GitHub Actions** (ruff + test làn nhanh), `CODING_STANDARDS.md` | `.github/workflows/checks.yml`, `pytest.ini`, `ruff.toml`, commits `284cfee`, `50f9491` |
| 11 | **Tài liệu & quyết định** | — | **Tự viết**: ADR-0001/0002, spec, 8 ticket + tracker, **12 file log theo ngày**, README cài đặt tái tạo được, `docs/colab-gpu.md`, notebook Colab | `docs/adr/`, `docs/task/`, `.scratch/`, `README.md`, `notebooks/colab_gpu_evaluation.ipynb` |
| 12 | **Số liệu đánh giá** | đo trên máy thật | **Tự đo & phân tích**: latency/FPS CPU, độ trễ tăng theo memory, đánh đổi `image_size` (1024/768/512/384/256), `reanchor`, độ phân giải camera, thread; phát hiện SAM 2 luôn trả mask với vùng nền | Bảng trong `README.md` mục "Đánh giá hiệu năng"/"Tối ưu tốc độ", `docs/task/18-10-2026-*.md`, `data/*_summary.json` |

## 3. Thành phần **không** tự viết (và vì sao hợp lệ)

| Thành phần | Nguồn | Vì sao dùng |
|---|---|---|
| **SAM 2.1 tiny** (`sam2_video_predictor.py` 1 176 dòng, `mask_decoder.py` 295 dòng, …) | Meta AI (Apache-2.0) | **Backbone** — đề cương + **ADR-0001** chốt: "Backbone: SAM 2.1 tiny với config SAMURAI". Đồ án không huấn luyện lại |
| **SAMURAI** (Kalman + motion-aware memory bank selection) | yangchris11/samurai | Spec ghi rõ: **"đóng gói Kalman + memory-bank selection có sẵn của SAMURAI (không viết lại)"** — em viết lớp bọc streaming quanh nó |
| OpenCV, PyTorch, NumPy, PyYAML, Pillow, pytest, ruff | thư viện mã nguồn mở | Hạ tầng bình thường của mọi đồ án |
| Google Colab (T4) | Google | Chỉ là **máy có GPU cho mượn** để đo số FPS GPU + xuất video minh hoạ; code chạy trên đó là repo của em (ADR-0002) |

## 4. Những kết quả **gốc** (không có trong repo nào khác)

1. **Adapt streaming**: SAM 2 gốc chỉ chạy offline cả video; em làm nó chạy **từng frame từ webcam**
   (đây là đóng góp kỹ thuật chính, tương ứng hướng nghiên cứu `docs/research/03`).
2. **Đo được giới hạn thật của CPU**: 3–8 s/frame, độ trễ **tăng dần** theo memory (3,4 s → 8,3 s),
   và giải thích nguyên nhân (số frame trong `non_cond_frame_outputs`).
3. **Đo đánh đổi có bảng số**: `image_size` 1024→384 nhanh **~6–10×** (IoU giảm 0,981 → 0,861 khi có
   che khuất); re-anchor nhanh 2,2× nhưng **không ổn định khi bị che** (IoU 0,509) → khuyến nghị bỏ.
4. **Phát hiện SAM 2 luôn trả mask cho vùng nền** (1,2% khung, score 17,8 vs 22,6) → thiết kế cảnh
   báo + HUD điểm tin cậy thay vì "chặn" (không thể).
5. **Fix webcam UVC trên Linux**: cần `CAP_V4L2` + `FOURCC=MJPG` + 640×480 mới trả frame, và
   `BUFFERSIZE=1` mới hết trễ do hàng đợi.
6. **Chế độ hiển thị mượt 3 luồng**: video 19 FPS trên CPU với overlay cập nhật ~2 lần/s (có tuổi
   overlay trên HUD — trung thực theo ADR-0002).
7. **Bảng số CPU vs GPU tự đo**: CPU 720p/1024 = 5 047 ms (0,20 FPS); CPU/384 = 445 ms (2,25 FPS);
   **Colab T4/1024 = 380 ms (2,63 FPS)**; **Colab T4/512 + reanchor = 65 ms (15,28 FPS)** — kèm phát hiện
   T4 (Turing) không bật được FlashAttention nên số GPU là cận dưới.

## 5. Cách hội đồng tự kiểm chứng (không cần tin lời)

```bash
git log --oneline                 # 25 commit, mỗi commit là một phần việc
python -m pytest -m "not slow"    # 128 test làn nhanh (không cần model)
python -m pytest                 # 131 test (gồm test model thật, cần checkpoint)
ruff check .                      # lint sạch
docs/task/16-10-2026-*.md         # 8 log phiên implement ticket 01–08
docs/task/18-10-2026-*.md         # log kiểm thủ công + các bug tìm được & cách sửa
docs/adr/0001, 0002               # quyết định kỹ thuật (backbone, CPU/Colab)
```

## 6. Nếu được hỏi "vậy em đóng góp gì?"

> "Em dùng SAM 2.1 + SAMURAI làm backbone theo đúng đề cương/ADR-0001, và **em xây toàn bộ hệ thống
> quanh nó**: adapt predictor sang streaming per-frame để nhận webcam trực tiếp, module chọn đối
> tượng bằng chuột, HUD + quỹ đạo + mặt nạ tiếng Việt, module đo FPS/độ trễ/độ ổn định, cấu hình
> YAML, chế độ headless cho Colab, chế độ hiển thị mượt, cùng 131 test tự động và CI. Em cũng tự đo
> và công bố giới hạn thật của laptop CPU theo ADR-0002."
