# Ngày 08-11-2026 — Đo cái giá của nội suy LK (drift_iou, mask_age) + ngưỡng nhiễu

## 🎯 Mục tiêu
- Trả lời câu hỏi nền mà **toàn bộ kiến trúc hybrid đứng trên nhưng chưa từng được đo**: *bỏ 2/3 lần
  suy luận (VOS) thì ô bao trôi bao nhiêu so với lần VOS kế tiếp?* `stability` hiện có chỉ đo **nhấp
  nháy**, không đo **đúng**.
- Công bố **ngưỡng nhiễu** để mọi phép so A/B sau này không bị đọc thành "cải thiện" khi thực ra là
  dao động giữa hai lần chạy (SAM 2 không tất định — đã ghi ở log 08-11).
- **Ngưỡng đăng ký TRƯỚC khi chạy** (không được đổi sau khi thấy số): binh1 @ `vos_every=3` phải có
  `drift_iou_p05 ≥ 0,70`, `drift_iou ≥ 0,85`, `mask_age_p95 ≤ 150 ms`; không đạt ⇒ hạ mặc định
  `vos_every` về 2.

## 📥 Input
- Plan 3 cố vấn (`docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md`): việc 2.
- Cố vấn A: *"repo đang đo sai thứ quan trọng nhất — `stability` không trả lời được câu duy nhất mà
  kiến trúc hybrid cần"*.

## 🔨 Công việc đã thực hiện
1. **`src/live_tracking.py`**:
   - `drift_iou` / `drift_iou_p05`: khi VOS mới về, so ô bao **đang hiển thị** (do LK nội suy) với ô
     bao của lần VOS đó. Chỉ tính khi **cả hai** bbox hợp lệ (mask rỗng ⇒ bbox `(0,0,0,0)` ⇒ bỏ mẫu,
     không được coi là "lệch 0").
   - `mask_age_ms` / `mask_age_p95`: thời điểm sinh mask được mang trong `_vos_state`; mỗi frame phát
     tính `now − produced_at`. Trả lời "mask đang hiện cũ bao lâu".
   - Cửa sổ 200 mẫu để lấy p05/p95 (đủ để phân vị có nghĩa), ghi dưới `_stats_lock`.
2. **`scripts/repeatability.py` (mới)**: `spread()`, `la_khac_biet()`, `danh_gia()` — hàm thuần, có
   test; dùng để phát biểu "khác thật" vs "inconclusive".
3. **Artifact** `data/drift_2026-11-08_metrics.json`: 7 lần chạy, `git_rev`, `git_dirty`, lệnh, môi
   trường, **ngưỡng đăng ký trước**, ngưỡng nhiễu, và danh sách phát hiện.

## 📤 Output / Kết quả
`image_size=192`, 600 frame/cấu hình, laptop CPU:

| Lần chạy | FPS phát | mask/giây | **drift_iou (p05)** | **mask_age p95** | mask rỗng |
|---|---|---|---|---|---|
| binh1 · vos3 | 29,3 | 8,3 | **0,928 (0,804)** | 112 ms | 0 |
| binh1 · vos3 · lần 2 | 29,9 | 8,2 | 0,925 (0,779) | 117 ms | 0 |
| binh1 · vos3 · lần 3 | 28,9 | 7,7 | 0,926 (0,773) | 115 ms | 0 |
| binh1 · vos1 (tắt LK) | 9,3 | 9,3 | 0,962 (0,891) | 0 ms | 0 |
| binh1 · vos6 | 29,4 | 4,9 | 0,897 (0,731) | **184 ms** ✗ | 0 |
| binh1_simloss · vos3 | 29,3 | 8,4 | 0,918 (0,783) | 115 ms | 13 |
| **binh2 · vos3** | 29,3 | 8,4 | **0,647 (0,000)** | 115 ms | **22** |

- **Ngưỡng đăng ký trước: ĐẠT** ở cả 3 lần chạy binh1 ⇒ **giữ `vos_every` mặc định = 3**. Từ nay
  README được phép viết: *"nội suy LK giữ ô bao trung bình 0,93 IoU so với lần VOS kế tiếp (p05
  0,78), mask cũ p95 ~115 ms"* — **chỉ cho binh1/binh1_simloss**.
- **Ngưỡng nhiễu (3 lần cùng cấu hình):** `drift_iou` ±0,003; `vos_fps` ±7,3 %; `measured_fps`
  ±3,4 %; `mask_age_p95` ±4,6 %. Mọi so sánh nhỏ hơn các mức này là **inconclusive**.
- **Phát hiện phải báo trung thực:** trên **binh2**, `drift p05 = 0,000` và **22 lần mask rỗng** ⇒
  nội suy LK **mất dấu** ở clip đó. Tuyên bố "hybrid giữ được ô bao" **không đúng cho mọi clip**;
  phải nêu điều kiện (clíp/đối tượng) hoặc đo drift cho từng phiên trước khi tin.
- `vos_every=6` vượt ngân sách tuổi mask (184 ms > 150 ms) ⇒ **không** dùng mặc định; muốn ít suy
  luận hơn thì phải chấp nhận mask cũ hơn và nói rõ.
- File thay đổi: `src/live_tracking.py`, `scripts/repeatability.py` (mới),
  `tests/test_repeatability.py` (mới), `tests/test_live_tracking.py` (+4 test drift/age),
  `data/drift_2026-11-08_metrics.json`.

## 🐞 Vấn đề gặp phải & cách xử lý
- Lần chạy bench đầu trả **0 frame** ở cả 7 cấu hình: script truyền thiếu tham số nên `bbox.json`
  rỗng ⇒ worker đứng ở trạng thái `waiting_selection` (đúng thiết kế — nó chờ người dùng chọn).
  Không phải lỗi code; sửa script. Bài học: `status.json` có `state` nên phải kiểm state trước khi
  tin số.
- `np.percentile` trên deque mỗi lần VOS: 200 phần tử, không đo được chi phí (µs) ⇒ không ảnh hưởng
  nhịp phát (FPS phát không đổi so với trước: 29,3–29,9).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Cảnh báo/ tự hạ cấp khi drift xấu**: `p05 < 0,2` (như binh2) ⇒ tự chuyển `vos_every=1` hoặc
      báo đỏ trên UI. Hiện mới đo, chưa hành động.
- [ ] **Mọi bảng số A/B trong báo cáo phải nêu ngưỡng nhiễu** (dùng `scripts/repeatability.py`) —
      đã ghi vào AGENTS §6.
- [ ] Đo drift cho **clip che khuất đi ngang** (kịch bản khó nhất) — dự đoán LK sẽ trôi qua vật cản.
- [ ] Video demo H.264 (recorder đang `mp4v`, Chrome không phát được).

## 📚 Tài liệu tham khảo
- `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md` (việc 1–2, ngưỡng đăng ký trước).
- `data/drift_2026-11-08_metrics.json`, `scripts/repeatability.py`.
- AGENTS §6 (mục "stability không phải thước đo độ chính xác").
