# Ngày 09-11-2026 — Chẩn đoán chất lượng bám: mất dấu theo CỬA SỔ + phơi drift kèm số mẫu

> Việc này theo plan `docs/plan/09-11-2026-chan-doan-chat-luong-bam.md` (3 ý kiến + chốt). Làm sau
> khi đã xong bằng chứng camera thật (`docs/task/09-11-2026-bang-chung-duong-camera-that.md`) và sửa
> 3 trang tài liệu bảo vệ.

## 🎯 Mục tiêu
Sửa hai con số **đang gây hiểu sai** trên UI live và phơi số chẩn đoán trung thực:

1. **"mất dấu: N lần"** lấy từ `empty_runs` — bộ đếm **trọn đời, không bao giờ giảm** ⇒ phiên đã hết
   mất dấu vẫn hiện "26 lần" như đang lỗi. Cần đại lượng **theo cửa sổ** (trở về 0 khi model bám lại).
2. **"độ ổn định N%"** cho `stability` — đại lượng này chỉ là IoU giữa hai mask **liên tiếp**, đo
   **nhấp nháy**, không đo chất lượng phân đoạn.
3. **`drift_iou_p05` chưa từng đi qua API/UI**, và nếu đưa lên thì phải kèm **số mẫu** + nhãn "IoU tự
   nhất quán (không phải độ chính xác)"; `None` (chưa đo) **không** được hiện thành `0,00`.

Tiêu chí đăng ký trước (ghi trong plan, không sửa sau khi thấy số): binh1 (clip khoẻ) ⇒
`empty_frac_window = 0`; binh2 (clip xấu đã biết) ⇒ `empty_frac_window > 0`; `vos_every=1` ⇒
`drift_p05 = null` + UI hiện "chưa đo được", **không bao giờ** hiện "tốt".

## 📥 Input
- `data/drift_2026-11-08_metrics.json` (số nền: binh1 p05 0,663–0,720, `empty_runs` 0/267 lần VOS;
  binh2 p05 0,000, `empty_runs` 26/233), ngưỡng nhiễu (±0,004 / ±0,057 / ±1,2 % / ±0,3 % / ±3 ms).
- Code: `src/live_tracking.py` (`_measure_stability`, `LiveTrackStats`, `status_payload`),
  `src/api/{domain,ports,schemas,routes,live}.py`, `src/api/adapters/worker_source.py`,
  `web/src/{api.ts,live.ts,components/LivePanel.tsx}`.
- Clip + ô chọn: `binh1` = `104,308,209,287`; `binh2` = `200,400,300,500` (ô chọn là **đầu vào** của
  phép đo — xem mục "Vấn đề").

## 🔨 Công việc đã thực hiện
1. **`empty_frac_window` + `empty_window_n`** (`src/live_tracking.py`): mỗi lần VOS trả kết quả đẩy
   **đúng một mẫu** (`True` = mask rỗng) vào deque 200 phần tử ⇒ `empty_frac_window` là tỉ lệ **200
   lần VOS gần nhất**, `None` khi < 5 mẫu. Có mặt trong `LiveTrackStats` + `status.json`.
2. **`_STAT_MIN_SAMPLES` 5 → 30** cho phân vị (`drift_iou_p05`, `mask_age_p95`): với n = 5,
   `np.percentile(values, 5)` lấy chỉ số 0,2 ⇒ nằm giữa **min** và phần tử nhỏ thứ 2, tức "một mẫu
   xui" — công bố nó thành "p05" là lỗi trung thực (phiên 0,7 s có thể hiện "p05 = 0,0").
3. **API**: `LiveTelemetry`/`LiveStatus`/`LiveStatusResponse` mang thêm `drift_p05`, `drift_n`,
   `empty_frac_window`, `empty_window_n`; adapter dùng `_so_hoac_none()` để **`None` không thành
   `0.0`** (bẫy AGENTS §6).
4. **UI** (`web/src/live.ts`): "độ ổn định" → "**nhấp nháy mask**"; "mất dấu: N lần" → "**P% của N
   lần chạy gần nhất**" (rơi về số trọn phiên khi chưa đủ mẫu). Thêm `driftLine()`: hiện
   `IoU tự nhất quán p05 (LK↔VOS): 0.65 · 200 mẫu gần nhất · không phải độ chính xác`, hoặc
   `IoU tự nhất quán (LK↔VOS): chưa đo được (12 mẫu) — không kết luận` (ngưỡng mẫu do **backend**
   quyết qua `drift_p05 == null`, UI không nhân bản hằng số).
5. **`scripts/measure_empty_window.py`** (+ `tests/test_measure_empty_window.py`): chạy worker cho
   từng clip + ô chọn, ghi artifact có `git_rev`/`git_dirty_code`/`lenh`/`do_luc`, có `--expect-lost`
   để **tự kiểm phép đo** (kỳ vọng sai ⇒ thoát mã 1).

## 📤 Output / Kết quả

### Số đo thật (mỗi clip 900 frame, `image_size 192`, `vos_every 3`)

Bảng dưới chép **từ artifact** (`data/empty_window_2026-11-09_metrics.json`), không chép từ trí nhớ:

| Clip (ô chọn) | `empty_runs` (trọn đời) | **`empty_frac_window`** (200 mẫu gần nhất) | `drift_iou_p05` (`drift_n`) | `mask_age_p95` |
|---|---|---|---|---|
| `binh1` (104,308,209,287) | **0** | **0.0** (200 mẫu) | 0.651 (200) | 236.5 ms |
| `binh2` (200,400,300,500) | 33 | **0.165** (200 mẫu) | **0.0** (193) | 240.5 ms |

> Bảy lần chạy (mỗi lần ghi đè **cùng** một file) cho `binh2` **0,12 / 0,13 / 0,14 / 0,165 / 0,17 /
> 0,20 / 0,205** và `drift_p05 = 0,000` **cả 7 lần**; `binh1` **0,00** cả 7 lần. Muốn giữ nhiều lần
> thì truyền `--out …_run<N>.json` — vì mọi lần ghi cùng một tên file nên chỉ lần cuối còn chứng cứ.

- Artifact cuối: `data/empty_window_2026-11-09_metrics.json` — `git_rev = af84285`
  (commit chứa code đang review), `git_dirty = false`,
  `git_dirty_code = **false**`, `git_loi = null`.
  Lệnh ghi trong file.
- **Kết luận có số:** clip khoẻ cho **0/200 lần VOS mất dấu (0,00)**; clip xấu cho **0,12–0,20** và
  `p05 = 0,000` ⇒ hai lớp **tách rời hoàn toàn**, không phụ thuộc ngưỡng nhiễu (đây là phép **đếm sự
  kiện**, không phải phân vị).
- **Độ tản phải nói rõ:** tỉ lệ của `binh2` dao động **0,12–0,20 qua 4 lần chạy** (SAM 2 không tất
  định — AGENTS §6). Chỉ nên trích **"0,00 vs > 0"** (phân biệt nhị phân, 4/4 lần đúng), **không**
  trích một con số lẻ như "12 %" cho báo cáo.

### Kiểm tra tự động
- `./run lint` ✓ · `./run test` **719 passed** (5 deselected, ~59 s) · `./run testall` **724 passed**
  (~183 s) · `./run webtest` **30 passed** · `npm --prefix web run build` OK · `./run e2e` **PASS**
  (chạy ở repo chính: worktree không chạy được e2e vì node Windows không resolve symlink
  `web/node_modules`)
- Test mới: 4 test đếm theo cửa sổ (1,0 → 0,5 → 0,0 trong khi bộ đếm trọn đời đứng yên; 200 mẫu có
  vật ⇒ về 0; < 5 mẫu ⇒ `None` chứ không phải 0), 2 test ngưỡng phân vị (n = 5 thì "p05" là mẫu xui),
  4 test adapter/API (`None` ≠ 0,0; ca `binh2` p05 = 0,0 vẫn là **0,0**), **14 test vitest** (nhãn
  nhấp nháy đúng chiều + `driftLine` + ngưỡng mẫu lấy từ backend), **11 test** cho script đo, và
  2 test session-level kiểm `empty_window_n == min(200, vos_runs)` qua **đường thật** (double-push
  sẽ làm đỏ).
- **Test cũ phải sửa (có lý do, không phải "sửa cho xanh")**: `test_status_duoc_ghi_moi_frame` thêm 2
  khoá vào allowlist; `test_tuoi_mask_literal_va_gom_ca_vos_ms` trước kiểm `mask_age_p95` với **10
  mẫu** — đúng loại lỗi vừa sửa, nên đổi thành: 10 mẫu ⇒ `None`, 30 mẫu ⇒ có số.

### Review độc lập (§9.1)

| Vòng | Ai | Phát hiện | Xử lý |
|---|---|---|---|
| 1 | subagent `reviewer` (đọc-only) | **P1**: nhãn UI `nhấp nháy mask: N%` in `stability × 100` — **đảo chiều** (`stability = 1,0` là *êm*), và `stability = 0` vừa là "chưa đo" vừa là giá trị bị đặt khi mask rỗng ⇒ in "0 %" đúng lúc mất dấu. P2: hằng số 30 nhân bản ở UI; chữ "LK lệch" đọc thành "không lệch"; log chép tay thay vì chép từ artifact | Sửa `100 − Math.round(...)` + 2 test (đảo lại ⇒ **đỏ**); UI bỏ hằng số, ngưỡng do backend; đổi wording; log chép lại từ artifact |
| 2 | subagent `reviewer` | P1 trên (đọc bản **trước** khi commit nên tưởng còn) + P2: `--expect-lost` vắng ⇒ clip xấu đo thành công vẫn thoát mã 1; log mô tả copy UI cũ + số test cũ; P3: docstring "mask rỗng không vào mẫu", 2 khối `_stats_lock` liền nhau, test chỉ gọi hàm phụ (`_feed`) nên double-push vẫn xanh, `frames` ngắn không bị chấm, `mask_drops ≡ 0` không ghi chú, `git_rev` artifact (pre-rebase) không reachable | Sửa hết: chỉ chấm clip được khai + `frames` ngắn là lỗi đo; gộp 1 khối lock; docstring rõ; thêm 2 test **session-level** `empty_window_n == min(200, vos_runs)` (append 2 lần ⇒ **đỏ**); ghi chú `mask_drops`; **đo lại** artifact tại `af84285` |
| 3 | subagent `reviewer` | (kết quả ghi ở mục "Việc cần làm tiếp" nếu còn P1/P2) | — |

Race `_drift_window` (2 luồng ghi, một ngoài lock — có từ 08-11) → **ticket 17**, không nới phạm vi PR.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Ô chọn sai ⇒ số vô nghĩa**: lần đầu chạy `binh2` bằng bbox của `binh1` (104,308,209,287) cho
  `empty_runs = 0`, `p05 = 0,255` — trông như "binh2 không còn xấu". Đúng bbox của binh2
  (200,400,300,500, lấy từ log 08-11) cho lại **`empty_runs` = 24–40, `p05 = 0,000`**. Bài học đã ghi
  vào docstring script: **bbox là đầu vào của phép đo**.
- **`git_dirty_code` = true** khi đo trong worktree: symlink `models`/`samurai`/`web/node_modules`
  bị tính là file lạ. Xử lý: `.gitignore` bỏ dấu `/` cho `models` và `samurai` (symlink tới bản dùng
  chung), và gỡ symlink `web/node_modules` trước khi đo.
- **Rebase nhánh này lên nhánh watchdog**: hai bên cùng thêm class test ở cuối file ⇒ giữ **cả hai**
  vế (không mất test nào), 711 test xanh sau rebase.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Ticket 17**: `_drift_window` có 2 luồng ghi, một luồng ngoài `_stats_lock` ⇒ có thể
      `deque mutated during iteration` (lỗi có từ 08-11, không phải của nhánh này).
- [ ] API thêm `stability_n` (như `drift_n`) để người dùng API phân biệt "0 = tệ nhất" với
      "0 = chưa đo" — hiện chỉ UI phân biệt được (note review vòng 2).
- [ ] E2E trình duyệt đang chạy live ở `mode=raw` (`mask_fps = 0`) nên **không** render 2 dòng UI
      mới; muốn phủ thì stub `/api/live/status` với `mask_fps > 0` (note review vòng 2).
- [ ] **Cờ phán quyết** (`model_lost` / `drift_trend`) — ticket 14: **chờ** clip có `p05` thấp mà
      `empty_frac_window ≈ 0`; hiện chưa có nên cờ sẽ chỉ là bản sao của `empty_frac_window`.
- [ ] **Log từng mẫu drift ra CSV + đối chứng cảnh tĩnh** — ticket 15 (để ngưỡng thành tái lập được).
- [ ] Chạy cùng đường này khi có **clip vật bị che đi ngang** (điều kiện duy nhất để biết `p05` có
      giá trị độc lập hay chỉ là bản sao của tỉ lệ mất dấu).
- [ ] Ảnh UI có dòng chẩn đoán mới (cần người ngồi trước máy chụp màn hình).

## 📚 Tài liệu tham khảo
- `docs/plan/09-11-2026-chan-doan-chat-luong-bam.md` — 3 ý kiến + chốt + phương án **bị bác** kèm số
  (tự giảm `vos_every`: p05 đổi 0,000–0,010 < ±0,057 và `mask_fps` không tăng; reset LK: cơ chế đã
  chạy mỗi frame và binh2 hỏng ở phía VOS).
- `AGENTS.md` §6 — `0` ≠ `None`, `drift_iou` là độ tự nhất quán, SAM 2 không tất định.
- `docs/task/08-11-2026-do-cai-gia-noi-suy-lk-va-nguong-nhieu.md` — ngưỡng nhiễu + số nền 3 clip.
