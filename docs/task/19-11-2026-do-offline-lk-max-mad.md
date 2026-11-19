# 19-11-2026 — Đo offline `LkBoxTracker` theo `max_mad`/`grid` (ticket #38, bước 1)

## Mục tiêu

Trả lời bằng **số** câu hỏi của ticket #38: cửa chống-trôi `DEFAULT_MAX_MAD = 1,5` px có **quá chặt**
với vật cầm tay không, và nới ra thì LK **bám tốt hơn thật** hay chỉ **nhận bừa**? Không sửa production
trong phiên này (AGENTS §6: "đo trước, hứa sau").

## Input

- `data/drift_samples_binh1_2026-11-19_123641.csv` — CSV của lần đo live thật (`binh1` @192,
  `vos_every 3`), có ô VOS ở từng lần VOS ⇒ dùng làm **mốc tham chiếu**, khỏi phải nạp model.
- `data/binh1.mp4` — clip gốc (lấy frame xám cho LK).
- Chẩn đoán trước đó (ticket #38): LK **không thiếu điểm** (≈50/64) mà bị chặn bởi MAD.

## Công việc đã thực hiện

1. **`scripts/do_thu_lk.py`** — đo offline: với mỗi cặp `base → target` (hai lần VOS liên tiếp), đặt
   `LkBoxTracker(grid, max_mad)` tại `base` với ô VOS của `base`, `update()` **một bước** trên frame
   `target`, chấm IoU(ô LK, ô VOS của `target`). Hàm thuần tách riêng: `doc_moc`, `cap_ke`, `tom_tat`.
2. Ba đại lượng **đo riêng** (không gộp thành một "điểm"): `ok_frac` (LK dám nhận), `iou_median_khi_ok`
   (nhận có đúng không), `ok_va_sai_frac` (nhận **mà sai** — nguy hiểm nhất vì HUD không cảnh báo).
3. `--frame-window dau:cuoi` (lặp được) để **chỉ đo trong khung vật còn trong hình** — đúng bài học
   14-11: tỉ lệ "mất dấu" tính cả lúc vật đã rời khung là số vô nghĩa.
4. Artifact ghi `git_rev`/`git_dirty_code` qua `measure_watchdog._git_provenance`; thiếu provenance ⇒
   **thoát 1** (không ghi artifact "trông hợp lệ").
5. 5 test cho hàm thuần (`tests/test_do_thu_lk.py`): bỏ dòng bbox rỗng/ô diện tích 0 khi lập mốc, cặp
   phải là hai lần VOS liên tiếp, tách `ok` khỏi `iou_median_khi_ok`, `None` ≠ 0 khi rỗng, bỏ IoU
   `None` khỏi trung vị.

## Output / Kết quả

Hai artifact, **cùng** `git_rev c522230`, `git_dirty_code false` — trích số phải đọc đúng file:

**(a) `data/lk_thu_binh1_2026-11-19_trongkhung_metrics.json`** — `"khung": [[0,110],[165,262]]`, n = **44**
cặp (ghép cặp **trong từng khung**, nên không có cặp nhảy qua khe):

| `max_mad` | LK `ok` | `ok_frac` | IoU trung vị **khi-ok** | IoU trung vị **mọi mẫu** | nhận-bừa |
|---|---|---|---|---|---|
| **1,5 (hiện tại)** | 10/44 | **0,227** | **0,9505** | 0,6479 | 0 |
| 3,0 | 13/44 | 0,295 | 0,9335 | 0,7156 | 0 |
| **6,0** | **25/44** | **0,568** | 0,9198 | **0,8128** | 0 |
| 10,0 | 29/44 | 0,659 | 0,9102 | 0,8581 | 0 |

**(b) `data/lk_thu_binh1_2026-11-19_metrics.json`** — `"khung": null`, n = **48** (cả lúc chai đã rời
clip): `ok_frac` 0,25 → 0,312 → 0,562 → 0,646; IoU khi-ok 0,9382/0,9327/0,9102/0,9082; 2 mẫu
"nhận-bừa" duy nhất nằm ở frame **324/327** = **sau khi chai rời clip** ⇒ không phải lỗi cửa MAD.

- Nới 1,5 → 6,0 (trong khung): `ok_frac` **×2,5** (0,227 → 0,568), IoU khi-ok giảm **0,031**,
  **0** mẫu nhận-bừa ⇒ cửa 1,5 quá chặt **thật** (không phải "LK hỏng").
- Đại lượng thứ ba đáng chú ý: **IoU trung vị trên MỌI mẫu** 0,6479 → **0,8128** — nghĩa là kể cả khi
  LK từ chối (ô đóng băng ở `base`), nới cửa vẫn làm ô người xem thấy **gần vị trí thật hơn hẳn**. Đây
  là con số ủng hộ "nới ngưỡng" mạnh hơn cả `ok_frac`.
- `grid` 8 vs 12: `ok_frac` chênh ≤ 0,046 (0,568 vs 0,591), IoU khi-ok lệch 0,010 ⇒ **không phải nút
  điều khiển**, không đổi.

## Vấn đề & cách xử lý

- **P1 review độc lập #52 (đúng, đã sửa)**: bản đầu mình commit artifact **toàn dãy** (`"khung": null`)
  nhưng log lại trích **số trong khung** ra từ nó — số tái lập được nhưng *không có artifact kèm* và câu
  gán sai sự thật (trái AGENTS §6). Nay có **hai** artifact, mỗi con số trích từ đúng file, `lenh` trong
  artifact chứa `--frame-window`.
- **P2 (đã sửa)**: bản đầu lọc khung **trước** khi ghép cặp ⇒ sinh cặp nhảy **60 frame** giữa hai khung
  vẫn được tính là "một bước VOS" (n 45 → nay **44**). Nay ghép cặp **trong từng khung**.
- **P2 (đã sửa)**: nhánh `not-ok` từng gán cứng `iou = 0.0` (sàn giả tạo cho `iou_median_tat_ca`); nay
  chấm IoU(ô **sẽ hiển thị**, ô VOS target) — nhờ đó mới có con số 0,6479 → 0,8128.
- **Không đổi `DEFAULT_MAX_MAD` trong phiên này.** Ba hạn chế: đo **một bước ~3 frame** trong khi
  pipeline live đi **chuỗi** 1 frame/bước; mốc là **ô VOS** (chứng minh "LK khớp model", **không** phải
  "bám đúng vật"); **một clip** ⇒ chưa có ngưỡng nhiễu `±` để so (AGENTS §6: n < 2 không kết luận).
  Điều kiện đổi default đã ghi vào ticket #38 (knob `lk_max_mad` → A/B 1,5 vs 6,0 × 3 lần × `binh1` +
  `binh2` → kiểm **ảnh** `bbox_check.jpg` rằng ô không bị kéo vào nền).
- `_git_provenance()` trả **tuple**, không phải dict (mình viết `**` sai lần đầu) ⇒ nay gán 4 biến, và
  artifact có `git_loi` để đọc được "vì sao không có rev".
- Lần chạy đầu ra `git_dirty_code: true` vì script còn untracked ⇒ **commit code trước, đo lại** mới ra
  artifact tái lập được (đúng bài học 08-11).

## Next steps

- Ticket **#38** bước 2: knob `lk_max_mad` (`LiveTrackConfig` + `--lk-max-mad`) → A/B live 1,5 vs 6,0,
  3 lần chèn kẽ, `binh1` + `binh2`, kèm `bbox_check.jpg`.
- Nếu A/B không đạt ⇒ kết luận trung thực: **ẩn ô cũ** giữa hai lần VOS thay vì tăng ngưỡng.

## Tài liệu tham khảo

- `ticket #38` (`.scratch/camera-ai-realtime/issues/38-…md` — đã thêm mục "Đo offline 19-11")
- `scripts/do_thu_lk.py`, `tests/test_do_thu_lk.py`, `src/light_tracker.py:18-23`
- `docs/task/19-11-2026-csv-drift-ghi-o-hien-thi-va-lk-ok.md` (số live 0,093 = 4/43)
