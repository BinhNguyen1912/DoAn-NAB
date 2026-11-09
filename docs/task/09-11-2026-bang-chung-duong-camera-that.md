# Ngày 09-11-2026 — Bằng chứng "camera thật đã chạy": webcam → relay HTTP → API live → mask

> Việc này nằm trong plan `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md` ở dạng **câu hỏi
> chưa trả lời**: plan ghi thẳng "đường relay→web **chưa từng chạy**, E2E chỉ dùng video 160×120 tự
> sinh". Vì máy này webcam WSL kẹt `usbipd` (AGENTS §6), relay là đường demo thật **duy nhất** ⇒ phải
> có bằng chứng trước ngày bảo vệ, không phải thử trước hội đồng.

## 🎯 Mục tiêu
Trả lời bằng **file mở được** (không bằng lời) ba câu hội đồng chắc chắn hỏi:
1. *Camera thật đã chạy chưa, hay chỉ video?*
2. *Đường web (API + React) có đi với camera thật không?*
3. *Mask có thật sự cập nhật khi chạy camera, hay chỉ HUD 30 FPS?*

Điều kiện đăng ký trước (ghi trong script, không sửa sau khi thấy số): `state=running`,
`frames > 0`, `measured_fps > 0`, `mask_fps > 0`. **Không** đặt mục tiêu FPS/mIoU — đây là bằng chứng
"đường ống chạy được", không phải benchmark chất lượng bám.

## 📥 Input
- Relay camera Windows → WSL: `scripts/cam_relay.sh` (`./run relay`), phục vụ
  `http://<win>:8090/snapshot.jpg` **và** `/video` (MJPEG). Đoạn này chạy trên máy Windows của sinh
  viên, camera 640×480 @ ~21 fps.
- API live: `src/api/live.py` + adapter `OpenCvFrameSource` (nguồn `mode=track` spawn worker SAM 2).
- Trạng thái worker: `status.json` (schema ở `src/live_tracking.py:151-179`).
- **File thay đổi**: `scripts/measure_live_relay.py` (mới), `tests/test_measure_live_relay.py` (mới),
  `docs/task/09-11-2026-bang-chung-duong-camera-that.md` (mới), `docs/tom-tat-do-an.md`,
  `docs/doi-chieu-yeu-cau-gvhd.md`, `docs/team-contribution.md` (sửa số cũ), `.gitignore`
  (chặn symlink worktree), `data/live_web_relay_2026-11-10_metrics.json` (artifact).
- Trước việc này: **chưa có artifact nào** chứng minh relay → API live → worker SAM 2 → mask.

## 🔨 Công việc đã thực hiện
1. **`scripts/measure_live_relay.py`** (mới): dựng `uvicorn src.api.main:app`, `POST
   /api/live/start` với `{source: <snapshot URL>, mode: "track", bbox, image_size, vos_every}`, chờ
   `running`, lấy mẫu `/api/live/status` mỗi 0,5 s trong N giây, chụp tối đa 3 frame từ
   `/api/live/frame` (có overlay mask), `POST /api/live/stop`, rồi ghi artifact JSON.
   - Ghi **cả hai nguồn số**: `/api/live/status` (chỉ 6 trường) và `status.json` của worker
     (`drift_*`, `mask_age_*`, `vos_ms`…) — vì `drift` **không đi qua API live**.
   - Provenance dùng lại `_git_provenance()` của `scripts/measure_watchdog.py` (`git_rev`,
     `git_dirty`, `git_dirty_code`, `git_loi`) để artifact tái lập được (AGENTS §6).
   - `None` (chưa đo) **không** bị đổi thành `0,0`; phán quyết tách khỏi số liệu (`_verdict`).
2. **`tests/test_measure_live_relay.py`** (mới, 8 test hàm thuần): `summarize()` + `_verdict()` —
   khoá 2 bẫy đã gặp trong repo: (`None`→`0,0`) và ("phiên không vào `running` vẫn in bảng đạt").
3. **Chạy thật** với camera (relay đang sống: `/info` trả `{"w": 640, "h": 480, "fps": 21.3}`),
   ô chọn `110,35,95,110` (vùng tối ở góc trên-trái khung: giá treo/quạt trên gác lửng).

## 📤 Output / Kết quả

### Số đo thật — `data/live_web_relay_2026-11-10_metrics.json`
`git_rev = da1d671`, `git_dirty = true` (chỉ do chính file
artifact đang được ghi), **`git_dirty_code = false**`, `git_loi = null`,
`ket_qua = true` · `do_luc = 2026-11-10T00:21:20`
lệnh: `python scripts/measure_live_relay.py --source http://172.19.176.1:8090/snapshot.jpg --bbox 110,35,95,110 --image-size 192 --vos-every 3 --seconds 25 --port 8015 --out data/live_web_relay_2026-11-10_metrics.json`
môi trường: WSL laptop CPU (Iris Xe, torch CPU), SAM 2.1 tiny, nguồn = **camera thật qua relay**:

| Chỉ số | Giá trị | Nguồn |
|---|---|---|
| `state_cuoi` | **running** (kết thúc bằng `stop()` của script) | `/api/live/status` |
| `frames` | 1 → **681** trong 25 s (frame *đổi nội dung*) | `/api/live/status` |
| `measured_fps` max | **29.9** | `/api/live/status` |
| `display_fps` max / cuối | **30.1** / 29.9 (nhịp HUD, nhờ LK lặp frame) | `/api/live/status` |
| `mask_fps` max / cuối | **8.4** / 6.6 | `/api/live/status` |
| `vos_ms` / `lk_ms` | 99.2 / **1.56** | `status.json` |
| `vos_fps` / `vos_runs` | 6.7 / 173 | `status.json` |
| `drift_iou` / `p05` / `drift_n` | **0.965 / 0.933 / 171** | `status.json` |
| `mask_age_total_ms` / `p95` | 259.7 / **281.6** (`age_n` 200) | `status.json` |
| `stability` | 0.976 | `status.json` |
| `empty_runs` / `mask_drops` / `lost_streak` | **0 / 0 / 0** | `status.json` |
| Ảnh overlay | `data/live_web_relay_2026-11-10/frame{1,2,3}.jpg` | `/api/live/frame` |

**Kết luận: ĐẠT** cả 4 điều kiện đăng ký trước (0 lý do không đạt).

> **Frame 694 (lần đo 09-11) / 681 (lần này) không phải "FPS thấp hơn HUD".**
> `frames` đếm frame **đổi nội dung**; relay phát lại khung hình cuối (`/snapshot.jpg`) nên `frames`
> thấp hơn `display_fps`. Hai số đo hai thứ khác nhau — đừng chia `frames / 25 s` rồi so với HUD.

### Ảnh bằng chứng
> Ảnh **không** được commit: repo không giữ binary trong `data/` (`.gitignore` chỉ cho
> `*_metrics.json`, `*_summary.json`, `*_metrics.csv`…). Muốn đưa vào báo cáo thì copy 3 file này sang
> thư mục tài liệu/hình của báo cáo.

`data/live_web_relay_2026-11-10/frame2.jpg` (mở được trên máy demo): khung hình camera thật + **mask
màu cam** trong hộp đỏ + HUD `LIVE 29.8fps | VOS 8.4fps 182ms | LK 1.4ms`. Đây là ảnh trả lời trực
tiếp câu "mask có thật sự chạy khi dùng camera không".
> Ảnh **chỉ có trên máy đã chạy phép đo** — KHÔNG nằm trong repo (quy ước không giữ binary trong
> `data/`). Bằng chứng trong repo là **artifact JSON**; muốn ảnh trong báo cáo thì copy sang thư mục
> hình của báo cáo.

### Điều ảnh/số này KHÔNG nói
- **Không** nói "bám đúng vật": ô chọn do người chọn tay, SAM 2 bám đúng *vùng đó*; khung cảnh (gác
  lửng, giá treo) không phải cảnh demo đẹp.
- **Không** phải benchmark chất lượng: `drift_iou` 0,952 là **độ tự nhất quán** của ô bao, KHÔNG phải
  độ chính xác (AGENTS §6). Chất lượng phân đoạn vẫn chỉ có cận trên trên fixture tổng hợp.
- **`mask_age_p95` 281,6 ms ở cấu hình này** (nguồn snapshot qua relay, `image_size 192`, `vos_every 3`)
  — cao hơn dải 210–250 ms đã đo trên clip `binh1`; **khác nguồn** nên đừng trộn hai số.
- Chưa chạy phần **kéo chuột chọn đối tượng trên UI web** với camera thật (e2e phủ thao tác đó bằng
  nguồn video 160×120 tự sinh); việc này cần trình duyệt + camera cùng lúc.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Lần đo đầu `drift_n`/`mask_age_p95` = None**: tưởng worker không đo drift; thực ra
  `/api/live/status` **không mang** các trường đó (chỉ 6 trường). Sửa: đọc thêm `status.json` của
  worker và ghi rõ nguồn từng số trong artifact (`tom_tat` = từ API, `worker_status` = từ file).
- **Commit message bị shell nuốt lệnh**: `git commit -m "… `drift_iou` …"` trong bash khiến phần trong
  dấu backtick bị thực thi (`/snapshot.jpg: No such file…`). Sửa bằng `git commit -F <file>` —
  từ nay mọi commit message có backtick đều phải dùng `-F`.
- **`_read_safely`/health không liên quan**: đường relay ở đây dùng `OpenCvFrameSource` **đã** có
  watchdog (nhánh `fix/health-mode-raw-va-message-409`); nhánh này dựa trên nó.

### Review độc lập (§9.1)

| Vòng | Phát hiện | Xử lý |
|---|---|---|
| 1 | **P1**: `git_rev = e54439f` **không phải tổ tiên của HEAD** (nhánh đã rebase sau khi đo) ⇒ clone mới không `git show` được; **P1**: số đếm mâu thuẫn ngay trong 3 trang được sửa (164 vs 167 commit, 692/697 vs 704, "28 file log" vs 44, ADR 0001→0004 vs 5, còn sót "131 test"); P2: `ket_qua: true` kèm `loi`; `summarize` đọc `drift_*` mà API **không có** (luôn `None`); `status.json` cũ của lần trước có thể bị gán cho lần này; ảnh bằng chứng không có trong repo; log thiếu mục review + danh sách file | **Chạy lại phép đo trên HEAD** (`da1d671`, camera sống) ⇒ `git_rev` hợp lệ, số mới; cảnh báo tự động khi `git_rev` không phải tổ tiên của HEAD; dọn số đếm 3 trang; `ket_qua` gộp `loi`/`git_loi`; `summarize` bỏ khoá API không có + thêm `display_fps`; xoá `status.json` trước khi `Popen`; ghi rõ ảnh không có trong repo; thêm mục review + danh sách file |

Nợ lại (không chặn merge): đưa 3 lỗi **trước `try`** trong `main()` (mkdir/Popen/open log) vào
`try` để mọi nhánh đều ghi artifact; bước CI `grep` cấm số đếm cũ trong `docs/`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Chạy lại đúng đường này **trong trình duyệt** (kéo chuột trên khung ảnh camera) và chụp màn hình
      UI — cần người dùng, vì phải quan sát màn hình.
- [ ] Quay clip camera thật (vật bị che một phần; vật ra/vào khung) để đo drift che khuất — cần người.
- [ ] Bộ **preflight** cho ngày demo: kiểm relay sống + checkpoint có + cổng trống, in checklist.
- [ ] Sửa 3 trang tài liệu bảo vệ còn câu sai/thiếu (`docs/tom-tat-do-an.md` mục "Chưa có BE/FE web",
      `docs/team-contribution.md` số liệu cũ, `docs/doi-chieu-yeu-cau-gvhd.md` cập nhật 02-11).

## 📚 Tài liệu tham khảo
- `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md` (mục "chưa từng chạy").
- `scripts/cam_relay.sh`, `scripts/win_camera_relay.py` — relay và lý do chọn `/snapshot.jpg`
  (rẻ hơn MJPEG ~22 ms/frame, đo 05-11).
- `AGENTS.md` §6 — quy tắc trích số (`drift_iou` là tự nhất quán, `mask_age` phải kèm `age_n`).
