# Ngày 14-11-2026 — Đo lại với ô chọn ĐÚNG + trả lời "có phải train lại model không"

## 🎯 Mục tiêu
- Sau audit ô chọn (log `14-11-2026-plan-3-y-kien-va-audit-bbox.md`: hộp `binh1` phủ **khuôn mặt**,
  hộp `binh2` phủ **2 chai + 2 tay**), đo lại đường live với **ô đúng** để biết chất lượng thật.
- Trả lời câu hỏi của người dùng: *"test đi, **tự train lại model** cho phù hợp nếu cần"* — có cần
  train lại / đổi model không, và nếu không thì cái gì mới là nút thắt.

## 📥 Input
- Máy demo: MSI Modern 14 B11MOU (i7-1195G7 4c/8t, Iris Xe, 16 GB, không CUDA, WSL2), `torch 2.14.1+cpu`,
  `cv2 5.0.0`, python 3.11.17 (conda `samurai`). `/proc/cpuinfo` **không** có `avx512_bf16`.
- Clip: `data/binh1.mp4` (720×1280, **333 frame**, 11 s), `data/binh2.mp4` (720×1280, **360 frame**, 12 s).
- Ô chọn: cũ `binh1=104,308,209,287` (mặt) · `binh2=200,400,300,500` (2 chai+tay); mới
  `binh1=300,275,150,410` (chai) · `binh2=330,330,150,360` (1 chai trắng).
- Lệnh đo: `scripts/measure_live_relay.py --source data/<clip>.mp4 --bbox <ô> --image-size 192
  --vos-every 3 --seconds 55` (API live thật + worker thật), 3 lần **xen kẽ** mỗi ca.

## 🔨 Công việc đã thực hiện
1. **Dọn rác provenance**: thư mục `D:/` (6 file peek do agent đọc-only tạo) nằm trong repo làm
   `git status` bẩn ⇒ mọi artifact ghi `git_dirty_code=true`. Đã xoá; loạt đo chính chạy lại sau đó
   đều có `git_dirty_code=false`, `git_rev=34b512b`.
2. **Đo 3 ca × 3 lần, xen kẽ** (mặt `binh1` / chai `binh1` / chai `binh2`), @192, `vos_every 3`, 55 s.
3. **Tách "vật có trong khung" khỏi "vật đã rời khung"**: đọc lại CSV từng mẫu
   (`data/drift_samples_*_2026-11-14_*.csv`, có `frame_idx`) và chia theo `frame_idx ≤ 105` /
   `> 150` (binh1), `≤ 140` / `> 250` (binh2).
4. **Sàng lọc các nút điều khiển nghi ngờ** (mỗi cấu hình 2–3 lần): `image_size` 192 / 256 / 320;
   `vos_every` 1 / 2 / 3; thời lượng 10 s / 20 s / 55 s.
5. **Sàng lọc checkpoint** (offline, cùng `TrackerEngine`, cùng clip + ô + `image_size`): tiny vs small,
   119 frame (đoạn đầu, vật còn trong khung) rồi 299 frame (cả clip).
6. **Xem ảnh frame 100/110/120/160/260 của `binh1`** và 0/200/300 của `binh2` để biết chuyện gì xảy ra
   lúc mask rỗng.

## 📤 Output / Kết quả

### A. Đường live, `image_size 192`, `vos_every 3`, 55 s, 3 lần xen kẽ, `git_dirty_code=false`
| Ca | `empty_runs` % (tổng phiên) | `empty` % **khi vật trong khung** | `drift_iou` (tổng) | `drift_iou` **trong khung** | `vos_fps` (mask/s) | `mask_age_p95` |
|---|---|---|---|---|---|---|
| **mặt** (`binh1`, ô cũ) | **0,0** | 0,0 | 0,881 / 0,884 / 0,883 | 0,883 | 7,8–8,2 | 209,3 / 227,6 / 220,0 ms |
| **chai** (`binh1`, ô mới) | 36,0 / 36,2 / 36,7 | **1,7–1,8 %** (khung `0:110` ∪ `165:262`, n = 57–59) | 0,454 / 0,460 / 0,460 | **0,475–0,484** | 8,5–8,8 | 215,4 / 217,2 / 221,4 ms |
| **chai** (`binh2`, ô mới) | 21,7 / 22,2 / 23,4 | **0,0 %** (khung `0:160`, n = 44–45) | 0,621 / 0,619 / 0,617 | 0,702–0,721 | 8,1–8,5 | 209,4 / 218,7 / 210,9 ms |

Artifact: `data/lan2_{mat_binh1,chai_binh1,chai_binh2}_lan{1,2,3}_metrics.json` (+ CSV từng mẫu cùng tem).

### B. Nút điều khiển nào KHÔNG phải nút thắt (mỗi cấu hình 2–3 lần)
| Thử | Kết quả | Kết luận |
|---|---|---|
| `image_size` 256 | mask 4,6–4,8/s · `drift_iou` **0,341–0,359** · `mask_age_p95` 379–409 ms · empty 39 % | **tệ hơn** 192 và chậm 1,8× |
| `image_size` 320 | mask 3,4/s · `drift_iou` **0,285–0,323** · `mask_age_p95` 551–556 ms | **tệ nhất**, chậm 2,5× |
| `vos_every` 1 | empty 33 % · `drift_n = 0` (đường inline không chấm drift) | cadence không đổi chất lượng |
| `vos_every` 2 | empty 33 % · `drift_iou` 0,438 / 0,440 | như `every 3` (0,447–0,464) |
| 10 s vs 20 s vs 55 s | empty % 55 / 52 / 35 (tỉ lệ cùng chiều với phần clip **không có chai**) | **không** phải lỗi do lặp clip |

⚠️ Bảng B chạy **trước** khi dọn rác `D:/` ⇒ artifact của nó có `git_dirty_code=true`; dùng làm **sàng
lọc định hướng**, không trích như số nghiệm thu. Riêng `image_size 256` đã đo lại sau khi dọn
(`data/lan2_chai_binh1_256_lan1_metrics.json`, `git_dirty_code=false`) — vẫn 0,341, xác nhận.

### C. Checkpoint: tiny vs small (offline, cùng `TrackerEngine`, cùng clip/ô/192)
| Checkpoint | 119 frame đầu (vật còn trong khung) | 299 frame (cả clip) | ms/frame |
|---|---|---|---|
| **tiny** (đang dùng) | 7,6 % mask rỗng · stability 0,782 · dt 45 142 px | **31,8 % rỗng** · 100,4 ms | 97,5–99,4 |
| **small** (to hơn 1,3×) | 6,7 % rỗng · stability 0,723 · dt 35 057 px | **31,1 % rỗng** · 118,9 ms (+18 %) | 118,9–126,3 |

### D. Nguyên nhân thật của "mất dấu": VẬT RỜI KHUNG
- `binh1`: chai có trong **hai đoạn** — `0:110` và `165:262` (≈3,7 s + 3,2 s); giữa hai đoạn người ta
  **cất chai đi** — ảnh
  frame 160 và 260 **không có chai**. `binh2`: chai trắng rời khung từ ≈frame 250 (frame 300 chỉ còn
  chai đen ở vị trí khác).
- Vì vậy khi vật trong khung, `empty` rơi từ **36,0–36,7 %** xuống **1,7–1,8 %** (`binh1`, gộp hai đoạn;
  riêng `0:110` là **0,0 %**) và từ 21,7–23,4 % xuống **0,0 %** (`binh2`, khung `0:160`); ca mặt là
  **0,0 %** suốt phiên vì mặt không rời khung. Tức phần lớn "mask rỗng" là **model trả lời đúng**.
  `empty_runs`/`empty_frac_window` **không phân biệt** được "mất dấu do model" với "vật ngoài khung"
  ⇒ từ 14-11, `scripts/measure_live_relay.py` có `--frame-window` (lặp cờ được, ghi cả `so_vong`) và
  `scripts/analyze_drift_samples.py` cũng có, để cắt cửa sổ theo `frame_idx` trước khi trích số.
- `drift_iou` **trong khung**: mặt 0,883 > chai `binh2` 0,702–0,721 > chai `binh1` 0,475–0,484
  (chai binh1 nhỏ hơn + bị xoay/che bằng ngón tay suốt 3,5 s). Đây là **độ tự nhất quán** giữa ô LK
  và mask VOS kế tiếp, **không** phải độ chính xác (AGENTS §6).

## 🐞 Vấn đề gặp phải & cách xử lý
- **Kết luận "chai bị mất dấu 35 %" là SAI** (đã suýt ghi vào báo cáo): phải xem ảnh mới thấy vật
  rời khung. Bài học lặp lại lần thứ 2 trong ngày: **con số không tự bảo vệ mình — phải xem ảnh**.
- **Bẫy "119 frame đầu"**: ca offline 119 frame cho 7,6 % rỗng (trông như model tốt), chạy 299 frame
  mới ra 31,8 % — vì 119 frame đầu rơi đúng đoạn vật còn trong khung. Cửa sổ đo phải phủ hết clip.
- `vos_every=1` làm `drift_n = 0` (đường `_result_inline` không chấm drift) ⇒ **không** được đọc là
  "drift = 0" mà là **chưa đo** (đúng bẫy AGENTS §6).
- Rác `D:/` trong repo làm bẩn provenance của 30+ artifact; đã xoá + đo lại loạt chính.
- `./run lint` / `./run test` **không chạy trong phiên này** (chỉ đọc + đo, không sửa code). Trước khi
  merge PR docs này cần chạy theo §9.4.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **KHÔNG train lại model** (lý do ở dưới) — đóng hẳn hướng này trong báo cáo, kèm bảng C làm bằng chứng.
- [ ] Sửa `AGENTS.md` §6: bullet "binh2 p05 = 0,00 … mất dấu" + bullet "hybrid chỉ giữ được ô bao trên
      một số clip" phải nêu rõ **ô chọn cũ phủ 2 vật / vật rời khung** (tách PR riêng vì `AGENTS.md` là file nóng).
- [ ] Thêm cờ "vật còn trong khung" (người xem bấm) hoặc cắt cửa sổ theo `frame_idx` vào
      `scripts/measure_live_relay.py`, để `empty_frac_window` không trộn hai hiện tượng.
- [ ] Chọn clip demo có vật **ở trong khung suốt** (hoặc quay lại `binh1` chỉ 4 s đầu) — đây là yêu cầu
      của buổi demo, không phải của thuật toán.
- [ ] Đo "bám đúng" bằng nhãn điểm thưa (việc #6 của plan) — `drift_iou` không trả lời được.

## ✅ Trả lời câu "có phải train lại model không?"
**Không.** Bốn lý do, ba lý do có số:
1. **Không có dữ liệu để train**: `data/` có **0 file GT mask** (chỉ `lighting_iou_*` = IoU hộp bao).
   Không có GT thì không có hàm mất mát, không có cách biết train xong tốt hơn hay tệ hơn.
2. **Máy không đủ**: CPU-only (Iris Xe không CUDA), checkpoint 156 MB; fine-tune SAM 2 cần GPU-days.
   Trong 2 tuần còn lại là bất khả thi, và **ADR-0001 đã chốt "không train lại"**.
3. **Bằng chứng cho thấy model không phải nút thắt**: khi vật còn trong khung, mask rỗng = **0,0 %**
   ở cả mặt và chai; model to hơn 1,3× (small) cho **31,1 % vs 31,8 %** (không khác) mà chậm +18 %;
   tăng độ phân giải 256/320 làm `drift_iou` **giảm** (0,34/0,29 vs 0,45) và chậm 1,8–2,5×; đổi cadence
   1/2/3 không đổi gì.
4. **Nút thắt thật là dữ liệu demo + cách chọn ô**: hộp trên **mặt** cho 0,88 còn hộp trên **chai** cho
   0,42–0,75 — cùng model, cùng tham số. Sửa cách chọn ô và chọn clip có vật trong khung rẻ hơn
   train lại hàng trăm lần.

Nếu sau này vẫn muốn "model tốt hơn cho vật nhỏ", thứ tự đúng là: **(a)** dựng GT mask (5–10 frame
nhãn tay) để có thước đo → **(b)** thử knob tham số (`num_maskmem`, `mask_threshold`, prompt chặt hơn)
→ **(c)** chỉ khi (a)+(b) chứng minh còn thiếu ≥ vài điểm J&F mới nói tới fine-tune trên GPU.

## 📚 Tài liệu tham khảo
- `docs/plan/14-11-2026-plan-3-y-kien-toi-uu-msi.md` (plan §9.2 cùng ngày) + log audit bbox cùng ngày.
- Artifact: `data/lan2_*_metrics.json` (10 file, `git_rev=34b512b`, `git_dirty_code=false`) và
  `data/drift_samples_*_2026-11-14_*.{csv,meta.json}` (mỗi dòng = 1 lần VOS, có `frame_idx`).
- Ảnh bằng chứng ô chọn: `docs/media/bbox/*.jpg`.
- `AGENTS.md` §6 (drift/stability không phải độ chính xác; "0,0 = chưa đo"), §9.4 (checklist).
- `docs/task/08-11-2026-do-lai-do-phan-giai-va-kich-thuoc-model.md` — đã thêm đính chính 720×1280 + ô phủ mặt.
