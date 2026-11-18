# 18-11-2026 — Ticket #32 (rá số p95 độ trễ trong docs) + đóng sổ #31/#32/#34/#35/#37

## Mục tiêu

Đóng nốt các tiêu chí còn `[ ]` của ticket #32 (và ghi lại việc đã xong của #31/#34/#35/#37) để bảng
ticket phản ánh đúng thực tế, không để "resolved" mà còn ô trống.

## Input

- `.scratch/camera-ai-realtime/issues/32-*.md` — tiêu chí 3: "số p95 latency trong docs/báo cáo được rà
  lại: số nào đo bằng code cũ thì ghi rõ hoặc sinh lại artifact".
- Ticket #34, #35 (đã merge PR #37, #38), #36 (PR #39), #37 (PR #40).

## Công việc đã thực hiện

1. **Rà số p95 độ trễ trong docs** (phạm vi: bảng phụ lục "Số liệu dùng được ngay trong báo cáo";
   log/ADR lịch sử **giữ nguyên** theo AGENTS §2): `docs/doi-chieu-yeu-cau-gvhd.md` trích **312 ms** từ
   `data/res_1102_summary.json`; kiểm thêm `camtest` (370,42) và `demoip_1104-212328` (287,45) để xác
   nhận **cả ba** đều **không có** `p95_latency_ms_n`/`mean_latency_ms_n` (sinh trước 17-11).
   Cỡ mẫu **vẫn suy được**: `n = total_frames − frozen_frames` ⇒ **6** / **25** / **52**
   (`+ fast_1101-153223` 22, `gui` 15). Với **n = 6** thì `p95 312 ms` gần **max 340,4** ⇒ đó là điều
   phải cảnh báo, **không** phải "không nêu được cỡ mẫu" (bản nháp đầu của mình viết sai như vậy —
   review bắt đúng).
   **Không sinh lại artifact**: rerun sẽ ra số khác (máy/ánh sáng khác) mà không chứng minh được gì thêm
   — cách đúng là ghi rõ nguồn/số mẫu, đúng yêu cầu "số nào đo bằng code cũ thì ghi rõ".
2. **Đóng sổ ticket** (kiểm bằng code + test đã merge, không chỉ đọc lời):
   - #31: `mask_manifest_loi` có trong artifact, cảnh báo "CÙNG một hộp … copy-paste", `docs/thuoc-do-bam-dung.md` §1.2 có 2 dòng ⇒ tick 3 ô.
   - #32: `p95_ms` trả `None` + `p95_latency_ms_n`; `mean_latency_ms` **vẫn `0,0`** nhưng có
     `mean_latency_ms_n` (vì `effective_fps = 1000/mean` là hợp đồng cũ) — bản nháp đầu ghi "cả hai trả
     `None`" là **sai**; consumer (plot/summary/CLI) xử lý `None`/`n`; ô thứ 3 nay xong bằng mục 1.
   - #34, #35, #36, #37: đã merge (`PR #37`, `#38`, `#39`, `#40`) với review độc lập + diễn tập ngược — status `resolved`.

## Output / Kết quả

- 1 khối cảnh báo **đặt sau khi bảng kết thúc** trong `docs/doi-chieu-yeu-cau-gvhd.md` (bản đầu chèn
  **giữa bảng** ⇒ 11 dòng sau bị render thành paragraph — P1 review bắt đúng); bảng ticket không còn ô
  `[ ]` "mồ côi" ở các ticket đã xong (#31 tick cả 4 ô, #32 tick cả 3).
- **File thay đổi**: `docs/doi-chieu-yeu-cau-gvhd.md`, `docs/task/18-11-2026-ticket-32-ra-so-p95-va-dong-ticket-31.md`,
  `.scratch/camera-ai-realtime/issues/31-*.md`, `32-*.md`.
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

## Review độc lập (AGENTS §9.1)

Reviewer (phiên chỉ-đọc, **không** chạy được lint/test) bắt **3 P1 + 3 P2 + 4 P3**; đã sửa hết trong
cùng PR:

- **P1-1 (lỗi render)**: khối ⚠ chèn **giữa bảng** ⇒ 11 dòng sau thành paragraph. Đã dời xuống **sau**
  dòng cuối của bảng; kiểm lại bằng script: 17 dòng bảng, **0** dòng không-phải-bảng chen giữa.
- **P1-2 (tiêu chí chưa tick)**: script tick cũ đếm theo "dòng `- [ ]` thứ n" nên **không** tick được ô
  duy nhất của #32. Đã tick đúng; #31 tick nốt ô thứ 4 (`lint`/`test` xanh — Answer đã nêu).
- **P1-3 (câu cảnh báo SAI)**: "không nêu được cỡ mẫu" là sai — `total_frames − frozen_frames` cho
  n = 6/25/52/22/15; điều đáng cảnh báo là **n = 6 ⇒ p95 ≈ max**. Đã viết lại.
- **P2**: (a) `mean_latency_ms` **vẫn** trả `0,0` (chỉ `p95` thành `None`) — đã tách câu; (b) docs chỉ
  trích 312 ms, không phải "312/370/287" — đã sửa; (c) câu "#37 đã merge" chỉ đúng **sau** khi PR #40
  merge (`4a2788c`) — nay đã merge nên giữ, và ghi rõ PR.
- **P3**: thêm "`*_summary.json`" cho phạm vi khoá `_n`; nêu **phạm vi rà** (chỉ bảng phụ lục, log/ADR
  lịch sử giữ nguyên); cập nhật "Cập nhật lần cuối: 18-11-2026"; bổ sung mục Output (danh sách file) +
  mục review này.

**Đã kiểm, không phải lỗi** (reviewer xác nhận): ba artifact đúng là thiếu `*_n`; số trong bảng khớp
artifact; code hiện tại đúng hợp đồng #32 (`p95 → None` + `_n`, `mean → 0,0` + `_n`, có test ghim); 3 ô
đã tick của #31 là thật; mục "lỗi quy trình" khớp reflog.
