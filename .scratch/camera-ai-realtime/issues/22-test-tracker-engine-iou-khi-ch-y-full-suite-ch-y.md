# 22: Test tracker_engine IoU đỏ khi chạy full suite (chạy riêng xanh) — flaky do SAM 2 không tất định + máy tải

**What to build:** `./run testall` ngày 10-11 (nhánh `feat/live-gpu-device`) đỏ **1** test:
`tests/test_tracker_engine.py::TestTrackerEngineStreaming::test_process_theo_frames_iou_dat_o_cac_frame_mau`
(`IoU tại frame N thấp hơn ngưỡng` 0,5). Chạy riêng cả file: **8/8 pass** (82,9 s). Nhánh đó chỉ sửa đường `device` của worker live, không đi qua `TrackerEngine` ⇒ nhiều khả năng flaky: SAM 2 **không tất định** (AGENTS §6) + máy bị chiếm CPU sau ~6 phút chạy full suite.

**Vì sao cần xử lý:** một test đỏ ngẫu nhiên làm mọi người bỏ qua `testall`, và làm câu "CI xanh" vô nghĩa. Nhưng **không** được nới ngưỡng cho xanh: phải đo tần suất đỏ trước.

**Cách điều tra (gợi ý thứ tự):**
1. Chạy test đó 10 lần liền trong 1 tiến trình (`pytest --count`/vòng lặp) ⇒ tỉ lệ đỏ + phân bố IoU ở các frame mẫu (2, 5, 9).
2. Chạy nó **sau** khi máy đã tải (chạy `testall` rồi chạy lại riêng) ⇒ xem có tái hiện được đỏ không.
3. So sánh `TrackerResult.score`/IoU khi đỏ vs khi xanh — nếu IoU tụt do mask trôi thì đây là tín hiệu thật về chất lượng, phải ghi thành số trong báo cáo (không chỉ sửa test).

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] `./run testall` 3 lần liên tiếp xanh trên máy này, HOẶC test được đánh dấu theo cách không còn đỏ oan (kèm số lần đo và lý do chọn)
- [x] Ghi vào log số đo thật: tần suất đỏ của test khi chạy full suite (n≥3) và IoU đo được ở mỗi lần
- [x] Không nới ngưỡng IoU một cách im lặng: nếu đổi 0,5 → thấp hơn thì phải chứng minh bằng số (phân bố IoU) rằng 0,5 không hợp lý; ưu tiên chạy lại 1 lần (retry) hoặc tách khỏi full suite

## Comments

12-11 (nhánh `feat/live-device-status-api`): thêm **một** test flaky CÙNG LOẠI (đỏ dưới tải, xanh khi chạy riêng) — bằng chứng n=2 lần chạy full suite liên tiếp:

- `./run testall` lần 1 (12:58): **1 failed** / 820: `tests/test_live_tracking.py::TestVeSinhWorkerCu::test_reap_khong_cho_zombie_5_giay`; chạy riêng ngay sau đó: **8/8 xanh** (test đo `elapsed < 3.0 s` cho `_prepare_dir()` reap worker giả bằng subprocess ⇒ đo THỜI GIAN, không đo hành vi).
- `./run testall` lần 2 (13:05): **820 passed**.

Nhánh đó chỉ thêm khoá `device` vào `status.json` + chuỗi API/HUD ⇒ không đi qua `_prepare_dir`, nên gần như chắc chắn flaky sẵn có (không đổi ngưỡng, không sửa test khi chưa có số tần suất). Cần gộp vào phạm vi ticket này: đo tần suất đỏ của CẢ HAI test (n≥3 lần full suite), ưu tiên cách sửa "không đo thời gian tường" (assert `poll() is not None` + `elapsed < ngưỡng rộng theo số CPU, hoặc `pytest.mark.slow`/retry) thay vì nới ngưỡng im lặng.

## Answer

Đã xong (17-11, `fix/test-flaky-tracker-iou`), **không nới ngưỡng nào**:

**Số đo (máy này, cây sạch):**
- `./run testall` **3 lần liên tiếp: 3/3 xanh**, `1306 passed` mỗi lần, 199,5 / 199,5 / 202,4 s
  ⇒ hôm nay **0/3 lần đỏ**; không tái hiện được ca 10-11. (Log thô của 3 lần này **không commit** được
  — `.gitignore` chặn `data/*`; tái lập bằng `./run testall` 3 lần, mỗi lần ~200 s / 1306 passed.)
- Hai test từng đỏ oan, chạy riêng **10 lần liên tiếp: 10/10 xanh** (tái lập bằng vòng lặp
  `pytest tests/test_tracker_engine.py::TestTrackerEngineStreaming::test_process_theo_frames_iou_dat_o_cac_frame_mau
  tests/test_live_tracking.py::TestVeSinhWorkerCu::test_reap_khong_cho_zombie_5_giay`, ~50 s/lần).
- Phân bố IoU của chính test bị đỏ (5 lần chạy trên cây sạch, `scripts/measure_flaky_iou.py`,
  `data/flaky_iou_2026-11-17_metrics.json`, `git_rev 7f7e806`, `git_dirty_code false`):
  f2 **0,9512 ± 0,0000**, f5 **0,9652 ± 0,0134**, f9 **0,9506 ± 0,0000** ⇒ **0/15 lượt dưới ngưỡng 0,5**.
  Giá trị nhỏ nhất 0,9506 cách ngưỡng 0,5 khoảng **34 σ** (σ lớn nhất = 0,0134 ở f5) ⇒ **ngưỡng 0,5
  đúng, cấm hạ**;
  **Lần đỏ 10-11 không tái hiện được hôm nay.** Trong CÙNG một tiến trình, phân bố gần như tất định
  (f2/f9 `std = 0,0000`, f5 chỉ có 2 giá trị rời) ⇒ 10 lần này **không** đo được tính không tất định
  **giữa các phiên**; chỉ được viết "chưa tái hiện được", không được quy cho "ngoại lệ ngẫu nhiên của
  SAM 2" (P2 review 17-11). Số `git_rev`/`std` phải đọc lại từ artifact sau khi sinh lại — artifact cũ
  khai `git_rev` tại **thời điểm kết thúc** đo.

**Cách xử lý (tiêu chí 3):** `test_process_theo_frames_iou_dat_o_cac_frame_mau` **chạy lại MỘT lần**
khi lần đầu có frame dưới ngưỡng (`engine.reset()` rồi chạy lại đúng kịch bản). Cả hai lần đều dưới
ngưỡng ⇒ **vẫn ĐỎ**, và message in IoU của **cả hai lần** để hồi quy **ổn định** (mask trôi ở mọi lần)
không lọt qua "retry che lỗi"; lần 1 dưới ngưỡng còn được ghi bằng `warnings.warn` nên hồi quy **gián
đoạn** vẫn để lại dấu vết. Không đánh dấu `flaky`/`skip`, không hạ ngưỡng. Không hứa "không thể lọt":
retry 1 lần cho hồi quy có xác suất đỏ p mỗi lần lọt với xác suất `1 − p²`.

**Còn nợ:** `test_reap_khong_cho_zombie_5_giay` (đã tách thành **ticket #34** để không trôi) đo **thời gian tường** (`elapsed < 3 s`) — đúng gợi ý
của ticket là nên đổi sang assert `poll() is not None` + ngưỡng rộng theo số CPU, nhưng test đó
xanh 10/10 lần đo nên **không sửa** ở đây (sửa khi tái hiện được, tránh "sửa mù"); đã ghi vào log.
