# 25-11-2026 — Kalman của SAMURAI rò giữa hai phiên trong cùng process (tái lập số đo)

## 1. Mục tiêu
Cố vấn thứ 3 (độ bền & hiệu năng) của plan `docs/plan/25-11-2026-tu-het-nghi.md` khẳng định: trạng thái
**Kalman của SAMURAI** nằm trên **MODEL**, không bị `reset()`/`init_state()` dọn ⇒ hai phiên liên tiếp
trong một process không tái lập, và **bấm `r` chọn vật khác sẽ thừa hưởng Kalman của vật cũ**. Kiểm lại
bằng đo trên máy này rồi sửa.

## 2. Input
`data/binh1.mp4` (13 frame đầu), ô `(300,275,450,685)`, checkpoint tiny, `image_size 192`, CPU.

## 3. Công việc đã thực hiện
### 3.1 Tái hiện (không tin báo cáo, tự đo)
| lần chạy | `IoU` phiên 1 vs phiên N theo từng frame | min |
|---|---|---|
| đo lần đầu, **8 frame** | toàn 1,0000 | **1,0000** ⇒ **không** tái hiện |
| đo lại, **13 frame** | `1.0,1.0,1.0,1.0,1.0,0.8253,0.8976,0.8363,0.9738,0.8567,0.9769,0.99,0.9912` | **0,8253** |
| phiên thứ 3, **có** zero `kf_mean`/`kf_covariance`/`stable_frames` | toàn 1,0000 | **1,0000** |

⇒ Báo cáo **đúng**, nhưng ngưỡng tái hiện là **số frame**: lệch bắt đầu từ **frame thứ 6**. Lần đo 8
frame của tôi không đủ dài ⇒ nếu chỉ chạy một lần rồi kết luận "không có bug" thì đã bỏ sót (bài học
`n` nhỏ).

Cơ chế (đọc code): `src/tracker_engine.reset()` chỉ dọn `inference_state`; `sam2_base.py:203-205`
(`self.kf_mean`, `self.kf_covariance`, `self.stable_frames`) **thuộc model** và được dùng lại ở
`sam2_base.py:421-441`.

### 3.2 Sửa
`TrackerEngine.start()` gọi `_xoa_trang_thai_kalman()` (mới): zero 3 field nếu tồn tại, trả `True/False`
(engine giả trong test không có ⇒ không nổ). Đặt trong `start()` chứ không trong `reset()` để một chỗ
duy nhất, và vì `start()` là điểm bắt đầu **mọi** phiên (kể cả `r` chọn lại / `reanchor`).

Sau khi sửa: 3 phiên liên tiếp ⇒ **min IoU = 1,0000** ở cả hai cặp.

## 4. Output / Kết quả
- `src/tracker_engine.py`: `_xoa_trang_thai_kalman()` + gọi trong `start()` (docstring nêu số đo).
- `tests/test_tracker_engine.py::TestXoaKalmanGiuaHaiPhien`:
  - 2 test nhanh với predictor giả (zero đúng 3 field, không đụng field khác; engine không có
    `_predictor` ⇒ `False`, không nổ);
  - 1 test `@pytest.mark.slow` chạy thật: hai phiên liên tiếp phải **IoU ≥ 0,999** mọi frame
    (8 frame — đủ bắt vì lệch bắt đầu từ frame thứ 6; `timeout(900)` vì fixture dựng `image_size 1024`).
- `./run lint` xanh · `./run test` **2 083** xanh.

## 5. Vấn đề & cách xử lý
- Test slow đầu tiên **timeout 120 s** (26 lượt propagate ở 1024 trên CPU). Sửa: 8 frame + marker
  `timeout(900)`; ghi rõ lý do ngay trên test.
- **Không** làm theo đề xuất "verifier chạy trên state mới" (A′) của cố vấn: họ tự đo được
  **2 lần cùng frame cho IoU 0,695** — chính vì Kalman rò ⇒ A′ **không tái lập được**. Nay KF đã được
  xoá ở `start()` nên nếu sau này thử lại A′ thì phải đo lại tính tái lập.

## 6. Next steps
- **Đổi hành vi có chủ ý**: bấm `r` chọn vật khác giờ **không** còn mồi Kalman từ vật cũ. Mọi bảng số
  chạy **nhiều phiên trong một process** (không qua subprocess) phải coi là **cũ**; `./run bangcau` và
  `./run ab` chạy subprocess từng cấu hình ⇒ an toàn.
- Cố vấn còn nêu: `add_new_points_or_box` trên frame đã track **nổ** `KeyError: 'best_iou_score'` rồi
  **giết phiên** (2/2 lần) ⇒ đã chốt **không** đi đường "re-prompt tại chỗ"; ghi vào plan.
- Chưa làm: `tests/conftest.py` dùng engine **session-scoped** ⇒ sau sửa này kết quả test không còn
  phụ thuộc thứ tự (nhưng nên đổi sang function-scoped nếu một ngày có engine rẻ).

## 7. Tài liệu tham khảo
- `docs/plan/25-11-2026-tu-het-nghi.md` (góc nhìn C, việc 2)
- `samurai/sam2/sam2/modeling/sam2_base.py:203-205, 421-441`
- `docs/task/25-11-2026-round-trip-het-nghi.md` (luật round-trip — cùng nguồn)
