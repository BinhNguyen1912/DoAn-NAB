# 45: Cổng nghi đổi đối tượng = công tắc tắt vĩnh viễn khi không có re-ID (25,8 % phiên trắng)

**What to build:** Đo phiên `demoip_1123-144505` (re-ID tắt): cổng "nghi đổi đối tượng" bật ở **f144** (đúng — ô nhảy sang góc dưới-phải) rồi **không bao giờ xoá**: `nghi_doi_tuong=1` trên **50/194 frame = 25,8 %**, liên tục tới hết phiên. `reacquired_count=0`, `reselect_n=0` ⇒ không có cơ chế nào tự xoá latch khi re-ID tắt (chỉ phím `r`/`c`).

Bằng chứng ảnh: giây 20,5 của `data/demoip_1123-144505_web.mp4`, vật (remote vàng) **rõ trong khung**, HUD vẫn `NGHI DOI TUONG`, **không vẽ gì cả**.

Đây là hệ quả của quyết định 23-11 (`./run demoip` mặc định `--no-reid`): trước đó re-ID thành công sẽ reset latch; nay không còn gì reset.

Chọn phương án **(a)**: khi nghi, **vẫn vẽ ô bao NÉT ĐỨT** màu cảnh báo + nhãn, **không tô mask** ⇒ người xem luôn thấy hệ đang ở đâu, nhưng hệ không tuyên bố "mask này đúng". Bác (b) "tự xoá sau 8 s": sẽ vẽ lại đúng vùng SAI mà không có bằng chứng mới (đúng lỗi 21-11: bám sang cửa/tường be 65 frame). Bác (c) "chỉ thêm nút web": CLI demo vẫn trắng màn hình.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Khi `switch_warning=True` và KHÔNG có re-ID: vẽ ô NÉT ĐỨT màu cảnh báo + nhãn "NGHI", KHÔNG tô mask, KHÔNG vẽ quỹ đạo
- [ ] Hai đường (CLI `Visualizer.render` và worker `live_tracking._annotate`) hành xử GIỐNG nhau — có test chốt
- [ ] Banner `NGHI DOI TUONG — r: chon lai | c: van dung, tiep tuc` vẫn hiện
- [ ] Test: `render(switch_warning=True)` với mask không rỗng ⇒ có pixel màu cảnh báo ở viền ô, KHÔNG có pixel màu mask bên trong
- [ ] `./run lint`, `./run test`, `./run webtest`, `./run e2e` xanh
