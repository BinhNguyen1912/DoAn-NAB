# Thước đo "BÁM ĐÚNG" — mIoU mask vs GT (việc #6)

> Trả lời câu hỏi hội đồng chắc chắn hỏi: **"hệ thống bám có ĐÚNG không?"**.
> Mọi con số "chất lượng" khác trong repo (`drift_iou`, `stability`) chỉ là **độ tự nhất quán**:
> VOS bám lệch một cách ổn định thì `drift_iou` vẫn cao (AGENTS §6).

## 1. Thước đo là gì

- **mIoU** = trung bình `IoU(mask_model, mask_GT)` trên các frame chấm được.
- **GT mask** = mask nhị phân do **người** tô trên frame gốc (`docs/gt/<tên>/gt_<frame>.png`).
- Script: `scripts/score_miou.py`; mask của model do worker xuất ra:
  `tools/live_worker.py --dump-mask-frames "0,50,120"`.

### Quy tắc chấm (đây là phần dễ làm sai nhất)

| Ca | Kết quả | Vì sao |
|---|---|---|
| GT có vật, model trả mask rỗng | **0,0** | bám sai thật; gộp vào "không đo được" là thổi phồng điểm |
| GT rỗng (không có vật trong frame) | **không chấm** (`None`) | `IoU(rỗng, rỗng) = 1,0` theo công thức ⇒ nếu nhận thì "bám đúng tuyệt đối" mà chẳng đo gì |
| Thiếu file mask của model | `None` + `so_frame_thieu_mask` | *chưa chạy* ≠ *bám sai* |
| Không chấm được frame nào | `mIoU = None` | không bao giờ in `0` cho "chưa đo" |
| GT có phần do **model gợi ý** | **từ chối chấm** | chấm mIoU trên mask model tự sinh = đo chính nó, không phải đo chất lượng |

### 1.1. Dạng GT phải KHAI (`dang_gt`) — nếu không, con số bị gắn sai nghĩa

`index.json` của bộ GT phải khai **hình dạng** GT và cách làm ra nó:

| `dang_gt` | Nghĩa | Con số đo được gì |
|---|---|---|
| `silhouette` | mask **của vật** (người tô) | mIoU phân đoạn — so được với báo cáo/DAVIS (với cùng điều kiện) |
| `hop_bao` | **hộp chữ nhật** bao vật | IoU(mask, hộp) — chỉ nói mask có nằm ĐÚNG VÙNG; **chặn trên ~0,75–0,85** vì hộp > vật |

- Thiếu khoá ⇒ **cảnh báo mềm** ("không biết dạng GT") + **exit 1**.
- `hop_bao` ⇒ cảnh báo mềm nêu rõ "KHÔNG phải mIoU phân đoạn" + exit 1 (số vẫn ghi vào artifact, nhưng
  `meta.dang_gt`/`meta.phuong_phap_gt`/`canh_bao_gt` đi kèm).
- `label` **không** tự khai hộ: phải truyền `--dang-gt silhouette|hop_bao` (trước 15-11 nó ghi cứng
  `silhouette`, và một bộ GT vẽ bằng **hộp** đã lọt qua cổng với exit 0).
- `nguon_gt` ghi ai/máy nào dựng GT. Máy đề xuất (ngưỡng màu…) + người soi **vẫn phải** khai, và sai
  số của bộ dựng GT **chưa đo** thì phải nói ra.
- Artifact echo dạng GT ở **cả `meta.dang_gt` LẪN `ket_qua.gt_dang`**; khi `dang_gt != silhouette`
  còn có `ket_qua.mIoU_dinh_nghia` ("IoU(mask, GT dạng 'hop_bao') — KHÔNG phải mIoU phân đoạn
  silhouette"). Lý do: người ta hay `grep mIoU` rồi copy con số, mà cảnh báo nằm trong `meta` thì
  không đi theo con số (ticket #30). `--check-index` in thêm **dạng GT + nguồn GT + clip** ngay đầu.

### 1.2. Cổng kiểm bộ GT (ticket #30) — GT phải khớp **chính nó** và khớp **mask**

| Kiểm | Loại | Vì sao |
|---|---|---|
| `hop_bao_xywh` đúng định dạng `[x,y,w,h]` số nguyên, w/h > 0 | **CHẶN** (`dang_gt = hop_bao`) | hộp ghi sai ⇒ mIoU vô nghĩa |
| Hộp không vượt biên khung | **CHẶN** | hộp vượt biên bị cắt ⇒ `sum ≠ w*h` mà không rõ vì sao |
| `gt.sum() == w*h` | **CHẶN** | GT **lẫn frame khác** hoặc hộp ghi sai |
| Bao thực của mask đúng `(x, y, w, h)` | **CHẶN** | cùng số pixel nhưng nằm chỗ khác vẫn là GT sai |
| Khai `hop_bao` mà không có `hop_bao_xywh` | cảnh báo mềm | GT cũ chưa có hộp ⇒ không đối chiếu được |
| `index.clip` khác `manifest.nguon` của mask | cảnh báo mềm | mIoU đang ghép **hai clip** khác nhau |
| `index.frames` ngoài `manifest.frames_yeu_cau` | cảnh báo mềm | đúng lớp lỗi "ghép GT với mask của frame khác" (P0 14-11) |
| `manifest.json` **hỏng**/không phải JSON object | cảnh báo mềm | khác "không có manifest" (ca đó bình thường); hỏng ⇒ không ai biết mask từ clip/frame nào, lỗi được ghi vào `meta.mask_manifest_loi` |
| Hai frame khai **cùng một `hop_bao_xywh`** (chỉ khi `dang_gt = hop_bao`, và phải giống **hệt cả 4 số**) | cảnh báo mềm | bản hộp bao của `DUP_IOU` (`gt_check_silhouette`): nghi copy-paste GT; lệch 1 px hoặc `dang_gt` không khai ⇒ **không** cảnh báo. Vật đứng yên vẫn có thể trùng hộp thật nên không chặn |

`mask_ngoai_gt_max_frame` khi **hoà** (nhiều frame cùng "tràn" lớn nhất): chọn **frame_idx nhỏ nhất** —
ghim bằng test để con số không đổi theo thứ tự `index.frames`.

**Giới hạn của các cổng này (đọc trước khi tin "hợp lệ"):**

- Chúng kiểm **tự nhất quán** (mask GT ↔ hộp khai ↔ manifest), **không** kiểm nội dung frame. Với GT
  hộp bao, copy-paste **giống hệt** hộp khai giữa ≥ 2 frame chỉ bị **cảnh báo mềm** ("CÙNG một hộp"),
  và hộp chỉnh lệch 1 px thì im lặng ⇒ đừng đọc "đã qua cổng" là "không copy-paste". Với GT
  silhouette, dùng `scripts/gt_check_silhouette.py` (IoU > 0,98 giữa hai frame) — nó bắt được cả ca
  hai mask giống nhau mà hộp khai khác.
- `manifest.json` chỉ có `nguon` + `frames_yeu_cau` ⇒ cổng so được **tên file/clip**, không chứng minh
  được mask đúng nội dung frame (ca P0 14-11 "dump mask sai chỉ số frame" nay đã được sửa ở gốc).
- Tên khoá hộp là `hop_bao_xywh` (không phải `bbox_xywh` như `docs/gt/synthetic_tong_hop`); GT khai
  `dang_gt = hop_bao` mà dùng tên khác sẽ chỉ ra **cảnh báo mềm** chứ không qua cổng.
- Hộp phải là **số nguyên** (`282`, không phải `282.0`) — JSON viết tay/ công cụ ngoài dễ sinh float.

**Mã thoát của `score`:** `0` = chấm xong, không cảnh báo · `1` = chấm được nhưng có cảnh báo (GT hộp
bao / thiếu người gán / không khai `dang_gt` / `git_loi` / không chấm được frame nào) · `2` = **TỪ CHỐI**
(thiếu file GT, GT do model gợi ý, index hỏng). Đừng cắm `./run miou` vào CI mà coi exit 1 là đỏ: nó là
"đọc kèm cảnh báo".

**Chỉ số phụ `mask_ngoai_gt`:** phần mask nằm **ngoài** GT (thấp = không tràn ra ngoài). Nó **một phía**
— `0` KHÔNG có nghĩa mask phủ đủ vật (mask tí xíu nằm trong hộp cũng cho `0`), và nó không bị chặn trên
bởi GT hộp bao. Đọc kèm `mask_ngoai_gt_n` (số frame dùng được; frame model trả mask **rỗng** bị loại vì
không có gì để tràn, trong khi `mIoU` vẫn tính 0,0 cho frame đó).

## 2. Cách làm GT cho video THẬT (≈ 20–30 phút cho 10–20 frame)

```bash
# 1) cắt frame ra PNG để tô (chọn frame rải đều clip, có cả lúc vật bị che/một phần ra khung)
python scripts/score_miou.py label --clip data/binh1.mp4 \
    --frames 0,40,80,120,160,200,240,280 --ten binh1_tay --nguoi-gan "Nguyễn Văn A"

# 2) tô trắng vùng vật trên docs/gt/binh1_tay/frames/frame_000040.png
#    rồi lưu thành docs/gt/binh1_tay/gt_000040.png (cùng thư mục gốc của bộ GT, nền đen, vật trắng)

# 3) kiểm GT hợp lệ (đủ file, đủ người chịu trách nhiệm, không frame trùng)
python scripts/score_miou.py score --gt docs/gt/binh1_tay --pred-dir /tmp/x --check-index

# 4) chạy model trên đúng clip đó, xuất mask tại ĐÚNG các frame đã gán
#    ⚠ --vos-every 1 là BẮT BUỘC khi gán GT: với vos_every > 1 chỉ frame chia hết cho N mới có lần
#    VOS, nên frame 40 (N=3) không có mask nào và lần chấm sẽ thiếu frame mà không rõ vì sao.
#    Tên file mask = **chỉ số frame VIDEO** (không phải bộ đếm nội bộ của engine) — đã sửa 14-11.
#    ⚠ Phiên phải bám từ frame ĐẦU: `--bbox x,y,w,h` (dạng xywh, SỐ NGUYÊN) ghi bbox.json TRƯỚC khi
#    chạy. Nếu chạy CLI trước rồi mới có bbox.json (người dùng chọn ô sau), tên file mask là frame của
#    PHIÊN chứ không phải của clip — và nguồn quay vòng nên offset cũng không suy ra được ⇒
#    `live_worker` từ chối chạy, `score_miou` chặn chấm (ticket #36). Đường web KHÔNG dump mask nên
#    không bị ảnh hưởng.
python tools/live_worker.py --source data/binh1.mp4 --out-dir /tmp/run1 --bbox 300,275,150,410 \
    --image-size 192 --vos-every 1 --dump-mask-frames "0,40,80,120,160,200,240,280" \
    --stop-after-frames 300

# 5) chấm
python scripts/score_miou.py score --gt docs/gt/binh1_tay --pred-dir /tmp/run1/masks \
    --out data/miou_binh1_tay_metrics.json
```

Mask dump là mask **thô** của model (trước bước làm mượt `--mask-smoothing`) — đúng cái cần chấm.
Cạnh các file mask có `manifest.json` (nguồn · `image_size` · `vos_every` · `bbox` · frames yêu cầu);
`score_miou` copy nó vào `meta.mask_manifest` của artifact ⇒ số mIoU tự trả lời được "mask sinh ra ở
cấu hình nào" thay vì tin lời người chạy.

`--vos-every` **khác 1 bị CLI từ chối** khi có `--dump-mask-frames`: với N > 1 model không hề thấy
frame không chia hết cho N ⇒ mask không tồn tại (trước đây chỉ cảnh báo ở cuối phiên, quá muộn).

Lưu ý khi tô: **không** dùng chính SAM 2 để sinh mask rồi sửa lại — nếu dùng thì phải khai
`--gt-do-model-goi-y` và script sẽ **từ chối** dùng bộ GT đó làm bằng chứng (nó có thể dùng để tự
kiểm đường ống, không để tuyên bố độ chính xác).

## 3. Demo đã chạy: fixture TỔNG HỢP (chỉ để kiểm đường chấm)

```bash
python scripts/make_synthetic_gt_clip.py          # clip + GT biết trước (ô vuông 60 px trên nền nhiễu)
# bbox của frame 0 = bbox_xywh trong docs/gt/synthetic_tong_hop/index.json
python tools/live_worker.py --source data/synthetic_gt.mp4 --out-dir /tmp/demo_gt \
    --bbox 20,90,60,60 --image-size 192 \
    --vos-every 1 --dump-mask-frames "0,6,12,18,23" --stop-after-frames 30
python scripts/score_miou.py score --gt docs/gt/synthetic_tong_hop --pred-dir /tmp/demo_gt/masks \
    --out data/miou_synthetic_2026-11-14_metrics.json
```

Kết quả: **mIoU 0,9354 trên 5 frame**, `coverage = 0,208` (5/24 frame có GT được chấm) —
`data/miou_synthetic_2026-11-14_metrics.json`. Coverage nằm trong artifact, không chỉ in ra màn hình.
**Đây là CẬN TRÊN**: GT ≡ đúng vùng pixel của ô vuông và prompt là đúng bbox của nó. Cấm trích như
"mIoU trên video thật/DAVIS" (AGENTS §6).

## 4. Trạng thái trên video THẬT (15-11)

**Chưa có GT `silhouette`** cho video thật (cần người tô theo bước 2 — không tự động hoá trung thực
được). Đã có **GT hộp bao** cho `binh1` (12 frame): `docs/gt/binh1_hopbao` — dựng từ ngưỡng màu nhãn
tím + người soi 12/12 frame, sửa tay frame 62.

Số hiện có (`data/miou_binh1_hopbao_2026-11-15_metrics.json`, mask @192, `vos_every 1`):
**IoU(mask, hộp) = 0,6464** (n=12, min 0,469 @f12, max 0,774 @f92) và **`mask_ngoai_gt` trung bình
3,9 %** (tệ nhất 29,4 % @f62 — frame GT sửa tay, đọc kèm). Đây **không** phải mIoU phân đoạn; xem
`docs/so-lieu-bao-cao.md` (cột "cấm trích") trước khi đưa vào slide.

**`mIoU_p05` = `None` trên artifact này** (ticket #23): phân vị 5 % chỉ được công bố khi có ≥ **30**
frame chấm được — cùng ngưỡng với `drift_iou_p05`/`mask_age_p95` trong `status.json`. Với n = 12,
"p05" **chính là** frame xấu nhất (chỉ số 0,05 × 11 = 0,55 ⇒ vẫn nằm giữa min và phần tử nhỏ thứ hai)
⇒ công bố nó thành p05 là làm con số trông đáng tin hơn thực tế. Đọc cột `frames` của artifact để biết
frame nào xấu nhất; muốn p05 thật thì phải có ≥ 30 frame GT.

Muốn có mIoU phân đoạn: `score_miou.py label --dang-gt silhouette …` → tô **đặc** silhouette →
`score --gt docs/gt/<tên>`; thêm 1 dòng vào `REGISTRY` của `scripts/so_lieu_bao_cao.py` rồi chạy lại
script đó để số vào `docs/so-lieu-bao-cao.md`.

## 5. Liên quan

- `docs/so-lieu-bao-cao.md` — nơi mọi số được trích (kèm cột "CẤM trích thành").
- `docs/bang-cau-hinh.md` — chọn cấu hình (`image_size` × `vos_every`) có ngưỡng nhiễu.
- `scripts/measure_live_relay.py` — đo đường ống trên camera thật (KHÔNG đo độ chính xác).
