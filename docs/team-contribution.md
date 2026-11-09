# Đóng góp của sinh viên vs thành phần có sẵn

> Tài liệu để trả lời hội đồng: **phần nào em tự làm, phần nào dùng có sẵn (và dùng theo đúng
> phạm vi đề cương cho phép)**. Số liệu lấy từ chính repo (commit, file, test, log đo) — không
> phải tự khai.

## 1. Tóm tắt một câu

Đồ án **không huấn luyện lại model** (đề cương + ADR-0001 chốt backbone SAM 2.1 + config SAMURAI);
phần **em tự xây là toàn bộ hệ thống** chạy quanh model: streaming per-frame, chọn đối tượng, HUD
tiếng Việt, quỹ đạo, đo hiệu năng, cấu hình, chế độ headless, chế độ hiển thị mượt, **live hybrid
VOS+LK**, **API (ports & adapters) + web React**, test + CI. Số hiện tại: **7 175 dòng Python** trong
`src/` (+ **1 343 dòng** `web/src/`), **663 hàm test** (704 test chạy ở làn nhanh trên nhánh này),
**167 commit**, **5 ADR**, **44 log** trong `docs/task/`. Các số đếm **tính đến 09-11-2026**; đếm lại
bằng: `git rev-list --count HEAD`, `find src -name '*.py' | xargs wc -l | tail -1`,
`grep -rc 'def test_' tests/*.py | awk -F: '{s+=$2} END {print s}'` (số sẽ tăng sau mỗi PR — trích
khoảng "hơn 660 hàm test" an toàn hơn số tuyệt đối).

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
| 10 | **Guardrail kỹ thuật** | — | **Tự dựng**: 663 hàm test (704 test ở làn nhanh trên nhánh này), `pytest-timeout`, `ruff.toml` ghim rule, **CI GitHub Actions** (ruff + test làn nhanh), `CODING_STANDARDS.md` | `.github/workflows/checks.yml`, `pytest.ini`, `ruff.toml`, commits `284cfee`, `50f9491` |
| 11 | **Tài liệu & quyết định** | — | **Tự viết**: ADR-0001→0004, spec, **13 ticket** + tracker, **28 file log theo ngày**, README cài đặt tái tạo được, `docs/colab-gpu.md`, notebook Colab | `docs/adr/`, `docs/task/`, `.scratch/`, `README.md`, `notebooks/colab_gpu_evaluation.ipynb` |
| 12 | **Số liệu đánh giá** | đo trên máy thật | **Tự đo & phân tích**: latency/FPS CPU, độ trễ tăng theo memory, đánh đổi `image_size` (1024/768/512/384/256), `reanchor`, độ phân giải camera, thread; phát hiện SAM 2 luôn trả mask với vùng nền | Bảng trong `README.md` mục "Đánh giá hiệu năng"/"Tối ưu tốc độ", `docs/task/18-10-2026-*.md`, `data/*_summary.json` |
| 13 | **`ReIdSession` — tái nhận diện khuôn mặt** (mất dấu → đóng băng → tự bám lại đúng người) | YuNet + SFace của OpenCV Zoo (model có sẵn) | **Tự viết toàn bộ cơ chế**: máy trạng thái `tracking/lost/reacquiring`, **chặn bám sang người khác** bằng cách ngừng `engine.process`, **tập embedding tham chiếu** (chỉ lấy mặt nằm trong ô đang bám + cổng chất lượng), **max cosine**, ngưỡng hiệu chỉnh bằng số đo thật, cột metrics `state/reid_score/reacquired` | `src/reid.py`, `tests/test_reid.py` (16 test), `docs/adr/0003`, `configs/default.yaml` |
| 14 | **Tái nhận diện VẬT THỂ** (vật không có mặt: remote, ly, chén, bút) — ticket 10/11/13 | — (đặc trưng thủ công, **không dùng model nào**) | **Tự viết**: đặc trưng `covariance 5×5 [x,y,B,G,R]` + `HSV hist 8×8` ghép L2 (bù trừ: 0,061 vs 0,382), **cascade tìm lại** (NCC thu nhỏ 4× → top-20 → descriptor: 845 ms → 23,8 ms), **3 cổng chống kẹt** (score âm = mất dấu, xác nhận 2 frame, kiểm chứng 2 frame), **tách vai cổng cosine/NCC**, `scripts/calibrate_reid.py` đo ngưỡng từ CSV có nhãn | `src/appearance.py`, `src/reid.py`, `tests/test_appearance.py` (25), `tests/test_calibrate_reid.py` (9), `docs/adr/0004`, `data/reid_2clip_calib.json` |

| 15 | **Live hybrid VOS + Lucas–Kanade** (HUD 30 FPS, mask ~8,6 lần/giây) | OpenCV `calcOpticalFlowPyrLK` + SAM 2 (worker riêng) | **Tự viết**: thread VOS riêng + LK nội suy giữa hai lần model chạy, đóng gói `(x,y,w,h)`→`(x1,y1,x2,y2)` cho SAM 2, đo **giá của nội suy** (`drift_iou`, `mask_age_ms`), chống nhấp nháy mask (đo rồi mới quyết định **tắt** mặc định), HUD nói rõ "mask không phải 30 FPS" | `src/live_tracking.py`, `src/light_tracker.py`, `tests/test_live_tracking.py`, `data/drift_2026-11-08_metrics.json`, `docs/task/08-11-2026-hybrid-vos-lk-live-30fps.md` |
| 16 | **API backend theo ports & adapters** | FastAPI | **Tự viết**: `domain.py` (thuần) / `ports.py` (Protocol) / `service.py` / `adapters/` / `routes.py` / `main.py` = composition root (ADR-0005); **watchdog phiên live** (worker chết ⇒ `error` sau 116–117 ms; nguồn camera mất frame ⇒ 3,75 s); job store trên đĩa + chặn path traversal | `src/api/**`, `tests/test_api_*.py`, `data/watchdog_*_2026-11-09_metrics.json`, `docs/adr/0005-*` |
| 17 | **Web UI** (React + Vite, tiếng Việt) | React, Vite, TypeScript | **Tự viết**: chọn ô bằng chuột trên khung hình (`LivePanel`), phát MJPEG, dòng "nhịp mask" nói rõ FPS phát ≠ nhịp mask, bảng số liệu job, `api.ts` + hook poll; **test vitest** cho hàm thuần + **e2e Playwright** trên Chrome/Edge thật | `web/src/**`, `web/src/live.test.ts`, `scripts/e2e_web.js`, `docs/task/08-11-2026-web-fastapi-react-va-tang-runner.md` |
| 18 | **Đo lường có provenance + bằng chứng demo** | — | **Tự viết**: script đo ghi artifact JSON kèm `git_rev`/`git_dirty`/`git_dirty_code`/`lenh`/`do_luc`, ngưỡng nhiễu in kèm (`scripts/repeatability.py`), tách "không đo được" khỏi "đo được 0", `scripts/measure_live_relay.py` chứng minh **camera thật → API → mask** | `scripts/measure_watchdog.py`, `scripts/measure_live_relay.py`, `scripts/repeatability.py`, `data/*_metrics.json`, `docs/task/09-11-2026-bang-chung-duong-camera-that.md` |

## 3. Thành phần **không** tự viết (và vì sao hợp lệ)

| Thành phần | Nguồn | Vì sao dùng |
|---|---|---|
| **SAM 2.1 tiny** (`sam2_video_predictor.py` 1 176 dòng, `mask_decoder.py` 295 dòng, …) | Meta AI (Apache-2.0) | **Backbone** — đề cương + **ADR-0001** chốt: "Backbone: SAM 2.1 tiny với config SAMURAI". Đồ án không huấn luyện lại |
| **SAMURAI** (Kalman + motion-aware memory bank selection) | yangchris11/samurai | Spec ghi rõ: **"đóng gói Kalman + memory-bank selection có sẵn của SAMURAI (không viết lại)"** — em viết lớp bọc streaming quanh nó |
| OpenCV, PyTorch, NumPy, PyYAML, Pillow, pytest, ruff | thư viện mã nguồn mở | Hạ tầng bình thường của mọi đồ án |
| **YuNet** (phát hiện mặt) + **SFace** (embedding 128-D) | OpenCV Zoo (model ONNX có sẵn, tải về ở `models/face/`) | Dùng làm **tín hiệu nhận dạng** cho tái nhận diện (ADR-0003) — cùng triết lý ADR-0001: dùng model có sẵn, đóng góp nằm ở cơ chế + ngưỡng + đánh giá; không train lại |
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
   **Colab T4/1024 = 380 ms (2,63 FPS)**; **Colab T4/512 + reanchor = 49,6 ms (20,15 FPS** bỏ 5 frame
  warmup; mean thô 100,8 ms**)** — kèm phát hiện
   T4 (Turing) không bật được FlashAttention nên số GPU là cận dưới.

## 5. Cách hội đồng tự kiểm chứng (không cần tin lời)

```bash
git log --oneline                 # 164 commit, mỗi commit là một phần việc
python -m pytest -m "not slow"    # 692 test làn nhanh (không cần model) — dùng ./run test
python -m pytest                  # 697 test (gồm test model thật, cần checkpoint) — dùng ./run testall
npm --prefix web test             # 24 test web (vitest) — dùng ./run webtest
node scripts/e2e_web.js           # e2e Playwright trên Chrome/Edge thật — dùng ./run e2e
ruff check .                      # lint sạch
docs/task/                        # 44 log theo ngày (16-10 → 09-11)
docs/task/16-10-2026-*.md         # 8 log phiên implement ticket 01–08
docs/task/18-10-2026-*.md         # log kiểm thủ công + các bug tìm được & cách sửa
docs/adr/0001, 0002, 0003, 0004   # quyết định kỹ thuật (backbone, CPU/Colab, re-ID mặt, re-ID vật)
```

## 6. Nếu được hỏi "vậy em đóng góp gì?"

> "Em dùng SAM 2.1 + SAMURAI làm backbone theo đúng đề cương/ADR-0001, và **em xây toàn bộ hệ thống
> quanh nó**: adapt predictor sang streaming per-frame để nhận webcam trực tiếp, module chọn đối
> tượng bằng chuột, HUD + quỹ đạo + mặt nạ tiếng Việt, module đo FPS/độ trễ/độ ổn định, cấu hình
> YAML, chế độ headless cho Colab, chế độ hiển thị mượt, cùng 131 test tự động và CI. Em cũng tự đo
> và công bố giới hạn thật của laptop CPU theo ADR-0002."
