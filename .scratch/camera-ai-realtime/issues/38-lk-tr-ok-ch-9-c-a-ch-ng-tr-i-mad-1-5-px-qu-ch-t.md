# 38: LK trả `ok` chỉ ~9 %: cửa chống-trôi MAD 1,5 px quá chặt cho vật cầm tay — cần A/B max_mad

**Type:** grilling

**Blocked by:** None (can start immediately)

## Question

`lk_ok_frac` đo được **0,093** trong khung (`binh1` @192, `vos_every 3`, 44 mẫu, `data/lk_ok_binh1_2026-11-19_metrics.json`, `git_dirty_code=false`) ⇒ ~90 % thời gian ô người xem thấy là **ô VOS cũ đóng băng**, không phải nội suy. Chẩn đoán 19-11 (16 cặp base→frame rải trong `0:110`, ô chai `266,212,392,637`):

| bước nhảy | LK `ok` | điểm theo dõi được (median/64) | MAD trung vị |
|---|---|---|---|
| 1 frame | 9/16 | 50 | 1,4 px |
| 2 frame | 4/16 | 50 | 3,0 px |
| 3 frame | **1/16** | 49 | **4,8 px** |
| 5 frame | 2/16 | 47 | 12,4 px |

⇒ LK **không** thiếu điểm (≈50/64 mỗi bước); nó bị chặn bởi `DEFAULT_MAX_MAD = 1.5` (`src/light_tracker.py:23`): vật cầm tay **không rigid** (tay che, xoay, biến dạng) nên độ tản vector lớn **dù trung vị dịch đúng**. Nghĩa là hiện tại "hybrid VOS+LK" gần như chỉ là "ô cũ + 30 FPS vẽ lại".

**Việc phải làm**: A/B `max_mad` ∈ {1,5 (hiện tại), 3, 6, 10} × `grid` ∈ {8, 12} bằng `./run ab` (chèn kẽ, 3 lần/cấu hình), trên ≥ 2 clip + **ít nhất 1 clip vật đi chậm**; đồng thời kiểm bằng ảnh rằng tăng `max_mad` **không** làm ô bao bám vào nền (chốt MAD sinh ra để chặn đúng lỗi đó — AGENTS §6).

**Nghiệm thu có số**: báo cáo `lk_ok_frac`, `drift_iou` (trong khung), `mask_age_p95` cho từng cấu hình, kèm ngưỡng nhiễu theo ô chọn (±0,010 cho `drift_iou` ở ô chai, 55 s); chênh lệch < ngưỡng ⇒ viết "không phân biệt được". Nếu không cấu hình nào vừa tăng `lk_ok_frac` vừa giữ `drift_iou` ⇒ kết luận **trung thực** là phải **thôi hiển thị ô cũ** (ẩn ô giữa hai lần VOS) thay vì tăng ngưỡng.

**Không** được: chỉnh `max_mad` theo cảm giác rồi báo "đã cải thiện".

---

## Đo offline 19-11 (bước 1 của A/B) — `scripts/do_thu_lk.py`

Thay vì chờ `./run ab` (chưa có knob `max_mad` trong `LiveTrackConfig`), đo **offline** trên chính CSV
drift của lần đo live (`data/drift_samples_binh1_2026-11-19_123641.csv`, 55 mốc ô VOS): với mỗi cặp
`base → target` (hai lần VOS liên tiếp), đặt `LkBoxTracker` tại `base` rồi `update()` **một bước** trên
frame `target`; chấm IoU(ô LK, **ô VOS của target**).

**Trong khung vật còn trong hình** (`0:110 ∪ 165:262`, n = 45 cặp, `data/lk_thu_binh1_2026-11-19_metrics.json`,
`git_dirty_code=false`; file `/tmp` là lần chạy khung):

| `max_mad` | LK `ok` | `ok_frac` | IoU trung vị **khi-ok** | nhận-bừa (ok mà IoU < 0,5) |
|---|---|---|---|---|
| **1,5 (hiện tại)** | 10/45 | **0,222** | **0,9505** | **0** |
| 3,0 | 13/45 | 0,289 | 0,9335 | 0 |
| **6,0** | **25/45** | **0,556** | **0,9198** | **0** |
| 10,0 | 29/45 | 0,644 | 0,9102 | 0 |

Toàn dãy (n = 48, gồm cả frame vật đã rời khung): 0,25 → 0,312 → 0,562 → 0,646; 2 mẫu "nhận-bừa" duy
nhất nằm ở frame **324/327** — tức **sau khi chai đã rời clip**, không phải lỗi cửa MAD.

`grid` 8 vs 12: 0,25 vs 0,25 → 0,562 vs 0,583 → 0,646 vs 0,688, IoU khi-ok chênh ≤ 0,002 ⇒ **`grid`
không phải nút điều khiển**, không cần đổi.

### Trả lời một phần câu hỏi

- Cửa 1,5 px **quá chặt thật**: nới lên 6,0 làm `ok_frac` trong khung **×2,5** (0,222 → 0,556) mà IoU
  trung vị khi-ok chỉ giảm **0,031** (0,9505 → 0,9198) và **không** sinh mẫu nhận-bừa nào. Điểm gãy
  là **6,0**: 3 → 6 nhân đôi `ok_frac`; 6 → 10 chỉ thêm 0,088 `ok_frac` mà mất thêm 0,010 IoU.
- **Chưa đủ để đổi default.** Ba hạn chế phải nêu trước khi sửa production: (a) đo **một bước nhảy
  ~3 frame**, còn pipeline live đi **chuỗi** update 1 frame/bước ⇒ `ok` ngoài đời có thể khác; (b) mốc
  so là **ô VOS**, không phải GT người gán ⇒ mới chứng minh "LK khớp model", chưa phải "bám đúng vật";
  (c) **một clip** ⇒ chưa có `±` để so (AGENTS §6: n < 2 không kết luận).

### Bước tiếp (cần thiết mới được đổi `DEFAULT_MAX_MAD`)

1. Thêm knob `lk_max_mad` vào `LiveTrackConfig` + `--lk-max-mad` cho `tools/run_live.py`/worker
   (chỉ **phơi** tham số, **không** đổi default).
2. `./run ab`-kiểu: 1,5 vs 6,0 × 3 lần chèn kẽ, trên `binh1` **và** `binh2`, đo `lk_ok_frac` +
   `drift_iou` trong khung; cần `lk_ok_frac` tăng ≥ 2× và `drift_iou` chênh < ±0,010 (ngưỡng ô chai).
3. Kiểm **ảnh** (`bbox_check.jpg`) rằng 6,0 không kéo ô vào nền — đây là điều kiện bác bỏ.

Chỉ khi (2) và (3) cùng đạt mới đổi `DEFAULT_MAX_MAD`; nếu không ⇒ kết luận trung thực là **ẩn ô cũ**
giữa hai lần VOS.
