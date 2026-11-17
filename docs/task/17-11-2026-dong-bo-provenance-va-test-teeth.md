# 17-11-2026 — Đồng bộ provenance sau audit + test "có răng" cho 4 PR trong ngày

## Mục tiêu

Xử lý kết quả **audit sau merge** (reviewer độc lập, phạm vi `f753663..46abf0c` — 4 PR của ngày 17-11).
Kết luận của audit: **0 P0, 0 P1**; còn 2 P2 + 5 P3 đều thuộc docs/test/telemetry. Việc của phiên này là
đóng những mục đó, không đổi hành vi runtime.

## Input

- Báo cáo audit (đọc tĩnh): 2 P2 (`git_rev`/số trong ticket đã đóng không khớp artifact; retry của test
  #22 im lặng) + 5 P3 (câu "~106 chứ không ~95" trong `docs/so-lieu-bao-cao.md`; `dump_ms` lệch thế hệ;
  bất biến `age_n == frames` chưa được ghim; `api.ts` chưa cho `null`; test cũ `_dumped.discard`;
  `test_run_script` ghi vào `data/` của repo).
- Trạng thái `main` @ `147a81a`; `./run lint` xanh, `./run test` 1335 passed.

## Công việc đã thực hiện

| Audit | Đã làm |
|---|---|
| P2 ticket **#24** dẫn số của artifact **đã bị thay** (`1f0c89a`, 9,5 · vos 82,1 · p95 105,53) | Answer + thân ticket nay dùng bộ **`3cc0248`**: 9,33 ± 0,55 · vos 87,33 ± 4,52 · pre 10,96 · p95 109,9 ± 9,32, kèm câu "bộ số 1f0c89a đã bị thay thế" |
| P2 ticket/log **#22** dẫn `7f7e806` | đã sửa sang rev còn sống (`ca46b31`, artifact sinh lại đợt 3 trong PR #34) |
| P2 retry #22 **im lặng** khi lần 2 đạt + docstring "không thể lọt qua" | đã sửa trong PR #34 (`warnings.warn` + "hồi quy **ổn định** vẫn bị bắt") |
| P3 câu "vì sao **~106** chứ không ~95 ms" (số cũ, và `--check` không so văn bản) | generator `scripts/so_lieu_bao_cao.py` nay in phép cộng **đúng theo artifact**: tuổi **98,9** = `vos_ms` 87,3 + `pre_ms` 11,0 + `post_ms` ~0,6 (p95 = 109,9); sinh lại `docs/so-lieu-bao-cao.md` |
| P3 `dump_ms` lệch thế hệ so với `post_ms` | đã sửa trong PR #32 (gán cùng lock) |
| P3 bất biến "mỗi frame PHÁT ⇒ đúng 1 mẫu age" chưa ghim | `tests/test_live_tracking.py`: thêm `assert status["age_n"] == status["frames"]` cho **cả** `vos_every=1` và `6` |
| P3 test cũ dùng `session._dumped.discard(5)` (lối tắt đã bị bác) | **xoá** test đó; đường thật đã do `test_ghi_de_trong_CUNG_phien_phai_canh_bao` canh |
| P3 `api.ts` chưa cho `null` + UI không in `n` | PR #33 |
| P3 `test_run_script` ghi `data/` của repo (rác khi kill, không an toàn xdist) | `run` hỗ trợ `DOAN_DATA_DIR`; test dùng `tmp_path` + `monkeypatch.setenv`, và assert **không** ghi gì vào `data/` |

### Thêm mới: `./run provcheck` — kiểm `git_rev` của artifact bằng máy

Vì sao: chỉ trong **một ngày** tài liệu/ticket/log đã **3 lần** dẫn một `git_rev` đã chết
(rebase/squash/artifact sinh lại đè). Một lệnh `git cat-file -e` là đủ để bắt.

- `scripts/check_artifact_provenance.py`: quét `data/*_metrics.json`, ba trạng thái **không gộp**:
  `ok` (rev là tổ tiên của `HEAD`), `lech` (rev còn nhưng không thuộc cây này — cảnh báo), `chet`
  (không tồn tại — chặn với `--nghiem`).
- **Phát hiện ngay 1 ca thật**: `data/drift_2026-11-08_metrics.json` khai
  `git_rev ee9f256a…f0b0b8f0b0b8` — **không tồn tại** trong repo (nghi gõ tay lúc ghi artifact 08-11).
  Số đo vẫn dùng được (10 lần chạy thật, có lệnh từng lần) nhưng log `docs/task/08-11-2026-do-cai-gia-noi-suy-lk-va-nguong-nhieu.md`
  từng khẳng định "kiểm bằng `git show ee9f256:src/live_tracking.py`" — câu đó **không tái lập được**,
  đã **đính chính** trong log. Artifact để nguyên (không sửa tay bằng chứng đã commit) và nằm trong
  `CHO_PHEP` của script **kèm lý do**.
- 2 artifact còn lại (`empty_window_2026-11-10`, `live_web_relay_2026-11-10`): rev `eb008e3`/`da1d671`
  **chỉ tồn tại trong object LOCAL** — nhánh bị rebase trước khi push, nên trong **clone sạch** (đúng
  điều kiện CI) `git cat-file -e` thất bại. Số của chúng là số relay webcam thật dùng trong
  `docs/doi-chieu-yeu-cau-gvhd.md` (không sinh lại được nếu không có camera đúng thời điểm) ⇒ đưa vào
  `CHO_PHEP` kèm lý do "CẤM dẫn rev". **Phát hiện này chỉ lộ ra khi chạy trong clone sạch** — trên máy
  dev chúng hiện là `lech` (object còn trong `.git`), tức máy dev "che" mất lỗi; đây là lý do CI phải
  chạy kiểm này chứ không thể tin vào lần chạy tay.
- CI: job mới `git_rev của artifact` (`fetch-depth: 0` + `--nghiem`) ⇒ rev chết **mới** làm đỏ PR.

### Hai nợ "ngoài phạm vi 4 PR" đã tách ticket

- **#35**: frame `engine.start()` đi qua `_record_vos` **và** `_store_vos` ⇒ `stability` nhận **2 mẫu**
  cho cùng một frame, một mẫu là `IoU(mask, mask) = 1,0` ⇒ số "nhấp nháy" bị thổi nhẹ ở đầu phiên.
- **#36**: chọn ô **giữa phiên** ⇒ `mask_0000NN.png` là frame NN của **phiên**, không phải của clip ⇒
  mIoU lệch nếu dump qua UI (đường `--bbox` không bị).

## Output / Kết quả

- `./run lint` xanh · `./run test` **1339 passed**, 5 deselected (trước 1335: +5 test mới cho
  `provcheck`, +1 assert bất biến `age_n == frames`, −1 test cũ bị xoá).
- `./run provcheck`: **44 ok · 2 lệch · 1 chết-đã-biết · 0 chết-mới** (mã thoát 0; `--nghiem` cũng 0).
- `scripts/so_lieu_bao_cao.py --check` xanh sau khi sinh lại `docs/so-lieu-bao-cao.md`.
- Hành vi runtime **không đổi** (chỉ docs/test/script kiểm tra + `run` thêm `DOAN_DATA_DIR`).

## Vấn đề & cách xử lý

- **Không sửa tay artifact**: `git_rev` chết của `drift_2026-11-08_metrics.json` là bằng chứng đã commit
  — sửa nó là làm giả dữ liệu. Cách xử lý: allowlist có lý do + đính chính **lời khẳng định** trong log
  (chỗ sai thật), và để `--nghiem` chặn từ nay.
- **Đánh số ticket trùng**: ticket "nợ reap" tạo ở nhánh #34 (#34) trong khi nhánh này tạo #34 khác ⇒
  đổi bản mới thành **#35**, và ticket "chọn ô giữa phiên" là **#36**. Bài học: `tracker` đánh số theo
  thư mục hiện tại, nên khi làm song song nhiều nhánh phải kiểm số trước khi tạo.

## Next steps

- PR #33 (FE `n` cỡ mẫu) và PR #34 (P2/P3 của #22) đang chờ review độc lập ⇒ merge theo thứ tự sau khi
  review xong; PR này (#37) không phụ thuộc hai PR đó nhưng chạm `tests/test_live_tracking.py` nên
  rebase sau cùng.
- Ticket #35, #36 (mới), #34 (reap), #14, #11 — xem frontier.
- Chờ người dùng: silhouette ≥ 30 frame `binh1` (mIoU phân đoạn thật), clip chai đen (#11), clip
  drift-trong-khung (#14), relay webcam trước demo.

## Tài liệu tham khảo

- Báo cáo audit: phiên `reviewer` sau merge 17-11 (kết luận "mergeable, 0 P0/P1").
- AGENTS §6 (`0/None ≠ đã đo`, "số đo phải có `git_rev` == commit đang chạy"), §9.1 (review độc lập).
- `scripts/check_artifact_provenance.py`, `.github/workflows/checks.yml` (job `provenance`).
