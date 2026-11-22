# 2: Search window motion gate chặn nhảy vị trí sang nền

**What to build:** Ràng buộc không gian chuyển động dựa trên vận tốc Lucas-Kanade để ngăn SAM 2 nhảy cóc sang các mảng nền trắng/tường trắng khi bị mất tự tin ở vật thể ít texture.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] Tính toán bán kính dịch chuyển tối đa (search window radius) dựa trên tâm bbox và vận tốc Lucas-Kanade các frame trước
- [x] Khi mask VOS mới nhảy đột ngột ra ngoài search window, chặn không nhận vị trí nhảy sang nền
- [x] Kích hoạt trạng thái nghi_doi_tuong trong IdentityWatch để ẩn mask hiển thị thay vì bám nhầm tường
- [x] Test tự động: mô phỏng mask nhảy vị trí phi thực tế, kiểm tra gate kích hoạt và chặn thành công

## Answer

Đã hoàn thành search window motion gate: tính search_window_radius theo kích thước đối tượng và LK velocity, bắt đúng các cú nhảy 100-150 px của vật nhỏ (như remote máy lạnh f109->f110 114 px); khi nhảy, IdentityWatch giữ cờ nghi, hệ ẩn mask và không ghi đè vị trí nhảy vào last_good_bbox; toàn bộ 1728 test xanh 100%.
