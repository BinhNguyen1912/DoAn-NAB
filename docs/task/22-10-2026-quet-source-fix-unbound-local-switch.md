# Ngày 22-10-2026 — Quét source, fix lỗi `switch` UnboundLocalError + defer import sam2

> Log phiên quét kiểm (lint + test nhanh) toàn bộ `src/`, `scripts/`, `tests/` và sửa 2 lỗi phát sinh.

## 🎯 Mục tiêu
- Quét (scan) source: chạy `ruff check .` và `pytest -m "not slow"` để rà lỗi cơ học.
- Sửa mọi lỗi do quét phát hiện để bộ test nhanh và lint xanh.

## 📥 Input
- Repo `DOAN-NAB` tại `D:/DOAN-NAB` (Python 3.14, chưa có venv local; deps cài tạm bằng `uv` vào `/tmp/nab-venv`).
- Quy ước kiểm trong `AGENTS.md` mục 5: làn nhanh `pytest -m "not slow"` + `ruff check .`.

## 🔨 Công việc đã thực hiện
1. Tạo venv tạm `/tmp/nab-venv` (Python 3.14) bằng `uv`, cài `numpy`, `opencv-python-headless`, `pytest`, `pytest-timeout`, `pyyaml`, `pillow`, `torch` (CPU), `matplotlib` — đủ để chạy fast suite không cần checkpoint SAM 2.
2. Chạy `ruff check .`:
   - `F821` `src/live_pipeline.py:252` — dùng tên `switch` chưa gán.
   - `F841` `src/live_pipeline.py:273` — gán `switch` nhưng (theo ruff) không dùng.
3. Chạy `pytest -m "not slow"`:
   - 3 test FAIL vì `UnboundLocalError: cannot access local variable 'switch'` đúng vị trí F821:
     - `tests/test_interactive_loop.py::TestVisualizerIntegration::test_visualizer_hud_va_ghi_video_trong_vong_lap`
     - `tests/test_interactive_loop.py::TestVisualizerIntegration::test_phim_r_reset_quy_dao_visualizer`
     - `tests/test_run_live_cli.py::TestCtrlCFlush::test_display_ctrl_c_van_ghi_metrics_csv`
   - Collection ERROR `tests/test_experiment_occlusion.py`: module `scripts/experiment_occlusion.py` `import sam2` ở top-level → lỗi khi env thiếu `sam2`.
4. Sửa `src/live_pipeline.py`: khởi tạo `switch = False` ngay trước vòng lặp chính (cạnh `last_result = None`). `switch` vẫn được tính lại mỗi frame track ở cuối vòng lặp (dòng 273) để frame kế tiếp dùng. Khởi tạo đảm bảo vòng `track` đầu tiên (vào từ nhánh `select`/`start`) không còn `UnboundLocalError`.
5. Sửa `scripts/experiment_occlusion.py`: defer `from sam2.build_sam import build_sam2_video_predictor` vào một wrapper `_build_sam2_video_predictor()` chỉ gọi trong `main()`. Module giờ import được không cần `sam2` → test `iou`/`run_scenario` (dùng engine giả) chạy được trong fast suite.
6. Chạy lại cả hai gate:
   - `ruff check .` → `All checks passed!`
   - `pytest -m "not slow"` → 189 test pass (không cần `--ignore` bất kỳ file).

## 📤 Output / Kết quả
- Lint xanh, fast suite xanh (189 passed, 0 failed).
- File thay đổi:
  - `src/live_pipeline.py` — thêm khởi tạo `switch = False` trước vòng lặp (sửa `UnboundLocalError` + 2 cảnh báo ruff F821/F841).
  - `scripts/experiment_occlusion.py` — defer import `sam2` vào `_build_sam2_video_predictor()` để module import được trong env thiếu sam2.

## 🐞 Vấn đề gặp phải & cách xử lý
- Môi trường WSL không có `ruff`/`pytest`/`torch` sẵn → dùng `uv` tạo venv tạm và `uvx ruff`; torch CPU cài qua `--index-url https://download.pytorch.org/whl/cpu`. Đây là thiết lập tạm cho phiên quét, không thay đổi `requirements.txt`.
- `F841` của ruff ban đầu tưởng là biến thừa, nhưng thực chất `switch` vẫn được dùng ở dòng 252 — root cause là `F821` (dùng trước khi gán). Sửa bằng khởi tạo biến thì cả hai cảnh báo cùng mất.

## Cập nhật: đã chạy full suite
- Dựng lại venv `/tmp/nab-venv` (Python 3.14) bằng `uv`, cài đủ deps sam2: `torch` (CPU), `torchvision`, `tqdm`, `hydra-core`, `iopath`, `loguru`, `scipy`, `matplotlib`, `opencv-python-headless`, `numpy`, `pyyaml`, `pillow`, `pytest`, `pytest-timeout`; cài `sam2` editable từ `samurai/sam2`.
- `pytest` (không marker, build model thật + propagation): **189 passed in 118.35s**. 4 `FutureWarning` là upstream của torch trong sam2 (`torch.backends.cuda.sdp_kernel` deprecated) — không phải code repo.
- Kết luận: cả 2 gate `ruff check .` và full `pytest` đều xanh, không regression sau 2 fix.

## Cập nhật: môi trường THẬT (không phải /tmp)
- Thay venv tạm `/tmp/nab-venv` bằng `.venv/` **trong repo** (đã `git check-ignore` → nằm trong `.gitignore`), Python 3.14, cài theo README mục 1: `-r requirements.txt`, `torch`+`torchvision` (CPU index), `pip install -e samurai/sam2`, `loguru`, `scipy`.
- Chạy lại từ `.venv`: `ruff check .` → All checks passed; `pytest -m "not slow"` → 185 passed, 4 deselected; `pytest` (full, build model thật) → **189 passed in 128.21s**.

## Cập nhật: sửa 2 gap tài liệu
1. `README.md` mục 1 bước 5 + mục 3 bước 2 (Colab): thêm `scipy` vào lệnh cài — `samurai/sam2/sam2/utils/kalman_filter.py` import `scipy.linalg` nhưng `setup.py` của sam2 và README cũ **không nhắc**, nên clone mới làm theo hướng dẫn sẽ crash ngay khi import predictor.
2. `.gitignore`: thêm `~$*` và `.~lock.*` (file tạm Office/LibreOffice); `git rm --cached docs/~$AnCameraAI.docx` để bỏ file log Word đang bị track (file đã không còn trên đĩa).
- Lưu ý: `docs/DoAnCameraAI.docx` đang ở trạng thái `M` (người dùng sửa đề cương) — **không đụng vào**.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Chạy full suite (`pytest` không marker) trên máy có GPU/Colab nếu cần số liệu GPU cho báo cáo (ADR-0002).

## 📚 Tài liệu tham khảo
- `AGENTS.md` mục 5 (quy trình kiểm: làn nhanh + lint).
- `CODING_STANDARDS.md` (chuẩn defer import nặng).