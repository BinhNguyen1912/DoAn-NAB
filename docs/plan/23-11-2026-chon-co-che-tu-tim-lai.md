# Plan 23-11-2026 — Demo nên dựa vào cơ chế nào để "tự tìm lại" vật

> Plan theo **AGENTS.md §9.2**: 3 ý kiến độc lập (vòng 1) → phản biện chéo (vòng 2) → chốt.
> Bối cảnh: 3 phiên `./run demoip` liên tiếp (23-11) đều **bám nhầm** (remote be trơn → bám tường be,
> rồi bám áo người). Riêng ngày 23-11 đã có 9 commit sửa re-ID mà **càng sửa càng tệ**
> (`c8077f4` thêm mẫu "ô chữ nhật" → `2f0103c` revert vì chính nó làm tường khớp 0,976).

## 🎯 Câu hỏi cần quyết

> Với **cùng một clip, cùng ô chọn, cùng `image_size`**, cơ chế nào thật sự đưa mask về đúng vật sau
> khi vật bị che/rời khung: **(A)** re-ID ngoại hình (cosine/NCC) ép `engine.start()` lại, hay
> **(C)** cứ để SAM 2 lan truyền liên tục và tự bám lại?
> Ràng buộc: đo trên máy này (CPU, không GPU), phải chấm bằng **mIoU mask vs GT** (không dùng
> `reacquired`/`drift_iou`), và **cấm** tuyên bố gì từ `n < 3` lần chạy.

## 🧭 Ba góc nhìn (vòng 1 — độc lập, không biết nhau)

### A. Chất lượng & số đo
Đề xuất 6 việc nặng về đo: (1) đóng lỗ telemetry `verify_cos`, (2) **benchmark re-ID CÓ NHÃN** (6–8
frame GT mới cho ca "vật ra/vào khung"), (3) đo **recall@K** của bộ sinh ứng viên, (4) xếp hạng ứng
viên bằng mask-cos, (5) re-ranker `engine.start` top-1 mỗi frame LOST, (6) test giết-mutant.
"Trần của mọi kỹ thuật xác minh là **≤31 %** frame tìm lại" (suy ra từ `reid_score = -1`).

### B. Sản phẩm & bằng chứng bảo vệ
Đề xuất: (F1) cơ chế → (F2) telemetry `verify_cos` + `search_*` → (F3) `prompt_bbox`/`reselect_n`;
cộng các mục C (chọn lại giữa phiên), D (mIoU trên đúng vật be), E (chốt artifact).
Chỉ ra: **web live KHÔNG có Re-ID** (`LiveStartRequest` không có `reid`) ⇒ mọi tuyên bố re-ID chỉ
đúng cho CLI; `IdentityWatch` latch không có đường "sai, chọn lại".

### C. Độ bền & hiệu năng
Đề xuất: (B0) commit cây bẩn + bịt 3 lỗ provenance, (B1) `cand_best_cos`/`cand_n` + `prompt_bbox`,
(B2) một ngoại lệ `step()` không được đóng băng demo, (B3) YuNet lười (chỉ detect khi có ứng viên
qua NCC: **2,65 s / 25,8 s = 10,2 %**), (B4) chốt artifact kèm nhãn "không replay được".
Tính đúng ngân sách: probe chỉ chạy ở frame LOST ⇒ 1/5 = **+12,6 ms (1,12×)**, không phải 1,15×.

## ⚔️ Tranh chấp (vòng 2 — phản biện chéo)

| Điểm tranh chấp | A nói | B nói | C nói | Chốt |
|---|---|---|---|---|
| "Trần ≤31 % frame tìm lại" | suy từ `reid_score = -1` | lặp lại con số đó | **sai mẫu số**: 254 frame gồm 93 `tracking` ⇒ 78/160 = **48,8 %**; và `-1` KHÔNG có nghĩa "không có ứng viên" (170/175 dòng có `ncc=-1` mới là bộ sinh rỗng) | **Bỏ con số 31 %.** Thêm cột `cand_n` để tách "bộ sinh rỗng" khỏi "cổng chặn" — **tái lập được** |
| Veto mặt là nút thắt | có | có | **không còn**: toàn bộ 78 dòng đo trên `783621c`, mà veto-hình-học là `c8077f4` sau đó; phiên mới `101110` có `reid_veto_mat_n = 0` | Bỏ giả thuyết veto |
| `_verify_ok` "đã pass tường" | — | có (⇒ top-K vô ích) | **suy luận trên code đã revert**; trên HEAD cos(tường, mẫu-MASK) = 0,457 | Bỏ lập luận đó; lý do bác top-K chỉ còn **chi phí + recall@K chưa đo** |
| Làm `engine.start` mỗi frame LOST | #5 | — | **+17–22 s/phiên** (161 frame × 105–139 ms trên phiên 25,8 s) | **Không làm** |
| Điểm âm/mẫu inset | #4 | #3 (M3) | bằng chứng là clip **tổng hợp** (`remote_trang`, `synthetic_exact`, mIoU 1,0) ⇒ không nói gì về ca tường be thật | **Không làm** |
| Telemetry tốn bao nhiêu | 3 h | 3 h | 1 h (phần lớn đã có trong working tree) | 1 h (đã xong) |

## 🔬 Quyết định được ĐO, không phải bàn

Trước khi chốt, chạy đúng câu hỏi của plan. Clip `data/binh1.mp4`, `image_size 192`,
`bbox 300,275,150,410`, 333 frame, `vos_every 1` (inline), cây sạch `git_rev 7bac7ae`,
`./run miou score --gt docs/gt/b1` (GT silhouette, có sẵn từ 20-11):

| Nhánh | Cấu hình | `mất dấu` (CSV) | **mIoU** | mask NGOÀI GT | f181 / f211 / f241 |
|---|---|---|---|---|---|
| **A** | `--reid --reid-cue object --reid-obj-threshold 0.75 --reid-obj-ncc-min 0.40` | **5/333** | **0,4236** | **43,1 %** (tệ nhất 100 %) | **0,0016 / 0,0 / 0,0** |
| **C** | không `--reid`, `--lost-after-frames 999 --lost-score-threshold -99` | 113/333 | **0,7794** | 0,6 % | **0,7994 / 0,8495 / 0,8435** |

- **Tái lập 3/3 lần, giống nhau tới 4 chữ số** (cả 2 nhánh).
- Nhánh **C trùng khít** artifact đã commit `data/miou_b1_2026-11-20_metrics.json`
  (mIoU 0,7794 · f181 0,7994 · f211 0,8495 · f241 0,8435) ⇒ **cùng một cơ chế**, chứng minh số của
  artifact 20-11 là "mask lan truyền liên tục", **không** phải re-ID.
- ⇒ Re-ID **nhận lại SAI** trên đúng clip này: HUD báo `mất dấu 5/333` (đẹp nhất từ trước tới nay)
  nhưng mask nằm **hoàn toàn ngoài** vật (IoU 0,0016 / 0,0 / 0,0). Đây là dạng lỗi
  "chỉ số đẹp, kết quả sai" đã ghi ở AGENTS §6 (phiên `101110`).
- ⇒ Và nút thắt thật là **cổng "đóng băng khi mất dấu"** của đường CLI (`--lost-after-frames`,
  mặc định 2): khi nó đóng băng, SAM 2 **không được gọi nữa** nên khả năng tự bám lại của model bị
  vô hiệu hoá, và toàn bộ máy re-ID phải gánh — rồi gánh sai.

## 🔍 Phát hiện thêm: re-ID còn BỊA mask khi vật đã rời khung

Diện tích mask thực tế trong 2 bộ dump đã commit (`data/ab_binh1_*_lan1_masks/`):

| frame | GT (`docs/gt/b1`) | A (re-ID) | C (lan truyền) |
|---|---|---|---|
| 121 | **rỗng** (vật đã cất) | **33 199 px** | **0 px** |
| 151 | **rỗng** | **37 574 px** | **0 px** |
| 181 | có vật (82 293) | 130 289 px — IoU **0,0016** | 65 832 px — IoU **0,7994** |
| 211 | có vật (261 042) | 53 134 px — IoU **0,0** | 222 440 px — IoU **0,8495** |
| 241 | có vật (41 081) | 79 338 px — IoU **0,0** | 35 769 px — IoU **0,8435** |
| 272 / 302 / 332 | **rỗng** | 6 385 / 34 696 / 52 056 px | **0 / 0 / 0 px** |

⇒ Re-ID **sai ở CẢ HAI chiều** trên clip này: **bịa mask ở 5/5 frame vô vật** (6,4k–52k px trên
tường/áo) và **đặt mask sai ở 3/3 frame có vật**. Ngược lại SAM 2 lan truyền trả **mask rỗng đúng
lúc vật vắng** — tức lý do tồn tại của cổng đóng băng ("chống SAM 2 tưởng tượng mask") **không đúng
trên clip này**: thứ tưởng tượng mask là re-ID, không phải model.

## ✅ Quyết định

- **Chọn:** **C là cơ chế của demo** — ưu tiên "không đóng băng lan truyền" + giữ Re-ID **tắt mặc
  định** trong kịch bản demo, và **chỉ bật re-ID khi có bằng chứng đo được trên chính clip đó**.
- **Vì sao:** mIoU 0,7794 vs 0,4236 (chênh 0,356 = **19× ngưỡng nhiễu đã biết** cho đại lượng này
  không tồn tại, nhưng khoảng cách tuyệt đối + mask-ngoài-GT 0,6 % vs 43,1 % + tái lập 3/3 loại bỏ
  khả năng nhiễu); và C trùng khít artifact 20-11 độc lập.
- **Bác:**
  - **Re-bật mặc định re-ID / hạ ngưỡng cosine** — 3 phiên thật 21–23/11 đều bám nhầm; đo lại trên
    `binh1` cho mIoU 0,42. Bác tới khi có clip tái hiện + số tốt hơn C.
  - **Top-K / re-ranker / `engine.start` mỗi frame LOST** — +17–22 s/phiên và **chưa có** recall@K
    (dùng `cand_n` để đo trước, 1 lần chạy, ~40 s).
  - **Đổi loại mặt nạ/ngưỡng/mẫu inset** — `2f0103c` đã chứng minh hậu quả (tường khớp 0,976).
- **Tiêu chí nghiệm thu (có SỐ):**
  - [x] A vs C trên `binh1`, **3 lần mỗi nhánh**, `git_dirty_code = false`: mIoU **0,4236** vs **0,7794**
        (artifact `data/ab_*_2026-11-23_*`, log `docs/task/23-11-2026-*.md`).
  - [x] C trùng khít `data/miou_b1_2026-11-20_metrics.json` (f181/f211/f241 sai khác 0).
  - [ ] Kịch bản demo ghi rõ 1 câu **được nói** / 1 câu **cấm nói** (bổ sung §6
        `docs/demo-clip-va-o-chon.md`) — *chưa làm, xem ticket*.
  - [ ] Trên **web live** (`LiveTrackingSession`): kiểm lại "vật rời khung rồi về" có tự bám lại
        không (web **không** có re-ID, và cũng **không** có cổng đóng băng như CLI) — *chưa đo*.

## 📌 Việc tách ra ticket

- [ ] **`cand_n`/`cos_truoc_cong` trên một phiên `./run demoip` thật** ⇒ biết "bộ sinh rỗng" hay
      "cổng chặn" trên ca tường be (đã có cột, chưa có phiên).
- [ ] **Kịch bản demo 1 trang** (§6 `docs/demo-clip-va-o-chon.md`): câu được/cấm nói + 3 điều chưa biết.
- [ ] **Đưa số A/C vào `scripts/so_lieu_bao_cao.py` REGISTRY** để CI chặn lệch.
- [ ] **Đo trên web live** ca "vật rời khung rồi về" (đường duy nhất không có re-ID).
- [ ] **Ticket riêng: cổng đóng băng** — `--lost-after-frames 2` có còn đúng không, hay nên để
      SAM 2 chạy tiếp và chỉ ẩn overlay khi điểm tin cậy thấp (đây là gốc của mọi lỗi re-ID).

## 📚 Tham chiếu

- `docs/task/23-11-2026-demo-nen-dua-vao-co-che-nao.md` (log của phiên này, có bảng số đầy đủ)
- `data/miou_b1_2026-11-20_metrics.json` (nhánh C, độc lập, 20-11)
- `docs/task/23-11-2026-phan-tich-phien-demoip-1123-bam-nham-remote.md` (phân tích 3 phiên thật)
- `AGENTS.md` §6 (mục "Muốn nói bám ĐÚNG thì phải chấm mIoU", "`reacquired=1` không có nghĩa bám đúng")
- `docs/gt/b1/index.json` (GT silhouette, 12 frame, người gán: Binh)
