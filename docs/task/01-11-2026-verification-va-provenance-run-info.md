# Ngày 01-11-2026 — Verification + provenance `run_info.json` cho lần đo local

> Phiên nối tiếp 29-10 (demo sau khi sửa `min_side 24→8`). Mục đích: chốt trạng thái repo
> trước khi chuẩn bị hồ sơ, rồi vá lỗ hổng "lần đo thất bại không tự giải thích được".

## 🎯 Mục tiêu
- Chạy verification (ruff + pytest làn nhanh), xử lý 6 file `data/fast_1029-*` chưa commit.
- Rà xem đồ án còn cần cải thiện gì (không thêm feature nếu không cần).
- Vá gap: `./run fast` sinh số liệu nhưng KHÔNG ghi `run_info.json` → lần đo thất bại
  không phân biệt được "vật rời khung" (đúng) với "re-ID lỗi" (bug).

## 📥 Input
- Repo `DoAn-NAB` nhánh `main` (commit `cb6cb5d`).
- 6 file đo sinh ngày 29-10 bởi `./run fast` (3 cặp metrics.csv/summary.json).
- Yêu cầu người dùng: "làm đi, rồi xem dự án có cần cải thiện gì thêm không".

## 🔨 Công việc đã thực hiện
1. **Verification baseline**: `.venv/bin/ruff check .` → sạch; `.venv/bin/python -m pytest -m "not slow"`
   → **275 passed, 4 deselected** (29,55 s). Rà `TODO/FIXME/HACK` → 0.
2. **Commit 3 lần đo 29-10** (`7954707`) — đều là bằng chứng trung thực theo ADR-0002:
   - `211544`: 93f, 5,13 FPS, 1 reacquire.
   - `212010`: 234f, **75 % lost, 0 reacquire** — bằng chứng giới hạn (chưa giải thích được).
   - `212632`: 576f, 5,46 FPS, **17 reacquire** — demo chính (khớp `39a4ede`).
3. **Phát hiện gap**: chỉ `scripts/colab_run_all.py:103 write_run_info` ghi `run_info.json`;
   đường local `./run fast` không ghi. `.gitignore` đã whitelist `!data/*_run_info.json`
   nhưng local không tạo file → lần `212010` (mất dấu từ f58 đến hết) không chẩn đoán được.
4. **TDD vá gap** (seam chốt trước khi viết test):
   - `src/metrics_logger.py` thêm `run_info_path_for(metrics_csv, metrics_summary)` (pure) —
     suy `X_summary.json`/`X_metrics.csv` → `X_run_info.json`, giữ nguyên kiểu phân cách,
     ưu tiên summary, không có gì → `None`.
   - `src/metrics_logger.py` thêm `write_run_info(path, timestamp=None, **fields)` —
     ghi JSON, tự tạo thư mục cha, tự thêm `timestamp` ISO.
   - `tools/run_live.py`: `_git_rev()` (git SHA, `"unknown"` khi không phải repo) +
     `_write_run_info(args)` gọi trong `_finish_metrics` sau khi ghi summary.
   - Test mới `tests/test_run_info.py` (7 test) + 2 test wiring trong `tests/test_run_live_cli.py`
     + 1 assert provenance ở test `main()` end-to-end.
5. Cập nhật `run` (help `fast` + dòng `[fast] ghi:`), `README.md` (mục xuất artefact).

## 📤 Output / Kết quả
- Làn nhanh: **284 passed, 4 deselected** (32,32 s); `ruff check .` sạch.
- Lần đo giờ tự giải thích được: `data/fast_<mốc>_run_info.json` chứa `git_rev`, `source`,
  `image_size`, `reanchor_every`, `max_frames`, `reid*`, `lost_score_threshold`, `timestamp`.
- Các lệnh khác có `--metrics-summary` (vd `./run reid`) cũng tự sinh run_info (không cần sửa).
- File thay đổi:
  - `src/metrics_logger.py` — thêm `run_info_path_for`, `write_run_info`.
  - `tools/run_live.py` — `_git_rev`, `_write_run_info`, gọi trong `_finish_metrics`.
  - `tests/test_run_info.py` (mới), `tests/test_run_live_cli.py` — test provenance.
  - `run`, `README.md` — tài liệu lệnh đường dẫn run_info.
  - `data/fast_1029-{211544,212010,212632}_*` — commit số liệu đo 29-10.

## 🐞 Vấn đề gặp phải & cách xử lý
- `ruff`/`pytest` không có trong PATH (dùng `.venv/bin/`, không phải conda `samurai`) — chạy
  qua `.venv/bin/...` để khớp môi trường.
- Lần đo `212010` (75 % lost) **chưa kết luận** được nguyên nhân: CSV cũ không ghi nguồn/config.
  Từ nay run_info sẽ trả lời được; riêng lần 212010 chỉ còn cách xem lại video (nếu còn).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Chạy `/retro` để chốt phiên build re-ID (đề xuất cải environment, không phải code).
- [ ] Nếu còn video lần `212010`: xem lại để ghi chú "vật rời khung" hay "re-ID lỗi"
      vào báo cáo (dùng run_info của các lần chạy mới để tránh lặp lại).
- [ ] Khi chạy lại `./run fast`: xác nhận có `data/fast_<mốc>_run_info.json`.

## 🧪 Bổ sung — Retro và sửa 2 phát hiện

Chạy `/retro` trên chuỗi build re-ID (25-10 → 29-10) + phiên này. Phát hiện 2 việc, đã sửa ngay:

**1. Ngưỡng re-ID có 3 giá trị ở 5 file (nặng nhất).** `reid_obj_ncc_min` thực tế = **0.0 (TẮT)**
(khoá bởi `test_reid.py::TestCauHinhMacDinh`), nhưng README nói "bật mặc định 0,70",
`docs/tom-tat-do-an.md` nói 0,70, comment `configs/default.yaml` nói 0,75, `src/config.py` lại gọi
NCC là "cổng CHÍNH". Nguyên nhân: **6 lần đổi ngưỡng trong 3 ngày** (`3a2d447`→`44bbbee`→
`1eabb3c`→`2f7b35b`→`f6927fa`), mỗi lần sync 3 chỗ bằng tay.
- Sửa 5 chỗ về đúng: cổng chính = **cosine 0,60**, NCC = **cổng PHỤ, mặc định TẮT (0.0)**,
  khoảng dùng được **0,5–0,6** (0,95 là sai — ca đúng có lúc chỉ 0,55).
- Thêm `tests/test_threshold_consistency.py` (5 test): bắt buộc **4 nguồn khớp nhau**
  (`DEFAULTS` ↔ `configs/default.yaml` ↔ hằng số `reid.py` ↔ tham số `ReIdSession`) + tài liệu
  không được khẳng định "bật mặc định" khi cấu hình đang TẮT. Đây đúng lớp bug 27-10
  (`reid.py` truyền `min_side=24` đè hằng số → bản sửa "vật mảnh" không có tác dụng).

**2. `AGENTS.md` §5 chép lệnh kiểm tra và lệnh đó sai trên máy này.** §5 ghi `ruff check .` /
`python -m pytest -m "not slow"`; chạy `ruff check .` → **`ruff: command not found`** (phải mò ra
`.venv/bin/ruff`). Repo đã có `./run lint` / `./run test` / `./run testall` tự chọn môi trường.
- §5 nay trỏ `./run lint` + `./run test` (giữ câu "CI chạy `ruff check .`" làm hợp đồng CI).
- Sửa `run` help: `test nhanh (~10 giây)` → `~30 giây` (đo thật 19–34 s).

**Kiểm chứng 2 lệnh vừa ghi vào AGENTS.md (chạy thật):** `./run lint` → All checks passed;
`./run test` → **289 passed, 4 deselected** (19,6 s).

**Còn lại (đề xuất, chưa làm):** `scripts/calibrate_reid.py` — quét lưới
`reid_obj_threshold` × `reid_obj_ncc_min` trên clip có nhãn, in bảng (đúng/sai nhận lại).
Đó là gốc của phát hiện 1 (hiệu chỉnh không có nhà đo) → nên đi qua `/to-spec` thay vì sửa tay.

## 📚 Tài liệu tham khảo
- `docs/adr/0002-giu-laptop-cpu-demo-live-colab-cho-offline.md` (báo cáo trung thực, số liệu tái tạo được).
- `scripts/colab_run_all.py:103` — mẫu `write_run_info` sẵn có.
- `docs/agents/issue-tracker.md`, `AGENTS.md` mục 2 (quy ước log).
