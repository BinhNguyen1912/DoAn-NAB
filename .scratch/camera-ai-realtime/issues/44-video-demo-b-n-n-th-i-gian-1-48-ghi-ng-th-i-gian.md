# 44: Video demo bị nén thời gian 1,48×: ghi đúng thời gian thực

**What to build:** Đo phiên `demoip_1123-144505`: thời gian suy luận thật **30,76 s** (194 bước × 158,5 ms) nhưng `_web.mp4` chỉ **625 frame @30 fps = 20,83 s** ⇒ video **chạy nhanh 1,48×** so với thực.

Nguyên nhân: `Visualizer._write()` ghi **1 frame cho mỗi frame hiển thị** nhưng dán nhãn fps cố định 30; nhịp hiển thị thật của live chỉ ~20 fps (relay 17 fps + model 6,3 bước/s).

Hệ quả: hỏng yêu cầu "hiển thị **quỹ đạo di chuyển theo thời gian thực**" khi người xem/chấm xem lại video.

Yêu cầu: `_write()` giữ **nhịp theo đồng hồ thực** — mỗi lần ghi tính `đích = (now - t0) * fps`, lặp frame đang hiển thị cho đủ tới `đích` (có trần chống bùng nổ, ví dụ ≤ 2 s). Không đổi nội dung frame, không đổi fps khai báo.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] `_web.mp4` của phiên live có thời lượng = thời lượng thực (sai lệch < 5 %), không còn 20,83 s cho 30,76 s
- [x] Số frame ghi = duration_thuc × fps, frame lặp là frame ĐANG hiển thị (không bịa nội dung)
- [x] Chặn trần: một lần treo > 2 s không đẩy hàng trăm frame lặp (có test)
- [x] Test: 10 frame hiển thị trong 1 s với fps=30 ⇒ file ghi 30 frame
- [x] `./run lint`, `./run test`, `./run e2e` xanh
