## Chẩn đoán chất lượng bám: "0,00" không phải "chưa đo" — và nhãn "nhấp nháy" bị đảo chiều

Nhánh này trả lời đúng một câu hỏi: **khi mask rơi vật, HUD/API đang nói gì?** Câu trả lời trước PR: nó in `0,00` (đọc thành "không lệch") hoặc nói ngược chiều (`nhấp nháy mask: 0%` = "êm tuyệt đối") đúng lúc mất dấu.

### Bằng chứng trước khi sửa

`data/empty_window_2026-11-10_metrics.json` (900 frame mỗi clip, `image_size 192`, `vos_every 3`; `git_rev = eb008e3`, `ket_luan = "đạt"`, `git_dirty_code = false`, `git_loi = None`):

| Clip (ô chọn) | `empty_runs` (trọn đời) | `empty_frac_window` (200 mẫu gần nhất) | `drift_iou_p05` (`drift_n`) | `mask_age_p95` |
|---|---|---|---|---|
| `binh1` (104,308,209,287) | 0 | **0.0** (200 mẫu) | 0.661 (200) | 236.0 ms |
| `binh2` (200,400,300,500) | 32 | **0.16** (200 mẫu) | **0.0** (196) | 229.8 ms |

`binh2` có **32 lần model trả mask rỗng** (KHÔNG phải LK mất dấu: `mask_drops`/`lost_streak` = 0) ⇒ `drift_iou_p05 = 0,000`. Trước PR, UI in `LK lệch p05: 0.00` — đọc thành "lệch 0,00 = không lệch", tức **mất dấu được trình bày như bám hoàn hảo**. Đồng thời `stability = 0` (vừa là mặc định "chưa đo" vừa là giá trị bị đặt khi mask rỗng) làm nhãn `nhấp nháy mask: 0%` = "êm tuyệt đối".

`binh2` dao động **0,12–0,21 qua 9 lần chạy**, p05 = **0,000 cả 9 lần**; `binh1` = **0,00 cả 9 lần** ⇒ tín hiệu phân biệt được (0,00 vs > 0), nhưng **không** phải "chất lượng bám" theo nghĩa mIoU.

### Thay đổi

**1. Chỉ số mới "mask rỗng theo CỬA SỔ"** (`src/live_tracking.py`) — `_vos_lost_window = deque(maxlen=200)`, mỗi kết quả VOS đẩy **đúng một** mẫu; `empty_frac_window` = tỉ lệ 200 lần gần nhất (`None` khi < 5 mẫu). `empty_runs` vẫn là bộ đếm **trọn đời** — hai đại lượng khác nhau, không thay thế nhau. Ghi vào `status.json`.

**2. `stability` không còn "0 = chưa đo"** — mất dấu đặt `stability = 0.0` **và** reset `_prev_raw_mask` (không nối IoU xuyên qua khoảng mất dấu).

**3. UI không đoán, không nhân bản hằng số** (`web/src/live.ts`, `LivePanel.tsx`) — `nhấp nháy mask: N%` in **`100 − stability`** (vì `stability = 1,0` là *êm*), `stability <= 0` ⇒ "chưa đo"; `IoU tự nhất quán p05 (LK↔VOS): … (n mẫu) · không phải độ chính xác`, `drift_p05 == null` ⇒ "chưa đo được (n mẫu)" — ngưỡng 30 do **backend** quyết.

**4. API tự mô tả** — `drift_iou`, `drift_iou_p05`, `empty_frac_window` đi adapter → domain → schema (`float | None`) → `api.ts` với `None` nguyên vẹn; `0,0` **đo được** vẫn là `0,0` (có test).

**5. Script đo tái lập được** (`scripts/measure_empty_window.py`) — provenance `git_rev`/`git_dirty`/`git_dirty_code` (bẩn **bỏ qua `data/`**)/`git_loi`/`lenh`/`do_luc`; exit 1 **chỉ** cho lỗi đo; clip không khai `--expect-lost` ghi "kỳ vọng không đặt"; **không khai clip nào ⇒ `ket_luan = "CHỈ ĐO — không kiểm chứng gì"`** (một lần đo không được đọc thành "đã đạt").

### Kiểm tra

- `./run lint` ✓ · `./run test` → **725 passed** · `./run testall` → **730 passed** · `./run webtest` → **31 passed** · `npm --prefix web run build` OK · `./run e2e` → **PASS**
- "Có răng": đảo `100 − stability` ⇒ 2 test vitest đỏ; append hai lần vào cửa sổ ⇒ 2 test session-level đỏ.

### Review độc lập (§9.1) — 3 vòng

| Vòng | Phát hiện | Xử lý |
|---|---|---|
| 1 | **P1**: nhãn `nhấp nháy` **đảo chiều số** ⇒ in "0 %" đúng lúc mất dấu; P2: hằng số 30 nhân bản ở UI, chữ "LK lệch", log chép tay | `100 − Math.round(...)` + 2 test; UI bỏ hằng số; log chép từ artifact |
| 2 | P2: `--expect-lost` vắng ⇒ clip xấu thoát mã 1; log mô tả copy UI cũ + số test cũ; P3: docstring "mask rỗng không vào mẫu", 2 khối lock, test chỉ gọi hàm phụ, `frames` ngắn không bị chấm | Sửa cả 5; thêm 2 test **session-level** `empty_window_n == min(200, vos_runs)` |
| 3 | **P1**: `--help` hứa "clip không khai ⇒ kỳ vọng KHÔNG mất dấu" nhưng code chỉ chấm clip được khai (3 chỗ chữ, 2 nghĩa); P2: `co_truong_empty_window` luôn `True`, artifact sinh bằng bản script cũ, log còn "qua 4 lần"; P3: `_iou_window.append` ngoài lock, UI "chưa đo" lúc mất dấu, thiếu test `stability` NaN | `_ket_luan()` (đạt/KHÔNG ĐẠT/**CHỈ ĐO**); `_row_from_status()` tính cờ từ status THÔ; `ky_vong` cho mọi clip; đo lại artifact; append vào lock; +1 test vitest; `stability_n` → **ticket 18** |

| 4 | **P1** (tài liệu): plan chép số của artifact **đã bị ghi đè** trong khi nguồn dẫn file khác. P2: clip **không khai** kỳ vọng mà `empty_frac_window = None` vẫn exit 0. P3: `live_worker.py` **luôn** trả 0 kể cả khi luồng VOS chết (`state=error` không ai đọc); stderr rỗng in repr list; `--expect-lost` chỉ khai được clip xấu; test session-level dùng 12 frame ⇒ đúng 5 mẫu = ngưỡng ⇒ **flaky**; README thiếu 4 trường | Chép lại số từ artifact; `_chua_du_mau()` + `_frame_shortfall()` (có test); đọc `state == "error"`; **`--expect-keep`**; 30 frame; README liệt kê `empty_frac_window`/`empty_window_n`/`drift_p05`/`drift_n` |

Race `_drift_window` (2 luồng ghi, một ngoài lock — có từ 08-11) → **ticket 17**, không nới phạm vi PR.

### Cái PR này KHÔNG nói

- **Không** nói chất lượng bám tốt hơn: `drift_iou` là **độ tự nhất quán**, không phải độ chính xác. Độ chính xác chỉ có mIoU mask vs GT (0,96 nền / 0,89 che 50 % trên fixture tổng hợp).
- **Không** nói "mask 30 FPS": mask lấy từ model cũ ~0,2 s; HUD 30 FPS là nhờ LK.
- Chỉ **một clip, một máy**; SAM 2 không tất định ⇒ chỉ kết luận "0,00 vs > 0".
