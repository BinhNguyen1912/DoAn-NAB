# 19-11-2026 — A/B LIVE cửa chống-trôi LK (`--lk-max-mad`) trên 2 clip — bước 2 ticket #38

## Mục tiêu

Bước 1 (PR #52) đo **offline** và kết luận cửa `DEFAULT_MAX_MAD = 1,5` px quá chặt. Nhưng phép đo đó là
**một bước nhảy ~3 frame** với mốc là **ô VOS** — chưa phải đường live (đi **chuỗi** 1 frame/bước, ô
hiển thị còn qua `_interp`). Việc của phiên này: **phơi cờ để đo**, chạy A/B live **chèn kẽ** trên 2 clip,
và chỉ đổi mặc định nếu số + ảnh cùng đạt.

## Input

- `binh1.mp4` ô chai `300,275,150,410` · `binh2.mp4` ô chai `330,330,150,360` (theo
  `docs/demo-clip-va-o-chon.md`), `image_size 192`, `vos_every 3`, `--frames 262`, cửa sổ
  `0:110,165:262` (lúc vật còn trong khung).
- Ngưỡng đăng ký trước (ticket #38): `lk_ok_frac` tăng **≥ 2×** VÀ `drift_iou` **không giảm quá 0,010**
  (ngưỡng nhiễu ô chai, AGENTS §6) ⇒ mới đủ điều kiện đổi mặc định.

## Công việc đã thực hiện

1. **Phơi tham số, KHÔNG đổi mặc định**: `LiveTrackConfig.lk_max_mad` (mặc định
   `light_tracker.DEFAULT_MAX_MAD`), cả `_lk` và `_interp` dùng **cùng** một cửa (lệch ngưỡng thì số đo
   không nói được gì); `--lk-max-mad` cho `tools/live_worker.py`; `cau_hinh_yeu_cau` **echo**
   `lk_max_mad` vào `status.json` (không echo thì không ai biết artifact đo ở 1,5 hay 6,0 — đúng lý do
   `cau_hinh` tồn tại, review 15-11).
2. **`scripts/ab_lk_max_mad.py`** — chạy thẳng worker (không qua API: trường này **chưa** có trong hợp
   đồng HTTP nên nó là **dụng cụ đo**, không phải tính năng), **chèn kẽ** `a,b,a,b,a,b` và **đảo thứ tự**
   ở vòng lẻ để "cấu hình chạy sau" không luôn được ưu ái. Artifact ghi `cau_hinh_hieu_luc_lech` (lần
   chạy nào echo sai thì thoát **1**) + `git_rev`/`git_dirty_code`.
3. 9 test hàm thuần (`tests/test_ab_lk_max_mad.py`).

## Output / Kết quả

`data/ab_lk_max_mad_2026-11-19_metrics.json` (`git_rev b5dea7a`, `git_dirty_code false`, 3 lần/cấu hình,
`cau_hinh_hieu_luc_lech []`). **Artifact là lần chạy thứ hai** (lần đầu `git_rev f853868`, cùng lệnh,
cùng kết luận: binh1 ×3,73 / binh2 ×1,61, drift binh1 +0,071) — trích số phải lấy từ **artifact này**.

| clip | `max_mad` | `lk_ok_frac` (±) | `drift_iou` | `measured_fps` | `vos_ms` | `mask_age_p95` |
|---|---|---|---|---|---|---|
| binh1 | **1,5** | **0,119 ± 0,014** | 0,495 | 29,90 | 93,8 | 293,2 |
| binh1 | 3,0 | 0,232 ± 0,004 | 0,513 | 29,83 | 91,4 | 301,6 |
| binh1 | **6,0** | **0,402 ± 0,060** | **0,561** | 29,73 | 102,7 | 303,2 |
| binh2 | **1,5** | **0,405 ± 0,005** | 0,710 | 29,87 | 107,3 | 303,1 |
| binh2 | 3,0 | 0,611 ± 0,054 | 0,726 | 29,87 | 98,7 | 301,9 |
| binh2 | **6,0** | **0,636 ± 0,010** | 0,717 | 29,87 | 101,9 | 301,9 |

- **LK nhận nhiều hơn thật, đơn điệu theo `max_mad`, trên CẢ HAI clip**: binh1 **×3,37** (0,119 → 0,402),
  binh2 **×1,57** (0,405 → 0,636). Gộp 2 clip ×1,98 — **chỉ để tham khảo**, không dùng để chốt.
- **`drift_iou` KHÔNG giảm ở đâu**: binh1 **+0,067** (0,495 → 0,561; std 0,009–0,030 ⇒ ngoài ngưỡng
  nhiễu, cải thiện thật), binh2 +0,007 (trong ngưỡng ±0,010 ⇒ **không phân biệt được**).
- **Quyết định trong artifact**: `quyet_dinh.du_dieu_kien_doi_mac_dinh = false`, `so_clip_dat 1/2` —
  đúng bằng kết luận của log, vì luật là **AND trên mọi clip**, không phải trung bình.
- Không có giá nào về tốc độ: `measured_fps` 29,73–29,90; `mask_age_p95` 293–303 ms (chênh ≤ 10 ms,
  dưới ngưỡng ±32 ms của phiên ngắn); `vos_ms` 91,4–107,3 **không theo thứ tự cấu hình** (binh2 @1,5 =
  107,3 còn @6,0 = 101,9) ⇒ đó là dao động giữa các lần chạy, không phải giá của `max_mad`.
- Kiểm **ảnh** (`docs/media/lk/so_sanh_max_mad_binh1.jpg`, frame 60 và 95, trái 1,5 / phải 6,0): ô đỏ
  vẫn **nằm trên chai** ở cả hai mức, không nhảy sang nền. HUD của **phiên kiểm ảnh riêng** đó ghi `LK`
  5,2 ms (1,5) / 3,1 ms (6,0) — phiên này **không có artifact**; `lk_ms` trong artifact (3 lần/cấu hình)
  là 2,37 / 3,51 ms cho binh1 ⇒ đừng trộn hai nguồn.

## Vấn đề & cách xử lý

- **Luật kết luận của mình sai một chiều**: bản đầu dùng `abs(chênh drift_iou) <= 0,010` để xét "không
  phân biệt được" ⇒ coi cả **cải thiện** +0,033 là "không đủ điều kiện đổi". Đã sửa thành chỉ chặn
  chiều **giảm** (`chenh >= -0,010`) + thêm test. Đây đúng lớp "cổng danh nghĩa" đã gặp nhiều lần.
- **`status.json` ghi stats ở cấp NGOÀI CÙNG**, không lồng trong `stats`; bản đầu đọc `status["stats"]`
  ⇒ `fps`/`mask_age_p95` ra `None` **im lặng**, tức câu "không làm chậm phiên" không có bằng chứng
  (bẫy "0/None ≠ đã đo"). Đã sửa + test khoá đúng khoá.
- **Ngưỡng 2× KHÔNG đạt trên binh2** (1,57×). Ghi nhận trung thực thay vì gộp 2 clip cho ra 2,04× rồi
  tuyên bố "đạt": binh2 vốn đã 42 % ở 1,5 (vật to, ít bị tay che) nên dư địa ít hơn hẳn binh1 (11 %).
- **Kiểm ảnh mới là 2 frame × 1 clip** — đủ để nói "không thấy hiện tượng trôi vào nền", **KHÔNG** đủ để
  nói "đã kiểm hết".

## Next steps (quyết định: **CHƯA đổi mặc định**)

Đủ bằng chứng nới cửa **có lợi và không thấy hại**, nhưng **chưa** đổi `DEFAULT_MAX_MAD` vì tiêu chí
đăng ký trước chỉ đạt 1/2 clip và `drift_iou` vẫn là độ tự nhất quán với **ô VOS**, không phải độ chính
xác bám vật. Điều kiện chốt: **mIoU vs GT người gán** (`./run miou`) ở 1,5 vs 6,0 trên cùng các frame GT
của `binh1` — nếu mIoU ở 6,0 **không thấp hơn** 1,5 thì đổi mặc định sang 6,0.

Trong lúc chờ: demo **có thể** chạy `tools/live_worker.py --lk-max-mad 6.0` (đã phơi cờ), nhưng báo cáo
phải ghi rõ đó là **cấu hình đo**, không phải mặc định.

## Tài liệu tham khảo

- PR #52 (đo offline), ticket #38, `scripts/ab_lk_max_mad.py`, `tests/test_ab_lk_max_mad.py`
- `src/live_tracking.py` (`lk_max_mad`, echo `cau_hinh`), `tools/live_worker.py` (`--lk-max-mad`)
- `docs/media/lk/so_sanh_max_mad_binh1.jpg` · `data/ab_lk_max_mad_2026-11-19_metrics.json`
