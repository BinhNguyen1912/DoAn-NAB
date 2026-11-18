# 18-11-2026 — Ticket #32 (rá số p95 độ trễ trong docs) + đóng sổ #31/#32/#34/#35/#37

## Mục tiêu

Đóng nốt các tiêu chí còn `[ ]` của ticket #32 (và ghi lại việc đã xong của #31/#34/#35/#37) để bảng
ticket phản ánh đúng thực tế, không để "resolved" mà còn ô trống.

## Input

- `.scratch/camera-ai-realtime/issues/32-*.md` — tiêu chí 3: "số p95 latency trong docs/báo cáo được rà
  lại: số nào đo bằng code cũ thì ghi rõ hoặc sinh lại artifact".
- Ticket #34, #35 (đã merge PR #37, #38), #36 (PR #39), #37 (PR #40).

## Công việc đã thực hiện

1. **Rà số p95 độ trễ trong docs**: `docs/doi-chieu-yeu-cau-gvhd.md` trích `p95 312/370/287 ms` từ
   `data/res_1102_summary.json`, `data/camtest_summary.json`, `data/demoip_1104-*_summary.json`. Kiểm ba
   artifact: **không có** `p95_latency_ms_n`/`mean_latency_ms_n` (sinh trước 17-11, code cũ trả `0,0`
   khi rỗng) ⇒ thêm khối ⚠ ngay dưới bảng: số dùng được nhưng **không nêu được cỡ mẫu**; artifact từ
   17-11 trở đi có `*_n`, `n == 0` = **chưa đo**.
   **Không sinh lại artifact**: rerun sẽ ra số khác (máy/ánh sáng khác) mà không chứng minh được gì thêm
   — cách đúng là ghi rõ nguồn/số mẫu, đúng yêu cầu "số nào đo bằng code cũ thì ghi rõ".
2. **Đóng sổ ticket** (kiểm bằng code + test đã merge, không chỉ đọc lời):
   - #31: `mask_manifest_loi` có trong artifact, cảnh báo "CÙNG một hộp … copy-paste", `docs/thuoc-do-bam-dung.md` §1.2 có 2 dòng ⇒ tick 3 ô.
   - #32: `p95_ms`/`mean_latency_ms` trả `None` + `_n`; consumer (plot/summary/CLI) xử lý `None`; ô thứ 3 nay xong bằng mục 1.
   - #34, #35, #36, #37: đã merge (`PR #37`, `#38`, `#39`, `#40`) với review độc lập + diễn tập ngược — status `resolved`.

## Output / Kết quả

- 1 khối cảnh báo trong `docs/doi-chieu-yeu-cau-gvhd.md`; bảng ticket không còn ô `[ ]` "mồ côi" ở các
  ticket đã xong.
- `./run lint` xanh (không đổi code sản phẩm — chỉ docs + tracker).

## Vấn đề & cách xử lý

- **Lỗi quy trình của mình (ghi lại cho trung thực)**: commit ticket #37 được tạo **thẳng trên `main`**
  rồi mới tách nhánh (`fix/37-bbox-khong-cuop-phien-api`) và push. Đã đưa `main` về đúng `origin/main`
  (`reset --hard`), commit đó chỉ còn trên nhánh + PR #40 ⇒ lịch sử `main` không có commit lén. Việc đúng
  phải làm ngay từ đầu: `git checkout -b <nhánh>` **trước** khi sửa file.
- Số p95 trong docs **không** sinh lại: lý do ở mục 1 (không tăng được độ tin cậy, lại tốn ~30 phút
  chạy máy).

## Next steps

- Ticket còn mở và **cần người**: #11 (`ready-for-human`), #14 (chờ clip có p05 thấp mà `empty ≈ 0`),
  #21 (thiết bị/`image_size` mặc định theo GPU — cần máy GPU), #09 (re-ID, đang `claimed` 8/9).
- Chưa có ngưỡng nhiễu cho `stability` ⇒ mọi A/B `stability` vẫn phải ghi "không phân biệt được" (ticket
  #35, ô 3 để mở có chủ ý).

## Tài liệu tham khảo

- `docs/doi-chieu-yeu-cau-gvhd.md` (bảng yêu cầu 10 + khối ⚠ mới)
- `data/res_1102_summary.json` (không có `*_n`), `src/metrics_logger.py`, `src/live_pipeline.py`
