# Ngày 16-10-2026 — Retro: guardrail tự động + chuẩn code + tách template log

## 🎯 Mục tiêu
- Chạy `/retro` trên phiên implement ticket 01–08 và áp các cải tiến **môi trường agent**: chặn lỗi cơ học bằng kiểm tra tự động, tách tài liệu dài khỏi context thường trực, bổ sung navigation cho phần từng tốn thời gian.

## 📥 Input
- Skill `/retro` + `writing-for-agents`.
- Bằng chứng từ phiên trước: test script phím `r` treo **1800s** (hết timeout bash); 3 bug chỉ lộ khi chạy smoke CLI ~90s; 3 lỗi cơ học (unused import ×2, import trùng, comment tiếng Việt không dấu); full suite 100s chạy ~8 lần; mất ~6 tool call để hiểu hydra `model_cfg`.
- Trạng thái repo trước phiên: **không CI, không pre-commit, không linter** (chỉ pytest), `AGENTS.md` 146 dòng có template log 40 dòng inline.

## 🔨 Công việc đã thực hiện
1. **Timeout test** — cài `pytest-timeout`, thêm `--timeout=120` vào `pytest.ini`. Kiểm chứng: tạo test treo thử → chết sau đúng 120.2s với message `Timeout (>120.0s)` (lần đầu thử ở `/tmp` KHÔNG fire vì ngoài rootdir — đã thử lại trong `tests/` mới đúng).
2. **Ruff** — cài `ruff 0.17.1`, viết `ruff.toml` ghim `select = ["E4","E7","E9","F"]` (không phụ thuộc config máy: phát hiện ruff đang đọc default rộng ngoài repo), per-file-ignore E402 cho `tools/*.py`. Chạy → **7 finding thật**, sửa tay từng cái: `import time` thừa (`live_pipeline`), `path_tmp = None` chết (test), `import cv2` thừa + import lồng trùng (test metrics — ban đầu sed làm mất import thật, đã sửa lại đúng), `import pytest` trùng (`test_synthetic_video`), `import torch`/`import numpy` thừa và `out =` không dùng (2 tool cũ). Sau đó `ruff check .` → **All checks passed**.
3. **CI** — `.github/workflows/checks.yml`: 2 job (`lint` = ruff; `tests` = pytest làn nhanh), python 3.10, torch CPU qua index-url, `pip install -r requirements.txt`. `.gitignore` thêm `.pytest_cache/`, `.ruff_cache/`. `requirements.txt` thêm `pytest-timeout`, `pillow`, `ruff` (pillow trước đó là phụ thuộc ngầm của Visualizer).
4. **Test CLI `tools/run_live.py`** (trước đó 0 test, 3 bug của phiên nằm ở đây) — `tests/test_run_live_cli.py`: FakeEngine thay `build_default`, 7 test trong **1.5s**: YAML bật ghi → mp4+CSV+JSON đủ; CLI `--record` thắng YAML; `record_enabled: false` không tạo file; `source: null` → exit code 1 + thông báo; `max_frames` từ YAML; **--display wiring** với bề mặt cv2 giả lập (setMouseCallback/imshow/waitKey/destroyAllWindows → q).
   - Bài học cứng: gọi `cv2.namedWindow` thật khi headless **SIGABRT cả process** (kill luôn pytest) → phải monkeypatch toàn bộ GUI trong test; đã ghi thành chuẩn.
5. **AGENTS.md gọn lại** (146 → 125 dòng) — template log 40 dòng chuyển sang `docs/task/_template.md` (progressive disclosure: chỉ cần cuối phiên), §2.2 còn pointer + yêu cầu 7 mục; §4 thay 4 bullet bằng pointer tới `CODING_STANDARDS.md`; §5 thêm làn nhanh + lệnh lint + khi nào chạy full suite; §6 thêm pointer `docs/samurai-setup.md`; §3 cập nhật cây thư mục (thêm `.github/`, `docs/adr/`, `docs/agents/`, `tools/`, `tests/`, `ruff.toml`, `pytest.ini`).
6. **`CODING_STANDARDS.md` (mới)** — quy tắc máy không phán được: comment/docstring/print **tiếng Việt CÓ DẤU** (ngoại lệ duy nhất: chuỗi `cv2.putText` ASCII vì font Hershey); UI phải tiêm qua callback để test headless, cấm gọi GUI thật trong test (kèm lý do SIGABRT); vòng lặp trong test phải có đường thoát hữu hạn; số liệu kỳ vọng viết literal; dùng fixture chung + `FakeEngine`.
7. **`docs/samurai-setup.md` (mới)** — bảng vị trí package/checkpoint/config + giải thích hydra tự init trong `sam2/__init__.py` (vì sao `model_cfg` resolve trong package, chạy được mọi CWD) + lệnh kiểm tra môi trường nhanh.
8. **README** — thêm mục 5 "Kiểm tra chất lượng (guardrail)" với 3 lệnh + ghi chú CI/timeout; đánh số lại mục 6–7.

## 📤 Output / Kết quả
- Làn nhanh: **78 passed, 4 deselected trong ~8s** (trước: không có khái niệm làn nhanh, mỗi lần 100s).
- Full suite: **82 passed (116s)** — không regression.
- `ruff check .` → **All checks passed** (7 lỗi cơ học đã dọn).
- Test CLI mới: **7 test / 1.5s** thay cho smoke 90s; phát hiện thêm rủi ro SIGABRT của GUI headless.
- File thay đổi:
  - `pytest.ini` — `--timeout=120`; `requirements.txt` — +pytest-timeout, pillow, ruff
  - `ruff.toml` — rule ghim tại repo (mới)
  - `.github/workflows/checks.yml` — CI ruff + pytest làn nhanh (mới); `.gitignore` — cache
  - `tests/test_run_live_cli.py` — 7 test CLI với FakeEngine + GUI giả lập (mới)
  - `AGENTS.md` — tách template, làn nhanh, pointer chuẩn code + setup SAMURAI, cây thư mục
  - `CODING_STANDARDS.md` — chuẩn code cho reviewer (mới)
  - `docs/task/_template.md` — template log tách ra (mới)
  - `docs/samurai-setup.md` — navigation cơ chế hydra/checkpoint (mới)
  - `README.md` — mục kiểm tra chất lượng (sửa)
  - Dọn lint: `src/live_pipeline.py`, `tests/test_metrics_logger.py`, `tests/test_interactive_loop.py`, `tests/test_synthetic_video.py`, `tools/benchmark_sam2_realtime.py`, `tools/demo_tracker_frames.py`

## 🐞 Vấn đề gặp phải & cách xử lý
- `pytest-timeout` không fire khi test nằm ngoài rootdir (`/tmp`) → phải thử lại trong `tests/` mới xác nhận đúng; bài học: probe phải chạy đúng chỗ config được áp.
- Ruff cho kết quả khác default dự kiến (I001/BLE001...) vì đọc rule mặc định ngoài repo → ghim `ruff.toml` để CI/máy nào cũng giống nhau.
- `sed` xoá `import cv2` ở test metrics làm `cv2` không định nghĩa (import lồng còn lại là alias) → sửa tay: import đầu file, bỏ import lồng.
- Test `--display` đầu tiên dùng `try/except cv2.error` → **SIGABRT giết cả pytest**; chuyển sang monkeypatch toàn bộ GUI + scripted `waitKey = q`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Kiểm thủ công trên Windows: `--display` (kéo chuột/r/q), webcam (ticket 03), `--record` live.
- [ ] Colab GPU: video minh hoạ 15–25 FPS + số liệu đối chiếu CPU (ADR-0002) — phase mới, vào bằng `/grill-with-docs` hoặc `/to-spec`.
- [ ] Biểu đồ latency/quỹ đạo từ `metrics.csv` cho báo cáo (cùng phase Colab).
- [ ] (Tuỳ chọn) bật `pre-commit` framework local để hook = CI; CI đã là guardrail phiên bản hoá cho cả nhóm.

## 📚 Tài liệu tham khảo
- Skill `/retro`, `writing-for-agents` (context load vs cognitive load, progressive disclosure).
- ruff docs (`select`/`per-file-ignores`), pytest-timeout docs, GitHub Actions (`setup-python` cache, torch CPU index-url).
- ADR-0002 (số liệu trung thực); `docs/samurai-setup.md` (hydra init trong `sam2/__init__.py`).