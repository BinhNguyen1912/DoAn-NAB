# 26: Ghi mask dump nằm TRONG cửa sổ `post_ms`; chọn lại ô giữa phiên chưa có test canh

**What to build:** hai điểm tồn đọng của đường `--dump-mask-frames` (review hẹp 14-11, P3):

1. `_dump_mask` chạy bên trong `_record_vos`, tức **trong** cửa sổ `post_ms`; `post_ms` vào thẳng
   `mask_age_total_ms`/p95 và `cycle_ms` của mẫu đó ⇒ **dụng cụ đo làm bẩn số đang đo** (~1–3 ms @640×480,
   ~5–15 ms @1080p). Với vài chục frame được dump thì p95 gần như không đổi; dump gần như mọi frame thì có.
2. Chọn lại ô giữa phiên (`engine.reset()` + `start()`): tên file dùng `self._frame_index` của **phiên**
   (không reset) nên hiện **không** ghi đè — nhưng **không có test nào canh**, nên một lần ai đó "dọn"
   code reset `_frame_index` là mask của hai lần chọn trộn vào nhau mà không ai biết.

**Vì sao cần xử lý:** đây là "số đo bị chính công cụ đo làm lệch" — loại lỗi khó thấy nhất vì mọi thứ
vẫn xanh.

**Cách làm:** đo riêng `dump_ms` (hoặc ghi sau khi đã đặt `_vos_state`) để `post_ms` chỉ còn phần xử lý
kết quả; thêm test: chọn lại ô giữa phiên ⇒ file `mask_*` của lần chọn đầu **không** bị ghi đè (hoặc bị
từ chối rõ ràng).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `post_ms` không còn bao gồm thời gian ghi PNG (hoặc `dump_ms` được trừ ra và ghi riêng)
- [ ] Test: chọn lại ô giữa phiên khi dump bật ⇒ không ghi đè âm thầm (hoặc từ chối)
