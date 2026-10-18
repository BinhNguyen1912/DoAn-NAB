# Ngày 16-10-2026 — Fix CI đỏ: test phụ thuộc checkpoint bị gitignore

## 🎯 Mục tiêu
- CI (`checks`) chạy lần đầu sau push → 1 test đỏ. Sửa gốc: test phải chạy được trong môi trường **chỉ có code trong Git**, và test CLI phải chạy được ở CI (không clone SAMURAI).

## 📥 Input
- Log CI: `FAILED tests/test_config.py::TestResolveCheckpoint::test_duong_dan_tuong_doi_giai_theo_repo_root` — `FileNotFoundError: Checkpoint không tồn tại … /home/runner/work/DoAn-NAB/.../sam2.1_hiera_tiny.pt`.
- Nguyên nhân: test cũ assert **sự tồn tại** của checkpoint thật; `samurai/` + `*.pt` bị `.gitignore` → CI không có.
- CI còn 1 test **skip** (`test_run_live_cli.py` dùng `pytest.importorskip("sam2")`) → mất 7 test phủ CLI.

## 🔨 Công việc đã thực hiện
1. `tests/test_config.py::TestResolveCheckpoint` — viết lại 2 test theo `tmp_path` + `monkeypatch REPO_ROOT`: dựng file giả trong `tmp_path/samurai/sam2/checkpoints/…` rồi assert đường dẫn giải đúng = đường dẫn giả. Test chỉ kiểm **quy tắc** (tương đối → REPO_ROOT) và **thông báo lỗi**, không phụ thuộc artifact nào.
2. `tools/run_live.py` — bọc import `sam2.sam2_video_predictor` trong `try/except ImportError` (chỉ dùng để tắt tqdm): module CLI import được khi chưa cài `sam2`; `TrackerEngine.build_default` vẫn import sam2 lazily khi chạy thật.
3. `tests/test_run_live_cli.py` — bỏ `pytest.importorskip("sam2")` + dọn `# noqa: E402`; 7 test CLI giờ chạy cả trong CI.
4. `CODING_STANDARDS.md` — thêm chuẩn: **làn nhanh không được phụ thuộc artifact bị `.gitignore`** (checkpoint/video/`samurai/`); cần file mẫu → `tmp_path` + `monkeypatch`. `.github/workflows/checks.yml` ghi rõ CI không có `samurai/` + checkpoint.

## 📤 Output / Kết quả
- **Mô phỏng đúng môi trường CI** (tạm `mv samurai /tmp/samurai_off`): `ruff` → All checks passed; `pytest -m "not slow"` → **78 passed, 0 skipped, 0 failed trong 3.66s**. Trước đó ở CI: 70 passed, 1 failed, 1 skipped.
- Khôi phục `samurai/` → full suite local **82 passed (118s)**, không regression.
- File thay đổi:
  - `tests/test_config.py` — 2 test resolve checkpoint dùng tmp_path + monkeypatch
  - `tools/run_live.py` — import sam2 có bảo vệ (try/except ImportError)
  - `tests/test_run_live_cli.py` — bỏ importorskip, dọn noqa (7 test chạy được ở CI)
  - `CODING_STANDARDS.md` — chuẩn mới cho test làn nhanh
  - `.github/workflows/checks.yml` — comment nêu rõ môi trường CI

## 🐞 Vấn đề gặp phải & cách xử lý
- CI là guardrail "miễn phí" vừa chứng minh giá trị ngay lần chạy đầu: bắt 1 test phụ thuộc máy và 1 skip che mất 7 test.
- Muốn kiểm chứng thật thì phải **mô phỏng môi trường CI** (cất `samurai/` đi) chứ không chỉ tin "local xanh" — đây là bài học lặp lại của repo (trước đó: test treo chỉ lộ khi chạy pytest thật).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Xem lại tab Actions sau push: cả 2 job phải xanh (nếu codec `mp4v` lỗi trên runner thì báo lại).
- [ ] Giai đoạn 1 (kiểm GUI/webcam trên Windows) — chưa làm.
- [ ] Colab GPU + biểu đồ (phase mới, `/grill-with-docs`).

## 📚 Tài liệu tham khảo
- Log CI GitHub Actions; `CODING_STANDARDS.md` mục Test; `docs/samurai-setup.md`.
