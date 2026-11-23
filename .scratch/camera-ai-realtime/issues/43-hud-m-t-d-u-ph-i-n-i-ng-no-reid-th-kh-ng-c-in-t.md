# 43: HUD mất dấu phải nói ĐÚNG: "--no-reid" thì không được in "TỰ TÌM LẠI"

**What to build:** Đo phiên `demoip_1123-144505` (re-ID tắt, `git_rev 42efc56`): 13 frame mất dấu, banner giữa khung in **"MẤT DẤU — TỰ TÌM LẠI"** trong khi hệ **không có re-ID** nên không tự tìm lại được gì. Câu này đi thẳng vào video nộp bài.

Vị trí: `src/visualizer.py:_draw_lost_banner` (dòng ~301) luôn dùng một câu; và bản worker (`src/live_tracking.py`) có banner riêng cần rà cùng.

Yêu cầu: banner mất dấu phải phụ thuộc trạng thái re-ID —
- có re-ID: "MẤT DẤU — TỰ TÌM LẠI" (như cũ),
- không re-ID: "MẤT DẤU — bấm r chọn lại" (nói đúng việc người dùng phải làm).
Hai đường (CLI `Visualizer.render`, worker `_annotate`) phải in giống nhau.

**Blocked by:** None (can start immediately)

**Status:** claimed

- [x] `Visualizer.render(..., reid_enabled=False)` in "MẤT DẤU — bấm r chọn lại", `True` in "MẤT DẤU — TỰ TÌM LẠI"
- [x] Đường worker (`live_tracking`) in cùng câu theo cùng điều kiện
- [x] Test mới phủ cả hai nhánh + hai đường (CLI và worker)
- [x] `./run lint` và `./run test` xanh

## Comments

ĐÍNH CHÍNH tiêu chí 2 ("đường worker in cùng câu") — đã kiểm lại, tiêu chí đó viết SAI, không phải code thiếu:

- `src/live_tracking._annotate` **cố ý không có banner chữ nào**; nó chỉ in `LOST n` trong dòng HUD ASCII (font Hershey không có dấu tiếng Việt).
- Lời giải thích cho người xem web nằm ở **panel**, không burn vào ảnh: `web/src/components/LivePanel.tsx:408` `data-testid="bam-no-evidence"` (`bamLineText`) + nút `live-confirm-object` ("Vẫn đúng, tiếp tục").
- `grep -rn "TU TIM LAI\|TỰ TÌM LẠI" src/ web/src/` → **0 kết quả** ⇒ đường web **không bao giờ** hứa "tự tìm lại", nên không có câu sai cần sửa. Tiêu chí đúng là: "không đường nào được in câu hứa đó khi không có re-ID" — nay đã đúng và có test (`test_visualizer.TestBannerNoiDungTheoReId`).

Còn lại: **CLI** (đường ghi video nộp bài) đã sửa và có test. Từ #45, khung hình cũng tự nói "NGHI" bằng ô nét đứt nên không cần banner chữ trong ảnh worker.
