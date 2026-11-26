# Ngày 26-11-2026 — Bước 2: sinh 1 251 MASK NHÁP từ 1 490 ô người dùng đã vẽ (SAM 2)

## 🎯 Mục tiêu

Đường ngắn nhất để có mask mà **không phải tô tay từ đầu**: mỗi ô GT người dùng đã vẽ là một *prompt
hộp* đủ để SAM 2 tự cắt mask ở đúng frame đó. Mục tiêu không phải "có GT" mà là **có bản nháp để sửa**,
vì AGENTS §6 đã đo: train lại SAM 2 cần **mask pixel**, mà repo chỉ có 259 mask (bộ lớn nhất 36 frame).

## 📥 Input

- `data/nhan/*.jsonl`: 1 490 `bbox_dung` trên 32 phiên (người dán: `binh`).
- `data/<phiên>_metrics.csv` + video gốc; phép ánh xạ bước→frame dùng **chung**
  `tools.label_ui.chi_so_khung` (không viết lại — bài học "hai định nghĩa" trong AGENTS §6).
- Model: `samurai/sam2/checkpoints/sam2.1_hiera_tiny.pt`, `configs/samurai/sam2.1_hiera_t.yaml`,
  `image_size 512`, CPU (máy này không có GPU).

## 🔨 Công việc đã thực hiện

**`scripts/make_pseudo_masks.py`** (mới):

1. Thu thập mục tiêu: mọi `(phiên, bước)` có `bbox_dung` **hợp lệ** (`o_hop_le`: trong khung, `x2>x1`,
   `y2>y1`, cạnh ≥ 3 px) ⇒ **1 251** mục tiêu (1 490 ô nhưng chỉ 1 251 bước có ô, và có ô trùng bước).
2. Với mỗi mục tiêu: đọc đúng frame (kiểm lại vị trí seek, `|lệch| ≤ 1`), gọi
   `TrackerEngine.build_default(...).start(frame, box)` (dùng lại đường nạp model của repo, **không**
   viết bộ nạp thứ hai; `build_overrides` được dùng nên `image_size` đi qua hydra, không copy config),
   ghi mask ra `data/gt_pseudo/<phiên>/<bước>.png`, cộng **cờ QC**.
3. **QC** mỗi mask: `rong` (rỗng dù có hộp), `nho` (<20 % diện tích hộp), `tran` (>150 %), `cham_bien`
   (mask chạm mép khung mà hộp không chạm). Ghi `ty_le_dien_tich` + cờ vào `manifest.jsonl` và **đếm**
   trong artifact.
4. Cache: PNG đã có ⇒ đọc lại, **không gọi model** (chạy lại chỉ mất ~1 phút thay vì 13 phút).
5. Lỗi model/đọc frame: **đếm** rồi bỏ qua từng mục, không để một frame làm chết cả lô.
6. `--qc` để in danh sách mask cần xem bằng mắt; `--limit N` để đo tốc độ.

**`tests/test_make_pseudo_masks.py`** (mới, 19 test): `o_hop_le` (7 ca sai), `qc` (rỗng/khớp/nhỏ/tràn/
chạm biên — kèm ca thật "hộp cắt mất phần dưới của vật"), `nghi` phải là OR của **mọi** cờ, cache không
gọi model, model lỗi không làm chết lô, không có nhãn ⇒ danh sách rỗng.

## 📤 Output / Kết quả

`data/gt_pseudo/` — **1 251 mask PNG** (5,4 MB) trên **1 018 frame khác nhau**, 30 phiên.
Artifact: `data/gt_pseudo_metrics.json` (`git_dirty_code = false`, `image_size_hieu_luc = 512`).

| | số |
|---|---|
| ô hợp lệ | **1 251** |
| mask sinh được | **1 251** (lỗi đọc frame 0 · lỗi model 0) |
| tốc độ | **518 ms/mask** @512 trên CPU ⇒ 12,5 phút cả lô |
| QC: mask rỗng | **0** |
| QC: `nho` (<20 % hộp) | **38** |
| QC: `tran` (>150 %) | **0** |
| QC: `cham_bien` | **337** |
| **tổng mask "nghi"** | **369 / 1 251 (29,5 %)** |

Phân bố tỉ lệ diện tích mask/hộp: **med 0,62** · p05 0,24 · p95 0,90 (hợp lý: vật thật thường chiếm
60–90 % cái hộp người kéo).

## ⚠️ Vấn đề & cách xử lý

**1. Đây KHÔNG phải GT — và đã kiểm bằng mắt để nói rõ mức độ.** Xem 3 mask đầu tiên (ảnh chồng mask
tím + hộp xanh):

| ca | nhận xét |
|---|---|
| `demoip_1104-212328#4` | **rất tốt**: mask ôm đúng điện thoại, khớp hộp; bị cờ `cham_bien` vì **hộp người vẽ cắt mất phần dưới của vật** ⇒ SAM nới tới mép khung |
| `demoip_1104-212328#6` | **kém**: mask **ăn cả bàn tay và vùng nền hoa văn** bên phải — và **QC KHÔNG bắt** (tỉ lệ 0,457, không chạm biên) |
| `demoip_1104-212328#13` | mask lệch một phần, tràn ra ngoài hộp |

⇒ **QC tự động chỉ là lưới thô**: nó bắt được ca "hộp cắt vật" và "mask tí xíu", **không** bắt được ca
"ăn tay/nền". Vì vậy **cấm** dùng `data/gt_pseudo` làm GT để tuyên bố chất lượng model. Dùng đúng cách:
**bản nháp để người sửa** (sửa mask nhanh hơn vẽ từ đầu rất nhiều) hoặc **self-training có lọc tay**.

**2. `cham_bien` 337 ca không phải 337 lỗi.** Với ca #4 nó nghĩa là *hộp người vẽ quá sát*. Nên đọc cờ
này là "cần xem lại hộp hoặc mask", không phải "mask sai".

**3. `image_size 512` là đánh đổi có ý thức.** 320 nhanh hơn (186 ms/mask) nhưng biên mask thô hơn;
1024 chậm 5,5 s/mask ⇒ 1 251 ô = ~2 giờ. Đo được 518 ms/mask ở 512 nên chọn 512. Muốn nhanh hơn nữa
phải chạy trên GPU (Colab T4 ~50 ms/frame đã đo 22-11).

**4. Mask không được commit**: `data/gt_pseudo/**` bị `data/*` chặn (kiểm bằng `git check-ignore`),
chỉ `data/gt_pseudo_metrics.json` vào repo. Từ clone sạch phải chạy lại script (~13 phút CPU).

## ➡️ Next steps

1. **Sửa tay 369 mask "nghi" trước** (hoặc ít nhất 38 ca `nho` + các ca xem mắt thấy ăn nền) ⇒ có ~880
   mask "tạm tin". Cần một UI sửa mask (chưa có) — hiện chỉ sửa được bằng công cụ ngoài.
2. Dùng 880 mask đó để **chấm mIoU trên nhiều frame hơn** (hiện `docs/gt/b1` chỉ 12 frame) — nhưng phải
   ghi rõ *pseudo-GT*, và **không** so với số mIoU trên GT người tô.
3. Chỉ khi có ≥ vài trăm mask **đã sửa tay** mới bàn tới fine-tune (và cần thêm người dán thứ 2).

## 📚 Tài liệu tham khảo

- `docs/task/26-11-2026-verifier-dataset-va-baseline.md` (cùng ngày: nhãn chưa đủ train lại vì thiếu mask)
- `scripts/build_verifier_dataset.py` (dùng chung `doc_nhan_hieu_luc`), `tools/label_ui.py`
  (`chi_so_khung`, `_mo_video`, `_CAP_LOCK`)
- AGENTS §6: "muốn nói bám ĐÚNG thì phải chấm mIoU mask vs GT"; "GT ≡ pixel màu ô trên ảnh tổng hợp là cận trên"
