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

`data/ab_o_hien_thi_vs_gt_2026-11-20_metrics.json` (`git_rev 44967fa`, `git_dirty_code false`,
3 lần/cấu hình, `cau_hinh_hieu_luc_lech []`, 7 frame GT, cùng `binh1` + ô chai `300,275,150,410`, @192,
`vos_every 3`, 300 frame):

| `max_mad` | IoU(ô hiển thị, ô GT) | tệ nhất | `lk_ok_frac` ở các frame GT | FPS |
|---|---|---|---|---|
| **1,5** | **0,5295 ± 0,0514** | 0,256 | **0,095** | 29,93 |
| **6,0** | **0,5327 ± 0,0236** | 0,120 | **0,429** | 29,93 |

- **Theo trung bình**: chênh **+0,0032** ≤ ngưỡng nhiễu **0,0514** ⇒ **KHÔNG phân biệt được**.
- **Theo cặp** (21 cặp): 6,0 tốt hơn **11**, 1,5 tốt hơn **5**, bằng **5**; chênh trung bình +0,0032,
  cặp tốt nhất **+0,257**, cặp tệ nhất **−0,592** ⇒ **không có chiều thắng nhất quán**.
- Ở lần chạy đầu, 6,0 **không tệ hơn ở cả 7 frame**; lần chạy lại thì có 5 cặp 1,5 tốt hơn (tới 0,59).
  ⇐ **Đây chính là lý do phải chạy ≥ 2 lần**: kết luận "không bao giờ tệ hơn" của một lần chạy **không
  tái lập**.

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
- `lk_ok_frac` ở đây (0,095 / 0,429) khớp độc lập với số trên CSV drift (0,12 / 0,44) ⇒ hai đường đo
  nhất quán, không phải lỗi dụng cụ.

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
