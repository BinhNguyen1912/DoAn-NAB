# 22: Test tracker_engine IoU đỏ khi chạy full suite (chạy riêng xanh) — flaky do SAM 2 không tất định + máy tải

**What to build:** `./run testall` ngày 11-11 (nhánh `feat/live-gpu-device`) đỏ **1** test:
`tests/test_tracker_engine.py::TestTrackerEngineStreaming::test_process_theo_frames_iou_dat_o_cac_frame_mau`
(`IoU tại frame N thấp hơn ngưỡng` 0,5). Chạy riêng cả file: **8/8 pass** (82,9 s). Nhánh đó chỉ sửa đường `device` của worker live, không đi qua `TrackerEngine` ⇒ nhiều khả năng flaky: SAM 2 **không tất định** (AGENTS §6) + máy bị chiếm CPU sau ~6 phút chạy full suite.

**Vì sao cần xử lý:** một test đỏ ngẫu nhiên làm mọi người bỏ qua `testall`, và làm câu "CI xanh" vô nghĩa. Nhưng **không** được nới ngưỡng cho xanh: phải đo tần suất đỏ trước.

**Cách điều tra (gợi ý thứ tự):**
1. Chạy test đó 10 lần liền trong 1 tiến trình (`pytest --count`/vòng lặp) ⇒ tỉ lệ đỏ + phân bố IoU ở các frame mẫu (2, 5, 9).
2. Chạy nó **sau** khi máy đã tải (chạy `testall` rồi chạy lại riêng) ⇒ xem có tái hiện được đỏ không.
3. So sánh `TrackerResult.score`/IoU khi đỏ vs khi xanh — nếu IoU tụt do mask trôi thì đây là tín hiệu thật về chất lượng, phải ghi thành số trong báo cáo (không chỉ sửa test).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `./run testall` 3 lần liên tiếp xanh trên máy này, HOẶC test được đánh dấu theo cách không còn đỏ oan (kèm số lần đo và lý do chọn)
- [ ] Ghi vào log số đo thật: tần suất đỏ của test khi chạy full suite (n≥3) và IoU đo được ở mỗi lần
- [ ] Không nới ngưỡng IoU một cách im lặng: nếu đổi 0,5 → thấp hơn thì phải chứng minh bằng số (phân bố IoU) rằng 0,5 không hợp lý; ưu tiên chạy lại 1 lần (retry) hoặc tách khỏi full suite
