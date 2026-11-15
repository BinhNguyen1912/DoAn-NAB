# Ngày 15-11-2026 — Chấm mIoU trên video THẬT: GT hộp bao + `mask_ngoai_gt` + cổng "GT phải khai dạng"

> Nối tiếp `docs/task/15-11-2026-status-json-echo-cau-hinh-hieu-luc.md` (việc `status.json` echo cấu
> hình). Đây là việc **#1** trong danh sách "nên làm gì tiếp" của phiên đó: *mIoU trên video THẬT* —
> thứ duy nhất trả lời được câu "hệ thống bám có ĐÚNG không".

## 🎯 Mục tiêu
- Có **một con số đo trên video thật** (không phải fixture tổng hợp), ghi rõ nó đo **cái gì**.
- Không bao giờ để con số đó bị trích thành "mIoU phân đoạn" khi GT không phải silhouette.
- Sửa lỗi prompt box: mask của model phải bám **chai**, không phải bàn tay/thân người.

## 📥 Input
- `AGENTS.md` §6 (bẫy `0/None`, "drift ≠ độ chính xác", artifact phải có provenance), §9.1 (review).
- `docs/thuoc-do-bam-dung.md` (quy trình chấm), `docs/demo-clip-va-o-chon.md` (ô chai CHUẨN).
- `data/binh1.mp4` (720×1280, 333 frame, chai xịt tím), checkpoint `sam2.1_hiera_tiny.pt`, CPU.
- GT do người dùng tô 12 frame (frame `2,12,22,32,42,52,62,72,82,92,100,106`).

## 🔨 Công việc đã thực hiện

### 1. Phát hiện 2 lỗi của chính dụng cụ đo (trước khi có số)
- **Prompt box sai**: tôi đã dựng mask bằng `288,287,431,734` — hoá ra đây là ô ghi theo dạng
  **`x1,y1,x2,y2`** (`288,287,719,1021` = cùng chỗ ô chai) đem vào `--bbox` (`x,y,w,h`) ⇒ hộp
  **431×734**, phủ chai + tay + thân người ⇒ mask model **168k px** (đúng cái bẫy `(x,y,w,h) ≠
  (x1,y1,x2,y2)` của AGENTS §6). Sinh lại với ô CHUẨN **`300,275,150,410`** ⇒ mask 23k–58k px.
- **Bộ GT đầu tiên không dùng được**: người dùng vẽ **khung chữ nhật RỖNG (viền ~10 px)** và khung
  **lệch ~80 px lên trên**, cắt mất phần nhãn ⇒ mỗi file chỉ 10,5k px (lấp 15–20 % khung của nó),
  IoU 0,01–0,08 — **đo sai vùng**, không phải model kém. Bằng chứng: ảnh overlay + số px + lấp đầy.

### 2. Bộ GT thay thế: **hộp bao** dựng từ ngưỡng màu (không dùng model)
- `docs/gt/binh1_hopbao/`: 12 frame, hộp = nhãn tím (HSV) + phần trắng phía trên; **người soi 12/12
  frame** bằng contact sheet, **sửa tay frame 62** (chai nghiêng, ngưỡng màu bắt dính nền trái).
- `index.json` khai đủ: `dang_gt = hop_bao`, `phuong_phap_gt`, `nguon_gt` (máy đề xuất + người soi),
  `nguoi_gan` (người thật), `frame_hw`, `hop_bao_xywh` từng frame.
- Bộ cũ `docs/gt/binh1_tay/` **bị vô hiệu hoá**: xoá 12 file `gt_*.png` + `dung_duoc: false` + lý do
  ⇒ `kiem_index` báo **lỗi CHẶN** (thiếu file GT), không thể chấm nhầm.

### 3. Cổng mới: GT phải khai **DẠNG** (`dang_gt`)
- `score_miou`: `dang_gt` + `phuong_phap_gt` → `meta` của artifact; `hop_bao` ⇒ **cảnh báo mềm** nêu rõ
  "KHÔNG phải mIoU phân đoạn, chặn trên ~0,75–0,85"; thiếu khoá ⇒ cảnh báo "không biết dạng GT";
  cảnh báo mềm ⇒ **exit 1** (trước đó code trả 0 dù hợp đồng đã ghi là 1 — P1 review 14-11 bị bỏ sót).
- `label` **không** tự khai hộ nữa: thêm `--dang-gt {silhouette,hop_bao}` + `--phuong-phap-gt`
  (bản trước ghi cứng `silhouette` ⇒ bộ GT vẽ bằng hộp **lọt cổng với exit 0**).
- `make_synthetic_gt_clip` khai `silhouette` + phương pháp.

### 4. Chỉ số phụ **`mask_ngoai_gt`** (phần mask tràn ra ngoài GT)
Lý do: với GT hộp bao, `mIoU` bị **chặn trên** ~0,75–0,85 (hộp > vật) nên không nói được model có
phủ quá tay không. `1 − |pred ∩ gt| / |pred|` đo đúng cái đó và **không** bị chặn trên bởi GT hộp.
Kèm `mask_ngoai_gt_n` (mẫu số **khác** `n_cham` khi có frame model trả mask rỗng) và cảnh báo khi lệch.

## 📤 Output / Kết quả

**`data/miou_binh1_hopbao_2026-11-15_metrics.json`** — `git_rev 17e1c85`, `git_dirty_code false`,
`meta.dang_gt = hop_bao`, `meta.mask_manifest.bbox_xywh = [300,275,150,410]`,
`image_size_hieu_luc = 192`, `vos_every 1`:

| chỉ số | giá trị |
|---|---|
| `mIoU` = **IoU(mask, HỘP BAO)** | **0,6464** (n = 12; min 0,469 @f12 · max 0,774 @f92 · std 0,092) |
| `mask_ngoai_gt_mean` | **3,9 %** (n = 12) |
| `mask_ngoai_gt_max` | **29,4 %** @ **frame 62** (frame GT sửa tay — đọc kèm, đừng quy hết cho model) |
| coverage | 12/12 frame chấm được |

Bảng từng frame (IoU): f2 0,570 · f12 0,469 · f22 0,595 · f32 0,632 · f42 0,696 · f52 0,654 ·
f62 0,536 · f72 0,696 · f82 0,645 · f92 0,774 · f100 0,750 · f106 0,740.

**Cách đọc (bắt buộc):** đây là IoU với **hộp bao**, KHÔNG phải mIoU phân đoạn; chặn trên ~0,75–0,85;
**sai số của bộ dựng hộp CHƯA ĐO**; n = 12 frame của **một** clip, `image_size 192`. Đã ghi vào
`docs/so-lieu-bao-cao.md` (cột "cấm trích"), `docs/thuoc-do-bam-dung.md` §1.1 + §4, và
`docs/gt/binh1_hopbao/README.md`.

**Kiểm tra:** `./run lint` xanh · `./run test` **1193 passed, 5 deselected** (thêm 11 test cho
`dang_gt`/`label`/`mask_ngoai_gt`).

**File thay đổi:** `scripts/score_miou.py`, `scripts/make_synthetic_gt_clip.py`,
`scripts/so_lieu_bao_cao.py`, `docs/gt/binh1_hopbao/*` (mới), `docs/gt/binh1_tay/*` (vô hiệu hoá),
`docs/thuoc-do-bam-dung.md`, `docs/demo-clip-va-o-chon.md` (§1.1 đính chính ô),
`docs/so-lieu-bao-cao.md`, `data/masks_binh1_192_2026-11-15/*`,
`data/miou_binh1_hopbao_2026-11-15_metrics.json`, `tests/test_score_miou.py`.

## 🐞 Vấn đề gặp phải & cách xử lý
- **"Người dùng tô xong" ≠ "GT dùng được"**: file có mặt, `--check-index` hợp lệ (vì mọi file đều giải
  mã được), nhưng nội dung là **viền rỗng + lệch**. Bài học: phải **kiểm bằng ẢNH + số** (diện tích,
  độ lấp đầy, toạ độ khung) trước khi chấm; đã ghim bằng cảnh báo "GT toàn đen" (không bắt được viền
  rỗng) ⇒ cần thêm kiểm `hop_bao_xywh` ↔ `gt.sum()` (ticket #30).
- **Cổng kiểm kích thước của chính repo bắt lỗi của tôi**: tôi ghi `frame_hw = [720,1280]` (W,H) ⇒
  `kiem_index` TỪ CHỐI 12/12 frame (`shape = (1280,720)`). Sửa thành `[1280,720]`. Đây đúng là lý do
  phải có cổng: `frame_hw` trước đây thiếu nên nhánh kiểm **chưa bao giờ chạy**.
- **`git_dirty_code = true`** ở lần chấm đầu vì index GT đang sửa dở ⇒ test
  `test_artifact_trong_bang_phai_co_provenance` **bắt đúng**; chấm lại trên cây sạch (`17e1c85`).
- **Commit message bị bash "ăn" dấu backtick** (`` `index.json` `` thành rỗng) — phải `--amend` bằng
  file message. Bài học: message có backtick thì dùng `git commit -F`.

### Review độc lập (§9.1) — 2 vòng, tất cả đã đóng
**Kết luận: KHÔNG có P0**; **2 P1 đã vá ngay**; con số 0,6464 tự nó trung thực (nhãn hộp bao có ở
`meta`, `canh_bao_gt`, REGISTRY, doc, tên file).

| Mức | Phát hiện | Xử lý |
|---|---|---|
| **P1** | `docs/gt/binh1_tay` khai `silhouette` nhưng là 12 hình chữ nhật đặc đã lệch ⇒ `--check-index` in **"hợp lệ" + exit 0**, `score` sẽ ghi artifact `dang_gt=silhouette`, `canh_bao_gt=[]`, exit 0 cho số vô nghĩa (văn xuôi README là chốt chặn duy nhất) | Xoá 12 `gt_*.png` + `dung_duoc: false` + lý do ⇒ `kiem_index` **CHẶN** (thiếu file GT) ⇒ exit 2 |
| **P1** | `label` ghi cứng `dang_gt: silhouette` **trước khi** ai tô ⇒ bộ GT vẽ bằng hộp lọt cổng, cảnh báo không bao giờ in; 0 test cho `label` | `--dang-gt`/`--phuong-phap-gt`, mặc định `None` + 3 test cho `label` |
| **P2** | `mask_ngoai_gt` mẫu số khác `mIoU` (frame mask rỗng bị loại) và không có `_n` ⇒ trung bình lạc quan im lặng | `mask_ngoai_gt_n` + cảnh báo khi lệch + 1 test |
| **P2** | Câu "đo over-segmentation" quá mạnh (chỉ một phía; `tran = 0` cả khi mask tí xíu nằm trong hộp) | Sửa REGISTRY + doc: "thấp = không tràn ra ngoài; KHÔNG nói mask phủ đủ" |
| **P2** | `nguoi_gan` của `binh1_hopbao` là **mô tả phương pháp** ⇒ lách cổng "phải có người chịu trách nhiệm"; sai số hộp chưa đo | `nguoi_gan` = người thật; thêm `nguon_gt`; ghi "SAI SỐ HỘP CHƯA ĐO" |
| **P2** | `docs/thuoc-do-bam-dung.md` **không** có `dang_gt`/`hop_bao`/`mask_ngoai_gt`/mã thoát; §4 vẫn nói "chưa có mIoU video thật" | Thêm §1.1 (bảng dạng GT + mã thoát 0/1/2 + `mask_ngoai_gt` một phía) và §4 viết lại theo số thật |
| **P2** | `288,287,431,734` được gọi là "ô chai **đúng**" trong 2 log + 2 artifact; thực chất là cùng ô ở dạng `x1,y1,x2,y2` | Đính chính §1.1 vào `docs/demo-clip-va-o-chon.md` (nguồn sự thật): 2 bảng `bangcau`/`ab` đã đo bằng hộp **431×734** |
| **P3** | `ket_qua.mIoU` trên artifact GT hộp mời gọi `grep` rồi trích | Ticket **#30** |
| **P3** | `hop_bao_xywh` không được đối chiếu `gt.sum()`; chưa đối chiếu `clip` ↔ `manifest.nguon`, `frames` ↔ `frames_yeu_cau`; `mask_ngoai_gt_max_frame` khi hoà chưa có test | Ticket **#30** |
| **P3** | Chặn trên ghi "~0,7-0,85" / "~0,75–0,85" là **số gõ tay** | Sửa thành "max quan sát 0,774 (f92); cận trên lý thuyết CHƯA đo" |
| **P3** | Bộ GT **đang dùng** không có README, bộ bị cấm lại có README to kèm lệnh chấm chạy được | Thêm `docs/gt/binh1_hopbao/README.md`; bỏ lệnh chấm khỏi README của `binh1_tay` |
| **P3** | REGISTRY trỏ khoá không tồn tại (`so_frame_cham`/`so_frame_gt`) | Sửa thành `n_cham`/`so_frame_tong` |
| **"đã kiểm, không phải lỗi"** | artifact tự nhất quán (mIoU = trung bình đúng 12 giá trị; `dien_tich_gt == w*h` 12/12); `dang_gt=hop_bao` mô tả đúng dữ liệu; exit 1 không phá CI (CI chỉ ruff + pytest); `mask_ngoai_gt_max_frame` không crash khi hoà/None; không nơi nào dùng `mask_ngoai_gt` như "độ chính xác" | Đồng ý cả 5 |

**Nợ quy trình (review nêu đúng):** 4 commit của việc này đi thẳng vào `main` (theo yêu cầu người dùng
"tự merge"), review chạy **sau** merge, và **chưa có plan §9.2** dù đổi hợp đồng `score_miou` (khoá
`meta` mới + mã thoát mới). Ghi lại ở đây thay vì im lặng; các P3 gom vào ticket #30.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **GT silhouette cho video thật** (việc còn lại của #1): tô **đặc** 10–20 frame
      (`score_miou.py label --dang-gt silhouette …`) ⇒ mới có **mIoU phân đoạn** để đối chiếu 0,6464.
      Ước lượng: 20–30 phút tô + 2 phút chấm.
- [ ] **#30** — chặn chặt hơn cho GT hộp bao (tên khoá, đối chiếu `hop_bao_xywh`, clip ↔ manifest).
- [ ] Đo **sai số của bộ dựng hộp**: 3–4 frame vẽ tay để so với hộp tự động (hiện chưa biết hộp lệch bao nhiêu).
- [ ] Frame 62: mở ảnh xác nhận `mask_ngoai_gt` 29,4 % là lỗi **model** hay lỗi **hộp GT sửa tay**.
- [ ] Các việc còn lại của phiên trước: **#28** (cờ lệch lên HUD), **#29** (ẩn `user:pass`), diễn tập
      camera thật, chốt phạm vi với GVHD.

## 📚 Tài liệu tham khảo
- `docs/thuoc-do-bam-dung.md` — quy trình chấm + §1.1 (dạng GT, mã thoát) sau khi sửa.
- `docs/demo-clip-va-o-chon.md` — nguồn sự thật clip + ô chọn (+ §1.1 đính chính định dạng ô).
- `docs/task/15-11-2026-status-json-echo-cau-hinh-hieu-luc.md` — việc trước trong cùng ngày.
- `AGENTS.md` §6 — bẫy `0/None`, `(x,y,w,h) ≠ (x1,y1,x2,y2)`, "drift ≠ độ chính xác".
