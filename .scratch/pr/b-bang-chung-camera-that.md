## Bằng chứng đường camera thật: webcam → relay HTTP → API live → mask

Trước nhánh này, mọi số "live 29,9 FPS" trong repo đến từ **file video** hoặc relay, chưa có lần nào chạy trọn **đường demo mà hội đồng sẽ bấm**: webcam (Windows) → `./run relay` → API live `mode=track` → mask. Nhánh này dựng phép đo tự động cho đúng đường đó và lưu artifact.

### Phép đo

`scripts/measure_live_relay.py`:
1. dựng API (`uvicorn`) trên cổng trống, chờ `/api/health`;
2. tạo phiên live `mode=track` với nguồn relay `/snapshot.jpg` + ô chọn;
3. trong **N giây** đọc `/api/live/status` + `status.json` của worker (vì `drift_*`/`empty_frac_window` **không** đi qua API), chụp ảnh `/api/live/frame` ở 3 mốc;
4. ghi artifact JSON có provenance: `git_rev`, `git_dirty`, `git_dirty_code` (bẩn **bỏ qua `data/`**), `git_loi`, `lenh`, `do_luc`, `moi_truong`, `thiet_lap`;
5. `_verdict()` chấm theo **4 điều kiện đăng ký trước** (`state = running`, `frames > 0`, `measured_fps > 0`, `mask_fps > 0`) — exit 1 nếu không đạt; `ket_qua` trong artifact chỉ `true` khi **cả** điều kiện, **không** có `loi`, **và** có provenance.

### Kết quả (`data/live_web_relay_2026-11-10_metrics.json`, `git_rev = da1d671` = tổ tiên của HEAD, `git_dirty_code = false`, `git_loi = null`, `ket_qua = true`)

| Đại lượng | Giá trị |
|---|---|
| `state` | `running` (kết thúc bằng `stop()`) |
| `frames` | 1 → **681** trong 25 s (frame **đổi nội dung** — relay phát lại khung cuối, nên đừng chia cho 25 rồi so với HUD) |
| `measured_fps` max | **29.9** |
| `display_fps` max / cuối | **30.1** / 29.9 (nhịp HUD, nhờ LK lặp frame) |
| `mask_fps` max / cuối | **8.4** / 6.6 (VOS chạy nền, `vos_every=3`) |
| `vos_ms` / `lk_ms` | 99.2 / **1.56** |
| `drift_iou` / `p05` (`drift_n`) | 0.965 / **0.933** (171) |
| `mask_age_p95` | **281.6 ms** (`age_n` 200) |
| `empty_runs` / `mask_drops` / `lost_streak` | 0 / 0 / 0 |

Ảnh bằng chứng `data/live_web_relay_2026-11-10/frame{1,2,3}.jpg` (HUD `LIVE 29.8fps | VOS 8.4fps 182ms | LK 1.4ms`) **không** commit — repo không giữ binary trong `data/`; ảnh chỉ có trên máy demo, bằng chứng trong repo là artifact JSON.

### Tài liệu bảo vệ được sửa cho khớp code

- `docs/tom-tat-do-an.md`: bỏ câu **sai** "Chưa có BE/FE web"; thêm bảng live hybrid; sửa "Không real-time" → "**mask** không real-time, HUD 29,9 FPS nhờ LK".
- `docs/doi-chieu-yeu-cau-gvhd.md`: mốc 02-11 → **09-11**, thêm web/API, camera thật, mIoU, drift, watchdog, H.264; số đếm kèm ngày + cách đếm lại.
- `docs/team-contribution.md`: số đếm khớp repo (**7 176 dòng** `src`, **1 343 dòng** `web/src`, **663 hàm test**, **167 commit**, 44 log).

### Kiểm tra

- `./run lint` ✓ · `./run test` → **704 passed** (5 deselected) · `./run testall` trong checkout chính → 709 passed (worktree thiếu checkpoint ⇒ 704 passed, 5 skipped)
- Artifact đọc lại: `git_dirty_code = false`, `git_loi = null`

### Review độc lập (§9.1) — 1 vòng

**P1**: artifact `git_rev = e54439f` **không còn là tổ tiên của HEAD** sau khi nhánh rebase (clone mới không `git show` được) ⇒ **đo lại phép đo trên HEAD** bằng camera thật (số ở trên), và script nay **tự cảnh báo** khi `git_rev` không phải tổ tiên của HEAD.
**P1**: số đếm mâu thuẫn ngay trong 3 trang được sửa (164 vs 167 commit, 692/697 vs 704, "28 file log" vs 44, ADR 0001→0004 vs 5, còn sót "131 test") ⇒ dọn về **một** nguồn, dùng dạng "hơn 660 hàm test" để không tái phát.
**P2/P3 đã sửa**: `ket_qua` gộp `loi`/`git_loi`; `summarize` không tạo khoá mà API **không có** (bỏ `drift_*`/`mask_age_p95`, thêm `display_fps`) và thiếu trường ⇒ `None` chứ không `0,0`; xoá `status.json` cũ trước khi đo (không gán số của phiên trước); `finally` gọi `/api/live/stop` (worker không mồ côi); đếm `anh_frame_loi`; log có mục review + danh sách file; `mask` ghi dải **6,6–8,4** thay vì một số lẻ; `age_n` kèm `mask_age_p95`; dòng "Thu nhận video" thêm caveat **USB/IP trực tiếp còn kẹt driver**.

Nợ lại (không chặn merge): 3 lỗi **trước `try`** trong `main()` (mkdir/Popen/open log) chưa ghi artifact; chưa có bước CI `grep` cấm số đếm cũ trong `docs/`.

### Cái PR này KHÔNG nói

- Nguồn là **relay HTTP trên localhost** (đường `./run relay` + `./run demoip`), không phải V4L2 trực tiếp trong WSL (webcam WSL kẹt `Device busy` ở driver usbipd — AGENTS §6).
- `mask_age_p95 = 272 ms` là của **nguồn relay**, **không** trộn với 210–250 ms của clip `binh1`.
- Không nói "mask 30 FPS".
