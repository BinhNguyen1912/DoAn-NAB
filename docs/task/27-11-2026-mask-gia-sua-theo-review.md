# Ngày 27-11-2026 — Sửa `make_pseudo_masks.py` theo review độc lập 26-11 (2 P1 + 7 P2)

## 🎯 Mục tiêu

Review độc lập 26-11 trên `scripts/make_pseudo_masks.py` (sinh 1 251 MASK GIẢ từ hộp người dùng vẽ) bắt
**2 P1 + 7 P2** — tất cả đều là lỗi kiểu "số công bố sai mà `loi_* = 0`". Hôm nay: sửa hết, thêm test bắt
hồi quy, rồi **sinh lại artifact trên cây sạch** (`git_dirty_code == false`) để số trong log đọc được từ
artifact (AGENTS §6).

## 📥 Input

- Review 26-11 (kết quả ghi trong commit trước của nhánh `feat/mask-gia-tu-o-nguoi-ve`) và
  `docs/task/26-11-2026-mask-gia-tu-o-nguoi-ve.md`.
- `data/nhan/*.jsonl` (1 490 `bbox_dung`), `data/gt_pseudo/` (1 251 PNG đã sinh), SAM 2 tiny @512, CPU.
- AGENTS §6 ("0/None ≠ đã đo", "tái lập được ⇔ `git_dirty_code == false`"), §9.1 (review độc lập).

## 🔨 Công việc đã thực hiện

Commit code `ab318b1` — `scripts/make_pseudo_masks.py`:

1. **P1 — cache phục vụ mask CŨ sau khi vẽ lại hộp.** Tên file nay là `<bước>_<hash hộp>.png`
   (`bam_hop`, 8 ký tự sha256) ⇒ đổi `bbox_dung` là cache-miss, không còn chuyện QC tính theo hộp mới
   trên mask cũ.
2. **P1 — cache không biết tham số/nguồn.** Thêm `.dau_van_tay` (`dau_van_tay`: `image_size` + checkpoint
   + model_cfg + mtime/size của **mọi** nhãn/CSV/video); khác vân tay ⇒ `don_cache_neu_can` xoá các thư
   mục con của `data/gt_pseudo` rồi ghi vân tay mới. Artifact ghi `dau_van_tay` + `da_xoa_cache_cu`.
3. **P2 — `cham_bien` so theo TỪNG phía.** Bản đầu `hop_cham` = OR 4 phía ⇒ hộp chạm đáy miễn luôn mask
   tràn sang trái/phải/trên. Nay mỗi phía so với mép hộp tương ứng (dung sai 2 px).
4. **P2 — mục tiêu bị bỏ phải ĐẾM.** `thu_thap_muc_tieu` trả `(việc, bo_qua)` với 6 lý do
   (`thieu_csv`/`csv_hong`/`thieu_video`/`buoc_ngoai_dai`/`hop_khong_hop_le`/`khong_anh_xa_duoc_frame`);
   artifact thêm `so_dong_co_bbox_tho`, `mat_do_gop_buoc`, `ghi_chu_gop_buoc` ⇒ câu "1 490 ô → 1 251"
   kiểm được, và 239 dòng bị gộp bước (append-only) không còn bị đọc thành "mất dữ liệu".
5. **P2 — `qc_dem` phát ĐỦ 4 khoá** kể cả khi bằng 0 (trước chỉ phát cờ > 0), thêm `so_mask_nhieu_co`.
6. **P2 — số dẫn xuất vào artifact**: `phan_bo_ty_le_dien_tich` (median/p05/p95, p05/p95 chỉ phát khi
   n ≥ 30), `so_frame_khac_nhau`, `so_phien`, `giay_tong` — log không còn trích số chỉ suy ra từ code.
7. **P2 — `image_size` so với HIỆU LỰC** (`engine.image_size_hieu_luc`); lệch ⇒ thoát 1, không công bố.
8. **P2 — không công bố khi lỗi**: có `loi_mask`/`loi_doc_frame`/`so_mask < so_o_hop_le` ⇒ thoát 1 **trước
   khi** ghi đè `manifest.jsonl` + artifact; ghi artifact qua file tạm + `os.replace`.
9. **P2 — test giả**: ca "model lỗi" cũ không bao giờ chạm model (thiếu video ⇒ chỉ tăng `loi_doc_frame`)
   nên xoá `try/except` vẫn xanh. Nay giả lập được frame (`_mo_video` + `_CAP_LOCK`) và engine hỏng. Thêm
   test: `nghi` = OR của tập cờ **ĐỘNG** (không hard-code 4 tên), `cham_bien` theo từng phía, hash hộp,
   vân tay đổi khi đổi `image_size`, đếm lý do bỏ.

## 📤 Output / Kết quả

Sinh lại toàn bộ trên **cây sạch** — `data/gt_pseudo_metrics.json` (`git_rev ab318b1`,
`git_dirty_code = false`, `image_size_hieu_luc = 512` = yêu cầu):

| | 26-11 (`127f428`) | 27-11 (`ab318b1`) |
|---|---|---|
| mask | 1 251 | 1 251 |
| mask "nghi" | 369 (29,5 %) | **308 (24,6 %)** |
| `rong` / `nho` / `tran` / `cham_bien` | 0 / 38 / 0 / 337 | 0 / 38 / 0 / **274** |
| số mask nhiều cờ | (không phát) | **4** |
| phân bố mask/hộp | med 0,62 · p05 0,24 · p95 0,90 | med 0,622 · p05 0,239 · p95 0,899 |
| frame khác nhau / phiên | 1 018 / 30 | 1 018 / 30 |
| thời gian | *(không có trong artifact)* | **13,9 s** (toàn cache) |

`cham_bien` **337 → 274** không phải mask được sửa: luật so theo từng phía bỏ cờ cho các ca mask chạm
đúng mép mà **hộp cũng** chạm mép đó — đó là các ca "hộp người vẽ quá sát", không phải mask sai.

**Tốc độ (cây sạch, `ab318b1`, CPU, `image_size 512`):** `--limit 25` ⇒ **471,9 ms/mask** (25 mask sinh
mới, `loi_* = 0`). Lần chạy đủ 1 251 mask **không đo được tốc độ** vì cache đã ấm
(`so_mask_moi_sinh = 0`, `ms_moi_mask = null`, `co_cache = 1 251`) — `null` ở đây nghĩa **chưa đo**, đúng
quy ước "0/None ≠ đã đo".

Kiểm tra: `./run lint` **xanh**; `pytest tests/test_make_pseudo_masks.py -q` = **23 passed**.

File thay đổi:
- `scripts/make_pseudo_masks.py` — 2 P1 + 7 P2 ở trên (commit `ab318b1`).
- `tests/test_make_pseudo_masks.py` — 19 → 23 test, sửa ca "test giả".
- `data/gt_pseudo_metrics.json` — sinh lại trên cây sạch (`ab318b1`).
- `docs/task/27-11-2026-mask-gia-sua-theo-review.md` — log này.

## 🐞 Vấn đề gặp phải & cách xử lý

1. **Làn nhanh KHÔNG xanh được trên máy này — thiếu gói, không phải lỗi code.** `./run test` (pytest
   `-m "not slow"`) chạy trong WSL: 30 ERROR `tests/test_api_live.py`, 24 ERROR `tests/test_api_routes.py`,
   3 ERROR `tests/test_live_watchdog.py`, 7 FAILED `tests/test_api_live_sources.py`, 5 FAILED
   `tests/test_worker_device.py` — **tất cả** là `ModuleNotFoundError: No module named 'fastapi'`. Kiểm
   `.venv` (WSL, dựng bằng uv): có `torch/cv2/numpy`, **không** có `fastapi/uvicorn/httpx/pydantic`
   (đều nằm trong `requirements.txt`). Không đụng file nào của diff này; chưa cài thêm vì đổi môi trường
   dev không nằm trong phạm vi việc.
2. **Không xoá được `data/gt_pseudo` bằng lệnh shell** (lớp duyệt chặn `rm -rf`/`mv` thư mục) ⇒ lần chạy
   đủ này trúng cache (`co_cache = 1 251`). Muốn có `ms/mask` cho **cả 1 251 mask** phải xoá cache rồi
   chạy lại (~11 phút CPU) — cần người dùng đồng ý thao tác xoá.
3. **`git_dirty` = true nhưng `git_dirty_code` = false.** `git_dirty` tính cả `data/`, mà `data/` đang có
   chính file artifact vừa ghi ⇒ đọc đúng phải là `git_dirty_code`: **code sạch**, số tái lập được.
4. **Chạy `--limit` không ghi đè artifact** (chỉ in JSON ra stdout) — đã kiểm để dùng nó đo tốc độ mà
   không làm bẩn số đã công bố.

## 📌 Việc cần làm tiếp (Next steps)

- [ ] Kết quả review độc lập cho `ab318b1` (AGENTS §9.1) — xử lý P0/P1 nếu có rồi mới mở PR.
- [ ] Cài đủ `requirements.txt` vào `.venv` WSL để làn nhanh `./run test` xanh được trên máy này.
- [ ] (Tuỳ chọn) xoá `data/gt_pseudo` rồi chạy lại đủ để có `ms/mask` cho cả 1 251 mask trên cây sạch.
- [ ] Sửa tay 308 mask "nghi" (38 ca `nho` + các ca xem mắt thấy ăn nền) ⇒ ~880 mask "tạm tin".

## 📚 Tài liệu tham khảo

- `docs/task/26-11-2026-mask-gia-tu-o-nguoi-ve.md` (sinh mask lần đầu), AGENTS §6/§9.1/§9.4.
- `scripts/make_pseudo_masks.py`, `tests/test_make_pseudo_masks.py`, `tools/label_ui.py`
  (`chi_so_khung`, `_mo_video`, `_CAP_LOCK`), `src/tracker_engine.py`.
