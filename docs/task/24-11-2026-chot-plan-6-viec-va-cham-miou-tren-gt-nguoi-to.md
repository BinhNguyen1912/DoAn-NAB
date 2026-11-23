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
