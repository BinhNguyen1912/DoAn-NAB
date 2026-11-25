# 25-11-2026 — Cho hệ tự hết nghi: luật "nhảy rồi quay về" (round-trip)

## 1. Mục tiêu
Người dùng báo ở phiên `data/demoip_1125-100334` (`git_rev 25e72e4`, 160 frame/43,2 s, 18,7 FPS):
*"nhận diện lại cũng được, nhưng mà nó để nghi, nghi cũng đúng vật, chưa cập nhật thành box đỏ."*
Sửa đúng cái đó, **không** được làm giảm recall của cổng (7/7 ca báo đúng đã dán nhãn) và **không**
được tuyên bố "đã xác minh danh tính" khi chưa có bằng chứng danh tính.

## 2. Input
- `data/demoip_1125-100334_{metrics.csv,run_info.json,_web.mp4}`
- `data/eval_gate_config_list.json` (10 phiên đóng băng / 1 509 frame) + `scripts/eval_gate_rules.py`
  (`CA_DUNG` 7 ca, `CA_SAI` 1 ca)
- Ảnh cắt từ video HUD tại t = 30,3 · 35,0 · 37,8 · 39,0 · 42,5 s

## 3. Công việc đã thực hiện
### 3.1 Chẩn đoán (đo, không đoán)
| phát hiện | số | nguồn |
|---|---|---|
| cổng báo ở f114 vì tâm nhảy | **229 px** | CSV |
| **f115 quay lại** cách ô tin cậy (f113) chỉ | **47 px** | CSV |
| nhưng latch không có đường tự xoá khi `--no-reid` ⇒ `chua_xac_minh` | **33 frame = 20,6 %** | `run_info.chua_xac_minh_n`, CSV |
| người dùng **không bấm `c`** lần nào | `reselect_n = 0` | `run_info` |
| ô nét đứt chiếm thời gian ở 4 phiên | **18,0 / 34,3 / 60,1 / 6,5 %** | `data/hud_jitter_2026-11-25_metrics.json` |

### 3.2 Plan 3 ý kiến (§9.2) → `docs/plan/25-11-2026-tu-het-nghi.md`
- **Cố vấn chất lượng** đo pilot **15 lần re-prompt**: ô lệch **60 px trên CÙNG vật** ⇒
  `IoU_ref = 0,908 / 0,270 / 0,119` ⇒ **không tồn tại ngưỡng** cho mask-vs-mask; và vì lớp "vẫy nhanh"
  đúng là lớp ô trễ lớn (**227 px**) nên A **cũng** cho 0 ở ca cần xoá nghi ⇒ bác A.
- **Cố vấn sản phẩm** đính chính (tôi kiểm lại bằng ảnh, đúng): ở t=35,0 s viền mask trùm **cả khung
  cửa/tường**, t=39,0 s ô **lệch trái ~90 px** ⇒ vùng "chưa xác minh" **có lúc sai thật**, nên
  "tự tin lại sau N bước" là **vẽ sai**; đồng thời cùng phiên có **13 bước (f94–f106)** bám khung cửa
  mà cổng **im lặng** ⇒ khiếm khuyết nặng hơn là **trôi dần**.

### 3.3 Chốt: chỉ nhận luật ROUND-TRIP (không phải "tự tin lại")
`IdentityWatch(round_trip_steps=2, round_trip_theta=0,3)`: trong **2 bước đầu** của đợt nghi, nếu tâm ô
về trong **0,3 × max(w,h)** của ô **tin cậy ngay trước cú nhảy đầu tiên** ⇒ `reset()`.
- Chấm **trước** nhánh `nhay` vì **cú quay về cũng là một cú nhảy** (f115: 217 px ngược lại).
- **Mốc chỉ đặt khi BẮT ĐẦU đợt nghi** — nếu mỗi cú nhảy lấy mốc mới thì mốc thành **vùng phantom** và
  luật không bao giờ khớp (đây là bug đầu tiên tôi gặp: cài xong vẫn 9/33, đọc code mới thấy).
- `0` = TẮT (tái lập hành vi trước 25-11). Ghi vào `run_info`.

### 3.4 Số đo (replay trên **chính code này**, không phải script nháp)
| kiểm | k=0 (cũ) | k=2 (mới) |
|---|---|---|
| `100334`: frame ẩn · chưa-xác-minh | 9 · 33 | **1 · 0** |
| vẫn báo cảnh báo ở f114? | có | **có** |
| 10 phiên đóng băng: frame bị giảm hiển thị | 120 | **120** (không đổi frame nào) |
| 7 ca báo ĐÚNG giữ được | 7/7 | **7/7** |
| ca báo OAN `085815#47` có bị xoá? | không | **không** |
| `144057` (k=8) | 37 · 48 | `k=8` = 28 · 18 ⇒ **k=8 KHÔNG an toàn**, ghim bằng test |

## 4. Output / Kết quả
- `src/identity_guard.py`: `DEFAULT_ROUND_TRIP_STEPS = 2`, `DEFAULT_ROUND_TRIP_THETA = 0.3`,
  `round_trip_steps`/`round_trip_theta`, `so_lan_round_trip` (chẩn đoán).
- Bật cho 3 đường: `src/smooth_display.py`, `src/live_pipeline.py`, `src/live_tracking.py` (worker web).
- `tools/run_live.py`: `--round-trip-steps` + `_round_trip_steps()` + `run_info.round_trip_steps`.
- `tests/test_identity_guard.py::TestRoundTripNhayRoiQuayVe` (10 test: 4 test khoá **số replay trên CSV
  thật** + 6 unit cho cơ chế, gồm `k=0` tắt, hết cửa sổ, `buoc_moi=False`).
- `./run lint` xanh · **2 081 test** xanh (+12).

## 5. Vấn đề & cách xử lý
- **Bug tự gây ra, bắt bằng test:** help của `--round-trip-steps` chứa `%)` ⇒ argparse định dạng
  `%`-style ⇒ `./run fast --help` **NỔ** (`unsupported format character ')'`) ⇒ 5 test `test_run_script`
  đỏ. Đã sửa (viết "phần trăm"). Bài học: **chuỗi help có `%` phải là `%%`**.
- **Bug thứ hai (logic):** cài đúng công thức nhưng mốc bị ghi đè ở cú nhảy thứ hai ⇒ luật không khớp
  ca thật. Chỉ phát hiện vì tôi replay **trên code thật** và so với replay nháp trước đó — nếu tin
  script nháp thì đã tuyên bố "xong" sai.

## 6. Next steps
- **Cần một phiên live mới** để xác nhận end-to-end (`run_info.round_trip_steps = 2`, kỳ vọng
  `chua_xac_minh_n` ≈ 0–1 thay vì 33) + A/B việc làm mượt ô (`--box-smooth-tau-ms 125`).
- **Chưa làm (cố vấn B, đã ghi vào plan):** HUD 3 mức phân biệt được + câu chữ đúng cơ chế; người thứ
  2 dán nhãn 8 ca; xử lý **trôi dần** (f94–f106) — cần mô hình chuyển động, chưa đo được.
- **Cấm trích:** "round-trip đã sửa báo oan" (nó không sửa `085815#47`), và "mask đã được xác minh".

## 7. Tài liệu tham khảo
- `docs/plan/25-11-2026-tu-het-nghi.md` (3 góc nhìn + bác phương án + tiêu chí)
- `docs/task/25-11-2026-o-do-dut-va-chu-de-len-nhau.md` (jitter đo trên video + chữ đè chữ)
- `docs/plan/24-11-2026-cong-nghi-bao-oan.md` (D1: vì sao không "tự tin lại")
- AGENTS.md §6 các bullet cổng nghi + `--smooth` không có LK
