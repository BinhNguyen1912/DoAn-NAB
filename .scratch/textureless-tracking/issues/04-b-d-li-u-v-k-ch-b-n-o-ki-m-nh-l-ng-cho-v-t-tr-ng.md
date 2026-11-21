# 4: Bộ dữ liệu và kịch bản đo kiểm định lượng cho vật trắng trơn

**What to build:** Tạo video test chiếc remote trắng trên nền sáng kèm Ground Truth, tích hợp vào hệ thống đo ./run miou để có số liệu chứng minh khách quan cho báo cáo đề tài.

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] Bổ sung clip test data/remote_trang.mp4 và manifest GT hộp bao/mask cho các mốc frame quan trọng
- [ ] Tích hợp kịch bản benchmark vào tools/score_miou.py và lệnh ./run miou
- [ ] So sánh định lượng mIoU và tỷ lệ mask_ngoai_gt giữa cấu hình mặc định cũ và cấu hình mới
- [ ] Đảm bảo không suy giảm kết quả mIoU trên các clip chuẩn hiện có (binh1, binh2)
