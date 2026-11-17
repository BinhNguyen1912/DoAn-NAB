Status: success

# Review — nhánh `fix/mask-age-vos-every-1` (HEAD `ce94809`, 2 commit trên `f753663`)

**Verdict: chưa merge được.** Không có P0 (không hỏng runtime), nhưng có **1 P1** làm sai provenance của chính artifact trong PR, **2 P2** về số liệu/test, và **1 P2 quy trình** (thiếu log phiên bắt buộc).
Đã kiểm bằng cách đọc trực tiếp file + reflog (không có shell nên **không** tự chạy lint/pytest; tin theo số của phiên code).

## Đối chiếu từng proposed change

| # | Đề xuất | Trạng thái | Bằng chứng |
|---|---|---|---|
| 1 | `_after_vos` đo `post_ms`, gán `_stats.post_ms`, gọi `_note_mask_age(0.0, vos, pre, queue=0, post)` | **có** | `src/live_tracking.py:797-814` |
| 2 | KHÔNG thêm `_measure_drift` vào `_after_vos` | **có** (và còn được chặn 2 lớp) | `live_tracking.py:791-814`; `_measure_drift` tự `if not self._use_lk: return` (`:957-958`) |
| 3 | Test mới: `age_n==2`, total ≈ vos+pre+post, `p95 is None`, `post_ms is not None`; test canh "age ≠ thời gian vòng lặp"; sửa test cũ `every=1` | **có, nhưng 1 vế vô răng** | `tests/test_live_tracking.py:1715-1743`, `:919-942` |
| 4 | Đo lại `bangcau --every 1` + artifact + REGISTRY + docs + AGENTS §6 | **có, nhưng metadata trong artifact tự mâu thuẫn** | artifact `:104`; `scripts/so_lieu_bao_cao.py:90-98`; `docs/so-lieu-bao-cao.md:29`; `AGENTS.md:320-329` |
| 5 | Đóng ticket #24 (2/2) | **có** | `.scratch/camera-ai-realtime/issues/24-…md` (`Status: resolved`, 2/2 ô tick) |

## Findings

### P1 — `DINH_NGHIA_TUOI_MASK` vẫn nói "`vos_every=1` thì `age_n=0`", và câu đó đã nằm trong artifact của chính PR này
`src/live_tracking.py:64-68` (dòng 67):
```
"Pha chưa đo được tính 0; chỉ đo ở đường LK (vos_every > 1) ⇒ vos_every=1 thì age_n=0"
```
Bằng chứng mâu thuẫn **trong cùng một file** `data/bang_cau_hinh_2026-11-17_every1_metrics.json`: `:104` chứa câu trên, còn `age_n.mean = 60.0` (`:88-96`). Chuỗi này được echo vào **mọi** `status.json`/artifact (`live_tracking.py:282`), đúng loại "số không truy được về định nghĩa" mà repo đã dựng cơ chế này để chặn.
Kèm theo: `tests/test_cau_hinh_hieu_luc.py:62-64` đang **ghim lý do sai** này (`"... để người trích không hỏi tại sao age_n=0"`) — test vẫn xanh vì chỉ kiểm chuỗi con `"age_n"`.
**Sửa:** thay vế cuối bằng "mỗi frame PHÁT đều ghi 1 mẫu (kể cả frame `engine.start()`); `vos_every=1` ⇒ age = 0, total = pre+vos+post"; sửa message/assert của test (kiểm cả `"vos_every=1"` + `"age = 0"`). Sinh lại artifact (`bangcau` chỉ sinh `cau_hinh` từ `status.json`, nên phải chạy lại — hoặc ghi rõ trong log là artifact sinh trước khi sửa chuỗi).

### P2 — Đường inline không ghi `_stats.pre_ms` ⇒ `mask_age_total_ms` không tách được, và claim "pre ~12 ms nằm TRONG tuổi" không kiểm được từ artifact
`_store_vos` ghi `self._stats.pre_ms = pre_ms` (`live_tracking.py:729`), còn `_after_vos` chỉ ghi `post_ms` (`:807-808`) dù vẫn dùng `result.pre_ms` cho tuổi (`:812-813`). Hệ quả đo được: artifact `data/bang_cau_hinh_2026-11-17_every1_metrics.json:53-59` có `pre_ms.n = 0 / mean = null`, trong khi `mask_age_total_ms.mean 92,47` so với `vos_ms.mean 82,1` ⇒ chênh 10,4 ms **không có cột nào giải thích**. `docs/so-lieu-bao-cao.md:29` lại khẳng định "vì sao ~106 chứ không ~95 ms: `pre_ms` (~12 ms) nằm TRONG tuổi" — người đọc artifact không có `pre_ms` để đối chiếu (12 ms là số vay từ artifact 192/3 khác), và `post_ms` cũng không có trong `COT` của `bang_cau_hinh`.
**Sửa:** trong `_after_vos` đặt thêm `self._stats.pre_ms = (None if result.pre_ms is None else round(float(result.pre_ms), 2))` cùng lock với `post_ms`, (tuỳ chọn) thêm `post_ms` vào `COT`; thêm test `vos_every=1` + engine có `pre_ms` ⇒ `status.pre_ms is not None` và `total == vos + pre + post`.

### P2 — Vế `pre` của test mới là vô răng (và không có test nào chạy `vos_every=1` với engine có `pre_ms`)
`tests/test_live_tracking.py:1727-1728`:
```python
assert stats.mask_age_total_ms == pytest.approx(12.5 + (stats.pre_ms or 0.0) + (stats.post_ms or 0.0), abs=0.3)
```
Vì `_stats.pre_ms` luôn `None` ở đường inline (findings trên) và `FakeEngine`/`_Result` đều **không** có `pre_ms`, `(stats.pre_ms or 0.0)` luôn = 0 ⇒ nếu ai đó truyền `pre_ms=0.0` thay vì `result.pre_ms` (mất ~12 ms của tuổi), test vẫn xanh. Không có test nào trong `tests/` tạo engine có `pre_ms` ở `vos_every=1` (grep `pre_ms\s*=` chỉ ra `:1684` và `:1728`).
**Sửa:** engine giả trả `pre_ms=7.0`, assert `mask_age_total_ms == pytest.approx(12.5 + 7.0 + stats.post_ms)` và `status["pre_ms"] == 7.0`.

### P2 — Docstring "cùng định nghĩa `post_ms` với `_consume_vos`" sai tên **và** sai nội dung; `_stats.post_ms` không so được giữa hai đường
`src/live_tracking.py:793-794` viết "cùng định nghĩa `post_ms` với đường có luồng VOS (`_consume_vos`)" — **không có hàm `_consume_vos`** trong file (hàm thật là `_store_vos`). Nội dung cũng khác: `_store_vos` đo `post_ms` bao gồm `_record_vos` + **`_measure_drift` (IoU + ghi 1 dòng CSV)** + `_smooth` (`:709-723`), còn `_after_vos` chỉ `_record_vos` + `_smooth` (`:797-802`). Nên `post_ms` của `vos_every=1` **hệ thống nhỏ hơn** của `vos_every>1` đúng phần drift + I/O; `LiveTrackStats.post_ms` cũng còn ghi "đo drift + làm mượt mask" (`:168`).
Không có consumer nào hỏng (xem mục c), nhưng đây đúng loại "hai số khác đại lượng" mà repo cấm so.
**Sửa:** "cùng cách đo với `_store_vos`, TRỪ `_measure_drift` (đường đơn luồng không có nội suy LK)"; sửa comment `:168` thành "đo drift (nếu có LK) + làm mượt".

### P2 (quy trình) — Thiếu log phiên `docs/task/17-11-2026-*.md` cho ticket #24, và thiếu ghi kết quả review độc lập
`docs/task/` chỉ có `17-11-2026-ticket-23-…md`; không có file nào cho #24 (`docs/task/16-11-*`, `17-11-ticket-23`, hết). AGENTS §5 bước 5 và §9.4 coi đây là **điều kiện hoàn thành**; ticket #23 trong cùng ngày có log nhưng #24 thì không, dù commit 2 là "data+docs".
**Sửa:** thêm `docs/task/17-11-2026-ticket-24-tuoi-mask-don-luong.md` theo `_template.md`, ghi bảng review này (P0/P1/P2 + đã sửa gì), số đo + `git_rev 1f0c89a`/`git_dirty_code false`, và quyết định (không cần plan 3 ý kiến: < 4 giờ, không đổi kiến trúc).

### P3 — Test canh "age không phải thời gian cả vòng lặp" không bắt được đúng mutation nó nêu
`tests/test_live_tracking.py:1732-1743`: nếu ai đổi thành `time.perf_counter() - bat_dau_post` như docstring cảnh báo, `age` ≈ 0,1–0,5 ms trên `FakeEngine` ⇒ `mask_age_total_ms ≈ 12,6 ms < 12,5 + 50` ⇒ **vẫn xanh**. Ngưỡng 50 ms quá rộng so với thời gian một lần `_after_vos` (dump không chạy + smooth tắt trên đường này).
**Sửa:** dùng một `FakeEngine` có `elapsed_ms` lớn (vd 400) và assert `mask_age_total_ms == approx(pre + 400 + post, abs=2)`; hoặc monkeypatch `time.perf_counter` trả mốc nhảy 500 ms giữa `bat_dau_post` và lúc gọi `_note_mask_age`.

### P3 — Thay đổi ngoài phạm vi ticket: `age_n` của cấu hình `vos_vos_every > 1` tăng thêm 1 mẫu
`_after_vos` cũng chạy cho frame `engine.start()` (`live_tracking.py:597`), nên với `vos_every>1` cửa sổ tuổi có thêm mẫu age=0 của frame đầu: `docs/bang-cau-hinh.md:6-16` ghi `age_n = 59` cho 60 frame (số cũ), chạy lại sẽ ra **60**. Mẫu thêm có `vos_ms = engine.start().elapsed_ms` — bao gồm `init_state` + encode (`src/tracker_engine.py:173-211`), tức một outlier lớn vào `_age_window`; **không** làm lệch `mask_age_p95` vì p95 chỉ công bố khi n ≥ 30 (chỉ số 27,55; outlier là max) nhưng phải nói ra để người sau không quy 59→60 cho bug khác.
**Sửa:** 1 câu trong log/AGENTS bullet: "mỗi frame PHÁT ⇒ 1 mẫu, kể cả frame `start()` ⇒ bảng 15-11 (`age_n 59`) và lần chạy lại (`60`) khác nhau đúng 1 mẫu".

### P3 — Điều kiện của con số còn thiếu ở 2 chỗ công bố
- `docs/so-lieu-bao-cao.md:29`: tuyên bố không ghi `image_size 192` (chỉ có trong khoá `cau_hinh.192_1`), không ghi clip/ô chọn.
- `AGENTS.md:320-329`: có `image_size 192`, "3 lần × 60 frame", `git_dirty_code false`, nhưng **không** nêu `git_rev 1f0c89a`, clip `binh1.mp4`, ô chai `300,275,150,410` (ô chọn là biến số đã từng làm sai toàn bộ kết luận — AGENTS §6).
- `docs/bang-cau-hinh.md` (bảng cấu hình chuẩn) vẫn **không có dòng `vos_every 1`** ⇒ người đọc bảng tưởng cấu hình đó chưa đo.

### P3 — `post_ms` của đường inline bị "dụng cụ đo làm bẩn" trên frame dump mask (đã có ticket #26, chỉ để nối)
`_record_vos` → `_dump_mask` nằm trong cửa sổ `post_ms` (`:797-802`, `:896-901`), nên khi chạy `./run miou` (`--dump-mask-frames`, tức cấu hình `vos_every=1` mặc định cho mIoU) tuổi mask sẽ nhảy thêm độ trễ ghi PNG. Không cần sửa trong PR này (ticket #26 đã ghi), nhưng đừng trích `age_n`/p95 của phiên có dump làm "tuổi mask của demo".

### Đã kiểm, không phải lỗi
- **(a) Không double-sample.** `_after_vos` chỉ được gọi từ `live_tracking.py:597` (frame `start()`) và `:788` (`_result_inline`); `_start_worker` không gọi `_note_mask_age` (chỉ đặt `_vos_state`, `:648-654`). Mỗi frame PHÁT đúng 1 mẫu ở cả hai đường; `age_n` = `frames` (artifact: 60 == 60), và với `vos_every=1` thì `age_n == vos_runs` (1 VOS/frame). Test `age_n == 2` (`:1724`) là chốt chống double-count thật.
- **(b) Không pha nào bị tính hai lần.** `pre_ms` **nằm ngoài** `elapsed_ms` (`tracker_engine.py:203-211`), `post_ms` chỉ đo sau khi đã có kết quả; `queue_ms=0` đúng (không có worker). Chỉ có khác biệt *định nghĩa* `post_ms` giữa hai đường (P2 ở trên), không phải đếm trùng.
- **(c) Không consumer nào giả định `post_ms` chỉ có ở đường LK.** `web/src/**` không đọc `post_ms`; `src/api/**` không ánh xạ nó; `bang_cau_hinh.COT` không có `post_ms`; `measure_live_relay.py:236` chỉ chép nguyên giá trị. `pre_ms`/`post_ms`/`queue_ms` = `None` vẫn được đọc là "chưa đo" ở `worker_source.py:168-172` — không đổi.
- **(d) Bỏ `_note_mask_age` trong `_after_vos` ⇒ ít nhất 3 test đỏ:** `test_live_tracking.py:1724` (`age_n == 2`), `:1730`/`:1725` (`post_ms`/`total` not None), `:1741` (`mask_age_ms == approx(0.0)` vs `None`), `:934/938` (`age_n > 0`, `mask_age_ms == 0`). Có răng cho mutation "xoá tính năng". (Vô răng: vế `pre` — P2 trên; test `:1743` — P3 trên; `test_cau_hinh_hieu_luc.py:62` — P1 trên.)
- **(e) Số khớp nhau:** docs `105,53 ± 5,4 (n = 60)` = artifact `mask_age_p95.mean/std` + `age_n.mean` (generator `scripts/so_lieu_bao_cao.py:203-210`, `_fmt` ⇒ dấu phẩy thập phân, `60.0`→`60`); AGENTS `vos_ms 82,1 ± 3,33`, `9,5 ± 0,5`, `age_n 60` = artifact. Artifact `git_rev 1f0c89a` = commit "fix(live): vos_every=1 cũng ghi tuổi mask" (reflog `.git/logs/HEAD:566`), commit sau nó (`ce94809`) chỉ là data+docs ⇒ provenance hợp lý; `git_dirty`/`git_dirty_code = false`. Điều kiện "đơn luồng, không LK, không so FPS với 29,8, `image_size 192`, ngày 17-11, 3×60" có mặt ở docs+AGENTS; thiếu `git_rev`/clip/ô chai (P3).
- **(f) HUD/API không hồi quy.** `web/src/live.ts:60-69` chỉ in khi `mask_age_total_ms` khác `null` (0 vẫn in, `null` ẩn) ⇒ `vos_every=1` nay hiện "… ms tuổi" (~92 ms), `maskAgeIsStale` (ngưỡng 1500 ms) không báo oan; `src/api/domain.py:130-133`, `schemas.py:138-147`, `routes.py:158-160`, `adapters/worker_source.py:170-172` chỉ chuyển tiếp `None`. `tests/test_api_live.py:1073-1099` dùng status **không có** hai khoá này ⇒ không phụ thuộc `vos_every`; không test nào assert `vos_every=1 ⇒ mask_age_total_ms is None`.

## Checks
- Đọc: `src/live_tracking.py` (toàn bộ đường VOS/inline/stats), `src/tracker_engine.py` (định nghĩa `elapsed_ms`/`pre_ms`/`start()`), `tests/test_live_tracking.py` (các lớp drift/tuổi mask + test mới), `tests/test_cau_hinh_hieu_luc.py`, `tests/test_api_live.py` (phần telemetry), `web/src/live.ts` + `live.test.ts` + `LivePanel.tsx`, `src/api/{domain,schemas,routes,live}.py` + `adapters/worker_source.py`, `scripts/{bang_cau_hinh,so_lieu_bao_cao,measure_live_relay}.py`, `data/bang_cau_hinh_2026-11-17_every1_metrics.json`, `docs/so-lieu-bao-cao.md`, `docs/bang-cau-hinh.md`, `AGENTS.md §6`, ticket #24, `.git/logs/HEAD`.
- Không chạy được `./run lint` / `./run test` / `so_lieu_bao_cao.py --check` (không có shell trong phiên này) — dựa theo trạng thái phiên code: lint xanh, 1303 passed, `--check` xanh.
- Không có `docs/task/` mới cho #24 (đã grep toàn thư mục).

## Residual risk
- Chưa diff được `origin/main..HEAD` bằng máy (không có shell); các kết luận "present/absent" dựa trên đọc file hiện tại + reflog, không phải trên `git diff`.
- Chưa xác minh bằng máy rằng `git_dirty_code=false` lúc đo ứng với đúng cây code đang merge — chỉ đối chiếu `git_rev 1f0c89a` với reflog.
- Hành vi HUD thật ở `vos_every=1` (dòng tuổi mask mới xuất hiện) chưa chạy `./run e2e`; API/DTO không đổi nên rủi ro thấp, nhưng nếu người review thấy cần thì chạy 1 phiên ngắn với `source=0`.
- Không đo lại được `mask_age_p95` để kiểm `105,53` (cần checkpoint + GPU/CPU thật).