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

**Trong khung** (`0:110 ∪ 165:262`, n = **44** cặp, `data/lk_thu_binh1_2026-11-19_trongkhung_metrics.json`,
`git_rev c522230`, `git_dirty_code=false`):

| `max_mad` | LK `ok` | `ok_frac` | IoU trung vị **khi-ok** | IoU trung vị **mọi mẫu** | nhận-bừa (ok mà IoU < 0,5) |
|---|---|---|---|---|---|
| **1,5 (hiện tại)** | 10/44 | **0,227** | **0,9505** | 0,6479 | **0** |
| 3,0 | 13/44 | 0,295 | 0,9335 | 0,6479 | 0 |
| **6,0** | **25/44** | **0,568** | **0,9198** | **0,8128** | **0** |
| 10,0 | 29/44 | 0,659 | 0,9102 | 0,8833 | 0 |

Toàn dãy (`data/lk_thu_binh1_2026-11-19_metrics.json`, `"khung": null`, n = 48, gồm cả frame vật đã rời
khung): `ok_frac` 0,25 → 0,312 → 0,562 → 0,646; 2 mẫu "nhận-bừa" duy nhất ở frame **324/327** — tức
**sau khi chai đã rời clip**, không phải lỗi cửa MAD.

`grid` 8 vs 12: 0,25 vs 0,25 → 0,562 vs 0,583 → 0,646 vs 0,688, IoU khi-ok chênh ≤ 0,002 ⇒ **`grid`
không phải nút điều khiển**, không cần đổi.

### Trả lời một phần câu hỏi

- Cửa 1,5 px **quá chặt thật**: nới lên 6,0 làm `ok_frac` trong khung **×2,5** (0,227 → 0,568) mà IoU
  trung vị khi-ok chỉ giảm **0,031** (0,9505 → 0,9198) và **không** sinh mẫu nhận-bừa nào. Mạnh hơn:
  IoU trung vị trên **mọi mẫu** 0,6479 → **0,8128** ⇒ kể cả mẫu LK từ chối, ô hiển thị vẫn gần vị trí
  thật hơn hẳn. Điểm gãy
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

---

## A/B LIVE 19-11 (bước 2) — `scripts/ab_lk_max_mad.py`, 2 clip, 3 lần/cấu hình, chèn kẽ

`data/ab_lk_max_mad_2026-11-19_metrics.json` (`git_rev b5dea7a`, `git_dirty_code false`,
`cau_hinh_hieu_luc_lech []`), `image_size 192`, `vos_every 3`, 262 frame, cửa sổ `0:110,165:262`:

| clip | `max_mad` | `lk_ok_frac` (±) | `drift_iou` | `measured_fps` | `vos_ms` | `mask_age_p95` |
|---|---|---|---|---|---|---|
| binh1 | **1,5** | **0,119 ± 0,014** | 0,495 | 29,90 | 93,8 | 293,2 |
| binh1 | 3,0 | 0,232 ± 0,004 | 0,513 | 29,83 | 91,4 | 301,6 |
| binh1 | **6,0** | **0,402 ± 0,060** | **0,561** | 29,73 | 102,7 | 303,2 |
| binh2 | **1,5** | **0,405 ± 0,005** | 0,710 | 29,87 | 107,3 | 303,1 |
| binh2 | 3,0 | 0,611 ± 0,054 | 0,726 | 29,87 | 98,7 | 301,9 |
| binh2 | **6,0** | **0,636 ± 0,010** | 0,717 | 29,87 | 101,9 | 301,9 |

- Tăng **đơn điệu** trên cả 2 clip; `drift_iou` **không giảm ở đâu** (binh1 +0,067 = cải thiện thật;
  binh2 +0,007 = trong ngưỡng nhiễu). Không mất tốc độ (`fps` 29,7–29,9).
- **Ngưỡng đăng ký trước "≥ 2×" chỉ đạt trên binh1 (×3,37)**; binh2 ×1,57 (vốn đã 40 % ở 1,5 vì vật to,
  ít bị tay che). Gộp 2 clip ×1,98 — **không** dùng con số gộp để tuyên bố "đạt":
  `quyet_dinh.du_dieu_kien_doi_mac_dinh = false`, `so_clip_dat 1/2` (luật AND trên mọi clip).
- Kiểm ảnh (`docs/media/lk/so_sanh_max_mad_binh1.jpg`, frame 60/95): ô đỏ vẫn trên chai ở cả 2 mức,
  không trôi vào nền. **Chỉ 2 frame × 1 clip** ⇒ chưa phải "đã kiểm hết".

### SỬA TIÊU CHÍ ĐĂNG KÝ TRƯỚC (ghi đè mục "Nghiệm thu" ở trên)

Câu cũ `|Δdrift_iou| < ±0,010` là **ill-posed**: nó loại cả trường hợp `drift_iou` **TĂNG** (tốt). Luật
đúng từ 19-11: `Δdrift_iou >= -0,010` (chỉ chặn chiều **giảm** quá ngưỡng nhiễu) **VÀ**
`lk_ok_frac >= 2×` **trên TỪNG clip** (AND trên mọi clip, không lấy trung bình). Lý do sửa: bản đầu chạy
2 clip rồi gộp cho ra ×2,04 "đạt" trong khi binh2 chỉ ×1,61 ⇒ artifact nói "đủ điều kiện" ngược với
quyết định (review độc lập PR #53, P1).

### Quyết định: **CHƯA đổi `DEFAULT_MAX_MAD`**

Điều kiện chốt còn lại là **mIoU vs GT người gán** ở 1,5 vs 6,0 trên cùng các frame GT của `binh1`
(`./run miou`): 6,0 không thấp hơn 1,5 ⇒ đổi mặc định sang 6,0. `drift_iou` là độ tự nhất quán với ô
VOS, **không** phải độ chính xác bám vật — nên nó chỉ đủ để loại phương án, không đủ để chốt.

Cờ `--lk-max-mad` đã phơi (worker + `LiveTrackConfig` + echo `cau_hinh`), nên demo **có thể** chạy 6,0
ngay, nhưng báo cáo phải ghi đó là cấu hình đo, không phải mặc định.

## Comments

20-11: **CHỐT — giữ `DEFAULT_MAX_MAD = 1,5`.** PR #61 merged (`main` = `f9b5620`). Có phép đo thứ ba bằng **GT người tô**, sau khi phát hiện `mIoU` không dùng được cho việc này.

**Vì sao cần phép đo mới**: chấm mIoU hợp lệ buộc `--vos-every 1` (repo tự từ chối dump mask khi >1), mà cấu hình đó **tắt hẳn LK** ⇒ `max_mad` không tham gia phép đo. `drift_iou` chỉ nói ô hiển thị khớp **ô VOS** (tự nhất quán). Nên thêm: **IoU(ô ĐANG HIỂN THỊ, hộp bao suy từ mask người tô)** — dụng cụ `--dump-shown-csv` + `scripts/ab_o_hien_thi_vs_gt.py`.

**Số** (⚠ artifact của phiên này **đã bị ghi đè** — xem ĐÍNH CHÍNH trong `docs/task/20-11-2026-o-hien-thi-vs-gt-chot-max-mad.md` §8; tệp cùng tên nay là phiên `b1b`; 3 lần/cấu hình chèn kẽ, 7 frame GT của `b1`, @192, `vos_every 3`, `git_dirty_code false`, `so_lan_chay_loi` 0/0):

| `max_mad` | IoU(ô hiển thị, ô GT) | tệ nhất | `lk_ok_frac` ở frame GT |
|---|---|---|---|
| **1,5** | **0,5490 ± 0,0309** | 0,261 | **0,048** |
| **6,0** | **0,5670 ± 0,0173** | 0,169 | **0,429** |

- Trung bình: chênh **+0,0180** ≤ ngưỡng nhiễu **0,0309** ⇒ **KHÔNG phân biệt được**.
- Theo cặp (21): 6,0 tốt hơn 8 · 1,5 tốt hơn 6 · bằng 7; tốt nhất +0,41, **tệ nhất −0,41** ⇒ không có chiều thắng nhất quán.
- **Ba lần A/B độc lập cùng kết luận "không phân biệt được"** (chênh +0,032/nhiễu 0,065 · +0,003/0,051 · +0,018/0,031), dù chi tiết từng lần đổi. Một lần chạy từng cho "6,0 không tệ hơn ở cả 7 frame" — **không tái lập** ⇒ đúng lý do phải ≥2 lần + so theo cặp.

**Hệ quả cách viết báo cáo**: nới cửa MAD làm LK **dám nhận nhiều hơn** (0,048 → 0,429) và ô **chuyển động** (không đứng yên ~88 % thời gian), **nhưng chưa chứng minh chính xác hơn** ô đóng băng so với GT người tô. Cấm dùng `drift_iou` để biện minh đổi ngưỡng (nới cửa làm nó **tăng** +0,07 trong khi độ đúng không đổi — đúng bẫy AGENTS §6).

**Còn mở (không chặn ticket này)**: (a) GT ở **giữa khe** VOS (`≡2 mod 3`: 2,32,62,92,182,212,242) mới thử được LK đúng mức — GT hiện tại nằm sát lần VOS nên LK chỉ có 1 bước; (b) muốn hybrid **chính xác hơn** thì `LkBoxTracker` phải nội suy cả **tỉ lệ** (vật ra gần/xa), rồi A/B lại bằng chính script này.
