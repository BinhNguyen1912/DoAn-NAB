# 39: Nối chẩn đoán LK (last_ly_do / last_ly_do_khop / n_points) ra shown.csv + status.json

**Type:** task

**Blocked by:** None (can start immediately)

## Question

**What to build:** `LkBoxTracker` (sau PR #65) có 2 field chẩn đoán quyết định nhưng **không rời khỏi tiến trình**:

- `last_ly_do`: `chua_chay`/`chua_reset`/`seed_rong`/`lk_hong`/`thieu_diem`/`mad_du`/`ok_shift`/`ok_scale` (kết quả cuối)
- `last_ly_do_khop`: `None`/`cong_similarity`/`bbox_hong`/`mad_du` (vì sao similarity bị bỏ)
- `last_scale`, `last_angle_deg`, `last_matrix`, và `n_points` (số điểm theo dõi được)

Hệ quả đã gặp thật: **suốt 3 vòng review của PR #65**, câu "vì sao f62 không có ô" chỉ **suy ra từ đường code** (`_seed` rỗng vì base VOS bbox `(0,0,0,0)`), không đọc được từ artifact nào; một lần còn suy sai thành "LK mất dấu". Không có field này trong artifact thì mọi phát biểu "LK từ chối vì X" đều là suy đoán.

**Phạm vi code** (đọc trước khi sửa):
- `src/light_tracker.py`: 3 field đã có, chỉ cần đọc.
- `src/live_tracking.py`: `_result_threaded` (`~917`) là nơi duy nhất biết cả `ok` và bbox; `_ghi_o_hien_thi` là nơi ghi `shown.csv`; `_update_stats_locked` ghi `status.json`.
- `scripts/ab_o_hien_thi_vs_gt.py`: `doc_shown` đọc CSV ⇒ thêm cột phải **tương thích ngược** (CSV cũ thiếu cột ⇒ cột `None`, KHÔNG được làm hỏng `cham()`).
- `status.json`: thêm khoá trong block chẩn đoán, echo giá trị **của frame gần nhất**; phải nêu rõ là "frame gần nhất", không phải trung bình.

**Ràng buộc (đã có tiền lệ sai trong repo):**
- CSV **cũ** (thiếu cột) phải đọc được: `doc_shown` trả `None` cho cột mới, và `scripts/ab_o_hien_thi_vs_gt.py` phải tự khai `csv_thieu_cot` trong artifact thay vì im lặng tính 0 (bẫy "0/None ≠ đã đo", AGENTS §6).
- `schema` của `ab_o_hien_thi_vs_gt.py` phải **tăng** nếu hình dạng `tong_hop`/`cham` đổi (đã có test buộc khoá ↔ schema).
- Không được để field chẩn đoán làm **chậm** đường phát: ghi vào CSV theo cùng nhịp ghi hiện tại, không thêm I/O mỗi frame.

**Nghiệm thu có số:**
1. Chạy `scripts/ab_o_hien_thi_vs_gt.py` 1 cấu hình ⇒ CSV có 4 cột mới; `status.json` có block chẩn đoán; `./run lint` + `./run test` xanh.
2. Test: CSV **cũ** (không có cột) ⇒ `doc_shown` trả `None`, artifact khai `csv_thieu_cot`, **không** ném lỗi.
3. Test: CSV **mới** ⇒ đếm được phân bố `last_ly_do` (ít nhất 2 giá trị khác nhau trên clip `binh1`) ⇒ chứng minh ghi đúng nhánh, không phải hằng số.
4. Đo lại được câu hỏi mở của ticket #38: tỉ lệ `lk_ok=false` do `mad_du` vs do `seed_rong` ở frame GT — nêu số cụ thể.
5. `measured_fps` không giảm quá ngưỡng nhiễu (±0,3 %) so với trước khi thêm (cùng clip + cấu hình).

**Không** được: ghi "đã nối ra CSV" mà chỉ ghi vào biến trong bộ nhớ; hoặc để `doc_shown` coi cột thiếu là chuỗi rỗng rồi đếm thành một giá trị thật.
