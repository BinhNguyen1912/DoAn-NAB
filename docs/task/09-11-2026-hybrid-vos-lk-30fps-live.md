# Ngày 09-11-2026 — Hybrid VOS + LK: live 30 FPS, mask vẫn ~8,5 FPS

## 🎯 Mục tiêu
- Phase 4c: hình live mượt **~30 FPS** trên laptop CPU (trần VOS @192 là ~10 FPS).
- Trung thực về giới hạn: **mask chỉ mới ở nhịp VOS**, phần giữa là mask cũ tịnh tiến theo LK.
- `vos_every` chỉnh được từ API (`/api/live/start`) và CLI (`--vos-every`), mặc định 3.

## 📥 Input
- Số đo LK trước đó: 2,22 ms (rảnh) / 3,19 ms (dưới tải), dùng ~10 % ngân sách 33 ms — `docs/research/09`.
- Trần pipeline SAM 2.1 tiny @192: ~78–108 ms/lần suy luận (AGENTS.md mục 6).
- Đoạn code cũ: `src/live_tracking.py` (Phase 4b) chạy VOS **mỗi frame**.
- Yêu cầu người dùng: "tiếp tục triển khai" (nối tiếp lộ trình Phase 4c đã chốt).

## 🔨 Công việc đã thực hiện
1. **`src/light_tracker.py` (mới)** — `LkBoxTracker`: gieo lưới 8×8 điểm trong ô bao, chạy
   `cv2.calcOpticalFlowPyrLK`, lấy **trung vị** vector dịch (bền với điểm trôi theo nền), tịnh tiến
   ô bao. Thêm chốt **độ tản (MAD > 1,5 px ⇒ mất dấu)** — không có chốt này LK "khớp" vào nhiễu và
   báo ô bao sai (test `test_khong_theo_duoc_khi_frame_sau_doi_hoan_toan` bắt đúng lỗi này).
   `shift_mask()` dịch mask VOS theo (dx, dy) giữa hai lần suy luận.
2. **`src/live_tracking.py`** — hai chế độ:
   - `vos_every=1`: VOS mỗi frame, không LK (đường cũ, giữ để so sánh).
   - `vos_every>1`: `_VosWorker` (thread) chạy model; vòng phát đọc frame → LK từ **frame VOS gần
     nhất** tới frame hiện tại (mốc luôn là frame VOS ⇒ sai số **không tích luỹ**) → vẽ → ghi.
     Frame gửi cho worker luôn là frame **mới nhất** (bỏ frame cũ, không xếp hàng).
   - `status.json` thêm `vos_runs`, `vos_fps`, `vos_ms`, `lk_ms`; HUD in cả hai nhịp.
3. **Xuyên tầng**: `LiveStartRequest.vos_every` (1–30) → `LiveStreamService.start` → nhà máy nguồn
   → `WorkerFrameSource` → `build_live_worker_command` → `tools/live_worker.py --vos-every`.
4. **Test mới**: `tests/test_light_tracker.py` (12 test: bám trục x/y, mất dấu, chi phí < 10 ms,
   `shift_mask`) + 5 test hybrid trong `tests/test_live_tracking.py` (VOS ít hơn frame phát,
   `vos_every=1` tắt LK, `display_fps > vos_fps` với engine giả 50 ms) + 2 test API (`vos_every`
   truyền xuống nhà máy nguồn, ngoài khoảng → 422).

## 📤 Output / Kết quả
- **Đo thật** (`tools/live_worker.py`, `data/binh1.mp4` 1280×720, `image_size=192`, `--max-fps 30`,
  30 s/phiên, SAM 2.1 tiny):

  | `vos_every` | FPS hiển thị | VOS (mask mới) | VOS ms | LK ms | vos_runs/frames |
  |---|---|---|---|---|---|
  | 1 (tắt LK) | 10,1 | 10,1 | 78 | — | 387/387 |
  | **3 (mặc định)** | **29,8** | 8,5 | 108 | 4,6 | 120/400 |
  | 6 | 29,8 | 5,0 | 94 | 4,5 | 68/400 |
  | 10 | 29,8 | 3,0 | 70 | 3,1 | 41/400 |

- **Đo tách bạch nguyên nhân** (engine giả "tốn" 78 ms, cùng video): đơn luồng `vos_every=3` chỉ
  **18,0 FPS**; tách luồng **29,7 FPS**. ⇒ 30 FPS đến từ **luồng riêng**, không phải từ LK;
  LK lo phần **vị trí ô bao/mask bám kịp** giữa hai lần suy luận.
- File thay đổi:
  - `src/light_tracker.py` — LK tracker + `shift_mask` (mới)
  - `src/live_tracking.py` — `_VosWorker`, `vos_every`, hai đường chạy, status mới
  - `src/api/schemas.py`, `src/api/routes.py`, `src/api/live.py`, `src/api/adapters/worker_source.py`,
    `src/worker/command.py`, `tools/live_worker.py` — nối `vos_every`
  - `tests/test_light_tracker.py`, `tests/test_live_tracking.py`, `tests/test_api_live.py`, `tests/conftest.py`
  - `README.md`, `AGENTS.md` — bảng số + quy tắc "cấm claim mask 30 FPS"

## 🐞 Vấn đề gặp phải & cách xử lý
- **LK "bám" vào nhiễu**: trên frame phẳng/nhiễu hoàn toàn, `calcOpticalFlowPyrLK` vẫn trả về vector
  cho mọi điểm ⇒ tracker báo bám tốt trong khi đối tượng đã mất. Xử lý: chốt **độ tản trung vị
  (MAD)** — vector dịch thật rất đồng nhất, khớp nhiễu thì tản mát.
- **Video test nền phẳng (toàn 90) ⇒ LK thất bại ⇒ rơi về VOS mỗi frame**, test hybrid đỏ. Xử lý:
  fixture `textured_video` (nhiễu nền + ô sáng dịch dần) — đúng bản chất "LK cần gradient".
- **Đơn luồng không đạt 30 FPS** dù `vos_every=3`: 108 ms của model nằm ngay trong vòng phát.
  Xử lý: `_VosWorker` thread + nội suy LK từ frame VOS gần nhất. Đã kiểm chứng bằng số (18 → 29,8).
- `time.sleep` không phải thủ phạm (đo riêng: sleep 20/33 ms chính xác 20,3/33,4 ms).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] HUD/UI hiện `vos_fps` để người xem biết mask đang mới ở nhịp nào (hiện chỉ trong status.json).
- [ ] Chống nhấp nháy mask giữa hai lần VOS khi vật bị che một phần (EMA mask hoặc hysteresis).
- [ ] Đo lại bộ số trên Colab T4 (`scripts/colab_run_all.py`) để có bảng GPU cho báo cáo.
- [ ] Video demo 30 FPS làm minh chứng cho báo cáo (ADR-0002 mục "video minh hoạ").

## 📚 Tài liệu tham khảo
- `docs/research/09-kha-nang-tang-toc-bang-tracker-nhe.md` — số đo LK/MIL/Nano.
- OpenCV `calcOpticalFlowPyrLK`: https://docs.opencv.org/4.x/dc/d6b/group__video__track.html
- Lucas–Kanade 1981, "An iterative image registration technique…".
- `docs/adr/0002-*.md` (trung thực số liệu), `docs/adr/0005-*.md` (API không import torch).
