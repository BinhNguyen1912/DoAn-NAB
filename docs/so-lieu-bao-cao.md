# Số liệu dùng cho báo cáo — sinh tự động, đừng sửa tay

> File này do `python scripts/so_lieu_bao_cao.py` sinh từ **artifact đã commit** (`data/*`).
> Sửa tay sẽ bị ghi đè; nếu cần thêm dòng thì thêm vào `REGISTRY` trong script.
> Chạy `python scripts/so_lieu_bao_cao.py --check` để CI báo khi file lệch artifact.
>
> Cột **CẤM trích thành** là phần quan trọng nhất: cùng một con số có thể bị đọc thành hai nghĩa
> khác nhau, và repo này đã 3 lần suýt trích sai (`drift_iou` → "độ chính xác"; tỉ lệ rỗng cả phiên
> → "model mất dấu"; `mask_fps` → "mask 30 FPS").

| Tuyên bố | Số | Đơn vị | Artifact | Lệnh / khoá | CẤM trích thành |
|---|---|---|---|---|---|
| Tốc độ model ở `image_size 192` (đường live) | **98,6** | ms/frame | `data/lan2_chai_binh1_lan1_metrics.json` | `worker_status.vos_ms` | KHÔNG phải "thời gian xử lý một frame người xem thấy" — thiếu `pre_ms` (14,3 ms) và thời gian vẽ; xem artifact chu kỳ. |
| Nhịp mask ở `vos_every 3` (đường live) | **9,1** | lần/giây | `data/lan2_chai_binh1_lan1_metrics.json` | `worker_status.vos_fps` | CẤM viết "mask 30 FPS": HUD 29,9 FPS là nhịp VẼ, mask chỉ ~8–10 lần/giây. |
| Tuổi dữ liệu ảnh, định nghĩa CŨ (age + vos) | **221,4** | ms (p95) | `data/lan2_chai_binh1_lan1_metrics.json` | `worker_status.mask_age_p95` | Chỉ dùng để SO với số trước 14-11. Số mới là `mask_age_total_ms` (tuổi dữ liệu thật). |
| Tuổi dữ liệu ảnh, tuổi THẬT (queue+pre+vos+post+age) | **301,2** | ms (p95) | `data/chu_ky_chai_binh1_1vong_lan2_metrics.json` | `worker_status.mask_age_p95` | Một lần chạy 11 s (1 vòng) — 3 lần cho 268,7–301,2 ms. KHÔNG so với 271–273 ms của bộ số 13-11 (định nghĩa CŨ: chỉ age+vos). |
| Chu kỳ VOS (1/vos_fps thực) | **101,47** | ms | `data/chu_ky_chai_binh1_1vong_lan2_metrics.json` | `worker_status.cycle_ms` | 3 lần: 101,5–121,6 ms. Các pha là **mẫu của lần VOS gần nhất**, KHÔNG cùng một chu kỳ ⇒ đừng cộng 4 pha rồi đòi khớp `cycle_ms`. |
| Tiền xử lý mỗi frame (resize + tensor) | **12,39** | ms | `data/chu_ky_chai_binh1_1vong_lan2_metrics.json` | `worker_status.pre_ms` | 3 lần: 11,6–13,1 ms. KHÔNG cộng vào `vos_ms` khi báo cáo (đếm hai lần) — nhưng PHẢI cộng khi nói "một frame tốn bao lâu". |
| Frame chờ trong worker trước khi được xử lý | **75,87** | ms | `data/chu_ky_chai_binh1_1vong_lan1_metrics.json` | `worker_status.queue_ms` | Mẫu của lần VOS CUỐI, dao động mạnh: 3 lần cho 2,1–75,9 ms (một lần đo n=1 từng ra 0,33 ms ⇒ cấm trích một lần chạy làm "queue ≈ 0"). |
| Tỉ lệ mask rỗng khi vật CÒN trong khung (`binh1`, chai) | **0,016** | tỉ lệ | `data/sach_chai_binh1_1vong_metrics.json` | `cua_so_frame.trong_khung.empty_frac` | CẤM trích tỉ lệ rỗng cả phiên (0,36) thành "model mất dấu 36 %": phần lớn là vật ngoài khung. |
| Tỉ lệ mask rỗng khi vật CÒN trong khung (`binh2`, chai trắng) | **0** | tỉ lệ | `data/sach_chai_binh2_1vong_metrics.json` | `cua_so_frame.trong_khung.empty_frac` | Cùng cảnh báo trên; và ô cũ `200,400,300,500` phủ 2 chai + 2 tay nên số cũ không dùng. |
| Độ tự nhất quán ô bao ↔ mask VOS (`binh2`, trong khung) | **0,726** | IoU | `data/sach_chai_binh2_1vong_metrics.json` | `cua_so_frame.trong_khung.drift_iou_mean` | CẤM gọi là "độ chính xác bám" — đây là độ TỰ NHẤT QUÁN (AGENTS §6); độ chính xác cần GT mask. |
| Số vòng nguồn file đã phát lại | **2,71** | vòng | `data/sach_lap27vong_binh1_metrics.json` | `cua_so_frame.so_vong` | Chỉ là ước tính từ frame đã phát/xử lý chia số frame clip; nguồn mạng ⇒ `null`. |
| mIoU mask vs GT bị che 50 % (fixture TỔNG HỢP, `image_size 320`) | **0,8922** | IoU | `data/occlusion_metrics_320_metrics.json` | `ket_qua.che 50%.mask_miou_trong` | ĐÂY LÀ CẬN TRÊN trên ảnh tổng hợp (GT = pixel một ô vuông màu, prompt = đúng bbox GT) — CẤM trích như "mIoU trên video thật/DAVIS". |
| Watchdog phát hiện worker chết (mode worker, `kill -9`) | **116,1** | ms | `data/watchdog_2026-11-09_metrics.json` | `tom_tat.tg_bao_error_ms.mean` | Nhanh vì `proc.poll()` bắt được; ca "sống mà treo" mất ~15 s, CẤM trích 0,1 s cho ca đó. |
| Nhịp mask ở `vos_every 2` (cấu hình nhanh nhất, `image_size 192`) | **7,53 ± 0,12 (n = 3)** | lần/giây | `data/bang_cau_hinh_2026-11-14_metrics.json` | `cau_hinh.192_2.vos_fps.mean` | CẤM viết 'mask 30 FPS' và CẤM so với FPS phát 29,7 — hai nhịp khác nhau. |
| Tuổi dữ liệu ảnh p95 ở `image_size 192`, `vos_every 3` | **315,8 ± 16,36 (n = 59)** | ms (p95) | `data/bang_cau_hinh_2026-11-14_metrics.json` | `cau_hinh.192_3.mask_age_p95.mean` | `vos_ms` chỉ là phần model; 'một frame tốn bao lâu' phải cộng `pre_ms`. p95 dựa trên `cau_hinh.192_3.age_n` mẫu — đọc kèm, n nhỏ thì p95 ≈ max. |
| Tuổi dữ liệu ảnh p95 ở `image_size 320`, `vos_every 3` (chi tiết vật nhỏ) | **637,43 ± 34,91 (n = 59)** | ms (p95) | `data/bang_cau_hinh_2026-11-14_metrics.json` | `cau_hinh.320_3.mask_age_p95.mean` | Chỉ được nói 'cũ hơn hẳn' nếu chênh với 192 LỚN HƠN `std` lớn hơn của hai dòng (đọc `std` ngay trong cột này, đừng gõ tay). |
| mIoU mask vs GT trên fixture TỔNG HỢP (ô vuông trên nền nhiễu) | **0,9354** | IoU | `data/miou_synthetic_2026-11-14_metrics.json` | `ket_qua.mIoU` | CẬN TRÊN: GT ≡ pixel ô vuông, prompt = đúng bbox của nó. Số này chấm trên `so_frame_cham` frame trong tổng `so_frame_gt` — CẤM nói 'mIoU cả clip'. CẤM trích như mIoU trên video thật — muốn số thật thì gán tay (`scripts/score_miou.py label`). |
