# 43: HUD mất dấu phải nói ĐÚNG: "--no-reid" thì không được in "TỰ TÌM LẠI"

**What to build:** Đo phiên `demoip_1123-144505` (re-ID tắt, `git_rev 42efc56`): 13 frame mất dấu, banner giữa khung in **"MẤT DẤU — TỰ TÌM LẠI"** trong khi hệ **không có re-ID** nên không tự tìm lại được gì. Câu này đi thẳng vào video nộp bài.

Vị trí: `src/visualizer.py:_draw_lost_banner` (dòng ~301) luôn dùng một câu; và bản worker (`src/live_tracking.py`) có banner riêng cần rà cùng.

Yêu cầu: banner mất dấu phải phụ thuộc trạng thái re-ID —
- có re-ID: "MẤT DẤU — TỰ TÌM LẠI" (như cũ),
- không re-ID: "MẤT DẤU — bấm r chọn lại" (nói đúng việc người dùng phải làm).
Hai đường (CLI `Visualizer.render`, worker `_annotate`) phải in giống nhau.

**Blocked by:** None (can start immediately)

**Status:** claimed

- [ ] `Visualizer.render(..., reid_enabled=False)` in "MẤT DẤU — bấm r chọn lại", `True` in "MẤT DẤU — TỰ TÌM LẠI"
- [ ] Đường worker (`live_tracking`) in cùng câu theo cùng điều kiện
- [ ] Test mới phủ cả hai nhánh + hai đường (CLI và worker)
- [ ] `./run lint` và `./run test` xanh
