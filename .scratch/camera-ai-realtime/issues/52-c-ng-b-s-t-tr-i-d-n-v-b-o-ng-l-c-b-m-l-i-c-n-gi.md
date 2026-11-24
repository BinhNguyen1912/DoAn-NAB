# 52: Cổng bỏ sót TRÔI DẦN và báo đúng lúc BÁM LẠI — cần giữ prev qua mất dấu + phát hiện trôi (log-only)

**What to build:** Phiên thật `demoip_1124-162458` (129 frame, 36,4 s, `image_size 192`, `--smooth --no-reid`, `loadavg 2.49`, `git_rev 6b1dc3f`): người dùng báo *"focus nhầm một khúc (không cảnh báo), focus đúng thì ghi NGHI"*. Số liệu xác nhận đúng:

| giai đoạn | thực tế | cổng |
|---|---|---|
| f0–f68 | ô trên **thìa gỗ** (đúng) | im lặng ✅ |
| f69 | nhảy **109,6 px** (< ngưỡng 200) sang **bàn tay/cẳng tay** | **im lặng** ❌ |
| f70–f104 | ô trên tay/đáy khung, sai | **im lặng** ❌ |
| f106, f109, f112, f113 | **mất dấu** (`mask_area = 0`) | — |
| f107–f119 | bám lại vào **TÓC/ĐẦU** (`score` = **−0,8**); đáy ô **chạm mép dưới 71/124 frame** (`y2 > 470`) | **im lặng** ❌ |
| f120–f123 | ô ở **nền bên phải** (x 480–611) | **im lặng** ❌ |
| f124 | nhảy **393,7 px** → ô về đúng **thìa NHỰA trắng** (người dùng đã đổi vật) | **NGHI** ✅ nhưng người dùng đọc là "báo oan" |

Nguyên nhân kép:
1. **Mất dấu reset mốc**: `last_bbox = (0,0,0,0)` khi mask rỗng ⇒ mọi cú **bám lại** sau mất dấu KHÔNG được chấm (5 frame mất dấu ở phiên này ⇒ 5 cú nhảy không chấm).
2. **Cổng chỉ nhìn 1 bước**: trôi 60–150 px/bước thì mỗi bước đều dưới ngưỡng 200 px ⇒ trôi 35 frame vẫn im lặng. Đúng bullet AGENTS §6 "cả hai cổng đều mù với trôi dần".

Việc: (a) giữ `prev` qua ≤ 2 frame mất dấu (chi phí đo trước: ẩn 56→104, chưa xác minh 171→326 trên 10 phiên đóng băng — cần quyết riêng); (b) **log-only** phát hiện trôi (`drift_px_5buoc` + `drift_canh_bao`) để có số trước khi đổi hành vi hiển thị.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Giữ `prev_bbox` qua ≤ 2 frame mất dấu (`mask_area == 0`) ở cả 3 điểm dựng cổng ⇒ cú bám lại sau mất dấu ĐƯỢC chấm; báo cáo số frame ẩn tăng (đo trước: 56→104 trên 10 phiên đóng băng)
- [ ] Log-only: cột `drift_px_5buoc` (tổng |Δtâm| 5 bước) + `drift_canh_bao` khi > 200 px mà KHÔNG có cú nhảy đơn lẻ nào vượt ngưỡng — đo trên phiên `demoip_1124-162458` (f69→f104 trôi 100 px/bước, cổng im lặng)
- [ ] Phiên `demoip_1124-162458`: replay phải báo `drift_canh_bao` ≥ 1 lần (hiện `nghi_doi_tuong` chỉ có 1 lần ở f124 = lúc bám LẠI)
- [ ] `./run lint` + `./run test` xanh; không đổi hành vi hiển thị (chỉ thêm cột CSV/summary)
