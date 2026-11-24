# 48: `IdentityWatch.update()` trả bool trong khi có 3 trạng thái — điểm nối có thể nửa vời

**What to build:** P3 review 24-11: `update()` vẫn trả `bool` (= `nghi`) để không phá caller cũ, còn trạng thái thứ ba đọc qua `watch.chua_xac_minh`. Caller mới nào quên đọc thuộc tính đó sẽ **lặng lẽ vẽ mask như đã kiểm** — đúng loại lỗi im lặng mà repo đã gặp 3 lần (bẫy "trường số liệu chết trong adapter", lần này là "cờ chết ở điểm nối").

Việc cần làm: thêm `IdentityWatch.che_do_ve -> "ok" | "nghi" | "chua_xac_minh"` (một nguồn duy nhất) và cho 3 đường vẽ (`visualizer.render`, `live_tracking._annotate`, `live_pipeline._annotate`) nhận **một** tham số `che_do` thay vì `switch_warning` + `chua_xac_minh` rời. Giữ `update()` bool + 2 property cũ để tương thích.

Tiêu chí: thêm một test "quên truyền `che_do`" phải đỏ hoặc kiểu TS/py không cho; `switch_warning=True` + `chua_xac_minh=True` cùng lúc phải bị từ chối (hiện có thể xảy ra do hai nguồn).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `IdentityWatch.che_do_ve` là nguồn DUY NHẤT cho kiểu vẽ
- [ ] 3 đường vẽ nhận 1 tham số `che_do` (không còn 2 cờ rời)
- [ ] Có test/kiểu chặn trạng thái mâu thuẫn (nghi + chưa xác minh cùng lúc)
