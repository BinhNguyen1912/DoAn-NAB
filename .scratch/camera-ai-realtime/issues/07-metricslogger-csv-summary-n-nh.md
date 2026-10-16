# 7: MetricsLogger (CSV + summary + độ ổn định)

**What to build:** Module hàm thuần: nhận bản ghi mỗi frame (thời gian xử lý ms, số frame, điểm tin cậy mask, tâm, cờ mất dấu) → ghi CSV từng dòng + thống kê tổng hợp (mean/p95 latency, FPS trung bình, tỷ lệ mất dấu) ra file. Dùng cho mục "Đánh giá hiệu năng" (yêu cầu 6 của thầy) — khớp các story 13–16 của spec.

**Blocked by:** 01

**Status:** claimed

- [x] Cho N bản ghi giả → CSV đúng cột/dòng; summary tính đúng mean/p95
- [x] Cờ mất dấu (mask rỗng/điểm dưới ngưỡng) đếm được tỷ lệ trong summary
- [x] Tâm (x,y) từng frame được ghi đủ để vẽ quỹ đạo cho báo cáo
- [x] Test nhanh, không cần model
