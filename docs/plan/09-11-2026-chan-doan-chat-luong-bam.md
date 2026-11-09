# Plan 09-11-2026 — Phản ứng gì khi "drift xấu"? (3 ý kiến + chốt)

> Làm theo `AGENTS.md` §9.2. Câu hỏi đặt ra từ Next steps của log 09-11: *"Tự hạ cấp/cảnh báo khi drift
> xấu (`p05 < 0,2` như `binh2`): hiện mới đo, chưa hành động."*
> Ba ý kiến độc lập, ba góc nhìn khác nhau, không biết đề xuất của nhau:
> **(A)** bản đồ code + 3 phương án (agent `explore`), **(B)** chất lượng bám & số đo trung thực
> (agent `advisor`, góc "chất lượng"), **(C)** sản phẩm & bằng chứng bảo vệ (agent `advisor`, góc "sản phẩm").
> Bản đầy đủ của ba ý kiến nằm ở phiên tương ứng (`.pi/artifacts/tasks/*.md`, không commit).

## 🎯 Câu hỏi cần quyết
Khi `drift_iou_p05` thấp (đo được: `binh2` = **0,000**; `binh1` 0,663–0,720; `simloss` 0,644):
1. **Tự hạ cấp** (`vos_every` nhỏ hơn khi drift xấu)? 2. **Chỉ cảnh báo** trên HUD/API/UI? 3. **Reset LK**?
Hay làm việc khác trước?

## 🧭 Ba ý kiến (vòng 1 — độc lập)

### A. Bản đồ code + 3 phương án (góc "đọc code")
- Nơi đo/ghi: `src/live_tracking.py:492-534` (`_measure_drift`, `_record_drift`, `_apply_drift_locked`),
  `_STAT_WINDOW = 200`, `_STAT_MIN_SAMPLES = 5` (`:48-50`); payload `status_payload` `:151-179`.
- `drift` **không đi qua API live**: `worker_source.telemetry()` `:142-148` chỉ lấy 6 trường;
  `web/` **0 khớp** chữ "drift".
- (a) tự giảm `vos_every`: sửa `:425` + state mới. **(c)** reset LK: `_interp.reset()` **đã chạy mỗi
  frame** (`:443`); `binh2` hỏng vì VOS trả mask rỗng 26 lần (`mask_drops = 0`, `lost_streak = 0`).
- (b) cảnh báo: phải xuyên 5 tầng `LiveTrackStats → LiveTelemetry → worker_source → LiveStatus →
  schemas → web/src/live.ts`; bẫy `float(status.get("drift_iou") or 0.0)` biến `None` → `0,0`.

### B. Chất lượng & số đo trung thực (góc "chất lượng")
- Chọn **(b) bản thu hẹp**: **bỏ phần "phán nguyên nhân"** ("LK nội suy lệch"). Lý do có bảng: trên
  cả 3 clip, `p05` và `empty%` **đi cùng nhau 1:1** (binh1 0/798 = 0 % → p05 0,663–0,720; [tỉ lệ
  trọn đời, xem chú thích mục quyết định]
  simloss 16/233 = 6,9 % → 0,644; binh2 26/233 = 11,2 % → **0,000**) ⇒ **không có clip nào p05 thấp
  mà empty ≈ 0** ⇒ cờ "nội suy lệch" là **claim chưa kiểm chứng được**.
- Phát hiện thêm (đều là lỗi trung thực đang tồn tại):
  - `_STAT_MIN_SAMPLES = 5` ⇒ từ mẫu thứ 5 `drift_iou_p05` đã được công bố, mà ở n = 5 nó **chính là
    min của 5 mẫu** ⇒ phiên 0,7 s có thể hiện "p05 = 0,0".
  - `mask_drops`/`mask_holds` **≡ 0** khi `mask_smoothing = 1.0` (mặc định) vì `_smoother` chỉ được
    tạo khi `< 1.0` (`:290`, gán ở `:605-606`) ⇒ **không được trích** "mask_drops = 0 ⇒ LK không mất dấu".
  - `drift_iou` là mean của `deque(maxlen=200)` ⇒ `binh1` vos3 chỉ phủ **200/267 = 74,9 %** lần VOS
    cuối clip, vos6 = 140 mẫu (92,7 %) ⇒ cấm gọi là "trung bình cả clip".
  - Nhánh `:506` **loại** mẫu khi VOS trả hộp suy biến ⇒ 26 lần mất dấu của `binh2` **không có mặt**
    trong p05 ⇒ drift là metric **bị cắt cụt**, luôn lạc quan hơn thực tế.
  - Độ trễ **bất đối xứng** của p05@200: bắt nhanh (~1,2 s khi hỏng hoàn toàn) nhưng **nhả chậm**
    (200 mẫu = **23,3 s @8,6 lần/giây**).
- Đề xuất: (1) **đếm mất dấu theo cửa sổ 200**; (2) **sửa 2 nhãn sai trên UI**; (3) phơi `drift_p05`
  **kèm `drift_n`** + nhãn "IoU tự nhất quán, không phải độ chính xác"; (4) cờ phán quyết + Schmitt
  0,30/0,45 **hoãn** tới khi có dãy mẫu; (5) log từng mẫu drift; (6) đối chứng cảnh tĩnh.

### C. Sản phẩm & bằng chứng bảo vệ (góc "sản phẩm")
- **Không (a), không (c), đừng (b) dạng banner ngay.** Việc tạo "câu chuyện bảo vệ" lớn nhất nằm ở chỗ
  khác: (i) **đường demo thật (webcam → relay → web → kéo chuột → mask) chưa từng chạy**, (ii) **3 trang
  tài liệu bảo vệ đang nói sai so với code** (`docs/tom-tat-do-an.md`: "Chưa có BE/FE web";
  `docs/team-contribution.md`: "131 test / 2 424 dòng / 25 commit"; `docs/doi-chieu-yeu-cau-gvhd.md`:
  cập nhật 02-11, chưa có web/API).
- Nếu vẫn làm cảnh báo: đổi tên thành **"Chẩn đoán chất lượng bám"**, luôn hiện **số nền** (không chỉ
  hiện khi xấu), không màu đỏ/từ "lỗi", và **không để lọt vào ảnh/video demo** của báo cáo.

## ⚔️ Điểm tranh chấp (vòng 2 — phản biện, do agent chính đóng vai trọng tài)

| Điểm | A | B | C | Chốt |
|---|---|---|---|---|
| Có làm cảnh báo ngay không? | (b) là lựa chọn duy nhất chưa bị số bác | làm, nhưng **thu hẹp** | **hoãn**, ưu tiên bằng chứng demo | **Làm phần "phơi số + sửa nhãn" (B#1–#3), hoãn cờ phán quyết (B#4)** — vì C đúng rằng bằng chứng demo cấp thiết hơn, nhưng B đúng rằng **2 nhãn đang in sai ngay bây giờ** là lỗi trung thực phải sửa ngay, và nó rẻ (2,5 h) |
| Tự hạ cấp `vos_every`? | khả thi về code | **bác** | **bác** | **BÁC** — số đo: vos3→vos2 đổi p05 chỉ **0,000–0,010** (< ngưỡng nhiễu ±0,057), `mask_fps` **không tăng** (7,5–7,8), `vos_every=1` làm FPS phát 29,9 → **9,5** |
| Reset LK khi drift xấu? | cơ chế đã có | **bác** | **bác** | **BÁC** — `_interp.reset()` đã chạy mỗi frame; `binh2` hỏng ở VOS (26 mask rỗng), reset LK không chạm nguyên nhân; và nó làm "drift đẹp lên" ⇒ **tối ưu chỉ số** |
| Cờ "LK nội suy lệch"? | đề xuất | **bác** (p05 và empty% đi cùng nhau) | — | **BÁC (tạm)** — chỉ xét lại khi có clip **p05 thấp mà empty ≈ 0**; ghi thành ticket |
| Ngưỡng p05 | 0,20 (next-steps cũ) | **0,30 vào / 0,45 ra** | — | **Hoãn** (chưa có dữ liệu để hiệu chuẩn; p05 < 100 mẫu không dùng) |
| Ưu tiên trước | (b) | #1+#2 (2,5 h) | bằng chứng demo + sửa docs | **Đã làm C trước** (bằng chứng camera thật + sửa 3 trang docs, xong 09-11), **nay làm B#1–#3** |

## ✅ Quyết định

**Đợt này (PR "chẩn đoán chất lượng bám", ~3–4 h, không cần model/GPU):**
1. **`empty_frac_window` + `empty_window_n`** trong `LiveTrackStats` + `status.json`: đếm **tỉ lệ lần
   VOS trả mask rỗng trong 200 lần chạy gần nhất**. Vì sao: `empty_runs` là bộ đếm **trọn đời, không
   bao giờ giảm** ⇒ UI đang in "mất dấu: 26 lần" cho một sự việc **đã qua**. Số nền đo được: clip khoẻ
   **0/798 = 0 %**, `binh2` **26/233 = 11,2 %** ⇒ phân biệt được, ngưỡng nhiễu không cần.
   *(Hai tỉ lệ này là số **TRỌN ĐỜI** lấy từ artifact 08-11 — 798/233 là số lần VOS cả phiên, không
   phải cửa sổ 200; tỉ lệ **theo cửa sổ** chỉ có từ 09-11: 0,00 vs 0,12–0,205.)*
2. **Nâng `_STAT_MIN_SAMPLES` 5 → 30** cho `drift_iou_p05`/`mask_age_p95`: ở n = 5, "p05" **là min của
   5 mẫu**; dưới 30 mẫu phải trả `None` (vẫn công bố `drift_n`/`age_n`). Giữ `p05` ở cửa sổ **200**
   (p05@30 lấy chỉ số 1,45 ≈ min — xem B).
3. **Phơi `drift_p05` + `drift_n` qua API live và UI**, `None` khi chưa đo (không bao giờ `0,0`), nhãn
   ghi rõ "IoU tự nhất quán (không phải độ chính xác)". `vos_every=1` ⇒ hiện "không đo được".
4. **Sửa 2 nhãn sai trên UI**: "độ ổn định N%" → "**nhấp nháy mask N%**" (`stability` chỉ đo nhấp nháy);
   "mất dấu: N lần" → dùng `empty_frac_window` + `empty_window_n`.
5. **Rút lại câu chữ `mask_drops`** ở mọi tài liệu (biến này **≡ 0** khi `mask_smoothing = 1.0`).

**Tickettize, chưa làm:**
- Cờ phán quyết + Schmitt (0,30/0,45) **chỉ sau khi có** clip `p05 thấp & empty ≈ 0` (điều kiện duy
  nhất để cờ này nói được điều `empty_frac_window` chưa nói).
- Log từng mẫu drift ra CSV (`frame_idx, vos_ms, empty, drift_iou, bbox`) để đo **độ trễ phát hiện** và
  **tỉ lệ báo oan** — biến ngưỡng từ "chọn tay" thành "chọn có số".
- Đối chứng **cảnh tĩnh**: `drift_iou ≥ 0,99` khi vật đứng yên (loại nghi ngờ "0,88 là sàn giả tạo").

**Tiêu chí nghiệm thu (có SỐ):**
- [x] Test: đẩy 5 mẫu rỗng ⇒ `empty_frac_window` **1,0**; thêm 5 mẫu có vật ⇒ **0,5** trong khi
      `empty_runs` **đứng ở 5**; đẩy thêm 200 mẫu có vật ⇒ **0,0**; < 5 mẫu ⇒ `None`
      (`::TestDemMatDauTheoCuaSo`, **unit-level**: gọi `_measure_stability` trực tiếp). Thêm 2 ca
      **session-level** `::TestMotMauMoiLanVos` (30 frame, `vos_every` 1 và 3) kiểm
      `empty_window_n == min(200, vos_runs)` đi qua `_record_vos` thật.
- [x] `binh1` (clip khoẻ): `empty_frac_window = **0,00**` (0/235 lần VOS, 200
      mẫu cửa sổ); `binh2`: **0.16** — `empty_runs` **trọn đời** =
      32/237 lần chạy (tỉ lệ trọn đời, KHÔNG phải `empty_frac_window`;
      cửa sổ dao động **0,12–0,21 qua 9 lần chạy**, p05 = **0,000 cả 9 lần**). Nguồn:
      `data/empty_window_2026-11-10_metrics.json`.
- [x] `/api/live/status` với phiên `vos_every=1` trả `drift_p05 = null`, `drift_n = 0` (**không** `0,0`)
      + UI hiện "chưa đo được", không hiện "tốt".
- [x] `drift_n < 30` ⇒ `drift_iou_p05 = null` (test đơn vị), `drift_n` vẫn công bố.
- [x] `./run lint`, `./run test`, `./run testall`, `./run webtest`, `./run e2e` xanh; review độc lập
      (§9.1) P0 = 0 — vòng 1 bắt **1 P1** (nhãn "nhấp nháy" bị **đảo chiều số**: in `stability × 100`
      trong khi `stability = 1,0` mới là êm; và `stability = 0` vừa là "chưa đo" vừa là "vừa mất
      dấu" ⇒ in "nhấp nháy 0 %" đúng lúc model rơi vật) — đã sửa: in `100 − stability`, và
      `stability <= 0` ⇒ "chưa đo".

## 📌 Phương án bị bác (ghi để không mở lại)
1. **Tự giảm `vos_every` khi p05 thấp** — bác bằng số: p05 đổi 0,000–0,010 (< ±0,057), `mask_fps`
   không tăng, `vos_every=1` làm FPS phát 29,9 → 9,5. Trần là `vos_ms ≈ 130–155 ms`, không phải
   `vos_every`.
2. **Reset LK khi drift xấu** — `_interp.reset()` đã chạy mỗi frame; `binh2` hỏng ở phía VOS
   (26 lần mask rỗng); reset chỉ làm số drift đẹp lên = tối ưu chỉ số.
3. **Cờ "LK nội suy lệch" ngay bây giờ** — chưa có bằng chứng độc lập với `empty%`; sẽ là claim vượt
   dữ liệu (AGENTS §6 cấm).
4. **Ngưỡng p05 = 0,20** — không có lớp dữ liệu nào giữa 0,000 và 0,644 để hiệu chuẩn nên ngưỡng này
   chỉ "rộng hơn" chứ không chính xác hơn; hoãn tới khi có dãy mẫu.
5. **Cửa sổ ngắn 30 cho `p05`** — p05@30 ≈ **min của 30 mẫu** (chỉ số 1,45), không phải phân vị; cửa
   sổ ngắn chỉ dùng để **đếm sự kiện** (nền = 0), không dùng cho phân vị.

## 📚 Tham chiếu
- `data/drift_2026-11-08_metrics.json` (số nền 3 clip + ngưỡng nhiễu ±0,004/±0,057/±1,2 %/±0,3 %/±3 ms).
- `docs/task/08-11-2026-do-cai-gia-noi-suy-lk-va-nguong-nhieu.md` (§ đo drift, `vos_every` không điều
  khiển độ tươi mask).
- `AGENTS.md` §6 (cấm claim `drift_iou` là độ chính xác; `0` vs `None`).
- `docs/task/09-11-2026-bang-chung-duong-camera-that.md` (việc C đã làm trước: camera thật chạy được).
