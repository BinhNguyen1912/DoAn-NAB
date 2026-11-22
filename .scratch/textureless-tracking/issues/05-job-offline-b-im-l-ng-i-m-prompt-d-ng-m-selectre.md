# 5: Job offline bỏ IM LẶNG điểm prompt dương/âm (SelectRequest khai points nhưng routes chỉ chuyển bbox)

**What to build:** `src/api/schemas.py` khai `SelectRequest.points` (dương/âm) và `web/src/api.ts` có kiểu `PointPrompt`, nhưng `src/api/routes.py:121-125` (`select_object`) chỉ gọi `service.select(job_id, (x,y,w,h))` — **điểm bị bỏ im lặng**. Đường LIVE thì đã nối đủ (routes → live.select → worker_source ghi bbox.json → live_tracking → tracker_engine → SAM 2). Hệ quả: UI job offline mà gửi điểm thì không có tác dụng, và người dùng không nhận được cảnh báo nào — "gửi mà không ai nhận" là bẫy đúng loại AGENTS §6 cấm.

Vì 22-11 đường live đã khôi phục điểm âm, chỗ này thành mâu thuẫn: cùng một component `SelectionCanvas` ở 2 trang, một bên dùng được điểm một bên không (hiện `points` là prop TUỲ CHỌN để không gửi nhầm ở trang job).

Việc phải làm: hoặc (a) nối `points` xuống `src/worker` + pipeline offline, hoặc (b) bỏ `points` khỏi `SelectRequest` và trả 400 nếu client gửi kèm, để không ai tưởng nó có tác dụng. Chọn (a) nếu pipeline offline dùng cùng `TrackerEngine.start`; (b) rẻ hơn và trung thực hơn nếu không.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Có test API: gửi `points` lên `/api/jobs/{id}/select` thì hoặc điểm được truyền xuống worker (kiểm bằng lệnh/argv hoặc file cấu hình) hoặc trả 400 nói rõ `points` chưa hỗ trợ
- [ ] `SelectionCanvas` ở `web/src/App.tsx` không còn phải dựa vào prop tuỳ chọn ngầm hiểu
- [ ] Log/tài liệu nói rõ đường offline có điểm hay không (không để người đọc tự đoán)
