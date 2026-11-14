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
| Tuổi dữ liệu ảnh, tuổi THẬT (queue+pre+vos+post+age) | **272,2** | ms (p95) | `data/chu_ky_chai_binh1_1vong_metrics.json` | `worker_status.mask_age_p95` | Chỉ của **1 vòng clip 11 s**, không phải 55 s; không so trực tiếp với số 271–273 ms (định nghĩa cũ). |
| Chu kỳ VOS và các pha | **105,6** | ms | `data/chu_ky_chai_binh1_1vong_metrics.json` | `worker_status.cycle_ms` | Pha là **mẫu hiện tại**, không phải trung bình phiên ⇒ đừng cộng 4 pha rồi đòi khớp `cycle_ms`. |
| Tiền xử lý mỗi frame (resize + tensor) | **14,25** | ms | `data/chu_ky_chai_binh1_1vong_metrics.json` | `worker_status.pre_ms` | KHÔNG cộng vào `vos_ms` khi báo cáo (sẽ đếm hai lần) — nhưng PHẢI cộng khi nói "một frame tốn bao lâu". |
| Frame có phải chờ trong worker không | **0,33** | ms | `data/chu_ky_chai_binh1_1vong_metrics.json` | `worker_status.queue_ms` | Số này ≈ 0 nên **cấm** dùng nó để đề xuất "đổi cadence cho nhanh hơn" — đã đo và bác. |
| Tỉ lệ mask rỗng khi vật CÒN trong khung (`binh1`, chai) | **0,016** | tỉ lệ | `data/sach_chai_binh1_1vong_metrics.json` | `cua_so_frame.trong_khung.empty_frac` | CẤM trích tỉ lệ rỗng cả phiên (0,36) thành "model mất dấu 36 %": phần lớn là vật ngoài khung. |
| Tỉ lệ mask rỗng khi vật CÒN trong khung (`binh2`, chai trắng) | **0** | tỉ lệ | `data/sach_chai_binh2_1vong_metrics.json` | `cua_so_frame.trong_khung.empty_frac` | Cùng cảnh báo trên; và ô cũ `200,400,300,500` phủ 2 chai + 2 tay nên số cũ không dùng. |
| Độ tự nhất quán ô bao ↔ mask VOS (`binh2`, trong khung) | **0,726** | IoU | `data/sach_chai_binh2_1vong_metrics.json` | `cua_so_frame.trong_khung.drift_iou_mean` | CẤM gọi là "độ chính xác bám" — đây là độ TỰ NHẤT QUÁN (AGENTS §6); độ chính xác cần GT mask. |
| Số vòng nguồn file đã phát lại | **2,71** | vòng | `data/sach_lap27vong_binh1_metrics.json` | `cua_so_frame.so_vong` | Chỉ là ước tính từ frame đã phát/xử lý chia số frame clip; nguồn mạng ⇒ `null`. |
| mIoU mask vs GT bị che 50 % (fixture TỔNG HỢP, `image_size 320`) | **0,8922** | IoU | `data/occlusion_metrics_320_metrics.json` | `ket_qua.che 50%.mask_miou_trong` | ĐÂY LÀ CẬN TRÊN trên ảnh tổng hợp (GT = pixel một ô vuông màu, prompt = đúng bbox GT) — CẤM trích như "mIoU trên video thật/DAVIS". |
| Watchdog phát hiện worker chết (mode worker, `kill -9`) | **116,1** | ms | `data/watchdog_2026-11-09_metrics.json` | `tom_tat.tg_bao_error_ms.mean` | Nhanh vì `proc.poll()` bắt được; ca "sống mà treo" mất ~15 s, CẤM trích 0,1 s cho ca đó. |
