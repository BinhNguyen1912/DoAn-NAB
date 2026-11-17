# Ngày 17-11-2026 — Ticket #22: test `tracker_engine` đỏ oan trong full suite (đo tần suất, không nới ngưỡng)

## 🎯 Mục tiêu
- Đóng ticket **#22**: `./run testall` ngày 10-11 đỏ 1 test IoU (`test_process_theo_frames_iou_dat_o_cac_frame_mau`,
  "IoU tại frame N thấp hơn ngưỡng" 0,5) trong khi chạy riêng xanh; 12-11 thêm 1 test flaky cùng loại
  (`test_reap_khong_cho_zombie_5_giay`, đo thời gian tường).
- **Không được nới ngưỡng im lặng** — phải đo tần suất đỏ + phân bố IoU trước.

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/22-…md`; `tests/test_tracker_engine.py`,
  `tests/test_live_tracking.py`, `pytest.ini` (`addopts = -q --timeout=120`), `src/tracker_engine.py`.
- `AGENTS.md` §6: **SAM 2 không tất định** ⇒ chỉ so sánh trong cùng một lần chạy; cấm nới ngưỡng im lặng.
- Máy: CPU (không GPU rời), checkpoint SAM 2.1 tiny.

## 🔨 Công việc đã thực hiện
1. **Đo tần suất đỏ thật** (cây sạch):
   - `./run testall` **3 lần liên tiếp: 3/3 xanh**, `1306 passed` mỗi lần (199,5 / 199,5 / 202,4 s) ⇒
     **0/3 lần đỏ**, **không tái hiện** ca 10-11.
   - Hai test từng đỏ oan, chạy riêng **10/10 xanh** (~50 s/lần).
   - Log thô không commit được (`.gitignore` chặn `data/*`); tái lập bằng chính 2 lệnh trên.
2. **Đo phân bố IoU** bằng script mới `scripts/measure_flaky_iou.py` (chạy đúng kịch bản của test,
   dùng chính hàm `iou` của test, engine nạp 1 lần): 5 lần trên cây sạch
   ⚠️ **Số ở mục 8–9 dưới đây là bản ĐẦU** (min trên 10 frame, gọi nhầm là "cổng test"); số dùng là
   mục **"Bổ sung (đợt 3)"** ở cuối file (cổng `tat_ca.cong_test`, `git_rev 472bc6e`).
   (`data/flaky_iou_2026-11-17_metrics.json`, `git_rev 472bc6e`, `git_dirty_code false`) ⇒
   f2 **0,9512 ± 0,0000** · f5 **0,9652 ± 0,0134** · f9 **0,9506 ± 0,0000** ⇒ **0/15 lượt dưới ngưỡng 0,5**,
   giá trị nhỏ nhất cách ngưỡng ~**34 σ**.
3. **Cách xử lý (tiêu chí 3)**: test IoU **chạy lại MỘT lần** khi lần đầu có frame dưới ngưỡng
   (`engine.reset()` rồi chạy lại đúng kịch bản). Cả hai lần dưới ngưỡng ⇒ **vẫn ĐỎ** và message in
   IoU của **cả hai lần** (retry không che được hồi quy thật). **Không** hạ ngưỡng, không `skip`,
   không `flaky`.
4. `@pytest.mark.timeout(300)` cho test đó: `pytest.ini` đặt `--timeout=120` chung, một lượt đo được
   44–74 s dưới tải ⇒ retry có thể chạm 148 s và bị `pytest-timeout` giết **trước** khi có kết quả.

## 📤 Output / Kết quả
- Ngưỡng 0,5 **giữ nguyên**, có số chứng minh (phân bố 0,95–0,975 so với 0,5).
- Flaky có cơ chế chạy lại 1 lần nhưng **không** nuốt lỗi (2 lần đỏ ⇒ đỏ, message đủ số).
- `./run lint` xanh · `./run test` **1301 passed**, 5 deselected.
- File thay đổi: `tests/test_tracker_engine.py`, `scripts/measure_flaky_iou.py` (mới),
  `data/flaky_iou_2026-11-17_metrics.json`, ticket #22.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Retry có thể đụng `--timeout=120`** (P1 review): xem mục 4 — nếu không sửa thì ở đúng điều kiện
  tải gây flake, test đỏ bằng "Timeout >120.0s" thay vì message IoU (tức retry vô dụng).
- **Provenance sai thời điểm** (P1 review): bản đầu `_git()` gọi **sau** vòng lặp ⇒ artifact khai một
  `git_rev` chỉ đúng ở thời điểm kết thúc (7/10 phút đầu lần đo, rev đó **chưa tồn tại**). Nay: chụp
  TRƯỚC khi nạp model, **từ chối chạy** nếu cây bẩn, và **từ chối ghi artifact (exit 2)** nếu rev/dirty
  đổi trong lúc đo. Artifact commit được sinh lại theo cách này.
- **Số "9 σ" trong docstring/ticket sai** (P2 review): artifact cho f5 std 0,0134 ⇒ khoảng cách
  ≈ 34 σ. Đã sửa cả docstring lẫn ticket cho khớp artifact.
- **Ticket dẫn 2 file log không tồn tại** (P2 review): `.gitignore` chặn `data/*` nên log thô không
  commit được; nay ticket ghi **lệnh tái lập** + số đếm thay vì dẫn file.

## ✅ Review độc lập (AGENTS §9.1)
- Agent `reviewer` (chỉ đọc): phần cốt lõi (retry 1 lần, không hạ ngưỡng, 2 lần đỏ thì đỏ) **đúng**;
  **2 P1 + 2 P2** còn lại **đã sửa** (timeout marker, provenance trước-khi-đo, số σ, dẫn log ma).
- Báo cáo đầy đủ: `.scratch/rev22.md`.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] `test_reap_khong_cho_zombie_5_giay` vẫn **đo thời gian tường** (`elapsed < 3 s`). Đúng gợi ý của
      ticket là đổi sang assert hành vi (`poll() is not None`) + ngưỡng rộng theo số CPU — **chưa sửa**
      vì test xanh 10/10 lần đo (sửa mù dễ làm test vô nghĩa). Làm khi tái hiện được.
- [ ] Chạy lại `./run testall` ×3 trên **máy có tải thật** (vd trong lúc render video) để thử tái hiện
      điều kiện 10-11 — số hôm nay là máy rảnh.
- [ ] Nếu CI bao giờ chạy `-m slow`: cân nhắc đưa test IoU ra khỏi làn nhanh (hiện đã là `slow`).

## 📚 Tài liệu tham khảo
- `AGENTS.md` §6 ("SAM 2 không tất định", ngưỡng nhiễu, `n < 2` không kết luận).
- `.scratch/rev22.md`; `tests/test_tracker_engine.py`; `data/flaky_iou_2026-11-17_metrics.json`.

## Bổ sung (đợt 3) — P2/P3 còn lại của review độc lập ticket #22

Báo cáo review về sau khi PR #30 merge; đối chiếu với cây `main` thì **2 P1 + 2 P2 đã được sửa trong
chính PR đó** (`@pytest.mark.timeout(300)` cho test có retry; provenance chụp **trước** khi nạp model +
từ chối ghi artifact nếu rev đổi giữa lúc đo; số σ tính lại; bỏ dẫn hai file log không commit được —
chúng bị `.gitignore` chặn). Phần còn mở đã xử lý trong đợt này:

| Phát hiện | Đã làm |
|---|---|
| P2 artifact **không echo cấu hình** model | `cau_hinh: {checkpoint, image_size_yeu_cau, image_size_hieu_luc, device}` (`_checkpoint_tu_config()` đọc `configs/default.yaml`) |
| P2 tóm tắt "0/N" **không phải** đại lượng test dùng | thêm `tat_ca.min_iou_moi_lan` = min trên **{0, 2, 5, 9}** + `so_lan_duoi_nguong`; đo được **0,928** (frame 0 trượt nhiều hơn 3 frame mẫu) |
| P2 lời "hồi quy thật không thể lọt qua" (sai xác suất: retry 1 lần lọt với `1 − p²`) | docstring đổi thành "hồi quy **ổn định** vẫn bị bắt"; nhánh retry thêm `warnings.warn` in IoU lần 1 ⇒ hồi quy **gián đoạn** còn dấu vết trong log `./run testall` |
| P2 kết luận "lần đỏ 10-11 là ngoại lệ của SAM 2 (không tất định)" vượt dữ liệu | sửa ở test + ticket: trong **cùng một tiến trình** phân bố gần như tất định (f2/f9 `std = 0,0000`) ⇒ chỉ được nói "**chưa tái hiện được**", chưa đo được tính tất định **giữa các phiên** |
| P3 `ms` mời đọc nhầm (là tổng 10 frame) | đổi tên `tong_ms`, in ra theo giây, docstring nói rõ khác `TrackingResult.elapsed_ms` |
| P3 `score_min` có thể là `NaN`/`inf` (JSON không hợp lệ với `JSON.parse`) | guard `math.isfinite`, ghi `score_n` |
| P3 comment "engine reset mỗi lần" nhờ auto-reset của `start()` | gọi `engine.reset()` **tường minh** đầu mỗi vòng |
| P3 `--lan 1` được nhận dù docstring nói ≥ 3 | từ chối `--lan < 3` (mã thoát 2) |
| P2 nợ `test_reap_khong_cho_zombie_5_giay` không có ticket | tạo **ticket #34** |

Sinh lại artifact trên cây sạch (`--lan 5`): `git_rev 472bc6e`, `git_dirty_code false`,
`tong_ms` 42,8 / 44,0 / 45,1 / 45,1 / 45,2 s; IoU f2 0,9512 · f5 0,9506–0,9750 · f9 0,9506;
cổng test (min trên {0,2,5,9}) = **0,928**; **0/5 lần** dưới ngưỡng 0,5.

`./run lint` xanh · `./run test` **1335 passed**, 5 deselected.

## Bổ sung (đợt 4) — P1/P2/P3 của review vòng 2 (PR #34)

Review vòng 2 bắt đúng **một P1**: `min_iou` lấy min trên **cả 10 frame** rồi được công bố như "cổng
test", trong khi test chấm **{0, 2, 5, 9}**; `0,928` hoá ra là **frame 4 (ngoài cổng)**. Đã sửa:

- `mot_lan()` tách **`min_iou_cong_test`** (min trên {0,2,5,9} = cổng thật) khỏi
  **`min_iou_moi_frame`** (min trên 10 frame, chỉ để tham khảo); `duoi_nguong` mỗi lần tính theo cổng.
- `tom_tat()` → `tat_ca.cong_test` với **hai mẫu số riêng**: `so_luot_frame_duoi_nguong/so_luot_frame`
  (lượt-frame) và `so_lan_chay_duoi_nguong/n` (lần chạy) — bản trước cộng 4 khoá rồi chia `lan*3` ⇒ trộn
  hai mẫu số vào một.
- P2 `cau_hinh.checkpoint`: `load_config()` **không** đọc `configs/default.yaml` (trả `DEFAULTS`) và
  engine dựng từ `DEFAULT_CKPT` ⇒ nay ghi `checkpoint` = `DEFAULT_CKPT` + `checkpoint_nguon` nói rõ
  đường đi, `checkpoint_loi` ghi lý do khi không lấy được (bắt **hẹp**, không nuốt lỗi thành `None`).
- P2 `cau_hinh.device`: `TrackerEngine` **không có** attribute `device` ⇒ trước đây luôn `null`; nay
  đọc từ `engine._predictor.device` + `str()` (vì `torch.device` không serialize được). `None` vẫn
  nghĩa "chưa kiểm được", **không** phải "cpu".
- P3 bỏ khung "σ" (σ là stdev của 5 mẫu ở riêng f5, so với min trên nhiều frame/lần là hai phân bố
  khác nhau) → viết "cách ngưỡng 0,5 khoảng 0,45 (gấp ~33 lần độ lệch lớn nhất đo được của một frame)".
- P3 message assert thôi khẳng định "SAM 2 không tất định" như sự thật (lần đo này chạy trong **một**
  tiến trình) → "nghi hồi quy thật".
- **Test mới** `tests/test_measure_flaky_iou.py` (6 test, engine giả, làn nhanh): assert `CONG_TEST ==
  {0,2,5,9}`, `min_iou_cong_test` = min trên đúng 4 frame (engine lệch ở frame 4 ⇒ min 10 frame thấp mà
  cổng vẫn 1,0), `duoi_nguong` theo cổng, hai mẫu số tách nhau, `score = NaN` ⇒ `score_min is None`,
  `--lan 2` bị từ chối. **Test này sẽ đỏ nếu ai đưa P1 trở lại.**

`./run lint` xanh · `./run test` gồm 6 test mới.
