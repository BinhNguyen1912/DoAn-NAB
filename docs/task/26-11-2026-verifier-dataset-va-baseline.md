# Ngày 26-11-2026 — Bước 1: dataset + baseline cho "bộ kiểm bám đúng" (verifier)

## 🎯 Mục tiêu

Trả lời bằng số, không bằng niềm tin: **nhãn người dán hiện có có đủ để dạy một bộ kiểm
"ô hệ đang vẽ có đúng là vật không" hay không?** Đây là bước 1 trong lộ trình 4 bước đã trình bày
sau khi đo rằng *train lại SAM 2 thì chưa đủ dữ liệu* (thiếu mask pixel, thiếu người dán thứ 2).

Lý do chọn hướng verifier: AGENTS §6 ghi, đo ngày 21-11, `mask-cos` của vùng SAI là **0,752–0,989**
nằm trong dải ca đúng (0,905) ⇒ **không tồn tại ngưỡng cos nào tách được**, phải **học** từ dữ liệu.

## 📥 Input

- `data/nhan/*.jsonl` — 33 phiên, 14 261 nhãn, 1 490 ô GT (người dán: `binh`).
- `data/<phiên>_metrics.csv` (tâm + cỡ ô của hệ mỗi bước) + video gốc.
- Máy này **không có GPU** (`torch 2.14.1+cpu`), 8 lõi; **không có sklearn** ⇒ AUC tự viết.

## 🔨 Công việc đã thực hiện

1. **`scripts/build_verifier_dataset.py`** — dựng dataset ảnh cắt 64×64 từ nhãn:
   - `pos_sys` = ô **hệ** đang vẽ ở bước nhãn `dung` → nhãn **1**
   - `neg_sys` = ô **hệ** đang vẽ ở bước nhãn `sai` (vùng SAI) → nhãn **0**
   - `pos_gt`  = ô **người** vẽ (`bbox_dung`) ở bất kỳ bước nào có nó → nhãn **1**
     *(loại này chống mẹo "tường trơn = sai": buộc mô hình coi vật thật là dương **kể cả** trong phiên
     hệ đang bám sai)*
   - Bỏ `khong_co_vat`/`bo_qua`; `mat_dau` không có ô của hệ nên chỉ sinh `pos_gt` nếu có `bbox_dung`.
   - Ánh xạ bước→frame dùng **chung** `tools.label_ui.chi_so_khung` (không viết lại phép bù — bài học
     "hai định nghĩa" trong AGENTS §6).
   - Cắt ảnh **tuần tự dưới `L._CAP_LOCK`** (OpenCV/FFmpeg không thread-safe — đã từng abort tiến trình).
   - Tách **train/val theo PHIÊN** bằng `sha256(tên)`: tất định, cùng một phiên không nằm cả hai phía.
2. **`scripts/train_verifier.py`** — CNN nhỏ (4 khối conv + GAP, ~60 k tham số), `BCEWithLogitsLoss`
   có `pos_weight` (mất cân bằng ~6:1), 12 epoch, **3 seed** (`--seeds 0,1,2`) để có `mean ± std`.
   - AUC tự viết (Mann–Whitney, hoà ⇒ hạng trung bình) + **CI95 bootstrap theo PHIÊN**.
   - Thêm **bộ phân loại NGỐ** (chỉ dùng độ lệch chuẩn pixel) làm mốc: nếu AUC của CNN không vượt rõ
     mốc đó thì nó chỉ học "vùng trơn = sai".
   - Kiểm `model.eval()` tất định: chấm **cùng một ảnh hai lần** phải ra cùng số.
3. **`tests/test_verifier_dataset.py`** — 15 test: AUC (tách hoàn hảo/đảo/hoà/thiếu lớp), CI tất định,
   `noi_o` kẹp biên + ô suy biến, **nhãn dòng CUỐI thắng**, CSV cũ không có `bbox_w` ⇒ không bịa ô,
   tách split theo phiên, end-to-end trên fixture 2 phiên (1 có ô của hệ, 1 không).

## 📤 Output / Kết quả

**Dataset** (`data/verifier_metrics.json`, `git_dirty_code = true` tại lúc dựng vì script chưa commit):

| | số |
|---|---|
| mẫu | **3 230** (cắt lỗi 0) |
| `pos_sys` / `pos_gt` / `neg_sys` | 1 566 / 1 250 / **414** |
| phiên dùng được | 31 |
| train / val | 2 599 / 631 |
| **val: âm / dương** | **57 / 574** |
| val: số phiên | **6** |

**Baseline** (`data/verifier_baseline_metrics.json`, 3 seed, `torch` CPU, 107 s tổng):

| seed | val AUC | CI95 (bootstrap theo phiên) | train AUC |
|---|---|---|---|
| 0 | 0,7890 | [0,7218, 0,8543] | 0,9487 |
| 1 | 0,6987 | [0,5655, 0,9450] | 0,9797 |
| 2 | 0,7912 | [0,7332, 0,8783] | 0,9676 |
| **trung bình** | **0,7596 ± 0,0528** | | 0,965 (TB) |
| **NGỐ (độ lệch chuẩn pixel)** | **0,5194** | [0,381, 0,590] | — |

Lịch epoch của seed 0 (dao động mạnh, không đơn điệu): 0,733 · 0,693 · 0,658 · 0,682 · 0,625 ·
0,772 · 0,723 · 0,756 · 0,634 · 0,731 · 0,610 · **0,789**.

**AUC theo TỪNG PHIÊN val** (âm và dương cùng nền ⇒ không trộn miền; đây là con số nên đọc):

| phiên | âm | dương | AUC |
|---|---|---|---|
| `demoip_1124-141352` | 19 | 68 | **0,8839** |
| `demoip_1124-193026` | 38 | 280 | **0,8111** |
| `fast_1029-210004` | **0** | 26 | `null` (không chấm được) |
| `fast_1029-212632` | **0** | 134 | `null` |
| `fast_1101-153223` | **0** | 13 | `null` |
| `fast_1101-154036` | **0** | 53 | `null` |

Trung bình trên **2 phiên chấm được**: **0.8475**
(min 0.8111). **Chỉ 2/6 phiên val có âm** ⇒ mọi trung bình đều tựa vào 2 phiên.

## ⚠️ Vấn đề & cách xử lý

1. **`46/78` CSV trong `data/` không có cột `bbox_w/bbox_h`** (chỉ được thêm vào `CSV_HEADER` từ 21-11)
   ⇒ không dựng lại được ô của hệ ⇒ các phiên đó **chỉ sinh `pos_gt`**, và đó là lý do `neg_sys` chỉ
   còn **414**. **Không bịa ô từ trung vị phiên khác** — bịa là làm hỏng cả thử nghiệm.
2. **Mất cân bằng nặng** 2 816 dương / 414 âm (6,8 : 1); val chỉ **57 âm**. CI vì thế rất rộng
   (seed 1: [0,566, 0,945]).
3. **Overfit rõ**: train AUC 0,95–0,98 vs val 0,70–0,79. Muốn giảm phải có **thêm âm** (chính là
   "vẽ ô ở bước SAI trên các phiên có CSV mới") — việc này người dùng làm tiếp được, không cần GPU.
4. **Âm DỒN vào 2 phiên val** (`1124-141352` 19 · `1124-193026` 38), 4 phiên val còn lại **0 âm**
   ⇒ AUC gộp (0,7596) trộn nền của 6 phiên dương với âm của 2 phiên, có thể bị "học nền" chứ không
   học "vùng bám nhầm". Vì thế artifact in thêm `val_auc_theo_phien` + `val_am_theo_phien`; số
   **0,8475** (TB 2 phiên) là số nên đọc, số gộp chỉ để so mốc ngố.
5. **Đọc số cho đúng** (AGENTS §6): `n = 3 seed` nhưng **chỉ 1 lần dựng dataset**; đây **chưa** phải
   tuyên bố "verifier dùng được". Điều đo được **chắc chắn** là: *cả 3 seed đều ≥ 0,699, đều vượt mốc
   ngố 0,519* ⇒ **có tín hiệu**, không phải 0,5 (đoán mò). Điều **không** được nói: "đã chặn được ca
   bám sang tường" — chưa đo trên đúng nhóm ca đó.
5. **Chưa đưa vào pipeline** — đây là quyết định có chủ ý: chạm `IdentityWatch`/hiển thị là vùng đã 3
   lần sinh P0/P1 trong 2 tuần (AGENTS §6), và việc > 4 h ⇒ phải lập plan 3 ý kiến (AGENTS §9.2)
   trước khi nối.

## ➡️ Next steps

- **Rẻ nhất, giá trị cao nhất**: dán thêm ô ở các bước **SAI** trên phiên có CSV mới (`demoip_1120+`,
  `1123`, `1124`, `1125`) ⇒ mỗi ô là 1 mẫu `neg_sys`. Cần cỡ **≥ 1 000 âm** để CI hẹp lại.
- Muốn **tuyên bố** verifier tốt hơn ngưỡng cos: chấm riêng trên nhóm "bám sang nền cùng tông"
  (cần gắn nhãn **ca** cho từng bước, chưa có cột này).
- Sau khi có ≥ 1 000 âm và kết quả ổn định ≥ 2 lần dựng dataset: lập **plan 3 ý kiến** (§9.2) để nối
  verifier vào cổng nghi — **không** tự ý nối trước.

## 📚 Tài liệu tham khảo

- AGENTS §6 (mask-cos 0,752–0,989; "không tồn tại θ tách được"; đã bác re-ID/đổi checkpoint/image_size)
- `docs/task/26-11-2026-phim-e-ve-o.md` (cùng ngày: phím vẽ ô E)
- `scripts/build_verifier_dataset.py`, `scripts/train_verifier.py`, `tests/test_verifier_dataset.py`
