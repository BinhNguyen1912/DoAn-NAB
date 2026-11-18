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

- Test mới **đỏ trên code cũ** (đã kiểm bằng `git stash push src/live_tracking.py` → 2/2 đỏ), **xanh**
  với bản sửa.
- `./run lint` xanh · `./run test` **1355 passed**, 5 deselected (1339 → 1355: +2 test ở ticket này và
  +14 từ các PR khác trong ngày).
- **Số trên clip thật: KHÔNG phân biệt được** — 2 phiên 20 s trên `data/binh1.mp4` (ô chai
  `300,275,150,410`, `vos_every 3`, `image_size 192`, 1 lần mỗi bên):
  | | `git_rev` | `stability` | `stability_n` | `vos_runs` | `empty_window_n` | `empty_runs` |
  |---|---|---|---|---|---|---|
  | trước | `04c8bcc` | 0,0 | 10 | 139 | 139 | 43 |
  | sau | `a3ac49a` | 0,0 | 10 | 142 | 142 | 46 |
  Artifact: `data/stability_ticket35_truoc_metrics.json`, `data/stability_ticket35_sau_metrics.json`.
  Lý do không phân biệt được: `empty_runs` 43–46/142 ⇒ mask rỗng phần lớn thời gian nên cửa sổ cặp bị
  reset liên tục (`stability_n` chỉ 10); và **n = 1 mỗi bên**. Theo AGENTS §6, chênh lệch trong mức này
  phải ghi là **"không phân biệt được"** — thay đổi được canh bằng **test cơ chế**, không bằng số trên
  clip này. Cái đo được và đúng: `empty_window_n == vos_runs` ở cả hai bên ⇒ bản sửa **không** làm mất
  mẫu cửa sổ mất dấu (rủi ro chính của cách làm đầu tiên).

## Vấn đề & cách xử lý

- Bản sửa đầu (bỏ hẳn đo + làm mượt cho frame `start()`) làm **2 test cũ đỏ**
  (`empty_window_n == vos_runs`, `mask_holds >= 1`) ⇒ đổi sang cách hẹp hơn (chỉ bỏ **mẫu cặp**). Ghi lại
  để lần sau không "tối ưu" ngược.
- **Còn nợ (chưa sửa, không nằm trong ticket này)**: `_smooth(result)` vẫn chạy **hai lần** cho frame
  `start()` ở đường có luồng (mask bị làm mượt 2 lượt + `stability_shown` thêm 1 cặp ≈ 1,0). Sửa nó
  chạm `mask_holds`/`stability_shown` nên cần ticket riêng + đo trước/sau; ghi ở Next steps.

## Next steps

- Ticket riêng cho `_smooth` hai lần ở frame `start()` (cùng lớp lỗi, khác đại lượng).
- Ticket **#36** (tên file mask khi chọn ô giữa phiên) — còn mở.

## Tài liệu tham khảo

- Ticket #35 · `src/live_tracking.py` (`_measure_stability`, `_record_vos`, `_after_vos`, `_store_vos`) ·
  AGENTS §6 (`stability` KHÔNG phải thước đo độ chính xác; "chênh lệch nhỏ hơn ngưỡng nhiễu ⇒ không phân
  biệt được").
