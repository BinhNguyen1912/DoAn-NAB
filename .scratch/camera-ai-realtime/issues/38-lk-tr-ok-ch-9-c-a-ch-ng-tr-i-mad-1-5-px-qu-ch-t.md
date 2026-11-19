# 38: LK trả `ok` chỉ ~9 %: cửa chống-trôi MAD 1,5 px quá chặt cho vật cầm tay — cần A/B max_mad

**Type:** grilling

**Blocked by:** None (can start immediately)

## Question

`lk_ok_frac` đo được **0,093** trong khung (`binh1` @192, `vos_every 3`, 44 mẫu, `data/lk_ok_binh1_2026-11-19_metrics.json`, `git_dirty_code=false`) ⇒ ~90 % thời gian ô người xem thấy là **ô VOS cũ đóng băng**, không phải nội suy. Chẩn đoán 19-11 (16 cặp base→frame rải trong `0:110`, ô chai `266,212,392,637`):

| bước nhảy | LK `ok` | điểm theo dõi được (median/64) | MAD trung vị |
|---|---|---|---|
| 1 frame | 9/16 | 50 | 1,4 px |
| 2 frame | 4/16 | 50 | 3,0 px |
| 3 frame | **1/16** | 49 | **4,8 px** |
| 5 frame | 2/16 | 47 | 12,4 px |

⇒ LK **không** thiếu điểm (≈50/64 mỗi bước); nó bị chặn bởi `DEFAULT_MAX_MAD = 1.5` (`src/light_tracker.py:23`): vật cầm tay **không rigid** (tay che, xoay, biến dạng) nên độ tản vector lớn **dù trung vị dịch đúng**. Nghĩa là hiện tại "hybrid VOS+LK" gần như chỉ là "ô cũ + 30 FPS vẽ lại".

**Việc phải làm**: A/B `max_mad` ∈ {1,5 (hiện tại), 3, 6, 10} × `grid` ∈ {8, 12} bằng `./run ab` (chèn kẽ, 3 lần/cấu hình), trên ≥ 2 clip + **ít nhất 1 clip vật đi chậm**; đồng thời kiểm bằng ảnh rằng tăng `max_mad` **không** làm ô bao bám vào nền (chốt MAD sinh ra để chặn đúng lỗi đó — AGENTS §6).

**Nghiệm thu có số**: báo cáo `lk_ok_frac`, `drift_iou` (trong khung), `mask_age_p95` cho từng cấu hình, kèm ngưỡng nhiễu theo ô chọn (±0,010 cho `drift_iou` ở ô chai, 55 s); chênh lệch < ngưỡng ⇒ viết "không phân biệt được". Nếu không cấu hình nào vừa tăng `lk_ok_frac` vừa giữ `drift_iou` ⇒ kết luận **trung thực** là phải **thôi hiển thị ô cũ** (ẩn ô giữa hai lần VOS) thay vì tăng ngưỡng.

**Không** được: chỉnh `max_mad` theo cảm giác rồi báo "đã cải thiện".
