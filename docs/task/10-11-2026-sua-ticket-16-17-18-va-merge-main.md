# Ngày 10-11-2026 — Sửa 3 ticket còn nợ (16, 17, 18) + merge 3 nhánh vào `main`

> Tiếp ngay sau phiên 09-11 (3 nhánh watchdog / bằng chứng camera thật / chẩn đoán chất lượng bám).
> Việc ở đây là **đóng nợ kỹ thuật** đã ghi ticket trong lúc review, không phải tính năng mới.

## 🎯 Mục tiêu
1. **Ticket 17** — `_drift_window` có nguồn ghi **ngoài** `_stats_lock` ⇒ có thể
   `RuntimeError: deque mutated during iteration` ⇒ luồng VOS chết giữa demo (`state=error`).
2. **Ticket 16** — phiên đang `error` rồi bấm Bật phát: `state` giữ `error` suốt 20–240 s nạp worker
   ⇒ UI hiện `role="alert"` + `/api/live/stream` trả 409 "Phiên live đã dừng vì lỗi: Đang mở …".
3. **Ticket 18** — API không phân biệt `stability = 0` ("tệ nhất"/"vừa mất dấu") với "chưa đo".
4. Merge 3 nhánh 09-11 vào `main` (máy không có `gh`; người dùng yêu cầu tự duyệt).

## 📥 Input
- 3 nhánh đã review: `fix/health-mode-raw-va-message-409` (4 vòng), `feat/bang-chung-camera-that`
  (1 vòng), `feat/chan-doan-chat-luong-bam` (4 vòng).
- Ticket 16/17/18 trong `.scratch/camera-ai-realtime/issues/`.

## 🔨 Công việc đã thực hiện

### Ticket 17 — một nguồn ghi, luôn dưới lock
- `src/live_tracking.py::_record_drift`: `append` + `_apply_drift_locked()` trong **cùng**
  `with self._stats_lock`. Đây là chỗ ghi thứ nhất; chỗ thứ hai (`_update_stats_locked`) vốn đã
  trong lock ⇒ nay **mọi** lần ghi `_drift_window` đều dưới lock.
- Test `TestDriftWindowChiMotNguonGhiTrongLock`: 2 thread ghi + 1 thread duyệt deque **kiểu Python**
  trong lock, hạ `sys.setswitchinterval(1e-6)` để việc chen ngang xảy ra thật, và dùng `deque` tự
  theo dõi — `append` nào chạy khi **không** giữ lock thì ghi lỗi.
  - Vì sao cần "deque tự theo dõi": CPython chỉ chuyển GIL mỗi 5 ms nên vòng duyệt 200 phần tử
    (vài µs) **không** bị chen ngang ⇒ test stress thuần xanh cả khi còn lỗi (đã thử: bản stress
    thuần xanh 2/2 lần với code còn lỗi).
  - Đã kiểm "có răng": trả `append` ra ngoài lock ⇒ **đỏ**; phục hồi ⇒ xanh.

### Ticket 16 — trạng thái `loading` thay cho `error` khi đang nạp
- `LiveState.LOADING = "loading"` (`src/api/domain.py`); `start()` công bố `LOADING` cùng câu
  "Đang mở …" thay vì giữ `error` của phiên trước.
- `routes.live_stream`: `loading` ⇒ 409 với câu **"Đang mở phiên live — chưa có frame"** (không còn
  câu "đã dừng vì lỗi").
- `schemas.LiveStatusResponse.state` thêm `"loading"`; `web/src/api.ts` thêm vào union;
  `LivePanel` hiện **"đang mở…"**, `role="alert"` chỉ còn cho `error`.
- Test `TestMoLaiSauPhienLoi` (đỏ khi bỏ dòng `_state = LOADING`): dựng phiên trước kết thúc `error`,
  bật lại và giữ `start()` trong lúc nạp ⇒ `state == "loading"`, stream 409 **không** chứa
  "đã dừng vì lỗi".

### Ticket 18 — `stability` có encoding "chưa đo"
- `LiveTrackStats.stability: float | None = None` + `stability_n: int`; cửa sổ IoU rỗng ⇒ `None`;
  mất dấu khi đã có mẫu ⇒ `0.0` (số đo được) + `stability_n > 0`.
- Xuyên chuỗi: adapter dùng `_so_hoac_none` (không `float(x or 0.0)`), `LiveTelemetry`/`LiveStatus`,
  schema `float | None`, `api.ts`, và `live.ts` in số **chỉ khi** `stability_n > 0` và
  `Number.isFinite(stability) && stability >= 0`.
  ⇒ `0,0` đo được in **"nhấp nháy 100 %"** (không còn "chưa đo" sai sự thật), `None` in "chưa đo".
- Test: 3 test `live_tracking`, 1 test API (`None` ≠ `0,0` qua cả chuỗi), 3 test vitest.

## 📤 Output / Kết quả

| Kiểm tra | Kết quả |
|---|---|
| `./run lint` | ✓ |
| `./run test` | **741 passed** (5 deselected, ~63 s) — trên `main` sau merge 3 nhánh |
| `./run testall` | **746 passed** (~184 s) |
| `./run webtest` | **32 passed** |
| `npm --prefix web run build` | ✓ |
| `./run e2e` | **PASS** |
| Ticket 16/17/18 | ✅ done (tiêu chí đã tick trong `.scratch/…/issues/`) |

Merge (máy không có `gh` nên làm bằng lệnh, có ghi ở đây để tái lập):
1. `git merge --no-ff fix/health-mode-raw-va-message-409` → `main` (16 commit, 15 file).
2. `git rebase main feat/bang-chung-camera-that` (7 commit, **không xung đột**) → merge `--no-ff`.
3. `git rebase main feat/chan-doan-chat-luong-bam` (25 commit, **không xung đột**) → merge `--no-ff`.
   B và C cùng rẽ từ nhánh A nên phải merge **tuần tự**; sau mỗi bước chạy `./run lint` + `./run test`.
4. Kiểm tra trên `main` sau cả 3 merge: lint ✓ · test **741** · testall **746** · webtest **32** ·
   build ✓ · e2e **PASS**.

Bài học: giữ `.gitignore`/`docs/*` chỉ thêm ở **cuối** file (AGENTS §7b) nên 3 nhánh không xung đột
— lần này `git rebase` chạy 25 commit mà không phải sửa tay dòng nào.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Test stress đầu tiên xanh cả khi có lỗi**: nguyên nhân là GIL switch interval 5 ms; cách xử lý ở
  trên (`setswitchinterval` + deque tự theo dõi). Bài học: test tranh chấp luồng phải kiểm **bất biến**
  (lock đang giữ?) chứ không chỉ "chạy 1.000 vòng không nổ".
- **`stability = None` làm đỏ 3 test cũ** so sánh `< 1.0`: sửa thành `is None or < 1.0` — đúng nghĩa
  ("chưa có mẫu" cũng không phải "ổn định 100 %"), không nới test.
- **`status.json` allowlist** (`test_status_duoc_ghi_moi_frame`) đỏ khi thêm `stability_n` — đúng
  thiết kế (khoá lạ phải khai), đã thêm vào allowlist.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Ticket 14/15 (cờ phán quyết drift + log từng mẫu drift) — **chờ dữ liệu**: cần clip có
      `p05` thấp mà `empty_frac_window ≈ 0`; hiện chưa có nên cờ sẽ chỉ là bản sao của tỉ lệ mất dấu.
- [ ] Bước CI `grep` cấm số đếm cũ trong `docs/` (nợ từ review nhánh bằng chứng camera).
- [ ] Quay clip camera thật có vật bị che + kéo chuột chọn vật trên UI (cần người ngồi trước máy).

## 📚 Tài liệu tham khảo
- Ticket: `.scratch/camera-ai-realtime/issues/16|17|18-*.md`.
- Log phiên trước: `docs/task/09-11-2026-watchdog-worker-chet-va-h264-record.md`,
  `docs/task/09-11-2026-bang-chung-duong-camera-that.md`,
  `docs/task/09-11-2026-chan-doan-chat-luong-bam.md`.
- AGENTS §6 (bẫy `0/None ≠ đã đo`), §9.1 (review độc lập), §7b (quy trình Git).
