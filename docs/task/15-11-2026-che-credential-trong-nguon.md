# 15-11-2026 — Che credential (`user:pass@`) trong chuỗi nguồn (ticket #29)

## 1. Mục tiêu

Nguồn frame là **chuỗi tự do**: `0` (webcam), đường dẫn file, hoặc URL (`rtsp://`, `http://…/snapshot.jpg`).
Chuỗi đó được **echo** vào nhiều nơi; với `rtsp://user:pass@camera/s` thì mật khẩu camera đi vào file
**được commit** và vào **phản hồi HTTP**. Việc này che credential ở mọi chỗ ECHO, **không** che ở chỗ mở
nguồn (che ở đó là phiên RTSP có xác thực không kết nối được; và `_reap_stale_worker` khớp worker qua
`argv` thật).

## 2. Input

- Ticket `.scratch/camera-ai-realtime/issues/29-*.md`.
- Hiện trạng: từ 15-11 `status.json` có `cau_hinh.source` (echo từ `cau_hinh_yeu_cau`) ⇒ credential vào
  `status.json` → artifact đã commit. Mẫu này có từ trước ở `meta.nguon`/`thiet_lap.source`.

## 3. Công việc đã thực hiện

**Module mới `src/url_safe.py`** (hàm THUẦN, chỉ dùng `urllib.parse`):

| Hàm | Việc |
|---|---|
| `an_userinfo(url)` | Bỏ `user:pass@` khỏi `netloc`. `rsplit('@', 1)` (mật khẩu có thể chứa `@`; trùng đúng quy tắc nội bộ của `urlsplit`). Trả **nguyên** chuỗi khi: không phải URL (`0`, `data/x.mp4`, `C:\x.mp4`), `netloc` rỗng, `netloc` không có `@`, URL hỏng (`ValueError`) |
| `co_userinfo(url)` | `"@" in netloc` — dùng để cảnh báo, **không** dùng để in chuỗi gốc |

**Các chỗ ECHO đã che** (đường tới file commit / HTTP):

| Chỗ | Đi tới |
|---|---|
| `src/live_tracking.py::cau_hinh_yeu_cau()` → `cau_hinh.source` | `status.json` → artifact |
| `src/live_tracking.py` `meta` của artifact mask (manifest) | `data/…_mask_meta.json` |
| `src/api/adapters/worker_source.py::label` | `GET /api/live/status.source` |
| `src/api/adapters/opencv_source.py::label` + `health()` (mode **raw**, mặc định của UI) | `GET /api/live/status` |
| `src/video_source.py` — 3 thông báo lỗi mạng + `FileVideoSource` | HTTP 400 `detail`, `status.json.message`, `worker.log` |
| `tools/live_worker.py` dòng "sẵn sàng \| nguồn:" | `worker.log` (bị chép vào artifact) |
| `tools/run_live.py::write_run_info(source=)` | `data/*_run_info.json` (**được commit**) |
| `scripts/measure_live_relay.py`: `nguon`, `moi_truong`, `lenh`, stdout | `data/*_metrics.json` (**được commit**) |
| `src/api/adapters/source_probe.py` | **không che** `source` (UI dùng đúng chuỗi đó để gọi `/api/live/start`) ⇒ cảnh báo `logger.warning` khi `CAM_RELAY_URL` có credential |

## 4. Output / Kết quả

```
./run lint      → All checks passed
./run test      → 1250 passed, 5 deselected (88,12 s)     [trước ticket: 1217]
./run e2e       → KẾT LUẬN: PASS
tests/test_url_safe.py → 32 test (URL khó, chuỗi không phải URL, 9 call site, doctest)
```

Đã kiểm: `grep -rn "://user:pass@" data/ docs/` = **0 hit** ⇒ chưa có credential nào lọt vào lịch sử git,
không phải đổi mật khẩu/viết lại lịch sử.

## 5. Vấn đề & cách xử lý

**Review độc lập vòng 1** (agent `reviewer`, nhánh `fix/an-userinfo-nguon`): **2 P0 + 3 P1** — bản đầu
chỉ che 4 chỗ trong commit message và **bỏ sót đúng đường mặc định**:

- **P0-1** `OpenCvFrameSource.label` (mode **raw** — mode UI mặc định) trả nguyên URL có credential ra
  `/api/live/status.source` + `message`. → đã che (+ `health()`).
- **P0-2** Artifact `data/*_metrics.json` còn credential ở `moi_truong` và `lenh` (= `sys.argv` thô).
  → `_lenh_an_credential()`/`_an_tham_so()` + `_moi_truong()`.
- **P1** 3 thông báo lỗi mở nguồn (`video_source.py`) → `HTTP 400 detail`/`status.json.message`/`worker.log`;
  **P1** dòng log "sẵn sàng | nguồn:"; **P1** `data/*_run_info.json`.
  (Lưu ý: `an_userinfo(str(exc))` **không** cứu được thông báo lỗi — cả câu là "path" với `urlsplit`,
  phải che **tại chỗ sinh chuỗi**.)

**Review độc lập vòng 2** (sau bản vá): **0 P0, 0 P1**, 3 P2 — đã sửa cả 3:

- `--source=URL` (argparse nhận cả hai kiểu) có `netloc` rỗng ⇒ `an_userinfo` trả nguyên ⇒ vẫn lọt vào
  `lenh`. → `_an_tham_so()` tách `flag=value`.
- Nguồn có scheme lạ (`rtsps://`, `rtmp://`) hoặc dán kèm dấu cách đầu **không** khớp adapter mạng ⇒ rơi
  vào `FileVideoSource`, nơi thông báo lỗi echo nguyên chuỗi. → đã che.
- `co_userinfo` là dead code; `CAM_RELAY_URL` có credential không cảnh báo gì. → dùng để `logger.warning`
  (không in URL) + test.
- P3 đã sửa: test `moi_truong` thật sự assert (tên test cũ hứa mà không kiểm), import module thật thay
  vì nạp lại bằng `importlib` (phụ thuộc CWD), `doctest.attempted >= 4`, che stdout của script đo (output
  hay được dán vào `docs/task`), ghim `pytest.raises(ValueError)` cho tiền đề của test URL hỏng.

**Nợ lại (P3, ghi để không quên):**

1. **Credential trong QUERY** (`?user=…&pass=…`, `?token=…`) **không** được che — `an_userinfo` chỉ bỏ
   userinfo. Cần ticket riêng nếu có nguồn dùng kiểu này.
2. **stderr native của OpenCV/FFmpeg** khi mở RTSP lỗi chảy vào `worker.log`, và `worker_log`/`api_log`
   được nhúng **nguyên văn** vào artifact ⇒ nếu libavformat in URL kèm userinfo thì code Python không
   chặn được. Muốn chắc: chạy 1 ca RTSP sai mật khẩu rồi `grep '://[^ ]*@' worker.log` — **chưa đo**.

**Bài học:** "vá một chỗ, hở ba chỗ" — với dữ liệu nhạy cảm phải liệt kê **mọi sink** (file commit, HTTP,
log, artifact) chứ không chỉ sink được nhắc trong ticket. Review độc lập bắt được đúng 2 P0 mà lần tự
kiểm đầu tiên bỏ qua.

## 6. Next steps

- Ticket #30+ (nếu cần): che credential trong query string + kiểm stderr native.
- Chờ người dùng tô 12 frame silhouette để chấm **mIoU mask vs GT** trên video thật (`./run miou`).

## 7. Tài liệu tham khảo

- `.scratch/camera-ai-realtime/issues/29-*.md`
- `src/url_safe.py` (hợp đồng + ví dụ doctest được chạy bằng test)
- AGENTS §6 (bẫy `None`/`0`), §9.1 (review độc lập 2 vòng)
