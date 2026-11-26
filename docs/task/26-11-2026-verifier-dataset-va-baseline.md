# Ngày 26-11-2026 — Bước 1: dataset + baseline cho "bộ kiểm bám đúng" (verifier)

> **Kết luận một dòng:** nhãn hiện có **chưa đủ train lại** SAM 2 (thiếu mask pixel); nhưng đủ để thử
> một verifier — và khi đo **đúng cách** (bỏ hẳn một NGÀY khỏi train) thì verifier **chỉ hơn mốc ngố
> 0,065** (AUC **0,585** so với ngố **0,520** trên **cùng 3 ngày**), tức **chưa chứng minh được** là tổng
> quát. Con số 0,83 chỉ đúng khi val nằm **cùng ngày/cùng cảnh**.

## 🎯 Mục tiêu

Trả lời bằng số: **nhãn người dán có đủ để dạy một bộ kiểm "ô hệ đang vẽ có đúng là vật không"?**

Đây là bước 1 của lộ trình sau khi đã đo rằng train lại SAM 2 thì chưa đủ dữ liệu (thiếu mask pixel,
GT mask lớn nhất trong repo 36 frame, chỉ 1 người dán).

Lý do thử hướng verifier: AGENTS §6 ghi, đo 21-11, `mask-cos` của vùng SAI là **0,752–0,989** nằm trong
dải ca đúng (0,905) ⇒ **không tồn tại ngưỡng cos nào tách được** ⇒ phải học từ dữ liệu.

## 📥 Input

- `data/nhan/*.jsonl` — 32 file phiên, **14 261 nhãn**, **1 490 ô GT** (người dán: `binh`).
- `data/<phiên>_metrics.csv` (tâm + cỡ ô của hệ mỗi bước) + video gốc.
- Máy này **không có GPU** (`torch 2.14.1+cpu`), 8 lõi; **không có sklearn** ⇒ AUC tự viết.

## 🔨 Công việc đã thực hiện

1. **`scripts/build_verifier_dataset.py`** — dựng dataset ảnh cắt 64×64 từ nhãn:
   - `pos_sys` = ô **hệ** đang vẽ ở bước nhãn `dung` → nhãn **1**
   - `neg_sys` = ô **hệ** đang vẽ ở bước nhãn `sai` (vùng SAI) → nhãn **0**
   - `pos_gt`  = ô **người** vẽ (`bbox_dung`) → nhãn **1** *(chống mẹo "vùng trơn = sai")*
   - Bỏ `khong_co_vat`/`bo_qua`; `mat_dau` không có ô của hệ nên chỉ sinh `pos_gt` — **dữ liệu hiện tại
     0/1 327 bước `mat_dau` có ô GT** ⇒ nhánh đó chưa từng chạy.
   - Ánh xạ bước→frame dùng **chung** `tools.label_ui.chi_so_khung`, **kèm** kiểm seek (đọc lại
     `CAP_PROP_POS_FRAMES`; `set()` có thể trả True mà vẫn đứng ở keyframe gần nhất).
   - Cắt ảnh **tuần tự dưới `L._CAP_LOCK`** (OpenCV/FFmpeg không thread-safe).
   - **Chia train/val theo NGÀY** (`--chia-theo ngay`, mặc định) hoặc theo phiên (`--chia-theo phien`).
   - **Dấu vân tay cache** = `CROP` + `margin` + `ti_le_val` + cách chia + `mtime_ns/size` của mọi
     CSV/video ⇒ đổi bất cứ thứ gì là **cắt lại**, không phục vụ ảnh cũ với tham số mới.
2. **`scripts/train_verifier.py`** — CNN nhỏ (4 khối conv + GAP, ~60 k tham số), `pos_weight` cho mất
   cân bằng, 3 seed:
   - AUC tự viết (Mann–Whitney, hoà = hạng trung bình); **NaN ⇒ NaN** (không ra "số trông hợp lệ").
   - CI95 bootstrap **theo NHÓM** (phiên/ngày), không theo dòng.
   - **Bộ phân loại NGỐ** (chỉ độ lệch chuẩn pixel) làm mốc.
   - **`--loao`**: leave-one-**day**-out / leave-one-**session**-out — mỗi lượt bỏ hẳn một nhóm, train
     trên phần còn lại, chấm trên đúng nhóm đó.
   - **Cổng `kiem_tra_so()` / `kiem_tra_so_loao()`**: không có số (NaN / val 0 âm / không nhóm nào
     chấm được) thì **không ghi artifact** + exit 1 — áp cho **cả** chế độ chia-split **và** `--loao`.
3. **`tests/test_verifier_dataset.py`** — **30 test**: AUC (hoàn hảo/đảo/hoà/thiếu lớp/NaN), CI theo
   nhóm phải **rộng hơn** theo dòng, nhãn **dòng cuối thắng**, CSV cũ thiếu `bbox_w` ⇒ không bịa ô,
   **ảnh crop ứng đúng frame** (fixture đổi màu theo frame — *dung sai đúng 1 bước màu, nên lệch 1 frame
   vẫn XANH, trùng với ngưỡng `> 1` của phép kiểm seek: test này bắt được lệch ≥ 2 frame, không phải
   mọi lệch*), đổi `--margin`/`--ti-le-val`/`--chia-theo` ⇒ cắt lại, phiên 0 mẫu, 2 người dán,
   `eval()` vs `train()` khác nhau và raise khi không tất định, `chay_loao` bỏ hẳn nhóm, cổng LOAO,
   `ci95 = None` khi 1 nhóm.

## 📤 Output / Kết quả

**Dataset** (`data/verifier_metrics.json`, `git_dirty_code = false` sau khi commit script):

| | số |
|---|---|
| mẫu | **3 230** (cắt lỗi 0) |
| `pos_sys` / `pos_gt` / `neg_sys` | 1 566 / 1 250 / **414** |
| phiên dùng được | 31 |

**Ba tầng đo — chỉ tầng 3 là số dùng được cho tuyên bố:**

| # | cách chia | AUC | nghĩa |
|---|---|---|---|
| 1 | train/val theo **phiên** (val 6 phiên, 57 âm) | **0,7596 ± 0,0528** (gộp) · **0,827 ± 0,021** (trong phiên — nhưng chỉ **2/6** phiên có đủ âm để chấm, **cả hai thuộc ngày 1124**) | **CẬN TRÊN** — 6/6 phiên val có phiên **cùng ngày** trong train (cùng phòng, cùng vật, cùng ánh sáng) |
| 2 | leave-one-**session**-out (10 phiên, 30 lần chạy) | **0,7391** (min **0,4198**, max 0,8932) | phiên mới, **cùng ngày** ⇒ vẫn lạc quan |
| 3 | **leave-one-DAY-out** (3 ngày có âm, 9 lần chạy) | **0,5846** (min 0,4198 · max 0,7432 **trên ngày×seed**, không phải CI) | **số dùng được**: *ngày* chưa thấy (khả năng cao vẫn **cùng phòng** ⇒ còn là cận trên cho "cảnh mới") |

Chi tiết tầng 3 — mỗi ngày kèm **mốc ngố đo trên CHÍNH fold đó** (0,5846 là **trung bình CỘNG theo
ngày**; trọng số theo số mẫu sẽ là 0,6105 vì `1124` chiếm 1 134/2 406):

| ngày | âm/dương | verifier | **ngố (cùng fold)** | chênh |
|---|---|---|---|---|
| `1123` | 65 / 429 | **0,4958** | 0,3732 | +0,123 |
| `1124` | 208 / 926 | 0,6890 | 0,6745 | **+0,014** |
| `1125` | 141 / 637 | 0,5688 | 0,5129 | +0,056 |
| **trung bình** | | **0,5846** | **0,5202** | **+0,065** |

⇒ Trên `1124` (ngày nhiều mẫu nhất) verifier **không tách được** khỏi mốc ngố. Train AUC 0,95–0,98 ⇒
**overfit nặng**. Mốc ngố **0,5194** ở tầng 1 được đo trên tập val của cách chia-theo-phiên — **không**
đem so chéo với tầng 3 (AGENTS §6).

**Các khoản BỊ BỎ** (`data/verifier_metrics.json → bo_qua`):

| lý do | số |
|---|---|
| `dung-khong-co-o-he` (CSV trước 21-11 không có `bbox_w/h`) | **1 156** |
| `sai-khong-co-o-he` | **859** |
| `mat_dau-khong-co-GT` | **1 327** |
| `khong_co_vat` | 643 |

Phiên ra 0 mẫu: `demoip_1120-224057` (`phien_0_mau`). `phien_nhieu_nguoi_dan` = rỗng.

## ⚠️ Vấn đề & cách xử lý

1. **Rò rỉ CẢNH là lỗi lớn nhất của phép đo đầu** (review độc lập vòng 2 bắt): chia theo phiên không
   cách ly phòng/vật/ánh sáng. Đã sửa bằng **leave-one-day-out**; chính vì thế con số đúng là **0,585**,
   không phải 0,76–0,88. **Cấm trích 0,83 mà không nói "cùng ngày".**
2. **Chỉ 3/9 ngày có mẫu âm** (1123 · 1124 · 1125) ⇒ chia ngẫu nhiên theo ngày cho val **0 âm** (đã thử:
   cổng chặn đúng, AUC = NaN). LOAO trên 3 ngày là cách duy nhất đo được ⇒ **n = 3 ngày**, chưa đủ để
   tuyên bố chắc.
3. **46/78 CSV trong `data/` sinh trước 21-11 không có `bbox_w/bbox_h`** ⇒ không dựng lại được ô của hệ
   ⇒ mất 1 156 bước `dung` + 859 bước `sai`. **Không bịa ô.**
4. **`±` trong artifact là std GIỮA CÁC SEED**, không phải CI của ước lượng.
5. **Bootstrap bỏ ~9 % resample** (`so_lan_hop_le` 898–919/1000: resample không rút được phiên có âm)
   ⇒ CI95 **hơi hẹp** so với thực. Ghi trong artifact (`bootstrap.ghi_chu`).
6. **20/401 cặp (phiên, bước) có ô hệ ≈ ô người (IoU > 0,7)** ⇒ cùng pixel mang cả nhãn 0 và 1
   (≈**1,2 %** mẫu). Nhiễu nhãn nhỏ nhưng có thật.
7. **Crop 64×64 xoá thông tin cỡ ô**: đã kiểm confound "blockiness" (trung vị cạnh ngắn nguồn 125–150 px,
   chỉ 5/3 230 mẫu phải phóng > 2×) ⇒ **không** phải lỗi.
8. **Chưa đưa vào pipeline** — có chủ ý: chạm `IdentityWatch`/hiển thị là vùng đã 3 lần sinh P0/P1 trong
   2 tuần (AGENTS §6), và việc > 4 h ⇒ phải lập plan 3 ý kiến (AGENTS §9.2).

## 🧭 Review độc lập (bắt buộc §9.1) — 2 vòng, P0 = 0 cả hai

**Vòng 1** (taskforce `advisor`): 3 P1 + 4 P2 + 4 P3. Đã sửa: `auc()` trả NaN khi điểm có NaN (từng ra
0,75 "trông hợp lệ"); **cổng `kiem_tra_so`** (val 1 lớp từng vẫn ghi artifact "thành công"); cache dùng
vân tay; đếm khoản bị bỏ; giữ AUC theo phiên cho mọi seed; `assert` tính tất định của `eval()`; sửa log
(rev/`dirty_code`, 33→32 phiên, 15→26 test, đánh số trùng).

**Vòng 2** (`reviewer`): P0 = 0, nhưng bắt đúng **2 P1**: (a) log dẫn `git_rev`/`git_dirty_code` **sai**
so với artifact; (b) **rò rỉ cảnh** (mục ⚠️1) — không nêu trong log. P2/P3 đã sửa: `ti_le_val` +
`chia_theo` vào vân tay; port kiểm seek; per-session có CI; `so_anh_thieu`; 3 test giả (grep-source,
`>= 1`, split 2 phiên 50 % xanh vô nghĩa) thay bằng test hành vi; bỏ import rác.

**Vòng 3** (`advisor`, sau khi sửa vòng 2): **P0 = 0** nhưng **4 P1 mới do chính các sửa sinh ra**:
(a) `--loao --nhom-theo ngay` lấy nhóm từ `m["nhom"]` do lúc **dựng** quyết định ⇒ manifest dựng
`--chia-theo phien` thì nó lặng lẽ chạy theo PHIÊN mà artifact vẫn ghi `ngay`; (b) `--loao` **không** đi
qua cổng ⇒ "không nhóm nào chấm được" vẫn ghi artifact + exit 0; (c) chỉ 1 nhóm ⇒ `ci95 = [auc, auc]`
(rộng 0) bị đọc thành "rất chính xác"; (d) so 0,5846 với mốc ngố **của tập val khác** (so chéo artifact).
Đã sửa cả bốn: `khoa()` dùng lại **một** `nhom_cua()`; thêm `kiem_tra_so_loao()`; `ci95 = None` khi
`so_nhom < 2`; `ngong` đo **trên chính fold** và ghi từng ngày — chính vì (d) mà câu kết luận đổi thành
"**chỉ hơn ngố 0,065 ⇒ chưa chứng minh được**" (mạnh hơn, không yếu đi).

**Cách kiểm các sửa đó** (chạy đúng 3 phép kiểm mà reviewer vòng 3 đề nghị, vì nó chưa chạy được):
manifest dựng `--chia-theo phien` + `--loao --nhom-theo ngay` ⇒ `nhom_cham_duoc == ["1123","1124","1125"]`;
`--loao --min-am-nhom 99999` ⇒ **exit 1, không có artifact**; `auc_theo_cum` với **1 nhóm ⇒ `ci95 = None`**.
**Chưa có vòng review thứ 4** trên chính các sửa này: phiên `reviewer` kẹt (401 lặp của provider, 25 lượt
không tiến triển) và taskforce `advisor` tự đóng sau khi trả kết quả ⇒ ghi lại đây để người sau biết
*phần sửa vòng 3 được kiểm bằng test + 3 phép kiểm trên, không bằng một vòng review độc lập mới*.

## ➡️ Next steps

- **Ưu tiên đổi hẳn**: dán ô ở bước SAI trên **NHIỀU NGÀY KHÁC NHAU** (hiện chỉ 3 ngày có âm ⇒ LOAO chỉ
  có n = 3). Thêm ô trong cùng một ngày làm fold đó **chắc hơn** nhưng **không** thêm ngày nào — mà
  chính số ngày mới là thứ đang thiếu để tuyên bố (chưa đo được điều này).
- Nếu muốn dùng verifier **trong một phiên** (hiệu chỉnh tại chỗ bằng chính các bước đầu của phiên) thì
  đây là bài toán khác — cần đo riêng (LOO-session cho 0,74, chưa phải "tổng quát").
- Muốn nói "verifier tốt hơn ngưỡng cos": phải chấm riêng nhóm "bám sang nền cùng tông" (cần cột gắn
  nhãn **ca** cho từng bước, chưa có) và trên ≥ 5 ngày.
- Chỉ sau khi LODO ≥ 0,75 ổn định qua ≥ 2 lần dựng dataset mới lập **plan 3 ý kiến** (§9.2) để nối vào
  cổng nghi.

## 🧷 Bẫy khi grep artifact

- Chuỗi `0.5846` xuất hiện **hai lần** trong `data/verifier_loao_ngay_metrics.json`: `auc_trung_binh`
  (con số headline) và **cận TRÊN của `ci95` ngày 1125**. Đừng `grep 0.5846` rồi kết luận.
- `nhom_bo_qua` liệt kê **6 ngày không chấm được** (`1029·1101·1104·1105·1114·1121`, đều `0 mẫu âm`) —
  trước đây artifact chỉ có nhóm "sống", nên không ai biết vì sao n = 3.
- `min/max` trong `theo_ngay` là **min/max trên ngày × seed**, **không** phải khoảng tin cậy; `ci95`
  của một ngày chỉ có khi ngày đó có ≥ 2 phiên (1123 chỉ 1 phiên ⇒ `ci95 = None`).
- Ngày `1123` chỉ có **1 phiên** ⇒ fold LODO-1123 **trùng khít** fold LOO-phiên-1123 (cùng bộ ba
  0,4406/0,4198/0,627) ⇒ tầng 2 và tầng 3 **không** phải hai bằng chứng độc lập.
- 3 ngày 1123/1124/1125 là **3 ngày liền, cùng phòng** ⇒ 3 điểm tương quan, n = 3.

## 🧷 Ghi chú tái lập

- `data/verifier/**` (3 230 JPEG) **bị `.gitignore`** ⇒ con số tái lập được **trên máy có video gốc**;
  từ clone sạch phải chạy `scripts/build_verifier_dataset.py` (32–79 s) trước.
- Manifest dựng bằng `--chia-theo phien` (dùng để chứng minh "6/6 phiên val có phiên cùng ngày trong
  train") **không còn trên đĩa**; luận điểm đó dẫn từ review vòng 2 và tái kiểm được bằng
  `nhom_cua(phien, "ngay")` trên danh sách phiên.
- `--chia-theo ngay` **ngẫu nhiên** thì val có thể **0 âm** (chỉ 3/9 ngày có âm) ⇒ đừng dùng cách đó để
  "chia cho nhanh"; phải LOAO.

## 📚 Tài liệu tham khảo

- AGENTS §6 (mask-cos 0,752–0,989 và "không tồn tại θ tách được"; đã bác re-ID, đổi checkpoint, `image_size`)
- `scripts/build_verifier_dataset.py`, `scripts/train_verifier.py`, `tests/test_verifier_dataset.py`
- `docs/task/26-11-2026-phim-e-ve-o.md` (cùng ngày: phím vẽ ô `E`)
