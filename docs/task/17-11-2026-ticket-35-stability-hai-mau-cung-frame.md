# 17-11-2026 — Ticket #35: `stability` nhận 2 mẫu cho CÙNG một frame video

## Mục tiêu

Ở đường có luồng VOS, frame `engine.start()` được worker `process()` **lại** ⇒ có **hai kết quả VOS cho
cùng một frame video** (một từ `_after_vos`, một từ `_store_vos`). `_measure_stability` coi chúng là "hai
mask liên tiếp" ⇒ đẩy thêm một mẫu `mask_iou(mask, mask) ≈ 1,0` ⇒ `stability` bị thổi lên ở đầu phiên và
`stability_n` đếm dư.

## Input

- `src/live_tracking.py`: `_after_vos` (frame `start()`) và `_store_vos` (worker) đều đi qua `_record_vos`
  → `_measure_stability`.
- Ràng buộc tìm ra khi làm: **không được bỏ đo ở frame `start()`** — `_measure_stability` cũng là nơi
  đẩy mẫu vào cửa sổ mất dấu, và test cũ `test_so_mau_bang_so_lan_vos` ghim
  `empty_window_n == vos_runs`. Bản sửa đầu tiên (bỏ hẳn `_measure_stability` + `_smooth` cho frame
  `start()`) làm **2 test cũ đỏ** — đúng vai trò của chúng, nên đã đổi cách làm.

## Công việc đã thực hiện

- `_measure_stability(result, frame_video=None)`: nếu `frame_video` **trùng** mẫu gần nhất thì **không
  đẩy mẫu cặp**, chỉ cập nhật mốc `_prev_raw_mask` (vẫn đếm cửa sổ mất dấu như mọi lần VOS).
- `_record_vos(result, frame_video=None, dump=True)`: tách **`dump`** (có ghi PNG không) khỏi
  `frame_video` (dùng cho tên file **và** cho `_measure_stability`). `_after_vos` của đường có luồng
  truyền `dump=False` nhưng **vẫn truyền `frame_video`** — nếu để `None` thì bước so "trùng frame" không
  chạy và bug vẫn còn (đã thử: test cơ chế đỏ).
- 2 test mới trong `tests/test_live_tracking.py::TestMotKetQuaChiDoMotLan`:
  1. **cơ chế**: gọi thẳng `_measure_stability(..., frame_video=0)` hai lần ⇒ `stability_n == 0` **và**
     `empty_window_n == 2`; gọi thêm `frame_video=3` ⇒ `stability_n == 1` (= IoU 1,0 của mask y hệt).
  2. **bất biến của phiên** (`vos_every=3`): `len(_measure_stability calls) == vos_runs`,
     `empty_window_n == vos_runs`, và `stability_n <= số frame khác nhau − 1`.

## Output / Kết quả

- Test mới **đỏ trên code cũ** và đỏ với **hai hồi quy tinh vi** (diễn tập ngược đã chạy):
  (a) bỏ bước so trùng frame ⇒ 2/2 đỏ; (b) `_after_vos` truyền `frame_video=None` cho đường có luồng
  ⇒ đỏ. Bản đầu của test **không thể đỏ** (cửa sổ `deque(maxlen=10)` cắt `stability_n` ở 10 ⇒ bất đẳng
  thức `<=` luôn đúng — P1 review 17-11); nay test nới cửa sổ (`deque(maxlen=100)`) và dùng **đẳng
  thức**, cộng thêm assert `lần đo đầu phải có frame_video=0`.
- `./run lint` xanh · `./run test` **1355 passed**, 5 deselected (1339 → 1355: +2 test ở ticket này và
  +14 từ các PR khác trong ngày).
- **Số trên clip thật: KHÔNG phân biệt được** — 1 phiên 20 s mỗi bên trên `data/binh1.mp4` (ô chai
  `300,275,150,410`, `vos_every 3`, `image_size 192`), đo **18-11 12:18 (sau) / 12:19 (trước)**.
  Lấy 3 **mẫu trong phiên** (`mau_cuoi`), **không** lấy `worker_status.stability`:

  | | `git_rev` | 3 mẫu `mau_cuoi` | mean ± std | `stability_n` | `empty_window_n` / `vos_runs` |
  |---|---|---|---|---|---|
  | trước | `04c8bcc` | 0,683 · 0,647 · 0,710 | **0,680 ± 0,032** | 10 | 139 / 139 |
  | sau | `a3ac49a` | 0,701 · 0,657 · 0,724 | **0,694 ± 0,034** | 10 | 142 / 142 |

  ⇒ chênh mean **0,014 < std 0,032** ⇒ theo AGENTS §6 phải ghi **"không phân biệt được"** (và repo
  **chưa có ngưỡng nhiễu cho `stability`**, nên kể cả n=3 phiên cũng chưa kết luận được A/B).

  **Vì sao `stability_n` = 10 ở cả hai bên và vì sao KHÔNG dùng `worker_status.stability = 0,0`**
  (đính chính so với bản log đầu — lý do cũ "mask rỗng reset cửa sổ" là **sai cơ chế**):
  - `_iou_window` là `deque(maxlen=10)`, `stability_n = len(_iou_window)` ⇒ sau 10 cặp là **bão hoà**,
    mẫu thừa (kể cả mẫu trùng) **không** hiện ra ở `stability_n`. Muốn thấy khác biệt phải ghi mẫu **đầu
    phiên** (khi `stability_n < 10`) — chưa có cột đó trong `measure_live_relay`.
  - `worker_status.stability = 0,0` là **"lần VOS cuối trả mask rỗng"** (`stability = 0.0 if _iou_window
    else None`), `lost_streak` 4–6 — đúng bẫy `0,0 ≠ số đo`; số của phiên nằm ở `mau_cuoi` (bảng trên).
  - Mask rỗng **không** xoá `_iou_window`; nó chỉ đặt `_prev_raw_mask = None` (**ngắt cặp**), và
    `empty_runs` 43–46/142 ≈ **30 %** số lần VOS (không phải "phần lớn thời gian").

  Cái đo được và đúng: `empty_window_n == vos_runs` ở cả hai bên ⇒ bản sửa **không** làm mất mẫu cửa sổ
  mất dấu (rủi ro chính của cách làm đầu tiên). Thay đổi được canh bằng **test cơ chế** (có diễn tập
  ngược), không bằng số trên clip này.

## Vấn đề & cách xử lý

- Bản sửa đầu (bỏ hẳn đo + làm mượt cho frame `start()`) làm **2 test cũ đỏ**
  (`empty_window_n == vos_runs`, `mask_holds >= 1`) ⇒ đổi sang cách hẹp hơn (chỉ bỏ **mẫu cặp**). Ghi lại
  để lần sau không "tối ưu" ngược.
- **Còn nợ (chưa sửa, không nằm trong ticket này)**: `_smooth(result)` vẫn chạy **hai lần** cho frame
  `start()` ở đường có luồng (mask bị làm mượt 2 lượt + `stability_shown` thêm 1 cặp ≈ 1,0). Sửa nó
  chạm `mask_holds`/`stability_shown` nên cần ticket riêng + đo trước/sau; ghi ở Next steps.
- **Còn nợ (mới, từ review)**: chưa có cột "stability ở 10 cặp ĐẦU phiên" trong `measure_live_relay`
  ⇒ mẫu trùng ở frame `start()` chỉ thấy được bằng test, không thấy được trên số của phiên (cửa sổ
  bão hoà 10). Và repo **chưa có ngưỡng nhiễu cho `stability`** — mọi A/B `stability` phải ghi "không
  phân biệt được" cho tới khi có.

## Next steps

- Ticket riêng cho `_smooth` hai lần ở frame `start()` (cùng lớp lỗi, khác đại lượng).
- Ticket **#36** (tên file mask khi chọn ô giữa phiên) — còn mở.

## Tài liệu tham khảo

- Ticket #35 · `src/live_tracking.py` (`_measure_stability`, `_record_vos`, `_after_vos`, `_store_vos`) ·
  AGENTS §6 (`stability` KHÔNG phải thước đo độ chính xác; "chênh lệch nhỏ hơn ngưỡng nhiễu ⇒ không phân
  biệt được").
