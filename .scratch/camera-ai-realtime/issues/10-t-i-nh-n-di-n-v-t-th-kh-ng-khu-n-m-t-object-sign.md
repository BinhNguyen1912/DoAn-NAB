# 10: Tái nhận diện VẬT THỂ (không khuôn mặt): Object Signature + quét lưới tìm lại

**What to build:** Hiện `ReIdSession` chỉ lưu/khớp **mặt** (`pick_face_near`, `face_quality_ok`) → với vật không có mặt (remote TV), `_refs` rỗng, `best_match` trả -1.0 → mất dấu là mất vĩnh viễn. Ticket này thêm cue **đặc trưng vật thể** dùng chung máy trạng thái.

Phạm vi (v1, không dùng model học sẵn):
- `src/appearance.py` (mới): `object_signature(frame, mask)` = covariance 5×5 trên [x,y,B,G,R] + HSV hist, ghép vector, chuẩn hoá từng khối; `signature_quality_ok`; `candidate_boxes(frame_shape, size, stride, scales)` để quét lưới khi mất dấu.
- `src/reid.py`: thêm chế độ cue `face | object | both`; lưu mẫu vật thể từ vùng mask khi đang TRACKING; ở trạng thái LOST thì chấm điểm các ô ứng viên và gọi `engine.start(bbox)` khi vượt ngưỡng.
- `configs/default.yaml` + `src/config.py`: `reid_cue`, `obj_sig_*`.
- Test thuần numpy trong `tests/test_appearance.py` + ca mới trong `tests/test_reid.py` (duck-type, không cần SAM 2).

Không làm ở v1: feature encoder SAM 2 (`TrackerEngine`), mạng embedding tự train (ticket sau), thay đổi luồng mặt.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] `src/appearance.py`: `object_signature` (covariance 5×5 + HSV hist), `signature_quality_ok`, `candidate_boxes` — hàm thuần
- [x] `tests/test_appearance.py`: cùng vật → cosine cao; khác màu → thấp; mask rỗng → bị chặn bởi quality gate; `candidate_boxes` phủ được đúng vị trí vật (có ô IoU ≥ 0.5)
- [x] `ReIdSession` thêm cue `object`: lưu mẫu từ vùng mask khi TRACKING, LOST → quét lưới → `engine.start(bbox)` khi vượt ngưỡng
- [x] `configs/default.yaml` + `src/config.py`: `reid_cue` (face|object|both) và tham số `obj_sig_*`; mặc định giữ nguyên hành vi cũ nếu không bật
- [x] `pytest -m "not slow"` + `ruff check .` xanh
- [x] Số đo ghi vào log: độ trễ thêm vào (ms/frame) và tỉ lệ nhận lại đúng trên fixture có che khuất
