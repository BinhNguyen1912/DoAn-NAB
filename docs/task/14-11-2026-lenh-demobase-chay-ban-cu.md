# Ngày 14-11-2026 — Lệnh `./run demobase` chạy bản demo cũ (dự phòng khi bản web lỗi)

## 🎯 Mục tiêu
- Người dùng cần một đường **dự phòng**: nếu bản web (React + FastAPI trên `main`) gặp sự cố lúc
  demo thì vẫn chạy được **bản demo cũ** (tag `demo-baseline-2026-11-08`, CLI `./run demoip`) mà
  **không phải đổi nhánh** và **không đụng vào `web/`**.
- Yêu cầu ràng buộc: chỉ **thêm 1 lệnh**, web giữ nguyên; truyền được tham số cho `demoip`.

## 📥 Input
- Yêu cầu người dùng (14-11): "setup lệnh checkout qua `demo-baseline-2026-11-08` để phòng nếu web
  lỗi, `./run demoip` truyền tham số, web đừng sửa, thêm mới 1 lệnh này thôi".
- Hiện trạng repo: `main` = `f6f19f5`; tag `demo-baseline-2026-11-08` có `web/src` = **0 file**
  (kiểm bằng `git ls-tree -r --name-only <tag> -- web/src`) ⇒ bản cũ thuần CLI.
- Ràng buộc kỹ thuật:
  - `samurai/`, `models/`, `data/*.mp4` **bị .gitignore** (`.gitignore:12-19`) ⇒ worktree mới của
    tag cũ **không có** checkpoint SAM 2.1 tiny và model mặt ⇒ phải symlink sang bản dùng chung.
  - `./run` của tag cũ gọi `scripts/cam_relay.sh` với đường dẫn Windows hardcode `D:\DOAN-NAB\…` —
    trùng vị trí repo thật nên relay vẫn dùng được.

## 🔨 Công việc đã thực hiện
1. **Tìm nguyên nhân lỗi `env: $'bash\r'`** (người dùng gặp lặp lại sau mỗi lần đổi nhánh):
   - `D:/Program Files/Git/etc/gitconfig` (config **system** của Git for Windows) có
     `core.autocrlf=true`; `~/.gitconfig` của WSL **không** có; repo **không** có `.gitattributes`.
   - Blob trong git **luôn là LF** (kiểm `git show <nhánh>:run` cho 4 nhánh/tag đều LF) ⇒ CRLF chỉ
     sinh ra ở **working tree** khi checkout bằng công cụ Windows (VS Code, `git.exe`, PowerShell).
   - Sửa: `git config core.autocrlf false` (repo-level, thắng config system) + trả 176 file về LF
     bằng `git checkout -- .` — trước đó đã kiểm `git diff --ignore-cr-at-eol --stat` **rỗng**
     (không có thay đổi nội dung nào, chỉ line ending) nên không mất dữ liệu.
2. **Thêm lệnh `demobase` vào `run`** (nhánh `feat/run-demobase`):
   - `BASELINE_TAG` mặc định `demo-baseline-2026-11-08`, đổi được qua env `CAM_BASELINE_TAG`.
   - `ensure_baseline()`: `git worktree add --detach .baseline <tag>` (đường dự phòng
     `git archive | tar -x` nếu không dùng được worktree) ⇒ **không đổi nhánh, không đụng `web/`**.
   - `_baseline_link_resources()`: symlink `samurai`, `models` và **chỉ** những `data/*.mp4` bản cũ
     chưa có (không ghi đè/xoá file nào).
   - File đánh dấu `.baseline/.demobase-tag`: đổi `CAM_BASELINE_TAG` ⇒ `git -C .baseline checkout
     --detach <tag>` rồi tạo lại symlink.
   - Cú pháp: `./run demobase [lệnh con] [tham số…]` — mặc định lệnh con là `demoip`, mọi tham số
     đẩy nguyên sang `run_live.py` (`./run demobase demoip --max-frames 100`).
   - Tag không tồn tại ⇒ in hướng dẫn `git fetch --tags origin`, thoát mã 1 (không chạy nhầm bản mới).
3. `.gitignore`: thêm `/.baseline/` (kèm 2 dòng giải thích) để worktree không làm bẩn `git status`.
4. `tests/test_run_script.py`: thêm `"demobase"` vào danh sách lệnh mà `./run help` phải in.

## 📤 Output / Kết quả
- Lệnh mới chạy được trên máy này (WSL, CPU, conda `samurai`):
  - `./run demobase help` lần 1 (dựng worktree): **2,8 s**, sau đó **1,9 s** (dùng lại).
  - Help của bản cũ **không** có mục `WEB (API …)` (đúng là code tag cũ); `./run demobase env` in
    `repo: /mnt/d/doan-nab/.baseline`, `env: samurai`, `DISPLAY=:0`.
  - `CAM_BASELINE_TAG=demo-web-e2e-2026-11-08 ./run demobase help` ⇒ có mục WEB (đổi tag đúng).
  - Tag sai (`CAM_BASELINE_TAG=khong-co-tag-nay`) ⇒ `[demobase] không checkout được tag …`, không đổi
    nhánh của người dùng.
- Kiểm tra: `./run lint` **All checks passed**; `./run test` **906 passed, 5 deselected** (thêm 5 test `TestDemobase`).
- Hành vi đã kiểm tay: `./run demobase help` → mã 0, in help **bản cũ**; `./run demobase -h` → mã 0, **không** bật relay; `CAM_BASELINE_TAG=khong-co-tag-nay` → mã **1** + `không thấy tag …`; `CAM_BASELINE_DIR=/tmp/fakebase` (có `run`, không phải git) → mã **1** + câu sửa.
- File thay đổi:
  - `run` — thêm `ensure_baseline()`/`_baseline_link_resources()` + nhánh `demobase)` + 4 dòng help.
  - `.gitignore` — `/.baseline/`.
  - `tests/test_run_script.py` — chốt tài liệu: help phải có `demobase`.
  - `docs/task/14-11-2026-lenh-demobase-chay-ban-cu.md` — log này.

### Lần chạy thật qua `demobase` (14-11 06:03) — artifact đã lưu
- Chạy `demoip` của bản cũ (tag `demo-baseline-2026-11-08`) qua relay
  `http://172.19.176.1:8090/snapshot.jpg`, `image_size 320`, re-ID bật ⇒ sinh frame + bám vật,
  ghi được 147 frame.
- Artifact: `data/demoip_1114-060249_{metrics.csv,summary.json,run_info.json}` —
  `mean_latency_ms` 325,7 · `p95_latency_ms` 387,4 · `effective_fps` 3,07 · `lost_ratio` 0,435
  (`lost_count` 64) · `reacquired_count` 19 · `rss_mb_peak` 680,8 · CPU 358 % (1 lõi) = 44,8 % máy 8 lõi.
- `run_info.git_rev = f3cca78` = đúng tag `demo-baseline-2026-11-08` (code **cũ**); code cũ **không**
  ghi field `git_dirty`. ⇒ **Cấm** trích các số này làm số báo cáo/nghiệm thu; đây chỉ là bằng chứng
  lệnh `demobase` chạy được. `effective_fps` 3,07 khớp với việc bản cũ chạy VOS **mỗi frame** bằng
  model @320 trên CPU (chưa có hybrid VOS+LK của `main`) chứ không phải lỗi của `demobase`.

### Kiểm tra lại trước khi merge (14-11)
- `./run lint` — All checks passed.
- `./run test` lần 1: **1 failed** `tests/test_live_tracking.py::TestVeSinhWorkerCu::test_reap_worker_cu_con_song`
  (`proc.poll()` còn `None` ngay sau khi dọn worker) → nghi flake; chạy riêng class đó **6 passed**,
  chạy lại cả làn nhanh **906 passed, 5 deselected** ⇒ **flake do tải**, không phải hồi quy của nhánh
  (nhánh này không chạm `src/api/adapters/worker_source.py`). Chưa sửa test; ghi nhận để xử lý riêng.

## 🔎 Review độc lập (AGENTS.md mục 9.1)
- **Ai:** agent `reviewer` (read-only, không phải phiên đã code); phạm vi `git diff main -- run .gitignore tests/test_run_script.py` + log này.
- **Verdict:** mergeable, **0 P0**; 12 điểm "đã kiểm, không phải lỗi" (symlink tương đối đúng khi đổi CWD; `exec bash` giữ exit code và bản cũ tự `activate_env`; `git checkout` không xoá symlink — reflog `.git/worktrees/-baseline/logs/HEAD` có 2 lần checkout thật; `^{commit}` là bắt buộc vì tag annotated; không đổi nhánh, không đụng `web/`).
- **P1 — ĐÃ SỬA:** nhánh "đúng tag rồi" so hai `rev-parse` mà **cả hai cùng rỗng** (khi `.baseline` không phải repo, hoặc tag không tồn tại) ⇒ `"" = ""` đúng ⇒ ghi mark cho tag ma rồi chạy code cũ, thoát 0. Sửa: kiểm tag (biến `want`, phải khác rỗng) **trước** khi dựng/đổi bản; nhánh nhanh (mark khớp) không đòi tag phải có. Test mới: `TestDemobase::test_tag_khong_ton_tai_bao_loi_ma_1`.
- **P1 (khả năng test) — ĐÃ SỬA:** thêm `CAM_BASELINE_DIR` để test không đụng `.baseline/` thật; 5 test mới trong `TestDemobase` (mặc định `demoip`, tham số đi nguyên, chọn lệnh con, `-h` không bật relay, tag sai → mã 1).
- **P2 — ĐÃ SỬA:** (a) `.baseline` hỏng/không phải repo ⇒ không còn "bó tay im lặng", in đúng câu sửa (`rm -rf .baseline && git worktree prune`); (b) `checkout -f` dọn cây checkout dở (Ctrl+C giữa lúc dựng) trước khi ghi mark; (c) symlink đứt được tạo lại (`ln -sfn` + `-L`) và `_baseline_link_resources` chạy cả ở nhánh nhanh; (d) in rõ file ghi ra `.baseline/data/`; (e) `git worktree prune` trước `worktree add`.
- **P3 — ĐÃ SỬA:** `./run demobase -h|--help` ⇒ in help bản cũ, **không** bật relay; in tham số bằng `%q` (không mất quoting khi hiển thị).
- **P3 — KHÔNG SỬA (có lý do, đã đo lại):** dọn `git status` của `.baseline` (mark + symlink hiện `??`). Thử ghi `info/exclude` của worktree: git **không** đọc file đó (`git -C .baseline check-ignore -v .demobase-tag` thoát 1), còn ghi vào `.git/info/exclude` dùng chung thì che cả repo chính ⇒ bỏ, ghi chú trong code. Repo chính vẫn sạch (`/.baseline/` đã ignore).
- **Nợ lại:** `git_dirty` của artifact đo **sinh từ bản cũ** sẽ là `true` (symlink + mark trong `.baseline`) ⇒ không dùng số từ `demobase` làm số báo cáo; số báo cáo phải chạy trên `main`.

## 🐞 Vấn đề gặp phải & cách xử lý
- **CRLF tái phát sau mỗi lần đổi nhánh**: do `core.autocrlf=true` ở config system của Git for
  Windows (bằng chứng: `D:/Program Files/Git/etc/gitconfig`). Đã chặn ở repo-level. **Chưa** thêm
  `.gitattributes` (cần PR riêng) ⇒ nếu sau này ai commit từ Windows với autocrlf bật, vẫn có thể
  sinh lại; cách chặn tận gốc: `* text=auto eol=lf` + `*.cmd text eol=crlf`.
- **VS Code trên Windows** có thể tự đổi LF→CRLF khi *save* (`files.eol`) — không liên quan git,
  không sửa được từ repo (phải set `"files.eol": "\n"` trong VS Code).
- **Đổi `CAM_BASELINE_TAG` khi `.baseline/` đã tồn tại**: bản đầu chỉ `return 0` khi thấy
  `.baseline/run` ⇒ đổi biến env mà vẫn chạy tag cũ (sai âm thầm). Sửa bằng file đánh dấu
  `.demobase-tag` + `git checkout --detach` (đã test 2 chiều).
- Ứng dụng **chưa** chạy thật `./run demobase` (mặc định `demoip`) vì nó mở cửa sổ + bật relay và
  chờ người dùng kéo chuột chọn vật — cần người dùng chạy tay.
- Ghi nhận ngoài phạm vi: `.scratch/camera-ai-realtime/issues/21-…md` đang có 13 dòng sửa **chưa
  commit** từ trước phiên này (không phải thay đổi của phiên này) — không đưa vào commit.

## 📌 Việc cần làm tiếp (Next steps)
- [x] Đã chạy `./run demobase` (mặc định `demoip`) — qua relay (không phải webcam trong WSL, xem
      AGENTS.md mục 6), có frame + bám vật; artifact ghi ở mục "Lần chạy thật qua `demobase`".
      **Chưa** có xác nhận bằng mắt trong phiên này (người dùng tự xem cửa sổ).
- [ ] Flake `TestVeSinhWorkerCu::test_reap_worker_cu_con_song` dưới tải nặng — nới/thay bằng chờ có
      điều kiện (`proc.wait(timeout=…)`) trong PR riêng.
- [ ] Cân nhắc thêm `.gitattributes` (`* text=auto eol=lf`, `*.cmd text eol=crlf`) ở PR riêng để
      chặn CRLF tận gốc.
- [ ] Nếu cần mở web từ bản cũ: `CAM_BASELINE_TAG=demo-web-e2e-2026-11-08 ./run demobase web`.
- [ ] PR `feat/run-demobase` → `main` (review độc lập đã xong, P0 = 0).
- [ ] (P3 còn nợ) Không dùng số đo sinh từ `demobase` làm artifact báo cáo vì `git_dirty = true`.

## 📚 Tài liệu tham khảo
- `AGENTS.md` mục 6 (kinh nghiệm đo), mục 7b (1 nhánh/nhiệm vụ), mục 9.1 (review độc lập).
- `docs/samurai-setup.md` — vì sao `model_cfg: configs/samurai/…` là tên trong package `sam2`
  (không tạo thư mục `configs/samurai/` trong repo).
- Git: `git help worktree`, `core.autocrlf` (git-scm.com/docs/git-config).
