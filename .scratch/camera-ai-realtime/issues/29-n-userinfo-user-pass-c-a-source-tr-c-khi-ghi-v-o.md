# 29: Ẩn userinfo (user:pass) của `source` trước khi ghi vào `status.json`/artifact

**What to build:** Từ 15-11, `status.json` có `cau_hinh.source` = chuỗi nguồn thô (do `cau_hinh_yeu_cau` echo). Với nguồn RTSP/HTTP có xác thực (`rtsp://user:pass@host/stream`), credential vào thẳng `status.json`, rồi vào artifact đã commit (`scripts/measure_live_relay.py::_worker_telemetry` ghi `cau_hinh`).

Mẫu này **đã có từ trước** (`meta.nguon`, `thiet_lap.source` của artifact cũ) nên đây không phải lỗi mới, nhưng khoá mới làm nó lan thêm ⇒ nên vá một lần ở chỗ sinh dữ liệu.

Cách làm: hàm thuần `an_userinfo(url)` (`urllib.parse.urlsplit` → dựng lại `netloc` không có `user:pass`) dùng khi echo `source`; không đụng tới nguồn thật mà worker mở. Test các dạng URL + chuỗi không phải URL (đường dẫn file, `"0"`).

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] `cau_hinh.source` (và mọi chỗ echo nguồn vào artifact) không còn chứa userinfo của URL
- [x] Có hàm thuần + test cho các dạng: `rtsp://u:p@h/s`, `http://u:p@h/x.jpg`, chuỗi không phải URL, đường dẫn file
- [x] Artifact cũ không bị ghi đè; thay đổi chỉ áp cho lần chạy mới

## Answer (15-11)

Xong trên nhánh `fix/an-userinfo-nguon` (3 commit: `0ebdb86`, `be835f5`, `0b7f276`), log:
`docs/task/15-11-2026-che-credential-trong-nguon.md`.

`src/url_safe.py::an_userinfo()` (hàm thuần) che credential ở **mọi sink echo nguồn**: `cau_hinh.source`
(`status.json`), `meta` artifact mask, `/api/live/status.source` (cả mode `raw` lẫn `track`), thông báo
lỗi mở nguồn (HTTP `detail` + `message` + `worker.log`), `worker.log`, `data/*_run_info.json`, và 4 khoá
của `data/*_metrics.json` (`nguon`, `moi_truong`, `lenh`, `thiet_lap`). KHÔNG che ở chỗ mở nguồn (lệnh
worker giữ URL gốc — có test ghim). `CAM_RELAY_URL` không che được (UI dùng đúng chuỗi đó để gọi
`/api/live/start`) ⇒ cảnh báo trong log.

Kiểm: `./run lint` · `./run test` **1250 passed** · `./run e2e` PASS · `grep '://user:pass@' data/ docs/`
= 0 hit (chưa có credential nào trong lịch sử git).

Review độc lập **2 vòng**: vòng 1 bắt 2 P0 + 3 P1 (bản đầu bỏ sót mode `raw` mặc định và `moi_truong`/
`lenh` của artifact) ⇒ đã vá; vòng 2: 0 P0/P1, 3 P2 ⇒ đã vá nốt. Nợ lại: credential trong **query**
(`?token=…`) và stderr native của FFmpeg (ghi ở mục Next steps của log).
