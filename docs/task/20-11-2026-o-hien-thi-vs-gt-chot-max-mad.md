# 20-11-2026 — Chấm **ô người xem thấy vs GT người tô** để chốt `max_mad` (ticket #38)

## Mục tiêu

`mIoU` (0,7794, PR #60) **không** chốt được `max_mad`: chấm mIoU hợp lệ buộc `--vos-every 1`, mà cấu
hình đó **tắt hẳn LK** ⇒ `max_mad` không tham gia phép đo. `drift_iou` thì chỉ nói ô hiển thị có khớp
**ô VOS** (độ tự nhất quán). Vậy cần phép đo thứ ba: **IoU(ô ĐANG HIỂN THỊ, hộp bao suy từ mask người
tô)** — "ô bám có đúng chỗ không", đúng thứ người xem quan tâm.

## Công việc đã thực hiện

1. **Dụng cụ mới `--dump-shown-csv`** (`LiveTrackConfig.dump_shown_csv`, mặc định **tắt**): ghi
   `frame_idx,x1,y1,x2,y2,lk_ok` cho **mọi frame đã phát**. Vì sao cần: CSV drift chỉ có dòng ở **lần
   VOS** (mỗi 3 frame), nên không chấm được các frame GT lẻ (`binh1`: 91/181/211/241 ≡ 1 mod 3).
   Ghi file **ngoài `_stats_lock`** (I/O dưới lock sẽ chặn luồng VOS — cùng lý do với CSV drift); lỗi
   ghi file **không** làm chết phiên (in cảnh báo + tự tắt).
2. **`scripts/ab_o_hien_thi_vs_gt.py`**: hộp GT = bao của mask người tô (bỏ `gt_rong`); chạy worker
   **chèn kẽ** (a,b,a,b,a,b, đảo chiều vòng lẻ), chấm `IoU(ô hiển thị, ô GT)`, rồi so **hai cách**:
   theo **trung bình** (ngưỡng nhiễu = `std` lớn hơn của hai bên) và theo **CẶP** (cùng lần chạy, cùng
   frame — khử phương sai giữa lần chạy).
3. Quy tắc chấm giữ nguyên tinh thần repo: GT có vật mà **không có ô hiển thị** ⇒ `0,0` (bám sai thật),
   **không** bỏ mẫu; hộp đảo toạ độ ⇒ `None` (không đo được), **không** quy thành 0; frame GT không có
   trong CSV ⇒ `thieu_frame` (chưa chạy tới), **không** phải 0.

## Output / Kết quả

`data/ab_o_hien_thi_vs_gt_2026-11-20_metrics.json` (`git_rev 0e84260`, `git_dirty_code false`, — **tệp này
KHÔNG còn trong cây**, xem ĐÍNH CHÍNH ở cuối mục 8
3 lần/cấu hình, `cau_hinh_hieu_luc_lech []`, 7 frame GT, cùng `binh1` + ô chai `300,275,150,410`, @192,
`vos_every 3`, 300 frame):

| `max_mad` | IoU(ô hiển thị, ô GT) | tệ nhất | `lk_ok_frac` ở các frame GT | FPS |
|---|---|---|---|---|
| **1,5** | **0.6203 ± 0.0137** | 0.421 | **0.000** | 30.03 |
| **6,0** | **0.6094 ± 0.0308** | 0.340 | **0.429** | 29.93 |

- **Theo trung bình**: chênh **-0.0109** ≤ ngưỡng nhiễu **0.0308** ⇒ **KHÔNG phân biệt được**.
- **Theo cặp** (21 cặp, `can_bo_cap False`): 6,0 tốt hơn **7**, 1,5 tốt hơn
  **8**, bằng **6**; chênh trung bình **-0.0109**, cặp tốt nhất
  **+0.1774**, cặp tệ nhất **-0.4021** ⇒ **không có chiều thắng nhất quán**.
> ⚠ Bảng + `git_rev 0e84260` ở trên **không kiểm lại được từ cây** (artifact bị phiên `b1b` ghi đè
> cùng đường dẫn — xem §8). Quyết định giữ 1,5 dựa trên **sáu phiên có dấu đổi chiều**, không dựa riêng bảng này.

- **BỐN lần A/B cho cùng kết luận "không phân biệt được"**, và **dấu của chênh lệch đổi chiều**
  (+0,032/nhiễu 0,065 · +0,003/0,051 · +0,018/0,031 · **-0.0109/0.0308**) ⇒
  chênh lệch nằm trong nhiễu, không phải hiệu ứng của cấu hình. Chi tiết từng lần chạy cũng đổi (lần thì
  "6,0 không tệ hơn ở cả 7 frame", lần thì 1,5 tốt hơn 6–8 cặp) ⇐ đúng lý do phải chạy ≥ 2 lần và so
  **theo cặp**, không tin một lần chạy.
- `so_lan_chay_loi` = `{'1.5': 0, '6.0': 0}` ⇒ 6/6 lần chạy hợp lệ, và **6/6 lần `so_dong_khop_frame
  = True`** (CSV ô-hiển-thị có đúng 1 dòng mỗi frame đã phát) ⇒ không mất mẫu, không ghi trùng.

## Kết luận cho ticket #38

1. **KHÔNG đổi `DEFAULT_MAX_MAD`.** Ba phép đo độc lập cùng chỉ một hướng: nới cửa (1,5 → 6,0) làm LK
   **dám nhận nhiều hơn** (0,095 → 0,429 ở các frame GT; 0,12 → 0,44 trên CSV drift) **nhưng ô không
   đúng hơn** so với GT người tô (chênh 0,003 ≤ nhiễu 0,051).
2. Vì thế câu "hybrid VOS+LK" phải nói **chính xác**: nó làm ô **chuyển động** (không đứng yên 88 % thời
   gian) chứ **chưa** chứng minh **chính xác hơn** ô đóng băng. Muốn nói "tốt hơn" thì phải cải tiến bộ
   nội suy (hiện chỉ **dịch** ô theo trung vị vector — không **co giãn** theo vật ra gần/xa), rồi đo lại
   bằng chính script này.
3. **Không** dùng `drift_iou` để biện minh cho việc đổi ngưỡng: nó là độ tự nhất quán, đã có số chứng
   minh nới cửa làm nó **tăng** (+0,07 trên `binh1`) trong khi độ đúng **không đổi** — đúng cái bẫy
   AGENTS §6 cảnh báo.

## Vấn đề & cách xử lý

- **Frame GT đều nằm sát lần VOS** (`0,30,60` ≡ 0 mod 3; `91,181,211,241` ≡ 1 mod 3) ⇒ LK chỉ có **1
  bước** để chứng minh mình ở đó. Muốn cửa MAD được thử đúng mức phải có GT ở **giữa khe** (≡ 2 mod 3).
  Đây là hạn chế của phép đo, đã ghi vào ticket.
- `lk_ok_frac` ở đây (0.048 / 0.429) khớp với số trên CSV drift
  (0,12 / 0,44) ⇒ hai đường đo **nhất quán** với nhau (cùng một luồng worker, nên đây là kiểm chéo chứ
  không phải hai phép đo độc lập).

## Review độc lập PR #61 — 3 P1 (đều trong dụng cụ đo), đã sửa

1. **"Không có ô" và "ô HỎNG" bị gộp**: `doc_shown` đổi hộp đảo toạ độ thành `None`, rồi `cham` chấm
   `0,0` cho `None` ⇒ hộp hỏng bị tính là "bám sai thật" (docstring hứa `khong_do_duoc` nhưng dict không
   có khoá đó). Test cũ gọi `cham` **trực tiếp** nên **xanh giả** (không đi qua `doc_shown`). Nay có hai
   sentinel `KHONG_CO_O`/`O_HONG`, khoá `khong_do_duoc`, và test đi qua `doc_shown`.
2. **`std = None` (n < 2) bị coi là ngưỡng nhiễu 0** ⇒ mọi chênh lệch thành "TỐT HƠN/TỆ HƠN". Nay trả
   `phan_biet_duoc: None` + "KHÔNG kết luận: cần ≥ 2 lần chạy".
3. **Lần chạy HỎNG bị tính là "bám sai thật"**: worker chết ⇒ không có CSV ⇒ mọi frame GT thành `0,0`.
   Nay `lan_chay_hop_le()` (mã thoát 0, `state ∈ {stopped, done}`, CSV có dữ liệu), loại khỏi trung bình,
   ghi `so_lan_chay_loi`, thoát mã 1.
4. P2: bỏ `dir="/dev/shm"` (máy dev Windows không có) → `tempfile.gettempdir()`; kiểm hai cấu hình có
   **cùng số lần chạy** trước khi so cặp.
5. P3: ghi lỗi CSV vào `status.json` (`dump_shown_loi`) thay vì sửa `cau_hinh` (để giữ provenance "đã yêu
   cầu ghi"); sửa chữ "ba phép đo **độc lập**" → **"nhất quán"**.
6. P3 (vá sau, cùng PR): `doc_shown` **cảnh báo** khi `frame_idx` trùng (trước đó ghi đè im lặng);
   `so_dong_khop_frame()` đối chiếu số dòng `shown.csv` với `status.frames` (1 dòng/frame đã phát);
   `so_sanh_theo_cap` tự khai `can_bo_cap` khi hai bên lệch số lần chạy.

## Next steps

1. **Người dùng**: gán GT thêm ở các frame **giữa khe** `2,32,62,92,182,212,242` (bộ `b1b`) — đó là nơi
   ô hiển thị **hoàn toàn** do LK quyết định.
2. Nếu muốn "hybrid thật": cho `LkBoxTracker` nội suy cả **tỉ lệ** (vật ra gần/xa) rồi A/B lại bằng
   script này — mới có cửa để **tăng** IoU ô-vs-GT.
3. Ticket #38 đóng phần `max_mad`: quyết định **giữ 1,5**, kèm số.

## Tài liệu tham khảo

- `scripts/ab_o_hien_thi_vs_gt.py`, `tests/test_ab_o_hien_thi_vs_gt.py` (11 test)
- `src/live_tracking.py` (`dump_shown_csv`, `_ghi_o_hien_thi`), `tools/live_worker.py` (`--dump-shown-csv`)
- `docs/task/20-11-2026-miou-dau-tien-tren-video-that.md`, ticket #38

## 8. ĐÍNH CHÍNH sau review độc lập (PR #64) — bằng chứng không còn tái lập được

Reviewer đối chiếu cả cây và phát hiện: **artifact của phiên này không còn tồn tại**.
`grep` cho `0.6203`, `0.6094`, `0e84260` trong `data/` = **0 kết quả**.

- Nguyên nhân: mọi phiên cùng ngày đều ghi vào **cùng một đường dẫn**
  `data/ab_o_hien_thi_vs_gt_2026-11-20_metrics.json` (`--out` mặc định chỉ có NGÀY). Phiên `max_mad` trên
  bộ `b1` (`0e84260`) bị phiên trên bộ `b1b` (`891f4f5`) **ghi đè**; tệp cuối cùng đã được đổi tên thành
  `data/ab_max_mad_b1b_2026-11-20_metrics.json` (nội dung = phiên `891f4f5`, KHÔNG phải phiên ở bảng trên).
- Hệ quả: bảng số ở mục "Output / Kết quả" **không kiểm lại được từ cây**; tệp cùng tên cũ nay nói
  **ngược chiều** (`so_sanh = "ô hiển thị TỐT HƠN 0.029 IoU"`, chênh +0,0287 / nhiễu 0,0218) vì đó là
  **phiên khác** (bộ GT `b1b`, 7 frame giữa khe).
- Quyết định **giữ `DEFAULT_MAX_MAD = 1,5` KHÔNG đổi**: nó dựa trên **bốn phiên độc lập** có dấu chênh
  đổi chiều (+0,032 / +0,003 / +0,018 / −0,0109) — và phiên thứ năm cùng ngày (`b1b`: +0,020 ≤ 0,034,
  chạy trên cây BẨN và artifact của nó **cũng đã bị ghi đè**; chỉ là đối chứng, không trích như số đo tái lập được)
  cũng nằm trong nhiễu, còn phiên thứ sáu (`b1b` cây sạch: +0,029 > 0,022) nói "tốt hơn". **Sáu phiên
  không cho một chiều nhất quán ⇒ không chứng minh được**, đúng kết luận cũ.
- Bài học (đã áp dụng ngay): đặt tên artifact kèm **clip + bộ GT**
  (`ab_max_mad_b1b_…`, `ab_image_size_b1b_…`, `ab_vos_every_b1b_…`) để phiên sau không ghi đè phiên
  trước; và khi trích số phải **đọc lại tệp**, không chép từ terminal.
