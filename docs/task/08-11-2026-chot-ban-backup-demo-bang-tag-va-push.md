# Ngày 08-11-2026 — Chốt bản backup demo bằng tag và push lên GitHub

## 🎯 Mục tiêu
- Chốt một **bản code đã kiểm chứng** làm mốc để quay lại khi thử tính năng mới bị lỗi
  (đặc biệt trước khi bắt đầu thêm backend FastAPI + frontend React).
- Push toàn bộ công việc còn nợ trên nhánh `main` lên GitHub.
- Đánh dấu bản đó bằng **tag** (không đổi được, khác với nhánh) để có thể checkout lại bất cứ lúc nào.

## 📥 Input
- Yêu cầu người dùng: "push code lên, ghi nhớ commit, để sau có lỗi thì dùng bản commit này để chạy backup demo lại".
- Trạng thái repo trước khi làm: nhánh `main` đang **ahead 19 commit** so với `origin/main`, working tree sạch, chưa có tag nào.
- Lệnh kiểm chứng của repo: `./run lint` (CI chạy `ruff check .`), `./run test` (CI chạy `pytest -m "not slow"`).

## 🔨 Công việc đã thực hiện
1. Kiểm tra trạng thái git: `git status --short`, `git branch -vv`, `git remote -v`, `git tag`.
   → Working tree sạch, `main` ahead 19 commit, remote `https://github.com/BinhNguyen1912/DoAn-NAB.git`, chưa có tag.
2. **Chạy kiểm chứng trước khi tag** (theo `AGENTS.md` §5 — không tag một bản chưa đo):
   - `./run lint` → `All checks passed!`
   - `./run test` → `362 passed, 5 deselected in 35.02s`
3. Tạo **annotated tag** `demo-baseline-2026-11-08` trỏ vào commit `f3cca78`, nội dung tag ghi rõ:
   trạng thái lint/test, các lệnh demo (`./run demo`, `./run fast`, `./run demoip`) và cách quay lại nhánh `main`.
4. `git push origin main` → `cb6cb5d..f3cca78  main -> main` (19 commit đã lên remote).
5. `git push origin demo-baseline-2026-11-08` → `* [new tag] demo-baseline-2026-11-08 -> demo-baseline-2026-11-08`.
6. Kiểm chứng lại sau khi push:
   - `git ls-remote --tags origin` → tag có trên remote, trỏ đúng `f3cca78`.
   - `git rev-list --left-right --count origin/main...HEAD` → `0  0` (main đồng bộ hai chiều).
   - `git status --short` → rỗng (working tree sạch).

## 📤 Output / Kết quả
- **Bản backup demo đã có trên GitHub**, bất biến, không thể bị sửa nhầm:
  - Tag: `demo-baseline-2026-11-08`
  - Commit: `f3cca78` — *research: VOS nao dat 25-30 FPS tren CPU — bang 11 model + bo sung do that encoder RepViT*
- Số liệu kiểm chứng tại mốc tag: **lint xanh, 362 test pass (35,02 s)**, working tree sạch.
- Cách khôi phục khi bản mới bị lỗi:
  ```bash
  git checkout demo-baseline-2026-11-08   # quay về bản đã kiểm chứng
  ./run demo                              # webcam mượt + ghi data/webcam_smooth.mp4 + CSV
  ./run fast                              # image_size 256 (~6,5 FPS) + tự ghi video/CSV/JSON
  git switch main                         # xong thì về lại nhánh chính
  ```
- Liệt kê file thay đổi:
  - `docs/task/08-11-2026-chot-ban-backup-demo-bang-tag-va-push.md` — log phiên này (file duy nhất thêm mới).

## 🐞 Vấn đề gặp phải & cách xử lý
- **Nhánh `main` đang nợ 19 commit chưa push** → nếu máy hỏng sẽ mất các kết quả nghiên cứu
  ngày 04–08/11 (trần realtime CPU, encoder RepViT, kiến trúc hybrid). Đã đẩy hết lên remote.
- **Tag annotated vs lightweight:** chọn annotated (`git tag -a`) vì nó lưu người tạo, ngày tạo
  và message. Message chứa sẵn các lệnh demo + số liệu test, nên chỉ cần
  `git show demo-baseline-2026-11-08` là biết bản này chạy được gì — không phải mở file nào khác.
- **Tag không tự đi theo commit mới:** sau khi tag, mọi commit tiếp theo (như log này) **không**
  làm thay đổi bản backup. Đây chính là điều cần: tag luôn trỏ đúng `f3cca78`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Bắt đầu **Phase 0** của lộ trình web: `src/api/` (FastAPI + health + schema job), `src/worker/stub.py`, `tests/test_api.py`.
- [ ] Trước khi thêm backend, chốt: chạy trong **WSL** hay trên **Windows** (quyết định cách gọi subprocess tới `tools/run_live.py`).
- [ ] Ba ngày tới: giữ đúng phạm vi MVP đã cắt (bỏ live streaming, bỏ Docker, bỏ DB/Redis, bỏ GPU worker).
- [ ] Đánh tag mới (`demo-baseline-<ngày>`) sau mỗi mốc chạy được, để luôn có đường lùi.

## 📚 Tài liệu tham khảo
- `AGENTS.md` §2 (log bắt buộc), §5 (lệnh kiểm chứng `./run lint`, `./run test`), §6 (số đo đã có).
- `docs/task/_template.md` — khuôn log này.
- `docs/research/08-real-time-25fps-tren-cpu-igpu.md` + `docs/research/11-do-encoder-repvit-tren-cpu-va-tran-realtime.md`
  — cơ sở cho nội dung tag (trần realtime ~18–22 FPS, encoder RepViT nhanh 2,2–3,2×).
