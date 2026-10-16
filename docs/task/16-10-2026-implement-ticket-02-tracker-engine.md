# Ngày 16-10-2026 — Implement ticket 02: TrackerEngine streaming (/tdd)

## 🎯 Mục tiêu
- Hoàn thành ticket 02 — nút nhân của hệ thống: bọc SAM 2 video predictor (config SAMURAI) thành streaming per-frame.

## 📥 Input
- Ticket `.scratch/camera-ai-realtime/issues/02-...md` (claimed, block bởi 01 — đã xong).
- Nghiên cứu code gốc: `sam2_video_predictor.py` (init_state / propagate_in_video / _get_image_feature) + `utils/misc.py` (_load_img_as_tensor, AsyncVideoFrameLoader) để thiết kế đúng chuẩn preprocess + cơ chế nạp frame từng bước.

## 🔨 Công việc đã thực hiện
1. **Thiết kế streaming** (chốt sau khi đọc code):
   - `TrackerEngine.start(frame, bbox)`: ghi frame 0 ra thư mục temp (1 JPG) → `init_state` → thay `state["images"]` bằng view `_StreamingImages` (trả tensor theo index) → `add_new_points_or_box` → propagate riêng frame 0.
   - `process(frame)`: preprocess theo đúng chuẩn SAM 2 (PIL resize 1024, BGR→RGB, /255, trừ mean 0.485/0.456/0.406, chia std 0.229/0.224/0.225) → append tensor, tăng `num_frames`, gọi `propagate_in_video(start_frame_idx=i, max_frame_num_to_track=1)` → đúng 1 frame/bước, memory SAMURAI chạy nguyên bản.
   - Giải phóng tensor raw sau khi xử lý (tiết kiệm RAM khi live dài).
2. TDD 3 chu kỳ: (1) start frame 0 mask không rỗng + IoU ≥ 0.5; (2) feed 10 frame → IoU ≥ 0.5 tại frame mẫu (2, 5, 9); (3) che khuất frame 3–4 → không crash, kết quả hợp lệ, SAMURAI hồi phục IoU ≥ 0.3 sau che.
3. `pytest.ini` khai marker `slow`; fixture `samurai_engine` session-scoped (build 1 lần, tắt tqdm khi test).
4. Script demo `tools/demo_tracker_frames.py` — đọc thư mục JPG, track theo bbox file txt, in bbox/score/ms từng frame.
5. Chạy demo thật trên 6 frame con chó (`data/demo_input_frames`): bbox bám đúng chó di chuyển (x2: 703→765), score ~9, ms/frame ~3.4k.
6. Code-review 2 trục: tìm 1 finding (biến TQDM_QUIET_NOTE thừa trong demo) → dọn; không thấy smell mới ở engine.

## 📤 Output / Kết quả
- **13/13 tests green** toàn suite (fast 0.2s + slow ~79s trên CPU, không GPU).
- Ticket 02: **4/4 tiêu chí ticked**.
- Demo thật: tracker bám chó qua 6 frame streaming per-frame ✓.
- File thay đổi:
  - `src/tracker_engine.py` — TrackerEngine + TrackingResult + _StreamingImages (mới)
  - `tests/test_tracker_engine.py` — 3 test slow (mới)
  - `tests/conftest.py` — thêm fixture samurai_engine, pytest.ini (sửa)
  - `pytest.ini` — marker slow (mới)
  - `tools/demo_tracker_frames.py` — script demo streaming (mới)

## 🐞 Vấn đề gặp phải & cách xử lý
- Sửa conftest bằng edit gây trùng lặp `return _write` → đọc lại file, viết lại sạch.
- tqdm 4.70.1 không đọc TQDM_DISABLE env → patch `vp.tqdm = lambda it, ...: it` trong fixture/demo.
- `data/demo_input_frames` là thư mục JPG — `cv2.VideoCapture` không mở được → demo script đọc ảnh trực tiếp (sắp xếp theo tên).
- Warning sam2 `_C` extension không import được (build CPU không compile CUDA extension) — vô hại theo INSTALL.md SAM 2.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Ticket đã mở 04 (Pipeline live end-to-end) — blockers 02+03 đã xong hết.
- [ ] 05 PromptSelector → 06 HUD → 07 MetricsLogger → 08 Headless+README.

## 📚 Tài liệu tham khảo
- `/implement`, `/tdd`; code gốc `samurai/sam2/sam2/sam2_video_predictor.py`, `utils/misc.py`; nghiên cứu `docs/research/03`.