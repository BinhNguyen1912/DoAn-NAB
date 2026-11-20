# 20-11-2026 — `image_size` 192 vs 320: lần đầu đo ĐỘ CHÍNH XÁC (IoU ô vs GT người tô), không phải `drift`

## 1. Mục tiêu

Trả lời bằng số: **tăng `image_size` lên 320 có làm ô bám ĐÚNG hơn không?** Trước nay repo chỉ có
`drift_iou` (độ tự nhất quán, KHÔNG phải độ chính xác) và FPS. Có GT người tô ở frame giữa khe (`b1b`)
thì mới đo được độ chính xác thật.

## 2. Input

- GT `docs/gt/b1b` (7 frame người tô, `chon_frame = {giua_khe 12, vos_every 3, khung 0:110,165:262}`).
- Clip `data/binh1.mp4`, ô chai `300,275,150,410`, `--vos-every 3`, `--frames 300`, `--lan 3`.
- Dụng cụ: `scripts/ab_o_hien_thi_vs_gt.py` **sau khi mở rộng** (commit `6969fc4`) — `--image-size`
  nhận **danh sách** ⇒ A/B **chèn kẽ trong cùng phiên**. Vì sao bắt buộc: cùng ngày, hai phiên A/B
  `max_mad` cho **hai phán quyết ngược nhau** (nhiễu 0,034 → 0,022) ⇒ so hai phiên là vô nghĩa.

## 3. Công việc đã thực hiện

1. Mở rộng `ab_o_hien_thi_vs_gt.py`: khoá lần chạy thành `"<image_size>/<max_mad>"`, vòng lẻ đảo thứ tự,
   `--image-size` nhận danh sách.
2. Tách hàm thuần `cau_hinh_lech()` — ba trạng thái `image_size` KHÔNG lẫn: khớp / lệch / **CHƯA KIỂM
   ĐƯỢC** (`None`); `lech == []` không được đọc thành "đã đúng".
3. Chấm **hai lần**: một lần trên cây bẩn (script chưa commit) và một lần trên cây sạch — để tự kiểm
   độ tái lập.

## 4. Output / Kết quả

### 4.1 320 TỆ HƠN HẲN — hai lần đo độc lập cùng kết luận

| Lần | `git_dirty_code` | 192 | 320 | chênh | nhiễu | phán quyết |
|---|---|---|---|---|---|---|
| 1 | true | 0,6074 ± 0,0229 | 0,3651 ± 0,0663 | **−0,2423** | 0,0663 | 320 tệ hơn |
| 2 | **false** (`6969fc4`) | **0,5960 ± 0,0150** | **0,3870 ± 0,0817** | **−0,2090** | 0,0817 | 320 tệ hơn |

Khác với ca `max_mad` (dấu nhất quán nhưng độ lớn nằm trong nhiễu), ở đây **chênh lớn gấp 2,5–3,6 lần
ngưỡng nhiễu** và tái lập được ⇒ kết luận bền vững: **không dùng `image_size 320` để bám chính xác
hơn trên clip này**.

Theo cặp (21 cặp): 192 thắng **16/21** frame; 320 chỉ thắng ở f2 (+0,186), f182 (+0,064), f242 (+0,031).

### 4.2 Vì sao 320 tệ — mất dấu, không phải "ô hơi lệch"

| frame | IoU 320 | ô hiển thị (320) | hộp GT |
|---|---|---|---|
| 62 | **0,000** | 317,254 → 445,678 | 76,0 → 234,504 |
| 92 | 0,117 | 339,0 → 485,502 | 285,337 → 433,850 |
| 182 | **0,000** | **không vẽ ô nào** | 324,227 → 507,807 |

(Ba dòng này lấy từ `lan_chay["320/1.5"][0]` của artifact `6969fc4`. Ở f182 không có ô nào được vẽ;
`cham()` chấm **0,0** — "GT có vật mà không có ô" là bám sai thật, không phải "không đo được".)

Ô ở 320 **đứng yên quanh vị trí ban đầu** (`300,275,150,410`) trong khi chai đã đi chỗ khác ⇒ VOS
**mất dấu** ngay sau f2 (f2 lại là frame 320 tốt nhất: 0,7649 vs 0,5790). Ở 192 cùng frame: 0,579 / 0,383 / 0,642.

`iou_min` của 320 = **0,000 ở 2/3 lần chạy** (lần 3 = 0,1147) ⇒ `tong_hop.iou_min = 0,0382 ± 0,0662`.
ĐÍNH CHÍNH: bản đầu của log ghi "cả 3 lần" — đúng là **2/3**; bảng dưới cũng được dựng lại từ artifact
`6969fc4` (bản đầu lấy từ lần chạy bẩn chưa commit, toạ độ khác).

⇒ 320 không chỉ chậm hơn 1,8–2,5× (AGENTS §6) mà còn **làm hỏng việc bám**. Khớp với kết luận cũ
(`drift_iou` 320 thấp hơn) bằng một thước đo khác — lần này là **độ chính xác**.

### 4.3 `measured_fps` = 29,9 ở CẢ HAI cỡ

Đúng như AGENTS §6: `measured_fps` bị LK lấp ⇒ **cấm** dùng nó để so cấu hình. Muốn nói "320 chậm hơn"
phải dùng `vos_ms` từ `./run ab`, không phải cột FPS của artifact này.

## 5. Vấn đề & cách xử lý

- **Cây bẩn làm artifact không tái lập**: lần 1 chấm khi script còn sửa dở ⇒ `git_dirty_code=true`.
  Đã commit dụng cụ (`6969fc4`) rồi chấm lại; artifact giữ lại là lần 2.
- Suýt so hai phiên: đã gộp cả hai cỡ vào **một** lệnh (chèn kẽ) đúng quy tắc AGENTS §6.

## 6. Next steps

1. ~~`image_size` 320~~ — **loại**, đã đo (tệ hơn 0,21 IoU, mất dấu).
2. Câu hỏi còn mở: sai số 111–128 px ở f2/f92/f212 là do **ô đóng băng ở giữa khe** (`lk_ok_frac` ≈ 0,05)
   hay do model? Đo bằng cách cho `vos_every` = 1 / 2 / 3 trong **cùng một phiên** (`--vos-every` nhận
   danh sách như `--image-size`) ⇒ lượng hoá bằng số "cái giá của hybrid 30 FPS".
3. Nội suy cả **tỉ lệ** trong `LkBoxTracker` (hiện `bbox = (x+dx, y+dy, w, h)`) — chỉ làm nếu (2) cho
   thấy ô đóng băng mới là nguồn sai số chính.

## 7. Tài liệu tham khảo

- `docs/task/20-11-2026-cham-o-hien-thi-tren-gt-giua-khe.md` (lần đo `max_mad`, hai phiên lật phán quyết)
- `docs/task/14-11-2026-do-lai-bbox-dung-ket-luan-khong-can-train-lai.md` (320 làm `drift_iou` giảm)
- Artifact: `data/ab_image_size_b1b_2026-11-20_metrics.json` (`git_rev 6969fc4`, `git_dirty_code=false`,
  `image_size_chua_kiem_duoc 0`, `cau_hinh_hieu_luc_lech []`)

## 8. ĐÍNH CHÍNH sau review độc lập (PR #64)

| Reviewer nêu | Thực tế trong artifact `6969fc4` | Đã sửa |
|---|---|---|
| "`iou_min = 0,000` ở **cả 3 lần**" | 2/3 lần (lần 3 = 0,1147) ⇒ `iou_min.mean = 0,0382 ± 0,0662` | mục 4.2 |
| Bảng §4.2 dẫn toạ độ **không có trong artifact** (f92 `372,0→527,523`, f182 `412,237→566,770`) — lấy từ lần chạy BẨN chưa commit | f92 `339,0→485,502`; f182 **không vẽ ô nào** | mục 4.2 |
| Commit message `ebad7b1` lặp lại câu sai "iou_min=0,000 cả 3 lần" | — | ghi tại đây; kết luận **"320 tệ hơn 0,21 IoU" KHÔNG đổi** |

Bài học: **artifact phải được nêu tên + đọc lại khi viết log**, không chép số từ terminal của lần chạy
khác (lần bẩn) — cùng lý do đã phải chấm lại trên cây sạch.
