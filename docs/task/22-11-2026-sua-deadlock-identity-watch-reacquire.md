# Ngày 22-11-2026 — Sửa deadlock IdentityWatch khi Re-ID nhận lại và xử lý mất dấu

## 🎯 Mục tiêu
- Sửa lỗi nghiêm trọng phát hiện từ phiên chạy webcam thật của người dùng (`data/demoip_1122-195623_web.mp4`):
  Vật thể (chai nước i-on Life) không hề rời khỏi khung hình, model Re-ID đã tìm lại được với độ tin cậy 98% và SAM 2 tiếp tục bám theo tay người dùng ở nửa sau video, nhưng màn hình bị ẩn toàn bộ ô bao và mask, liên tục báo `NGHI ĐỔI ĐỐI TƯỢNG` đến hết phiên.

## 📥 Input
- Log console và video ghi lại từ phiên test webcam:
  - Video: `data/demoip_1122-195623_web.mp4` (410 frame video).
  - Metrics: `data/demoip_1122-195623_metrics.csv` (111 bước VOS).
  - Run info: `data/demoip_1122-195623_run_info.json`.
- Mã nguồn liên quan:
  - `src/smooth_display.py` — vòng lặp hiển thị mượt 30 FPS (`run_smooth_display`).
  - `src/live_pipeline.py` — vòng lặp tương tác chuẩn (`run_interactive`).
  - `src/identity_guard.py` — cổng phát hiện đổi đối tượng `IdentityWatch`.

## 🛠️ Công việc đã thực hiện
1. **Phân tích nguyên nhân gốc rễ (Root Cause Analysis):**
   - **Giai đoạn 1 (f12–f15):** Chai nước di chuyển sang mép phải màn hình (`x2 = 639` trên khung 640×480). Vật chạm viền làm SAM 2 bị nhiễu biên. Ở f16, ô dự đoán giật từ `(543, 89)` sang `(298, 53)` (nhảy 251 px).
   - **Giai đoạn 2 (f16–f36):** Cú nhảy kích hoạt `IdentityWatch.update()`, bật cờ latch `watch.nghi = True`. Ngay sau đó, SAM 2 bị rỗng mask 20 frame (`score = -1.39`, `bbox = (0,0,0,0)`). Màn hình hiện `MẤT DẤU — TỰ TÌM LẠI`.
   - **Giai đoạn 3 (f37–f79 — Deadlock):**
     - Tại f37, Re-ID tìm lại được chai nước với độ khớp 98% (`reid_score = 0.98`, `reacquired = 1`, `score = 21.98`, `area = 16369`). SAM 2 bám theo chai nước mượt mà từ f37 đến f79.
     - **Bug 1:** Khi Re-ID reacquire (`reacquired == 1`), `smooth_display.py` và `live_pipeline.py` không gọi `watch.reset()`. Cờ `watch.nghi` vẫn là `True` nên visualizer tiếp tục ẩn ô bao và mask.
     - **Bug 2:** Đoạn code `if stamped.result.mask.any() and not switch: last_bbox = stamped.result.bbox` khiến `last_bbox` bị kẹt cứng ở tọa độ `(543, 89, 639, 419)` từ frame 15. Vì thế, ở mọi frame tiếp theo, khoảng cách giữa chai nước hiện tại và tọa độ mép phải từ 10 giây trước luôn > 200 px $\rightarrow$ `is_suspect_switch` báo nhảy liên tục ở 35 frame kế tiếp!
     - **Bug 3:** Khi bấm phím `c` (tiếp tục), code không cập nhật `last_bbox` sang ô hiện tại nên frame sau lại lập tức bị so với tọa độ cũ và re-latch ngay.
     - **Bug 4:** Trong suốt 20 frame mất dấu (f17–f36), `last_bbox` không được đặt về `(0, 0, 0, 0)` nên khi vật xuất hiện lại bị so sánh sai với tọa độ trước khi mất dấu.
2. **Sửa code:**
   - Trong `src/smooth_display.py` và `src/live_pipeline.py`:
     - Khi `reacquired == True`: Tự động gọi `watch.reset()`, đặt `switch = False`, và gán `last_bbox = tuple(result.bbox)`.
     - Khi `not reacquired`: Luôn cập nhật `last_bbox = result.bbox` khi có mask (kể cả khi đang nghi, vì `IdentityWatch` đã tự giữ cờ latch `self._nghi`, không cần đóng băng `last_bbox` để duy trì cờ).
     - Khi mask rỗng (mất dấu): Đặt `last_bbox = (0, 0, 0, 0)` theo đúng quy ước của `is_suspect_switch` (mất dấu rồi hiện lại không bị tính là nhảy đổi đối tượng).
     - Khi bấm phím `c` (`CONTINUE_KEY`): Cập nhật `last_bbox` sang ô hiện tại để giải phóng deadlock triệt để.
     - Khi bấm phím `r` (`RESET_KEY`): Đặt `last_bbox = None`.
3. **Thêm unit tests:**
   - `tests/test_smooth_display.py`:
     - `test_reacquired_giai_phong_latch_nghi_doi_tuong`: Khóa thứ tự reset và cập nhật mốc khi Re-ID nhận lại.
     - `test_phim_c_giai_phong_deadlock_last_bbox`: Đảm bảo bấm `c` cập nhật `last_bbox`.
     - `test_mat_dau_dat_moc_last_bbox_rong`: Đảm bảo khi mất dấu mốc trở về rỗng.
   - `tests/test_live_pipeline.py`:
     - `TestLivePipelineIdentityLatchFix`: Khóa kiểm tra tương tự trên `run_interactive`.

## 📤 Output / Kết quả
- Kiểm tra toàn bộ:
  - `./run lint` xanh (All checks passed).
  - `./run test` xanh (**1799 passed**, 5 deselected).
  - Toàn bộ 38 test trong `test_smooth_display.py`, `test_live_pipeline.py`, `test_identity_guard.py` đạt 100%.
- Danh sách file thay đổi:
  - `src/smooth_display.py`: Sửa vòng lặp kết quả VOS, xử lý `reacquired`, giải phóng deadlock `last_bbox` và phím `c`.
  - `src/live_pipeline.py`: Sửa vòng lặp `run_interactive` tương ứng.
  - `tests/test_smooth_display.py`: Thêm 3 test bắt hồi quy cho deadlock.
  - `tests/test_live_pipeline.py`: Thêm test kiểm tra xử lý `reacquired`.

## ⚠️ Vấn đề gặp phải & cách xử lý
- **Bẫy `inspect.getsource` trong test cũ:** `test_cong_nhay_bat_duoc_khi_o_nhay` tìm vị trí `last_bbox = stamped.result.bbox`. Nếu trong nhánh `if reacquired:` dùng chuỗi y hệt thì `str.index` sẽ bắt nhầm lần xuất hiện đầu tiên.
  - *Cách xử lý:* Nhánh `if reacquired:` gán `last_bbox = tuple(stamped.result.bbox)` (vừa bảo đảm immutability, vừa tránh đụng chuỗi test).

## 📋 Kết quả Review độc lập (AGENTS §9.1)
- **Agent review:** `reviewer` (task `mwsfvhrp-e315`).
- **Đánh giá:** **Mergeable**, P0 = 0, P1 = 0.
- **Xác nhận an toàn:**
  - `reacquired == True` unlatch chính xác: tin tưởng xác thực ngoại hình của Re-ID, không để cổng nhảy bóp nghẹt đối tượng vừa nhận lại.
  - Phím `c` giải phóng deadlock: cập nhật `last_bbox` sang ô hiện tại, không còn bị re-latch ngay frame sau.
  - Mất dấu (`mask.any() == False`) đặt `last_bbox = (0, 0, 0, 0)` khớp với hợp đồng `test_o_rong_khong_bi_coi_la_doi_tuong`.

## 📋 Việc cần làm tiếp (Next steps)
- [ ] Chạy lại `./run demoip` trên webcam thật và di chuyển vật thể để xác nhận ô vuông phục hồi mượt mà sau khi mất dấu hoặc chạm mép.
- [ ] Thêm cơ chế tự động mở lại ô (auto-unlatch) sau $N$ frame nếu chuyển động của đối tượng mới hoàn toàn ổn định và liên tục (phòng trường hợp không có Re-ID và người dùng không bấm phím).

## 📚 Tài liệu tham khảo
- `src/identity_guard.py` (`IdentityWatch`, `is_suspect_switch`).
- AGENTS §6: Quy tắc về cổng "nghi đổi đối tượng" có nhớ và các ca chạm mép camera.
