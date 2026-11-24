# 47: Đo `chua_xac_minh` trên phiên LIVE thật (số hiện có là replay, không phải live)

**What to build:** Mọi số của trạng thái "chưa xác minh" hiện có đều từ `scripts/replay_latch_settle.py` (replay CSV: ô dựng lại từ `center/bbox_w/bbox_h`, `frame_shape` một hằng 480×640 cho mọi phiên). Chưa có phiên live nào chứng minh `settle_steps = 8` (≈1,3–1,8 s) là đủ trên webcam thật, và chưa có số `chua_xac_minh_n` từ đường live.

Việc cần làm:
1. Thêm bộ đếm `chua_xac_minh_n` cho đường CLI (`InteractiveSummary` + `run_info.json`) — hiện chỉ đường web có.
2. Chạy ≥3 phiên `./run demoip` với vật ra/vào khung (như phiên `demoip_1124-125109`), ghi ra `data/` có `loadavg` + `git_dirty_code`.
3. So `chua_xac_minh_n` live với replay trên cùng phiên: nếu lệch lớn thì `settle_steps = 8` chưa đúng nhịp VOS thật (4,5 lần/s ở 192 nhưng 9 lần/s khi máy rảnh).

Tiêu chí nghiệm thu: artifact live có `chua_xac_minh_n > 0` và `nghi_doi_tuong_n` giảm so với 44,3 % của phiên 24-11; ghi rõ `settle_steps` dùng và `loadavg` lúc đo.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `InteractiveSummary` (đường CLI) có `chua_xac_minh_n` và ghi vào `run_info.json`/`summary.json`
- [ ] ≥3 phiên live thật, artifact có `git_rev` + `git_dirty_code=false` + `loadavg`
- [ ] Số live của `nghi_doi_tuong` giảm so với 109/246 = 44,3 % (phiên `demoip_1124-125109`)
- [ ] Ghi rõ `settle_steps` và nhịp VOS đo được của phiên

## Comments

Bằng chứng live #1 (phiên `demoip_1124-141352`, 87 frame / 21,1 s, `git_rev e18b953`, `loadavg 1,41`, re-ID TẮT): cổng báo **2 lần** (f29, f42) và mỗi lần **đúng 8 frame** ẩn (f29–36, f42–49) ⇒ `nghi_doi_tuong = 16/87 = 18,4 %`. Hành vi CŨ trên **chính CSV đó** = **58/87 = 66,7 %** ẩn ⇒ phiên này code cũ sẽ mất 2/3 buổi demo. Replay `scripts/replay_latch_settle.py --settle 8` trên chính CSV ra **16 frame** = trùng khít số live. `settle 8` ở nhịp VOS **4,12 bước/s** = **1,94 s**.

Ảnh tự kiểm: t=9,6 s "CHUA XAC MINH" với ô trên **vùng sai**; t=11,2 s "NGHI"; **t=12,6 s ô quay lại đúng cái thìa**; t=14,5 s chỉ còn 1 banner "MẤT DẤU".

⇒ Đã chứng minh cơ chế chạy trên đường live (không chỉ replay). Còn lại của ticket: (a) `chua_xac_minh_n` cho đường CLI, (b) thêm ≥2 phiên nữa (tổng ≥3). Hạn chế phải nói: 1 phiên, 87 frame, máy có `loadavg 1,41` nhưng `--smooth` ăn 4,4 lõi (mean 232 ms) nên **không** dùng ms này làm số công bố.
