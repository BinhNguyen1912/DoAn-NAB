# 29: Ẩn userinfo (user:pass) của `source` trước khi ghi vào `status.json`/artifact

**What to build:** Từ 15-11, `status.json` có `cau_hinh.source` = chuỗi nguồn thô (do `cau_hinh_yeu_cau` echo). Với nguồn RTSP/HTTP có xác thực (`rtsp://user:pass@host/stream`), credential vào thẳng `status.json`, rồi vào artifact đã commit (`scripts/measure_live_relay.py::_worker_telemetry` ghi `cau_hinh`).

Mẫu này **đã có từ trước** (`meta.nguon`, `thiet_lap.source` của artifact cũ) nên đây không phải lỗi mới, nhưng khoá mới làm nó lan thêm ⇒ nên vá một lần ở chỗ sinh dữ liệu.

Cách làm: hàm thuần `an_userinfo(url)` (`urllib.parse.urlsplit` → dựng lại `netloc` không có `user:pass`) dùng khi echo `source`; không đụng tới nguồn thật mà worker mở. Test các dạng URL + chuỗi không phải URL (đường dẫn file, `"0"`).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `cau_hinh.source` (và mọi chỗ echo nguồn vào artifact) không còn chứa userinfo của URL
- [ ] Có hàm thuần + test cho các dạng: `rtsp://u:p@h/s`, `http://u:p@h/x.jpg`, chuỗi không phải URL, đường dẫn file
- [ ] Artifact cũ không bị ghi đè; thay đổi chỉ áp cho lần chạy mới
