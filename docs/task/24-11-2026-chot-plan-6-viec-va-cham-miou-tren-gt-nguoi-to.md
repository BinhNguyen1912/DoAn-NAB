# 24-11-2026 — Chốt plan 6 việc (chống tràn nền cùng tông), chấm mIoU trên GT người tô, và sửa 1 P1 + 8 P2/P3 của review

## 1. Mục tiêu

1. Chốt phương án **sau** khi 3 agent tranh luận (vòng 2) về "chống bám nền cùng tông" — và **không** làm việc
   đã bị bác bằng số.
2. Làm 6 việc đo được trong ~6 h thay vì thêm cổng mới (đã bị bác: cổng diện tích làm phiên demo `144505` có
   **50,5 %** frame mang ô nét đứt thay vì 25,8 %).
3. **Chấm mIoU thật** trên clip "vật ra/vào khung" (`clip_be2`) với GT người tô — trả lời được câu "hệ có vẽ bừa
   khi vật vắng không" bằng **số**, không bằng đọc ảnh bằng mắt.
4. Review độc lập trước khi merge (AGENTS §9.1) và xử lý P0/P1 ngay.

## 2. Input

- Người dùng đã **tô xong 5 frame GT** còn thiếu trong `docs/gt/vat_be_vaolai/` (f258/f270/f300 = vật đã cất đi
  ⇒ GT rỗng; f344/f348 = tô remote màu be).
- Plan `docs/plan/24-11-2026-chong-tran-nen-cung-tong-chot.md` (3 agent × 2 vòng tranh luận).
- Phân tích `docs/phan-tich-dung-sai-model-may-code.md` (máy không đổi mIoU; model là trần; **code là yếu tố
  lớn nhất**: đổi ô chọn 0,4639 ↔ 0,7794 ↔ 0,6635 ↔ 0,5182).
- Review độc lập range `41b6bec..HEAD` (9 commit) — 0 P0, 1 P1, 7 P2, 4 P3.

## 3. Công việc đã thực hiện

### 3.1 Plan: 6 việc, có **điều kiện đổi ý** ghi trước

| # | việc | commit | kết quả đo |
|---|---|---|---|
| 1 | `wall_s`/`loadavg` + vá check vừa merge bị sai | `f069e52` vùng | — |
| 2 | (bỏ) cổng diện tích | — | **bác**: 98/194 = 50,5 % frame NGHI ở phiên demo |
| 3 | Trần đọc nguồn LIVE (`LatestFrameSource.max_fps`) | `f069e52` | relay **263–293 → 30** lần đọc/s |
| 4 | Cột chẩn đoán `bbox_area_ratio` (**không** phải cổng) | `125b743` | ô đúng cỡ 1,000; cú nhảy 4 655→29 110 px ⇒ **5,015** |
| 5 | Quỹ đạo theo **thời gian** (`--trajectory-seconds`) | `54b3265` | cùng 5 s: **31 điểm** @6,3 bước/s, **16 điểm** @3,1 bước/s |
| 6 | Luật trích số hiệu năng (AGENTS §6) | `125b743` | — |

### 3.2 Chấm mIoU trên 11 frame GT (số quan trọng nhất của phiên)

Lệnh (tái lập được, `git_dirty_code = false` ở **cả hai** tầng):

```bash
./run miou score --gt docs/gt/vat_be_vaolai --pred-dir data/be2_full_masks \
  --out data/miou_be2_full_2026-11-24_metrics.json
```

| chỉ số | kết quả |
|---|---|
| **Bịa mask ở frame GT RỖNG** | **0/3 frame · trung bình 0 px · tệ nhất 0 px** (f258/f270/f300) |
| mIoU (8 frame có vật) | **0,8625** |
| — trên 6 frame cũ | **0,8754** (khớp y số cũ ⇒ không có gì đổi) |
| — 2 frame mới (f344/f348) | 0,8358 / 0,8117 (tay che một phần ⇒ **kéo trung bình xuống**) |
| mask NGOÀI GT | 5,2 % trung bình · tệ nhất **15,3 %** (f348) |
| `mIoU_p05` | **`None`** — `n = 8 < 30` (đúng luật; `None` = *chưa công bố*, không phải 0) |
| độ ổn định | **3 lần sinh mask khác nhau ⇒ cùng 0,8625** |

**Cách đọc phải nói kèm:** GT để trống = *vật không có mặt*; hệ vẽ 0 px ⇒ câu "hệ không vẽ bừa khi vật vắng"
nay có artifact, không còn là cảm nhận. Và **không** loại 2 frame tệ ra khỏi mẫu (đó là lỗi "chọn frame cho đẹp").

### 3.3 Xử lý review độc lập (AGENTS §9.1)

**P1 (thật, do #45 gây ra) — đã sửa + test:** `live_tracking.py` gộp `nghi_doi_tuong` vào `an_o` ⇒ `shown = None`
trong khi `_annotate` **vẫn vẽ ô nét đứt** ⇒ `shown.csv` và `scripts/ab_o_hien_thi_vs_gt.py::ty_le_o_ma` đếm
"không vẽ ô" trên frame GT rỗng — **số liệu nói ngược lại ảnh người xem thấy**. Nay chỉ `no_evidence` mới ẩn;
cột `bam` (thứ 12 của CSV) đã đủ để lọc "ô đặc" vs "ô nét đứt".

**P2/P3 đã sửa (8 việc):**

- `bbox_area_ratio`: mốc = **trung vị 10 frame đầu** (ô kéo tay hẹp 2×/cạnh từng cho 4,00/3,67/3,40/3,17 —
  "báo tràn" trong phiên **ĐÚNG**), warm-up trả **trống** không trả 0, thêm cột `bbox_area_ref`/`bbox_area_n`
  để kiểm lại được tỉ lệ, `log()` **luôn** tiến EMA (replay có sẵn ratio từng làm lệch mốc).
- `--trajectory-seconds`: trần số điểm tự nới theo cửa sổ (30 bước/s × 5 s từng bị cắt còn 3,33 s), cửa sổ cực
  nhỏ không xoá sạch quỹ đạo, vào `DEFAULTS` + merge (YAML không còn ném "key lạ"), `run_info.json` ghi
  `trajectory_seconds`/`max_trajectory`.
- `LatestFrameSource`: `self._stop.wait()` thay `time.sleep` ⇒ `stop()` ngắt được giấc ngủ (trước: `max_fps`
  nhỏ làm join hết 2 s rồi `close()` chạy trong lúc `read()` ⇒ `RuntimeError` sau Ctrl+C).
- 7 chỗ mô tả "ĐÃ ẨN ô" (schemas/domain/routes/worker_source/api.ts/LivePanel) → "VẼ ô NÉT ĐỨT".
- `_cfg_tu_cli()` tách thành hàm thuần ⇒ **test được đường hợp nhất thật**; `reid_enabled` tri-state thật
  (`--no-reid` không còn bị đổi thành `None` rồi rơi về YAML).
- 2 test flaky dưới tải full suite: dọn worker cũ chờ `poll()` có hạn 5 s; 2 test nhịp đọc nguồn khẳng định
  **cận trên** theo `elapsed` đo được (trước đòi `n ≥ 26`, đã sát biên).
- Docs: plan **155 → 263–293 lần/s** (hai con số cùng ngày, không so được); AGENTS nói rõ "30 lần **đọc
  nguồn**/s ≠ 30 FPS hiển thị" và "`--trajectory-seconds` là **wall clock** ⇒ với nguồn FILE nó đổi nghĩa".

### 3.4 Cổng kiểm tra

| cổng | kết quả |
|---|---|
| `./run lint` | **All checks passed** |
| `./run test` | **1918 passed** (thêm 9 test), 5 deselected, 158 s |
| `./run webtest` | **99 passed** |
| `npm run build` | ✓ built (167,33 kB js) |
| `./run e2e` (Chrome thật) | **PASS** (không lỗi JS trên trang) |

## 4. Output / Kết quả

- **Số mới, dùng được trong báo cáo:** mIoU **0,8625** (8 frame) · **0/3 frame bịa mask khi vật vắng** ·
  mask ngoài GT 5,2 % · ba lần chạy cùng số ⇒ tất định.
- Artifact: `data/miou_be2_full_2026-11-24_metrics.json` (rev `6198c4f`, `git_dirty_code = false` ở cả tầng
  chấm **và** `meta.mask_manifest`).
- GT: `docs/gt/vat_be_vaolai/` đủ **11/11** frame (`701ae40`).
- 5 commit: `701ae40`, `7795f4c`, `daa6d8b`, `6198c4f`, `b838ca0`.

## 5. Vấn đề & cách xử lý

| vấn đề | cách xử lý |
|---|---|
| Artifact đầu tiên có `meta.mask_manifest.git_dirty_code = true` (mask sinh trên cây bẩn vì `docs/gt` chưa commit) ⇒ người đọc theo AGENTS §6 sẽ tưởng tái lập được | commit GT + `web/` rồi **sinh lại mask** và chấm lại ⇒ cả hai tầng `false`. Ghi vào commit message để không ai trích bản cũ |
| Test `test_reap_worker_cu_con_song` xanh khi chạy riêng nhưng đỏ trong full suite | `SIGTERM` bất đồng bộ ⇒ chờ `poll()` có hạn 5 s (vẫn khẳng định "phải bị dọn") |
| 2 test nhịp đọc nguồn khẳng định **cận dưới** (`n ≥ 26`) ⇒ flaky trên CI dùng chung | đổi sang khẳng định **cận trên** theo `elapsed` (`n ≤ 1,2 × 30 × elapsed`) + `n ≥ 5` |
| Review báo "`--trajectory-seconds` với nguồn file đổi nghĩa" | **không** sửa code (live là đường demo): ghi rõ trong help + AGENTS §6, và ghi `trajectory_seconds` vào `run_info.json` để artifact tự khai |

## 6. Next steps

1. **(người dùng, 2 phút)** `./run relay start` → `./run demoip` — phiên đầu tiên sau 6 commit; kiểm từ artifact:
   video dài đúng ~25–30 s, còn hay không đoạn "5,2 s mask sai".
2. **Push**: nhánh `feat/nhan-lai-vat-live` có **60+ commit chưa push**. Đề nghị tách `feat/demo-ok-24-11`
   (5 commit chính + plan + GT + artifact) để PR gọn theo AGENTS §7b.
3. P3 còn nợ: `config.py` chưa có test "YAML đặt `trajectory_seconds` không ném"; `identity_guard` chưa có test
   riêng cho ca latch + reacquire (đã sửa 22-11 nhưng chỉ có test qua `live_tracking`).

## 7. Tài liệu tham khảo

- `docs/plan/24-11-2026-chong-tran-nen-cung-tong-chot.md` — plan 3 agent × 2 vòng + **phương án bị bác**.
- `docs/phan-tich-dung-sai-model-may-code.md` — máy/model/code: cái nào quyết định mIoU.
- `docs/thuoc-do-bam-dung.md` — quy tắc chấm mIoU (GT rỗng ⇒ không chấm; model rỗng mà GT có vật ⇒ 0,0).
- `docs/demo-clip-va-o-chon.md` — ô chọn đúng theo clip (bài học 14-11: ô sai làm toàn bộ số Phase 4c sai).
- AGENTS §6: ngưỡng nhiễu, "0,0 là cạm bẫy", `mIoU_p05` chỉ công bố khi n ≥ 30.

---

## 8. Bổ sung cuối phiên — clip "vật TRẮNG MỜ trên tường TRẮNG" và 4 thí nghiệm bị BÁC

Người dùng quay `data/raw_tran_nen.mp4` (ở nhà, 25 fps), cắt thành `data/clip_tran_nen.mp4` (401 frame,
bắt đầu ở frame vật đã trong khung) và **tô GT 6 frame**: f0/f45/f222/f266/f400 có vật, **f133 GT RỖNG**
(vật đã hạ khỏi khung). Đây là clip **đầu tiên** trong repo tái hiện ca "vật sáng trên nền sáng" bằng
hình sạch (không HUD).

### Bảng đo (cùng 5 frame có vật, cùng ô chọn `405,65,90,365`, `git_dirty_code = false` cả 2 tầng)

| cấu hình | mIoU | mask NGOÀI GT | BỊA MASK @f133 (GT rỗng) | ms/frame |
|---|---|---|---|---|
| **@192 (mặc định)** | **0,6987** | 17,4 % | **3 713 px** | 283 |
| **@320** | **0,7268** | **11,7 %** | **0 px** | 534 |
| ngưỡng mask 1,0 | 0,6450 | 13,2 % | 536 px | — |
| ngưỡng mask 2,0 | 0,5321 | 9,7 % | 11 px | — |
| `--reanchor-every 30` | **0,3965** | **53,9 %** | 10 077 px | — |

### Bốn kết luận ÂM TÍNH (ghi để KHÔNG ai làm lại)

1. **Nâng `--mask-threshold` không cứu được**: 1,0 và 2,0 làm mIoU **giảm** (0,6987 → 0,6450 → 0,5321)
   vì vật mờ nên **logit ở giữa vật cũng thấp**; nó chỉ làm mask co lại dưới GT. Chỉ dùng ngưỡng khi
   mục tiêu là "bớt ăn viền", **không** phải "bám đúng hơn".
2. **`--reanchor-every` làm TỆ HƠN HẲN** (0,3965, mask ngoài GT 53,9 %): neo lại bằng **ô đã trôi** ⇒
   khoá cái sai vào bộ nhớ. Muốn re-anchor có ích thì phải có ô ĐÚNG (cần người bấm `r` hoặc oracle).
3. **Luật "mảnh mask phải tiếp nối" (đã viết `src/mask_continuity.py`, đã đo, đã REVERT)**: mIoU **y hệt**
   0,6987 — luật **không kích hoạt**, vì model **trôi DẦN** (ô co từ 18 174 px xuống ~3 000 px từ f100)
   chứ không "nhảy"; trượt dần thì mỗi bước vẫn giao mảnh trước ⇒ không có gì để cắt. Đúng cảnh báo
   AGENTS §6: "cả hai cổng đều mù với trôi dần".
4. **So cặp 192 vs 320 CHƯA đủ để tuyên bố "320 tốt hơn"** theo luật repo: 5 frame chung,
   mean **+0,0282**, **CI95 [−0,0416, +0,1126] chứa 0**, 3/5 dương, sign test **p = 1,000** ⇒
   **"không phân biệt được"**. Cái **đo được chắc chắn** ở 320 là **hành vi**: `BỊA MASK` ở frame vật
   vắng **3 713 → 0 px** và mask ngoài GT 17,4 → 11,7 %.

### Hệ quả cho báo cáo (được trích / cấm trích)

- **Được**: "vật càng khó (trắng mờ trên nền trắng) thì mIoU càng giảm: **0,6987** (túi trắng mờ) vs
  **0,7794** (chai binh1) vs **0,8625** (clip_be2)" — cả ba đo trên GT người tô, cùng máy.
- **Cấm**: "320 tốt hơn 192" (chưa đủ mẫu) và "đã sửa được trôi dần bằng luật tiếp nối" (đã revert).

### Việc còn lại (cần người dùng quyết)

- Muốn ca trắng-trên-trắng **bám đúng tự động** thì phải đổi **cơ chế bộ nhớ** của model (Cutie/XMem)
  — việc > 4 h ⇒ phải lập plan 3 ý kiến (AGENTS §9.2) và **cần GPU để còn real-time**.
- Đường rẻ nhất cho buổi bảo vệ: chọn vật **đặc, có màu** (số đo đã có: 0,78–0,86) và ghi ca trắng-trên-trắng
  vào mục **"hạn chế"** kèm đúng các số ở bảng trên.
