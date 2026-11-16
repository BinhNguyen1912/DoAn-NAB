# Ngày 16-11-2026 — Ticket #30: cổng kiểm GT hộp bao (đối chiếu hộp ↔ mask, clip ↔ manifest, tên khoá `mIoU`)

## 🎯 Mục tiêu
- Đóng 3 P3 còn lại của review độc lập 15-11 về bộ GT hộp bao `docs/gt/binh1_hopbao`
  (ticket `.scratch/camera-ai-realtime/issues/30-…md`):
  1. Artifact GT hộp bao không được mời gọi trích sai: ai `grep mIoU` phải thấy cảnh báo **ngay cạnh**
     con số.
  2. `kiem_index` phải đối chiếu `hop_bao_xywh` ↔ mask GT (hiện chỉ kiểm "file tồn tại + đúng cỡ khung"),
     và `main` phải đối chiếu `index.clip`/`index.frames` với `manifest.json` của mask.
  3. Quy ước xác định cho `mask_ngoai_gt_max_frame` khi hoà + test ghim.
- **Không** làm lại bất kỳ số mIoU nào (đây là cổng kiểm/tên khoá). Máy CPU-only, không nạp model.

## 📥 Input
- Ticket #30 (review độc lập 15-11) — 5 tiêu chí nghiệm thu.
- `scripts/score_miou.py` (403 dòng trước phiên), `tests/test_score_miou.py` (447 dòng).
- GT thật: `docs/gt/binh1_hopbao/index.json` (`dang_gt = hop_bao`, 12 frame, mỗi frame có
  `hop_bao_xywh`), mask model: `data/masks_binh1_192_2026-11-15/` (12 PNG + `manifest.json`,
  `nguon = data/binh1.mp4`, `frames_yeu_cau = [2,12,…,106]`).
- Artifact cũ: `data/miou_binh1_hopbao_2026-11-15_metrics.json` (`mIoU = 0,6464`, 12/12 frame).
- `AGENTS.md` §6 (quy tắc số đo), §9.1 (review độc lập), `docs/thuoc-do-bam-dung.md`.

## 🔨 Công việc đã thực hiện
1. **Tên khoá nói đúng nghĩa** (`scripts/score_miou.py`):
   - `ket_qua.gt_dang` echo `index.dang_gt`; khi `dang_gt != silhouette` (kể cả `None`) thêm
     `ket_qua.mIoU_dinh_nghia` ("IoU(mask, GT dạng 'hop_bao') — KHÔNG phải mIoU phân đoạn silhouette").
   - `ket_qua` dựng bằng `{gt_dang, mIoU_dinh_nghia, **cham(...)}` ⇒ hai khoá cảnh báo đứng **trước**
     `mIoU` trong file JSON (grep/copy thấy cảnh báo trước con số).
   - `meta.nguon_gt` được echo; `--check-index` in thêm 3 dòng: **dạng GT** (+ nghĩa), **nguồn GT**,
     **clip · N frame · mask từ <nguồn manifest>** (hoặc "KHÔNG có manifest ⇒ chưa đối chiếu được").
2. **Cổng `hop_bao_xywh` ↔ mask** (hàm mới `_hop_bao_hop_le` + `doi_chieu_hop_bao`, gọi trong
   `kiem_index` khi `dang_gt == hop_bao`) — **CHẶN** (exit 2, không ghi artifact) khi:
   hộp sai định dạng (`bool`/`float`/`w,h ≤ 0`/không đủ 4 phần tử) · hộp vượt biên khung ·
   `mask.sum() != w*h` · bao thực của mask ≠ `(x, y, w, h)`. Frame GT **rỗng** mà vẫn khai hộp ⇒ chặn
   kèm câu chỉ đúng cách sửa ("vật đã RỜI KHUNG ⇒ BỎ `hop_bao_xywh`"). Khai `hop_bao` mà **thiếu**
   `hop_bao_xywh` ⇒ **cảnh báo mềm** (GT cũ), gộp 1 dòng, không đếm frame GT rỗng.
3. **Đối chiếu GT ↔ manifest** (hàm thuần mới `kiem_khop_manifest` + `_cung_nguon`, gọi trong `main`
   cho cả nhánh `score` và `--check-index`) — cảnh báo **mềm** khi `index.clip` khác `manifest.nguon`
   (so đường dẫn thật khi file tồn tại) hoặc `index.frames` ra ngoài `frames_yeu_cau` (chấp nhận
   `frames_yeu_cau` dạng chuỗi `"2,12"`; float lẻ/`Infinity` bị từ chối chứ không cắt cụt im lặng).
4. **Hoà `mask_ngoai_gt_max_frame`**: `max()` với key `(tràn, -frame_idx)` ⇒ hoà thì chọn **frame_idx
   nhỏ nhất**, tái lập được dù `index.frames` xếp thế nào; có test đảo thứ tự.
5. **Tài liệu**: `docs/thuoc-do-bam-dung.md` §1.2 (bảng cổng CHẶN vs cảnh báo mềm + giới hạn: không bắt
   copy-paste, `hop_bao_xywh` ≠ `bbox_xywh`, hộp phải số nguyên); `docs/gt/binh1_hopbao/README.md`
   thêm mục "Cổng kiểm"; `scripts/so_lieu_bao_cao.py` câu CẤM trích trỏ `ket_qua.gt_dang`.
6. **Sinh lại artifact trên cây sạch** (chỉ THÊM khoá, không đổi số) + `docs/so-lieu-bao-cao.md`.

## 📤 Output / Kết quả
- `--check-index` trên bộ GT thật: **0 lỗi chặn**, 1 cảnh báo (GT hộp bao) ⇒ exit 1 đúng hợp đồng;
  12/12 file GT đều khớp `w*h` của hộp khai (kiểm độc lập bằng script: f2 67 080 = 156×430 … f106 61 904).
- `score` trên bộ thật: `mIoU = 0,6464` (**không đổi**), `n_cham = 12`, `coverage = 1,0`,
  `mask_ngoai_gt_mean = 0,0391`, `mask_ngoai_gt_max_frame = 62` (**không đổi**).
- Artifact mới: `git_rev = a2f8647`, `git_dirty_code = false` (tái lập được), `ket_qua` có
  `gt_dang = hop_bao` + `mIoU_dinh_nghia` trước `mIoU`; `meta.nguon_gt` đã có.
- Cổng bắt đúng ca sai (diễn tập trên `docs/gt/synthetic_tong_hop` + pred-dir của `binh1`): cảnh báo
  "clip của GT KHÁC nguồn của mask" + "21 frame KHÔNG nằm trong `frames_yeu_cau`".
- Kiểm tra: `./run lint` xanh · `./run test` **1270 passed, 5 deselected** (trước phiên 1263; +7 test
  mới cho cổng/hoà/manifest/artifact) · `python scripts/so_lieu_bao_cao.py --check` = OK.
- File thay đổi:
  - `scripts/score_miou.py` — cổng hộp bao, đối chiếu manifest, echo `gt_dang`/`mIoU_dinh_nghia`, tie-break
  - `tests/test_score_miou.py` — +13 test (định dạng hộp, diện tích, vị trí, biên khung, GT rỗng,
    manifest khác nguồn/frame, CLI gọi manifest, artifact `gt_dang`, hoà tràn, `frames_yeu_cau` chuỗi)
  - `scripts/so_lieu_bao_cao.py` — câu CẤM trích trỏ tên khoá mới
  - `docs/thuoc-do-bam-dung.md`, `docs/gt/binh1_hopbao/README.md` — §1.2 cổng kiểm + giới hạn
  - `data/miou_binh1_hopbao_2026-11-15_metrics.json`, `docs/so-lieu-bao-cao.md` — sinh lại

## 🐞 Vấn đề gặp phải & cách xử lý
- **Test biên khung viết sai** (`[3,3,2,2]` trên khung 10×10 vẫn trong khung) ⇒ sửa thành `[9,9,2,2]`;
  bài học: test "chặn" phải có ca biên `x+w == W` **hợp lệ** đi kèm, nếu không sẽ chặn oan frame 72
  của bộ thật (hộp chạm mép trên `y = 0`).
- **`f-string` lồng nháy** trong dòng in `--check-index` làm `SyntaxError` ⇒ tách biến `nguon_mask`/`duoi`.
- **`git_dirty_code` báo `true`** ở lần đo đầu vì file ticket trong `.scratch/` chưa commit ⇒ commit
  trạng thái ticket rồi **đo lại**; `git_dirty` vẫn `true` là do chính `data/` bị ghi (đúng quy ước
  `git_dirty_code` bỏ qua `data/`).
- **Hai câu khuyên ngược nhau** (review vòng 2 bắt): GT rỗng bảo "BỎ `hop_bao_xywh`" nhưng cảnh báo
  tổng lại bảo "thiếu hộp ⇒ thêm vào" ⇒ chỉ đếm frame **có** pixel vào `thieu_hop` + test ghim.

## ✅ Review độc lập (AGENTS §9.1)
- **Vòng 1** (agent `reviewer`, chỉ đọc): **không P0/P1**, 5 P2 + 9 P3. Điểm đáng chú ý: (a) `dang_gt`
  không khai thì artifact không có câu định nghĩa ⇒ lại bị đọc thành "mIoU phân đoạn"; (b) frame GT
  rỗng bị chặn với chẩn đoán sai "GT lẫn frame khác" (ca thật: `binh1` cất chai từ frame ~115);
  (c) **không test nào** chứng minh `main()` gọi `kiem_khop_manifest` (xoá dòng gọi mà test vẫn xanh);
  (d) không test trên bộ GT đã commit; (e) thiếu log/ticket. Đã xác nhận **không chặn oan** bộ GT thật
  và **không** consumer nào đọc `ket_qua` theo bộ khoá cố định (`so_lieu_bao_cao` tra theo đường dẫn).
- **Đã sửa cả 5 P2** (`e4f96a8`) + 4 P3 (biên khung, `frames_yeu_cau` chuỗi, câu cảnh báo clip khác
  nguồn nói rõ "không xác minh được nội dung", guard manifest non-dict/thiếu `nguon`).
- **Vòng 2** (agent `reviewer`, chỉ đọc, chỉ phần vừa sửa): **không P0/P1 mới**; P2-5 (log/ticket) đóng
  bằng file này; 2 P3 sửa luôn (`d8319af`): câu khuyên ngược nhau + `float`/`Infinity` trong
  `frames_yeu_cau`; ghi rõ test "bộ GT đã commit" là **một chiều** (chỉ canh "không chặn oan").
- **Còn nợ (P3, ghi ở Next steps)**: `_doc_manifest` nuốt lỗi JSON ⇒ manifest **hỏng** in y hệt "không có
  manifest"; cổng không bắt ca **copy-paste** cùng hộp+mask cho nhiều frame (đã ghi giới hạn trong docs).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] P3: phân biệt "manifest hỏng" vs "không có manifest" (`_doc_manifest` trả kèm lý do) + test
      `manifest.json` là list / JSON hỏng trên `--check-index`.
- [ ] P3: cân nhắc dùng `DUP_IOU` của `scripts/gt_check_silhouette.py` cho cả GT `hop_bao` để bắt
      copy-paste (hiện chỉ ghi giới hạn trong `docs/thuoc-do-bam-dung.md` §1.2).
- [ ] Việc lớn còn lại của plan 14-11: **tô silhouette** cho 10–20 frame `binh1` ⇒ mIoU phân đoạn thật
      (hiện chỉ có IoU với hộp bao 0,6464); đoạn demo ≥ 20 s; chốt phạm vi với GVHD.

## 📚 Tài liệu tham khảo
- `docs/thuoc-do-bam-dung.md` (§1.1 dạng GT, §1.2 cổng kiểm), `docs/gt/binh1_hopbao/README.md`
- `AGENTS.md` §6 (số đã đo), §9.1 (review độc lập), §9.4 (checklist kết thúc phiên)
- Ticket: `.scratch/camera-ai-realtime/issues/30-ch-n-ch-t-h-n-cho-gt-d-ng-h-p-bao-i-chi-u-hop-ba.md`
