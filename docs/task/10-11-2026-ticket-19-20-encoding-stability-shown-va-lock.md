# Ngày 10-11-2026 — Đóng ticket 19 (`stability_shown` hết "0 = chưa đo") + ticket 20 (2 cửa sổ `append` ngoài lock)

> Tiếp ngay sau phiên 10-11 (đóng ticket 16/17/18 + merge 3 nhánh vào `main`). Hôm nay là **trả nợ
> kỹ thuật** đã ghi ticket trong review, không phải tính năng mới. Nhánh:
> `fix/ticket-19-20-stability-shown-va-lock` (rẽ từ `origin/main` tại `ef69653`).

## 🎯 Mục tiêu
1. **Ticket 19** — `stability_shown` (IoU của mask ĐÃ LÀM MƯỢT) vẫn là `float = 0.0` ⇒ `0,0` mang
   **ba** nghĩa: "chưa đo" / "màn hình trống" / "đo được 0". Cùng lỗi mà ticket 18 vừa sửa cho
   `stability`. Không lộ ra UI/API, nhưng người đọc artifact `data/*_metrics.json` sẽ trích
   "ổn định 0 %" cho một phiên chưa đo gì (AGENTS §6).
2. **Ticket 20** — `_shown_iou_window` và `_age_window` còn `append`/duyệt deque **ngoài**
   `_stats_lock`: đúng mẫu code mà ticket 17 vừa phải sửa cho `_drift_window` (`RuntimeError: deque
   mutated during iteration` ⇒ luồng VOS chết). Hôm nay mỗi cửa sổ chỉ một luồng ghi nên chưa nổ,
   nhưng mẫu sai sẽ bị copy.
3. Chạy **review độc lập** (AGENTS §9.1) trước khi merge, gồm 2 vòng: vòng 1 trên cả PR, vòng 2 chỉ
   trên phần vừa sửa.

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/19-*.md`, `20-*.md` (tạo từ review 10-11).
- `src/live_tracking.py` (bản trên `main` tại `ef69653`): `LiveTrackStats`, `_smooth`,
  `_note_mask_age`, `_measure_stability`, `_shown_at`, `_measure_drift`, `status_payload`.
- Quy ước: `AGENTS.md` §6 (bẫy `0/None ≠ đã đo`, bất biến lock), §9.1 (review độc lập), §7b (git).

## 🔨 Công việc đã thực hiện

### Ticket 19 — `stability_shown` có encoding "chưa đo"
- `LiveTrackStats.stability_shown: float | None = None` + `stability_shown_n: int = 0`
  (độ dài `_shown_iou_window`); `status_payload` thêm khoá `stability_shown_n`.
- `_smooth`: nhánh mask hiển thị RỖNG ⇒ `0.0` **chỉ khi** cửa sổ đã có mẫu, ngược lại `None`
  (chưa đo) — đối xứng đúng cách ticket 18 đã làm cho `stability`. Cửa sổ `maxlen=10` nên khi `n > 0`
  thì không bao giờ về 0 ⇒ bất biến `None ⇔ n == 0` giữ suốt phiên.
- `scripts/measure_live_relay.py::_worker_telemetry` giữ thêm `stability_shown`/`stability_shown_n`
  trong artifact (trường này **không** đi qua `/api/live/status` nên chỉ lấy được từ `status.json`),
  và in thêm một dòng khi chạy (`stability_shown=... (n=...; null = CHƯA ĐO)`).
- Test: `TestStabilityShownCoEncodingChuaDo` (3) + `TestWorkerStatus` (2, gồm chiều ngược "`0,0` đo
  được phải giữ `0.0`"), allowlist `status.json` (`test_status_duoc_ghi_moi_frame`) thêm khoá mới.

### Ticket 20 — mọi cửa sổ thống kê chỉ ghi khi giữ lock
- `_note_mask_age`: `append` + `np.fromiter` + `np.percentile` gộp vào **cùng**
  `with self._stats_lock`.
- `_smooth`: `append` + `sum()` của `_shown_iou_window` trong **cùng** lock.
- Test `TestDriftWindowChiMotNguonGhiTrongLock` → `TestCuaSoThongKeChiMotNguonGhiTrongLock`, tham số
  hoá cho **3** cửa sổ (`_drift_window`, `_shown_iou_window`, `_age_window`); mỗi tham số vẫn dùng
  `deque` tự theo dõi (`append` nào chạy khi không giữ lock thì ghi lỗi) + hạ
  `sys.setswitchinterval(1e-6)`.

### Kết quả review độc lập vòng 1 (agent `reviewer`, trước khi merge) — P0 = 0, 1 P1
| Mức | Phát hiện | Xử lý |
|---|---|---|
| **P1** | `_shown_at()` duyệt `reversed(self._shown_by_frame)` **ngoài** `_stats_lock` trong khi luồng chính `append` trong lock ⇒ đây là cấu trúc **thật sự hai luồng** (VOS đọc, main ghi), đúng lỗi đã giết luồng VOS ở ticket 17 | Bọc `with self._stats_lock`; test mới `test_shown_at_doc_deque_trong_lock` (deque tự theo dõi `__reversed__` có giữ lock không — đỏ trước khi sửa, đã kiểm) |
| P2 | Comment mới ghi sai ví dụ "cửa sổ rỗng = phiên tắt làm mượt" (thật ra tắt làm mượt thì `shown = raw`, cửa sổ vẫn đầy mẫu) | Sửa comment: `None` = chưa có cặp mask nào; tắt làm mượt ⇒ đo trên mask thô |
| P3 | `_pending_drift` ghi ngoài lock (luồng VOS) trong khi luồng chính đọc/xoá trong lock ⇒ có thể **mất** một mẫu drift | Ghi dưới lock + test `test_pending_drift_ghi_duoi_lock` (lớp con theo dõi lần GÁN) |
| P3 | `mask_iou(...)` (0,2–1 ms ở 480p/720p) nằm **trong** lock ở `_smooth`/`_measure_stability` — critical section dài nhất | Tính ra biến cục bộ **ngoài** lock; chỉ `append`/`sum`/`len` trong lock |
| P3 | Docstring test nói `lock.locked()` = "thread này giữ" (thật ra là "một thread bất kỳ giữ") | Sửa docstring cho đúng thứ test chứng minh |
| P3 | Test tích hợp cũ `status["stability_shown"] < 0,999` sẽ ném `TypeError` nếu ai trả `None` vô điều kiện | Thêm guard `is not None` |
| P3 | `measure_live_relay` không in số mới; artifact thiếu test chiều "`0,0` đo được" | Đã thêm cả hai |

Vòng 2 (chỉ review phần vừa sửa, sau khi `./run lint` + `./run test` xanh) — **P0 = 0, P1 = 0**,
5 P3 (đã sửa hết trong cùng nhánh):
| Mức | Phát hiện | Xử lý |
|---|---|---|
| P3 | Log trên nói rộng hơn thực nghiệm: bỏ lock riêng ở `_shown_at` **không** làm `test_pending_drift_…` đỏ | Sửa câu trong log + chạy lại riêng từng chiều để xác nhận |
| P3 | Hai critical section **rời nhau** ở `_measure_drift` (tra cứu rồi mới ghi `_pending_drift`) ⇒ luồng chính chen vào giữa có thể làm **mất 1 mẫu drift** | Thêm `_shown_at_locked()` (biến thể không acquire) + gộp tra cứu & hẹn pending vào **một** `with self._stats_lock` |
| P3 | Bất biến "`_stats_lock` không tái nhập" chưa ghi tại chỗ định nghĩa lock | Ghi ngay trên dòng `threading.Lock()` trong `__init__` (kèm quy ước dùng biến thể `*_locked`) |
| P3 | Test dùng `maxlen=200` trong khi production là `_SHOWN_HISTORY = 90` | Lấy `maxlen` từ chính instance |
| P3 | Docstring lớp test đọc như thể bug còn đó; `_stats.lk_ms` ghi ngoài lock (mẫu xấu ticket 20 đang dọn) | Sửa thành "TRƯỚC KHI SỬA…"; `lk_ms` ghi dưới lock |

Reviewer cũng xác nhận bằng đọc mã: 16 site acquire `_stats_lock`, **không** site nào gọi hàm acquire lại
nó ⇒ không deadlock/tái nhập; `_shown_at` giữ lock ~1–5 µs (≤ 90 phép so sánh, 8–9 lần/s); 2 test mới
không rò trạng thái; thêm `stability_shown_n` vào `status.json` **không** phá API (`worker_source.py`
đọc từng khoá bằng `.get`, `web/` không dùng trường này).

## 📤 Output / Kết quả

| Kiểm tra | Kết quả |
|---|---|
| `./run lint` | ✓ |
| `./run test` | **752 passed** (5 deselected, ~73 s) |
| `./run testall` | **757 passed** (~215 s) |
| `./run webtest` / `run e2e` | **không chạy** — nhánh không chạm `web/` hay `src/api/` (chỉ `src/live_tracking.py`, `scripts/`, `tests/`) |
| Ticket 19 | ✅ done (4/4 tiêu chí tick) |
| Ticket 20 | ✅ done (3/3 tiêu chí tick) |

Bằng chứng test "có răng" (đã kiểm thật, không phải suy luận — mỗi lần đều phục hồi code):
- Trả `append` của `_shown_iou_window` ra ngoài lock ⇒ đỏ đúng tham số `[_shown_iou_window]`;
  trả `append` của `_age_window` ra ngoài lock ⇒ đỏ đúng tham số `[_age_window]`.
- Trả `stability_shown = 0.0` vô điều kiện ⇒ `test_cua_so_rong_thi_none_va_n_bang_0` đỏ.
- Trả `_shown_at` ra ngoài lock ⇒ **chỉ** `test_shown_at_doc_deque_trong_lock` đỏ (đã chạy lại riêng
  từng chiều — bản log trước ghi gộp cả hai test là sai, review vòng 2 bắt đúng); trả
  `_pending_drift` ra ngoài lock ⇒ `test_pending_drift_ghi_duoi_lock` đỏ.

File thay đổi:
- `src/live_tracking.py` — `stability_shown`/`stability_shown_n`; `_smooth`, `_note_mask_age`,
  `_measure_stability` (lock + `mask_iou` ngoài lock), `_shown_at` (lock), `_measure_drift`
  (`_pending_drift` dưới lock), `status_payload`.
- `tests/test_live_tracking.py` — allowlist `status.json`, `TestCuaSoThongKeChiMotNguonGhiTrongLock`
  (3 tham số), `TestShownByFrameDocTrongLock` (2), `TestStabilityShownCoEncodingChuaDo` (3).
- `scripts/measure_live_relay.py` — `_worker_telemetry` giữ thêm 2 khoá; in thêm 1 dòng.
- `tests/test_measure_live_relay.py` — `TestWorkerStatus` (2).
- `.scratch/camera-ai-realtime/issues/19-*.md`, `20-*.md` — tick tiêu chí + `Status: done`.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Test lock kiểu cũ chỉ đúng một phần**: `lock.locked()` trả True khi **bất kỳ** thread giữ lock,
  nên một `append` ngoài lock chỉ bị bắt khi tình cờ không thread nào giữ. Thực tế với 2 writer ×
  3000 lần + `setswitchinterval(1e-6)` thì luôn đỏ, nhưng docstring phải nói đúng mức độ chứng minh.
- **Test cho `_pending_drift` không dùng được `setattr` vào lớp thật** (rò trạng thái sang test khác,
  và `_stats_lock` chưa tồn tại trong `__init__`). Cách làm: **lớp con** `_SessionTheoDoi` với
  property theo dõi lần GÁN; lần gán trong `__init__` ghi `None` (chưa có lock) và không tính là vi phạm.
- **`_config()` của test ghim `vos_every=1`** ⇒ truyền `vos_every=3` vào bị `TypeError: multiple
  values`; và với `vos_every=1` thì `_measure_drift` return sớm (không có LK) ⇒ test "vô nghĩa nhưng
  xanh". Sửa: dựng `LiveTrackConfig` trực tiếp với `vos_every=3`.
- **Bẫy "test xanh nhưng không đo gì"** lặp lại lần thứ 3 trong repo: mọi test lock mới đều có chốt
  `assert _so_mau(...) > 0` ("không nhận mẫu nào ⇒ test vô nghĩa").

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Ticket 15 — log từng mẫu drift ra CSV + **đối chứng cảnh tĩnh** (`drift_iou ≥ 0,99`): hiện chỉ
      có mean/p05 của cửa sổ 200 mẫu nên **không đo được** độ trễ phát hiện / tỉ lệ báo oan, và
      không chọn ngưỡng bằng số được. Làm được ngay, không cần người ngồi trước máy.
- [ ] (P3 còn lại, không chặn merge) `_seq_frame` là dict hai luồng cùng dùng — an toàn dưới GIL hiện
      tại nhưng là race thật trên Python free-threading (3.13t); chỉ cần xử lý khi đổi interpreter.
- [ ] Ticket 14 (cờ phán quyết drift) — **vẫn chờ dữ liệu**: cần clip có `drift_iou_p05 < 0,30` mà
      `empty_frac_window < 3 %`; hiện p05 và tỉ lệ mask rỗng đi cùng nhau 1:1.
- [ ] Ticket 11 (vật đen/ít texture: NCC làm cổng quyết định) — `ready-for-human`.
- [ ] Bước CI `grep` cấm số đếm cũ trong `docs/` (nợ từ review nhánh bằng chứng camera 09-11).
- [ ] Quay clip camera thật có vật bị che + kéo chuột chọn vật trên UI (cần người trước máy).
- [ ] Ghi 1 dòng cạnh `_stats_lock`: "lock này KHÔNG tái nhập" (review vòng 1 gợi ý) — chưa làm vì
      phải sửa thêm comment trong `__init__`.

## 📚 Tài liệu tham khảo
- Ticket: `.scratch/camera-ai-realtime/issues/19-*.md`, `20-*.md`.
- Log phiên trước: `docs/task/10-11-2026-sua-ticket-16-17-18-va-merge-main.md`.
- `AGENTS.md` §6 (bẫy `0/None ≠ đã đo`, bất biến lock, `stability`), §9.1 (review độc lập), §7b (git).
- CPython: `deque` kiểm `state` khi duyệt ⇒ `RuntimeError: deque mutated during iteration`
  (cơ chế đã giết luồng VOS ở ticket 17).
