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

**Vòng 2 — sau review độc lập 27-11** (commit `537760c`; reviewer chỉ ra 1 P1 + 6 P2 mới):

10. **P1 — `don_cache_neu_can` xoá mọi thư mục con của `--out`** mà không kiểm đó là thư mục cache:
    `--out data` ⇒ xoá `data/nhan`; `--out .` ⇒ xoá `src/`, `.git/`; `--limit` cũng kích hoạt. Nay chỉ
    dọn khi `out_dir` đã có `.dau_van_tay` (hoặc đang rỗng), ngược lại `ValueError` ⇒ thoát 1, không xoá
    gì; `--limit` không gọi hàm này. Trả **số PNG đã xoá** (`so_mask_da_xoa`) thay vì bool.
11. **P2 — đếm lý do bỏ tách đơn vị**: `bo_qua_file` (theo phiên) / `bo_qua_buoc` (theo bước), thêm
    `nhan_cuoi_khong_co_hop` cho 20 bước mà nhãn CUỐI bỏ `bbox_dung` (trước bị `continue` im lặng).
12. **P2 — tách đếm DÒNG khỏi đếm BƯỚC**: `so_dong_trung_lap` + `so_dong_cua_buoc_bi_bo`; bỏ
    `mat_do_gop_buoc = max(0, …)` (che lệch giữa hai đơn vị).
13. **P2 — `giay_tong`/`ms_moi_mask`**: thêm `do_toc_do` + `ghi_chu_giay_tong` để không ai lấy
    `13,9 s / 1 251` ra làm ms/mask khi lần chạy toàn cache.
14. **P2 — `cv2.imwrite` trả False** (đĩa đầy/quyền) trước đây vẫn được tính là mask ⇒ thêm `loi_ghi`,
    không công bố, không ghi artifact.
15. **P2 — ngưỡng "hộp sát mép" 1 → 2 px** đổi cùng lúc với luật từng phía mà không khai: nay là hằng
    `SAT_MEP = 2` có docstring giải thích + test biên giữ hành vi.
16. **Test 23 → 32**: sửa ca `thieu_video` (trước thiếu luôn CSV nên nhánh `bo("thieu_video")` không bao
    giờ chạy), thêm ca "nhãn cuối bỏ hộp", số học dòng/bước, `don_cache` (từ chối thư mục không phải
    cache, đếm file đã xoá, vân tay không đổi thì không đụng), `imwrite` lỗi, ngưỡng `SAT_MEP`.

**Vòng 3 — sau lượt review cuối trên `537760c`** (commit `b35c7fa`; reviewer bắt 4 mục P2 + các P3 còn
nợ, mỗi cái ≤ 15 phút nên sửa ngay trong cùng PR):

17. **P2 — `don_cache_neu_can` đếm MỌI entry**, không chỉ thư mục con: `--out docs/task` (chỉ có file)
    trước đây được đóng dấu vân tay rồi lần sau bị coi là cache để xoá. Nay chỉ đếm PNG trong thư mục
    con (`so_mask_da_xoa` giữ nghĩa "số PNG đã xoá"), file ở gốc vẫn được giữ.
18. **P2 — `manifest.jsonl` ghi SAU cổng "không công bố"**: ghi trước thì một lần chạy lỗi để lại
    manifest rách, và lần `--qc` sau đó in theo bản rách đó.
19. **P2 — `thu_thap_muc_tieu` đòi `nhan` khác rỗng và `buoc` là int** trước khi ghi `dong_theo_buoc`;
    dòng nhãn không có `buoc` trước đây bị đếm thành bước 0.
20. **P2/P3 — PNG ghi ATOMIC** (`<tên>.tmp.png` rồi `os.replace`): Ctrl-C/đĩa đầy giữa đường trước đây
    để lại PNG cụt mang **đúng** tên cache ⇒ lần sau `imread` đọc nửa ảnh và **không bao giờ** sinh lại.
21. **P3 — `--qc` dùng `.get`** và in số bản ghi THIẾU `qc` thay vì chết bằng `KeyError` + traceback;
    `dem_dong` khử trùng theo **bước** (một bước lặp 2 lần làm `trung_lap` phồng); tách
    `so_buoc_co_hop_hieu_luc` (1 251) khỏi `so_buoc_tung_co_hop` (1 271) — hai đại lượng khác luật, gộp
    một số là không đọc được cái nào; thêm `ghi_chu_ms_moi_mask` (giữ nguyên tên khoá `ms_moi_mask` để
    artifact cũ còn so được).
22. **Test 32 → 36**: ca PNG atomic (không còn rác `.tmp.png`), `--out` chỉ có file bị từ chối,
    `frame_idx` phải đi qua `label_ui.chi_so_khung` (một định nghĩa duy nhất), manifest không bị ghi đè
    khi lỗi.

## 📤 Output / Kết quả

Sinh lại toàn bộ trên **cây sạch** — `data/gt_pseudo_metrics.json` (`git_rev b35c7fa`,
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
(`so_mask_moi_sinh = 0`, `ms_moi_mask = null`, `do_toc_do = false`, `co_cache = 1 251`) — `null` ở đây
nghĩa **chưa đo**, đúng quy ước "0/None ≠ đã đo"; `giay_tong = 8,9 s` là **thời gian đọc cache**, không
phải thời gian sinh mask (artifact có `ghi_chu_giay_tong`).

**Đếm dòng nhãn (kiểm được bằng số học):** 1 490 dòng có `bbox_dung` − **210** dòng bị dòng sau thay thế
(`so_dong_trung_lap`) − **29** dòng của **20 bước** mà nhãn CUỐI bỏ hộp (`nhan_cuoi_khong_co_hop`) =
**1 251** mask. `so_buoc_co_hop_hieu_luc = 1 251` và `so_buoc_tung_co_hop = 1 271` (1 271 − 20),
`bo_qua_file = {}`.

Ba rev (`ab318b1` → `537760c` → `b35c7fa`) cho **cùng** bộ số ở bảng trên: mọi sửa của vòng 2/vòng 3 là
đổi cách ĐẾM và đổi KHOÁ, không đổi mask. Khác duy nhất: `giay_tong` 13,9 → 8,9 → **8,0 s** (vẫn là đọc
cache, `do_toc_do = false`), và bộ khoá mới (`so_buoc_*`, `ghi_chu_ms_moi_mask`).

Kiểm tra: `./run lint` **xanh**; `pytest tests/test_make_pseudo_masks.py -q` = **36 passed**;
`./run test` (làn nhanh `-m "not slow"`) = **2 286 passed, 6 deselected** (230 s).

File thay đổi:
- `scripts/make_pseudo_masks.py` — 2 P1 + 7 P2 (`ab318b1`), P1 + 6 P2 của vòng review 2 (`537760c`),
  rồi 4 P2 + 4 P3 của vòng review 3 (`b35c7fa`), rồi P3 cuối: cờ `shape_la` trong `qc()`.
- `tests/test_make_pseudo_masks.py` — 19 → 23 → 32 → 36 → **37** test (thêm ca mask lệch chiều), sửa 2 ca "test giả".
- `data/gt_pseudo_metrics.json` — sinh lại trên cây sạch (`b35c7fa`).
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
5. **Kết quả review độc lập** (agent khác, chỉ đọc): 1 P1 (dọn cache xoá mọi thư mục con của `--out`),
   6 P2 (đếm lý do bỏ còn thiếu nhãn-cuối-bỏ-hộp + trộn đơn vị file↔bước; `giay_tong` không nói "chưa
   đo"; `imwrite` không kiểm; `da_xoa_cache_cu` sai nghĩa; ngưỡng 2 px không khai), 4 P3 (vân tay chưa
   gồm phiên bản code/nội dung checkpoint, `qc` chưa phòng thủ mask rỗng-shape, thứ tự import, `n` của
   phân bố). Reviewer **đếm lại độc lập** trên `data/nhan/*.jsonl` và ra đúng 1 490 dòng / 1 251 bước /
   210 trùng lặp / 29 dòng của 20 bước bị nhãn cuối bỏ hộp — khớp số trong artifact mới.
6. **Log 26-11 giữ nguyên** (AGENTS §2.3: không sửa log ngày cũ). Bảng số của ngày đó là của artifact
   rev `127f428` (`cham_bien 337`, `nghi 369`) — khác hôm nay vì **đổi định nghĩa** `cham_bien` (từng
   phía + ngưỡng 2 px), không phải mask tốt lên. Đọc số hiện hành phải lấy artifact `b35c7fa`.
7. **Ba lượt review độc lập trên nhánh này, không lượt nào có P0.** Lượt 26-11 → 2 P1 + 7 P2 (sửa ở
   `ab318b1`); lượt 27-11 trên `ab318b1` → 1 P1 + 6 P2 (sửa ở `537760c`); lượt cuối trên `537760c` → 4 mục
   P2 + các P3 còn nợ (sửa ở `b35c7fa`). Toàn bộ P1/P2 đã sửa; còn nợ 2 P3 ghi ở Next steps.

8. **Vòng 4 (sau khi đã merge-ready): sửa 1 P3, CỐ Ý hoãn 1 P3.** `qc()` thêm cờ `shape_la`
   (`mask.ndim != 2 or mask.size == 0`) và trả sớm, bỏ kiểm biên — trước đó `mask[0, :]` ném
   `IndexError` giữa lô, tức một ca lạ làm mất cả lượt sinh. Số artifact **không đổi** vì mọi mask
   hiện có đều `(H,W)`.
   Còn `dau_van_tay` **không** sửa lúc này, và đây là quyết định có lý do đo được: đổi công thức vân tay
   ⇒ `don_cache_neu_can` xoá **toàn bộ 1 251 PNG** trong `data/gt_pseudo/` — đúng thư mục đang là đích
   sửa tay của 308 ca "nghi" — rồi SAM 2 sinh lại **không tất định** (AGENTS §6) nên `rong/nho/tran/
   cham_bien` của artifact sẽ đổi mà **không phải mask tốt lên**. Việc này để dành đúng lúc sinh lại
   mask (khi đó cache vô hiệu là ý định, không phải tai nạn). Nay đã có **bảo vệ chặn việc
   xoá tự phát** — xem mục 9.

9. **Review độc lập vòng 4** (trên `b10d356`) → **2 P1 + 2 P2, mọi mục đã sửa**:
   - **P1 (chặn mất dữ liệu):** vân tay đổi ⇒ `don_cache_neu_can` **xoá** sạch mask cũ. Mà vân tay gồm
     `mtime` của `data/nhan/*.jsonl` ⇒ chỉ cần gán thêm **một** nhãn, lần chạy đầy đủ kế tiếp là mất
     1 251 PNG (kể cả mask đã sửa tay) mà **không ai bấm gì**. Nay `don_cache_neu_can(..., cho_xoa=False)`
     **từ chối** bằng `ValueError` (in `LỖI: … — không công bố số`, thoát 1); chỉ `--xoa-cache` mới xoá.
     Test `test_van_tay_doi_ma_KHONG_cho_xoa_thi_TU_CHOI` (PNG còn nguyên, `.dau_van_tay` không bị đóng
     dấu mới).
   - **P1 (mất nguồn gốc):** artifact của lần chỉ đọc cache khai `git_rev` của **chính nó** và
     `so_mask_moi_sinh = 0` ⇒ **không chỗ nào** ghi rev/checkpoint/`image_size` đã tạo ra 1 251 PNG.
     Nay có `data/gt_pseudo/sinh_luc.jsonl`: **một dòng mỗi lần có sinh mới** (`git_rev`,
     `git_dirty_code`, `image_size_hieu_luc`, `checkpoint`, `model_cfg`, `so_mask_moi_sinh`) và
     artifact có `phien_ban_sinh` (dòng đó, hoặc `null` khi lần chạy không sinh mask nào). File này
     **không** vào `dau_van_tay`: đưa vào là mỗi lần ghi lại tự phá vân tay ⇒ xoá cache.
   - **P1 (test):** `shape_la` mới chỉ "phòng thủ cho khỏi ném", mask lệch chiều vẫn **đi tiếp**. Đo lại:
     `cv2.imwrite` **nhận** cả mảng 1-D và 3-D (chỉ rỗng/scalar mới ném) ⇒ hậu quả là **ghi PNG sai
     trong im lặng**, tệ hơn là ném. Nay trong `sinh_mask`: `mask.ndim != 2 or mask.size == 0` ⇒
     `dem["loi_shape"] += 1` + `continue` (in 3 ca đầu) và `loi_shape` vào cổng "không công bố" ⇒
     **không ghi file, không chết cả lô 1 251 mask**. Test `test_shape_la_bi_BO_va_DEM_khong_ghi_PNG`
     kiểm `imwrite` **không** được gọi.
   - **P2:** `shape_la` vào tuple `CO` (4 → 5 khoá ⇒ artifact `qc_dem` phát đủ), `schema` 1 → **2**, và
     `ghi_chu_pham_vi_dau_van_tay` nói rõ cái **không** gồm (nội dung checkpoint, `src/tracker_engine.py`,
     đường prompt→mask) để không ai tưởng vân tay bảo vệ mọi thứ.
   - Test của file: **36 → 40**; `./run lint` xanh.
   - **Giới hạn phải nói kèm:** 1 251 mask hiện có được sinh **trước** khi có `sinh_luc.jsonl` ⇒ lần chạy
     lại (chỉ đọc cache) cho `phien_ban_sinh: null`. Nguồn gốc của chúng chỉ còn trong log/commit
     (`127f428`) — **không bịa** dòng provenance cho chúng.

## 📌 Việc cần làm tiếp (Next steps)

- [x] Review độc lập `ab318b1` (AGENTS §9.1): 1 P1 + 6 P2 + 4 P3; P1 và 5 P2 đã sửa ở `537760c`.
- [x] **Lượt review cuối** cho `537760c`: 4 mục P2 + các P3 còn nợ, đã sửa hết ở `b35c7fa`.
- [x] P3 `qc()` phòng thủ mask shape lệch chiều: cờ `shape_la` + test `test_mask_shape_la_khong_lam_chet_ca_lo`
      (4 shape: `(0,0)`, `()`, `(5,)`, `(1,4,4)`). Số artifact **không đổi** (mọi mask thật đều `(H,W)`).
- [ ] P3 **cố ý hoãn** — `dau_van_tay` chưa gồm **phiên bản code** (`src/tracker_engine.py`, chính script)
      và **nội dung** checkpoint, chưa gồm `data/<phiên>_web.mp4` (fallback của `_mo_video`).
      **Vì sao hoãn:** đổi vân tay ⇒ xoá sạch 1 251 mask đang sửa tay + SAM 2 sinh lại không tất định
      ⇒ số trong artifact đổi mà không phải mask tốt lên. Sửa vào lúc **sinh lại mask**, không trước đó.
- [x] Làn nhanh xanh **trong env `samurai`** (conda): `./run lint` + `./run test` = 2 286 passed /
      6 deselected (230 s). `.venv` của WSL vẫn thiếu `fastapi/uvicorn/httpx/pydantic` ⇒ vẫn phải chạy
      qua `/home/msi/miniconda3/envs/samurai/bin/python`.
- [x] Vòng 4 review (2 P1 + 2 P2) đã sửa + 4 test mới (36 → 40).
- [ ] Sinh lại `data/gt_pseudo_metrics.json` trên rev mới (schema 2; chỉ đọc cache, KHÔNG sinh lại mask).
- [ ] Mở PR `feat/mask-gia-tu-o-nguoi-ve` → `main` (merge commit, CI xanh trước khi merge).
- [ ] (Tuỳ chọn) xoá `data/gt_pseudo` rồi chạy lại đủ để có `ms/mask` cho cả 1 251 mask trên cây sạch.
- [ ] Sửa tay 308 mask "nghi" (38 ca `nho` + các ca xem mắt thấy ăn nền) ⇒ ~943 mask "tạm tin".

## 📚 Tài liệu tham khảo

- `docs/task/26-11-2026-mask-gia-tu-o-nguoi-ve.md` (sinh mask lần đầu), AGENTS §6/§9.1/§9.4.
- `scripts/make_pseudo_masks.py`, `tests/test_make_pseudo_masks.py`, `tools/label_ui.py`
  (`chi_so_khung`, `_mo_video`, `_CAP_LOCK`), `src/tracker_engine.py`.
