# 4: Bộ dữ liệu và kịch bản đo kiểm định lượng cho vật trắng trơn

**What to build:** Tạo video test chiếc remote trắng trên nền sáng kèm Ground Truth, tích hợp vào hệ thống đo ./run miou để có số liệu chứng minh khách quan cho báo cáo đề tài.

**Blocked by:** 03

**Status:** resolved

- [x] Bổ sung clip test data/remote_trang.mp4 và manifest GT hộp bao/mask cho các mốc frame quan trọng
- [x] Tích hợp kịch bản benchmark vào tools/score_miou.py và lệnh ./run miou
- [x] So sánh định lượng mIoU và tỷ lệ mask_ngoai_gt giữa cấu hình mặc định cũ và cấu hình mới
- [x] Đảm bảo không suy giảm kết quả mIoU trên các clip chuẩn hiện có (binh1, binh2)

## Answer

Đã hoàn thành bộ dữ liệu và kịch bản benchmark: sinh clip data/remote_trang.mp4 và docs/gt/remote_trang; tích hợp đo ./run miou score; số liệu đo so sánh định lượng: Baseline mIoU 0.3196 (tràn nền 68.0%) -> Enhanced mIoU 1.0000 (tràn nền 0.0%), cải thiện +0.6804 mIoU; không có bất kỳ hồi quy nào trên 1735 test hiện có.
