## Bằng chứng đường camera thật: webcam → relay HTTP → API live → mask

Trước nhánh này, mọi số "live 29,9 FPS" trong repo đến từ **file video** hoặc relay, chưa có lần nào chạy trọn **đường demo mà hội đồng sẽ bấm**: webcam (Windows) → `./run relay` → API live `mode=track` → mask. Nhánh này dựng phép đo tự động cho đúng đường đó và lưu artifact.

### Phép đo

`scripts/measure_live_relay.py`:
1. dựng API (`uvicorn`) trên cổng trống, chờ `/api/health`;
2. tạo phiên live `mode=track` với nguồn relay `/snapshot.jpg` + ô chọn;
3. trong **N giây** đọc `/api/live/status` + `status.json` của worker (vì `drift_*`/`empty_frac_window` **không** đi qua API), chụp ảnh `/api/live/frame` ở 3 mốc;
4. ghi artifact JSON có provenance: `git_rev`, `git_dirty`, `git_dirty_code` (bẩn **bỏ qua `data/`**), `git_loi`, `lenh`, `do_luc`, `moi_truong`, `thiet_lap`;
5. `_verdict()` chấm theo **4 điều kiện đăng ký trước** (`state = running`, `frames > 0`, `measured_fps > 0`, `mask_fps > 0`) — exit 1 nếu không đạt.

### Kết quả (`data/live_web_relay_2026-11-09_metrics.json`, `git_rev = e54439f`, `git_dirty_code = false`, `git_loi = null`)

| Đại lượng | Giá trị |
|---|---|
| `state` | `running` |
| `frames` | 1 → **694** trong ~25 s |
| `measured_fps` | **29,9** |
| `mask_fps` | **8,6** (VOS chạy nền, `vos_every=3`) |
| `drift_iou` / `p05` (`drift_n`) | 0,952 / **0,904** (182) |
| `mask_age_p95` | **272,4 ms** (kèm `age_n`) |
| `empty_runs` | 0 |

Ảnh bằng chứng `data/live_web_relay_2026-11-09/frame{1,2,3}.jpg` **không** commit (repo không giữ binary trong `data/`); đường dẫn + kích thước ghi trong artifact.

### Tài liệu bảo vệ được sửa cho khớp code

- `docs/tom-tat-do-an.md`: bỏ câu **sai** "Chưa có BE/FE web"; thêm bảng live hybrid; sửa "Không real-time" → "**mask** không real-time, HUD 29,9 FPS nhờ LK".
- `docs/doi-chieu-yeu-cau-gvhd.md`: mốc 02-11 → **09-11**, thêm web/API, camera thật, mIoU, drift, watchdog, H.264; số đếm kèm ngày + cách đếm lại.
- `docs/team-contribution.md`: số đếm khớp repo (**7 176 dòng** `src`, **1 343 dòng** `web/src`, **663 hàm test**, **167 commit**, 44 log).

### Kiểm tra

- `./run lint` ✓ · `./run test` → **704 passed** (5 deselected) · `./run testall` trong checkout chính → 709 passed (worktree thiếu checkpoint ⇒ 704 passed, 5 skipped)
- Artifact đọc lại: `git_dirty_code = false`, `git_loi = null`

### Cái PR này KHÔNG nói

- Nguồn là **relay HTTP trên localhost** (đường `./run relay` + `./run demoip`), không phải V4L2 trực tiếp trong WSL (webcam WSL kẹt `Device busy` ở driver usbipd — AGENTS §6).
- `mask_age_p95 = 272 ms` là của **nguồn relay**, **không** trộn với 210–250 ms của clip `binh1`.
- Không nói "mask 30 FPS".
