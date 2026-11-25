# 25-11-2026 — Đo lại việc làm mượt ô trên **phiên thật** (không phải mô phỏng) + vì sao bản quay hỏng

## 1. Mục tiêu
Xác nhận hai sửa của ngày (`--box-smooth-tau-ms 125`, luật round-trip) có tác dụng **trên phiên live
thật**, và giải thích vì sao bản quay `demoip_1125-121456` (98 s) trông vẫn chưa tốt.

## 2. Input
- `data/demoip_1125-121456_{metrics.csv,run_info.json,_web.mp4}` — 295 bước VOS / 98,3 s, 18,4 FPS
- So sánh: `demoip_1125-100334` (bản trước khi sửa), `demoip_1125-085815`
- `data/hud_jitter_2026-11-25_lan2_metrics.json` (`git_rev 696dbc4`, `git_dirty_code false`)

## 3. Kết quả

### 3.1 Code mới ĐÃ chạy thật
`run_info`: `git_rev 696dbc4` · `git_dirty_code false` · `round_trip_steps 2` · `box_smooth_tau_ms 125`
· `image_size 192` · `mask_threshold -1.0` · `loadavg_1m` **5,98**.

### 3.2 "Ô dựt" — hết, đo trên chính video phiên mới (dò màu từng frame hiển thị)
| đại lượng | 10:03 (trước sửa) | **12:14 (sau sửa)** | 08:58 |
|---|---|---|---|
| ô **đứng yên** rồi nhảy | med **8 frame** (~267 ms) | **2 frame** (~67 ms) | 8 frame |
| bước nhảy tâm | med 15,6 · p95 **160,8** px | **med 3,2 · p95 23,0 px** | med 18,1 · p95 89,9 |
| bước nhảy < 20 px | 57 % | **94 %** | 53 % |
| ô đỏ / nét đứt | 71,4 % / 18,0 % | 59,8 % / **20,3 %** | 74,0 % / 6,5 % |

⇒ Việc làm mượt **có tác dụng thật**, không chỉ trong mô phỏng: ô giờ trượt gần như mỗi frame.

### 3.3 Nhưng bản quay hỏng vì lý do KHÁC: bám sang **điều hoà**
Dòng thời gian (dò màu): **0–36,2 s ô đỏ** → **36,2–56,1 s nét đứt (19,9 s)** → **56,1–98 s ô đỏ**.
Ánh xạ `frame_idx→giây` bằng cộng dồn `latency_ms` (KHÔNG chia đều): f141 ≈ 34,9 s, f149 ≈ 37,9 s,
f197 ≈ 55,7 s, f198 ≈ 57,4 s.

CSV: `nghi_doi_tuong` chỉ ở **f141–148** (8 frame, đúng `settle_steps`) ⇒ `chua_xac_minh` f149–197
= **49 frame** ⇒ `run_info.chua_xac_minh_n = 49`; `reselect_n = 0`.

**Ảnh t = 46,8 s** (`data/tmp_1125/n46.8.jpg`): ô nét đứt + viền mask nằm trên **điều hoà / tường /
poster**, còn remote đang cầm ở giữa phải ⇒ **hệ đã mất remote và bám vào điều hoà trắng** (nền cùng
tông), không phải "bám đúng mà bị nghi".

Hệ quả đúng luật:
- cổng báo **1 lần** ở f140 (ô (157,128,639,479) → (30,142,230,479)) — hình học đúng, ô quá lớn;
- luật **round-trip KHÔNG kích hoạt** (đây không phải "nhảy rồi quay về");
- trạng thái thoát ở f198 vì mask rỗng **3 bước** f195–197 ⇒ luật "vật rời khung" (24-11) reset.

⇒ Hiển thị **trung thực** (không tô mask giả vờ tin cậy), nhưng 20 s nét đứt trong 98 s là **quá dài
cho video demo** ⇒ phải đổi kịch bản/vật, không phải đổi code.

### 3.4 Vì sao chậm: máy đang chạy dự án khác (người dùng xác nhận)
| | phiên 12:14 | máy rảnh (đo 10:53) |
|---|---|---|
| `loadavg_1m` | **5,98** | 0,70 |
| mean / p95 | **321 / 634 ms** | 137 / 188 ms |

⇒ Đúng luật AGENTS: **ms tuyệt đối không trích được khi `loadavg` cao**; cùng code chênh **2,3×**.
Hiển thị vẫn 18,4 FPS và `ti_le_thoi_luong = 1,00` nên video không bị nén sai thời gian.

## 4. Output / Kết quả
- `data/hud_jitter_2026-11-25_lan2_metrics.json` (`git_rev 696dbc4`, `dirty_code false`) — 3 phiên.
- Không sửa code (không có gì để sửa: cả hai tính năng chạy đúng; lỗi là **kịch bản quay**).

## 5. Vấn đề & cách xử lý
- **Bẫy ánh xạ thời gian**: chia đều `98,3 s / 295 frame = 0,33 s` cho f141 ≈ 46,6 s, **lệch 12 s** so
  với cộng dồn `latency_ms` (34,9 s) — vì các bước VOS dài ngắn khác nhau (1291–1771 ms ở f195–197).
  Mọi kết luận "frame nào ↔ giây nào" phải cộng dồn `latency_ms` (đúng như cố vấn đã làm).
- **Bài học kịch bản**: remote trắng trên điều hoà/tường trắng là ca khó nhất repo (AGENTS ghi 3 lần).
  Phiên `085815` dùng **tấm thẻ vàng** ⇒ chỉ **6,5 %** nét đứt. Chọn vật màu, ô sát vật (đừng ôm tay:
  ô đầu phiên này `156×275`, cao gấp 1,8 lần rộng).

## 6. Next steps
- Quay lại theo kịch bản ở mục 5 (vật màu, ô sát vật, giữ trong khung, đóng app nặng).
- Việc **sửa gốc** "bám sang nền cùng tông" (drift) vẫn nằm trong plan, cần plan riêng (§9.2).

## 7. Tài liệu tham khảo
- `docs/task/25-11-2026-o-do-dut-va-chu-de-len-nhau.md` (bản trước khi sửa)
- `docs/task/25-11-2026-round-trip-het-nghi.md`
- `src/box_smoother.py` (số mô phỏng 118 → 41,8 px; nay có số **thật** 160,8 → 23,0 px)
