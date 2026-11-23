# Ngày 23-11-2026 — Demo nên dựa vào cơ chế nào để "tự tìm lại" vật (A/B có chấm mIoU)

> Phiên này trả lời câu hỏi đã treo suốt 3 ngày (21–23/11): *vì sao `./run demoip` cứ bám nhầm, và
> sửa re-ID có cứu được không*. Câu trả lời là **số đo**, không phải suy luận: **re-ID đang LÀM HỎNG
> kết quả**, và nút thắt thật là **cổng "đóng băng khi mất dấu"** của đường CLI.

## 🎯 Mục tiêu

1. Chốt (bằng số) nên dựa vào **re-ID** hay **lan truyền liên tục của SAM 2** để vật "về lại" sau khi
   bị che/rời khung.
2. Bịt các lỗ telemetry khiến mọi kết luận trước đây không kiểm chứng được.
3. Làm được phép đo mIoU cho **phiên CLI** (trước đây chỉ đường web xuất được mask).

## 📥 Input

- 3 phiên thật bị bám nhầm: `demoip_1123-092343` (bám áo người), `demoip_1123-095901` (0 lần nhận
  lại), `demoip_1123-101110` (nhận vào **tường be**, 103 frame).
- Clip + GT có sẵn: `data/binh1.mp4`, `docs/gt/b1` (GT silhouette 12 frame, người gán: Binh,
  `phuong_phap_gt` = HSV gợi ý + sửa tay ⇒ **không** phải GT người vẽ hoàn toàn).
- Artifact độc lập: `data/miou_b1_2026-11-20_metrics.json` (mIoU 0,7794) — sinh bởi
  `tools/live_worker.py` (**đường web, KHÔNG có Re-ID**).
- 3 ý kiến vòng 1 + 3 ý kiến vòng 2 (AGENTS §9.2) — agent độc lập, mỗi vòng không biết nhau.

## 🔨 Công việc đã thực hiện

### 1. Telemetry: bịt 3 lỗ khiến "không kết luận được"

| Commit | Việc | Vì sao (bằng chứng) |
|---|---|---|
| `24cd2ad` | `Step.verify_cos` mang ra **cả nhánh xác minh THẤT BẠI** (`_abandon_reacquire()`) | Bản đầu chỉ ghi cos khi verify **được**; ca cần soi nhất (verify chặn) thì CSV trống |
| `24cd2ad` | cột `cos_truoc_cong` = cosine cao nhất chấm **TRƯỚC mọi cổng** | `reid_score = -1` không phân biệt "bộ sinh rỗng" với "cổng chặn"; phiên `095901` có 175/254 dòng `-1` mà không đọc được là ca nào |
| `6f36a04` | cột `cand_n` = **số ứng viên đã chấm** | Cùng lý do; reviewer vòng 2 chỉ ra 175 dòng `-1` (không phải 82 như vòng 1 nói) |
| `6f36a04` | nhánh `need_start` **reset** `_verify_cos`/`_cos_truoc_cong`/`_cand_n` | Rò số: sau khi bấm `r` chọn lại, frame đầu của lần chọn MỚI vẫn mang số của vật TRƯỚC |
| `6f36a04` | **1 ngoại lệ `step()` không giết phiên**: thử lại 3 lần rồi mới bỏ ô | Nhánh cũ đặt `_bbox=None` ngay lần lỗi đầu, mà vòng hiển thị vẫn dán `stamped.result` cũ ⇒ demo "trông như đang chạy" với mask **đóng băng** |
| `6f36a04` | in `search_mean_ms`/`search_p95_ms`/`search_n` ở dòng `[metrics]` | Phiên `095901` in "mean 161,8 ms (n=93)" trong khi **160 bước tìm lại (66,8 ms/bước)** không nằm trong con số nào |

### 2. `7bac7ae` — `./run miou` chấm được cho phiên CLI

`tools/run_live.py --dump-mask-frames 0,30,... --dump-mask-dir <dir>`:
- tên file theo **số frame video** (đếm thứ tự callback), **không** theo `result.frame_idx`
  (bài học P0 14-11);
- mask **rỗng vẫn ghi** (file toàn 0) — "model trả rỗng" là kết quả đo được, phải chấm 0,0;
- `mask is None` ⇒ **không** ghi file + cảnh báo (không được đọc thành "đã đo");
- ghi `manifest.json` (`nguon`, `image_size`, `bbox_xywh`, `frames_yeu_cau`, `frames_da_ghi`,
  `so_file_ghi_de`, `frame_goc_cua_phien`) để `score_miou` đối chiếu; **không ghi đè** manifest có sẵn;
- 8 test mới (`tests/test_run_live_cli.py::TestDumpMask`).

### 3. A/B quyết định — 3 lần mỗi nhánh, chèn kẽ, cây sạch (`git_rev 7bac7ae`)

Lệnh (nhánh A; nhánh C bỏ `--reid ...` và thêm `--lost-after-frames 999 --lost-score-threshold -99`):

```bash
python tools/run_live.py --source data/binh1.mp4 --image-size 192 --bbox 300,275,150,410 \
  --max-frames 333 --reid --reid-cue object --reid-obj-threshold 0.75 --reid-obj-ncc-min 0.40 \
  --dump-mask-frames 0,30,60,91,121,151,181,211,241,272,302,332 --dump-mask-dir data/... \
  --metrics-csv data/...
./run miou score --gt docs/gt/b1 --pred-dir <dir> --out data/...
```

## 📤 Output / Kết quả

### Bảng quyết định (tái lập **3/3** lần, giống nhau tới 4 chữ số)

| Nhánh | Cấu hình | `mất dấu` (CSV) | **mIoU** | mask NGOÀI GT | f181 / f211 / f241 |
|---|---|---|---|---|---|
| **A** | có re-ID | **5/333** | **0,4236** | **43,1 %** (tệ nhất **100 %**) | **0,0016 / 0,0 / 0,0** |
| **C** | không re-ID, không đóng băng | 113/333 | **0,7794** | 0,6 % | **0,7994 / 0,8495 / 0,8435** |

- **Nhánh C trùng khít** `data/miou_b1_2026-11-20_metrics.json` (cùng 7 frame, cùng IoU từng frame)
  ⇒ artifact 20-11 chính là "mask lan truyền liên tục", **không** liên quan re-ID.
- Nhánh A: HUD báo `mất dấu 5/333` — **chỉ số đẹp nhất từ trước tới giờ** — nhưng mask nằm **hoàn
  toàn ngoài vật** ở cả 3 frame có GT sau khi vật về. Đúng dạng lỗi "chỉ số đẹp, kết quả sai".

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

### Kết luận

1. **Re-ID đang làm HỎNG kết quả trên clip này** (mIoU 0,4236 vs 0,7794; mask tràn ra ngoài 43 % vs
   0,6 %). Nó "nhận lại" một vùng **không phải vật**.
2. **Nút thắt thật là cổng đóng băng** `--lost-after-frames` (mặc định **2**): khi đóng băng, đường CLI
   **không gọi SAM 2 nữa** ⇒ khả năng tự bám lại của model bị vô hiệu hoá ⇒ mọi trách nhiệm dồn cho
   re-ID, và re-ID gánh sai. Mở cổng ra (C) thì SAM 2 tự bám lại đúng.
3. Vì thế 9 commit sửa ngưỡng/mẫu/loại mặt nạ re-ID trong 3 ngày qua **không thể** cứu được demo:
   chúng đang tối ưu một cơ chế không phải cơ chế đang hỏng.

### File thay đổi

- `src/reid.py` — `Step.cos_truoc_cong`, `Step.cand_n`, `_abandon_reacquire` mang `verify_cos`
- `src/metrics_logger.py` — 2 cột CSV mới (`cos_truoc_cong`, `cand_n`)
- `src/live_pipeline.py`, `src/smooth_display.py` — truyền 2 số trên + retry lỗi + reset khi chọn lại
- `tools/run_live.py` — `--dump-mask-frames/--dump-mask-dir`, `_dump_cfg`, `_dump_mask_callback`,
  `_write_mask_manifest`, in `search_*`
- `tests/test_reid.py`, `tests/test_metrics_logger.py`, `tests/test_smooth_display.py`,
  `tests/test_run_live_cli.py` — test mới cho từng hành vi trên
- `docs/plan/23-11-2026-chon-co-che-tu-tim-lai.md` — plan 3 ý kiến + quyết định

## 🐞 Vấn đề gặp phải & cách xử lý

- **Probe đầu tiên của tôi SAI**: chạy `./run view` tưởng là headless, nhưng `./run view` =
  `--display --smooth --reid --image-size 384` ⇒ **`--smooth` trên file làm MẤT FRAME**
  (`LatestFrameSource` chỉ giữ frame mới nhất) ⇒ ra "mất dấu 36/40" vô nghĩa. Sửa: gọi thẳng
  `python tools/run_live.py` (không `--smooth`). **Bài học: mọi A/B trên file phải chạy inline.**
- **Test cũ khoá hành vi "1 lỗi là bỏ ô"**: phải viết lại thành 2 test (1 cú chập ⇒ không bỏ ô; lỗi
  liên tiếp ⇒ bỏ ô + **số dòng `[LOI]` có trần** = 3, không spam).
- **3 ý kiến vòng 2 tự sửa số của vòng 1** — 2 chỗ quan trọng: "trần ≤31 %" sai mẫu số
  (đúng: 78/160 = 48,8 %) và "veto là nút thắt" đo trên code đã bị thay (`783621c` vs `c8077f4`).
- **Review độc lập (§9.1)** cho 3 commit này: **đã chạy** (`reviewer`, task `mwsrqtxe-3c10`) —
  kết quả ghi ở mục dưới khi về.

## 📌 Việc cần làm tiếp (Next steps)

- [ ] Dán kết quả review độc lập vào log này; xử lý P0/P1.
- [ ] **Kịch bản demo 1 trang** (§6 `docs/demo-clip-va-o-chon.md`): 1 câu được nói / 1 câu cấm nói.
- [ ] Đo **web live** ca "vật rời khung rồi về" (đường web **không** có re-ID **và không** có cổng
      đóng băng ⇒ dự đoán tự bám lại được; **chưa đo**).
- [ ] Ticket riêng: `--lost-after-frames 2` có còn đúng? Đề xuất chỉ ẩn overlay khi điểm thấp, **không**
      ngừng gọi model.
- [ ] Đưa A/C vào `scripts/so_lieu_bao_cao.py` REGISTRY để CI chặn lệch số.
- [ ] Chạy `cand_n`/`cos_truoc_cong` trên **một phiên `demoip` thật** với vật be (biết "bộ sinh rỗng"
      hay "cổng chặn").

## 📚 Tài liệu tham khảo

- `docs/plan/23-11-2026-chon-co-che-tu-tim-lai.md` — plan 3 ý kiến + 2 vòng phản biện + quyết định
- `data/miou_b1_2026-11-20_metrics.json` — nhánh C độc lập (20-11, đường web)
- `docs/gt/b1/index.json` — GT silhouette 12 frame
- `docs/task/23-11-2026-phan-tich-phien-demoip-1123-bam-nham-remote.md` — 3 phiên bám nhầm
- `AGENTS.md` §6 — "phải chấm mIoU mới được nói bám đúng", "`reacquired=1` ≠ bám đúng"
