# 2: Search window motion gate chặn nhảy vị trí sang nền

**What to build:** Ràng buộc không gian chuyển động dựa trên vận tốc Lucas-Kanade để ngăn SAM 2 nhảy cóc sang các mảng nền trắng/tường trắng khi bị mất tự tin ở vật thể ít texture.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Tính toán bán kính dịch chuyển tối đa (search window radius) dựa trên tâm bbox và vận tốc Lucas-Kanade các frame trước
- [ ] Khi mask VOS mới nhảy đột ngột ra ngoài search window, chặn không nhận vị trí nhảy sang nền
- [ ] Kích hoạt trạng thái nghi_doi_tuong trong IdentityWatch để ẩn mask hiển thị thay vì bám nhầm tường
- [ ] Test tự động: mô phỏng mask nhảy vị trí phi thực tế, kiểm tra gate kích hoạt và chặn thành công
