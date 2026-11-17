# 17-11-2026 — P3 còn lại của review độc lập #26 + #32 (dump_ms cùng lock, hai encoding "rỗng", nợ FE)

## Mục tiêu

Báo cáo review độc lập cho **hai nhánh** `fix/dump-mask-ngoai-post-ms` (ticket #26) và
`fix/p95-latency-null-khi-chua-do` (ticket #32) về **sau** khi PR #28/#29 đã merge. Việc cần làm: đối
chiếu 19 phát hiện với cây `main`, sửa phần còn mở, tách phần phải làm riêng thành ticket.

## Input

- Báo cáo review: #26 — 2 P1 + 2 P2 + 5 P3; #32 — 1 P1 + 4 P2 + 5 P3 (agent `reviewer`, chạy trước merge).
- Trạng thái `main` @ `d9655f9`, cây sạch, `./run test` **1334 passed**.

## Công việc đã thực hiện

### 1. Đối chiếu 19 phát hiện với cây sau merge

**Đã sửa trong chính PR đó (11) — đối chiếu bằng code, không làm lại:**

| # | Phát hiện | Bằng chứng trên `main` |
|---|---|---|
| #26 P1 | `dump_ms` khác `None` khi **không có file** nào | `_dump_mask` trả `bool`; `_record_vos` đặt `None` khi `not da_ghi` (`live_tracking.py:976`) |
| #26 P1 | guard `_dumped` **bỏ cảnh báo** đúng ca "chọn lại ô giữa phiên" | `se_ghi_de = dich.exists()` — không còn điều kiện `not in self._dumped`; cảnh báo in "GHI ĐÈ" |
| #26 P2 | lời tuyên bố "`cycle_ms` đã sạch" + block comment dán nhầm | comment nay nói "`cycle_ms`/`queue_ms` **vẫn** chứa dump của lần VOS TRƯỚC" |
| #26 P2 | `so_file_ghi_de` không có ai **đọc** | `scripts/score_miou.py:235-240` cảnh báo mềm ở chỗ CHẤM |
| #26 P3 | bộ đếm tăng **trước** `imwrite` | `self._so_file_ghi_de += 1` nằm **sau** `if not cv2.imwrite(...)` |
| #26 P3 | manifest thiếu `frames_da_ghi` | có (`_write_mask_manifest`) |
| #26 P3 | `dump_ms` chỉ trong `cho_phep`, không `bat_buoc` | `dump_ms` nằm trong `bat_buoc` (`tests/test_live_tracking.py:142`) |
| #26 P3 | `_worker_telemetry`/`cau_hinh` không khai dump | `cau_hinh.dump_mask_frames` (`live_tracking.py:293-297`) |
| #32 P1 | `run:505` **crash** `TypeError` khi `p95_latency_ms: null` | `run:504-509` đọc `p95` + `_n`, in "chưa đo" |
| #32 P2 | `plot_compare` vẽ cột `0` cho "chưa đo" | lọc `if s.get("n_do_ms")` trước khi vẽ |
| #32 P2 | `mean_latency_ms` không có `_n` + không comment | `mean_latency_ms_n` + comment lý do giữ `0,0` |
| #32 P2 | không test cho `SessionSummary.p95_ms`/`_p95_txt` | `tests/test_live_pipeline_summary.py` (5 test) |
| #32 P3 | `n=None` cho artifact cũ | `run_live.py:366` in `n=?` |

**Còn mở → sửa hôm nay (2) + tách ticket (1):** xem mục 2–4.

### 2. `dump_ms` bị ghi tách khỏi `post_ms` (#26 P3 thứ 9)

`_record_vos` tự gán `_stats.dump_ms`, còn `post_ms` được gán ở **người gọi** (sau khi trừ `dump_ms`) ⇒
một lần VOS chen giữa hai lần ghi sẽ khiến `status.json` ghép `post_ms` của lần N với `dump_ms` của lần
N+1. Đây đúng loại "hai pha của hai lần chạy" mà snapshot `_vos_state` sinh ra để chặn — nhưng `dump_ms`
không nằm trong snapshot.

- `_record_vos` nay trả `(dump_ms, da_ghi)`, **không** gán `_stats.dump_ms`.
- Cả hai call site (`_store_vos`, `_after_vos`) gán `self._stats.dump_ms = dump_ms if da_ghi else None`
  trong **cùng khối `_stats_lock`** với `post_ms`.
- Test mới: `tests/test_mask_dump_frame_idx.py::test_record_vos_khong_tu_gan_dump_ms` — gọi
  `_record_vos` trực tiếp ⇒ `_stats.dump_ms is None`; sau `_after_vos` ⇒ khác `None`. Test này **đỏ**
  nếu ai đưa dòng gán về lại trong `_record_vos`.

### 3. Hai encoding của "rỗng" (#32 P2)

`metrics_logger` giữ `lost_ratio`/`mean_score = 0,0` (hợp đồng `summary.json` của phiên; consumer cũ
`SummaryTable`/notebook đọc thẳng số), `plot_metrics.summarize` trả `None` cho `lost_ratio` rỗng (nó
**vẽ** hình — cột 0 là nói "không mất dấu lần nào"). Chênh lệch là **chủ ý** nhưng trước đây không được
viết ra. Nay có comment tại chỗ: consumer nào đọc cái nào, và "chưa đo" phân biệt bằng `total_frames == 0`
+ `_n`.

### 4. Nợ FE tách thành ticket #33

`web/src/api.ts:23` vẫn khai `p95_latency_ms?: number` (backend có thể trả `null`) và `SummaryTable`
không in `n`. Ticket #32 chỉ ghi "tách ticket riêng" mà **không có ticket nào** ⇒ nay tạo **#33**
(`ready-for-agent`, 3 tiêu chí: kiểu `number | null` + `_n`, `SummaryTable` in `— (0 mẫu)` /
`119 ms (n=600)` có vitest, và `./run webtest` + `npm run build` + `./run e2e`). Ticket #32 trỏ sang #33.

## Output / Kết quả

- `./run lint` xanh · `./run test` **1335 passed**, 5 deselected (trước: 1334 — +1 test).
- Không đổi hành vi đo: `dump_ms` vẫn `None` khi không có file, vẫn được **trừ** khỏi `post_ms`.
- PR #32 (`fix/32-con-lai-p3`), ticket mới **#33**, ticket #32 cập nhật liên kết.

## Vấn đề & cách xử lý

- **Báo cáo review về muộn** (sau merge): 11/19 phát hiện đã được sửa trong chính PR — cách xử lý là
  **đối chiếu bằng code** từng dòng (bảng mục 1) rồi chỉ sửa phần còn mở, không làm lại.
- Reviewer cảnh báo "không nên kết luận định lượng" cho P2 `cycle_ms` (cần một phiên dump gần như mọi
  frame): **không** đưa số nào vào tài liệu, chỉ sửa **lời** (comment) cho đúng — đúng nguyên tắc
  "đo trước, hứa sau".
- Ngưỡng `n >= 30` cho `p95` độ trễ: giữ quyết định **không áp** (đã ghi lý do trong ticket #32) nhưng
  reviewer yêu cầu "hoặc áp ngưỡng, hoặc viết ngoại lệ ra + bắt buộc in `n`" ⇒ vế "in `n`" đã có ở CLI /
  `run summary`; vế còn lại (web) nằm trong ticket #33.

## Next steps

- Merge PR #32 sau khi CI xanh (đã review nội bộ các sửa đổi ở trên).
- Ticket **#33** (FE) — cần `./run webtest` + `./run e2e`, chưa ai nhận.
- Ticket **#14** (cờ phán quyết drift) và **#11** (ngưỡng NCC cho chai đen) vẫn chờ **clip thật** từ người
  dùng; ticket mIoU phân đoạn thật chờ **silhouette ≥ 30 frame** của `binh1`.

## Tài liệu tham khảo

- Báo cáo review: `.scratch/rev26-32.md` (vòng 1, trước merge).
- Log gốc: `docs/task/17-11-2026-ticket-26-dump-mask-ngoai-post-ms.md`,
  `docs/task/17-11-2026-ticket-32-p95-latency-none.md`.
- Ticket: `.scratch/camera-ai-realtime/issues/{26,32,33}-*.md`.
- AGENTS §6 (bẫy `0/None`, `cycle_ms` chứa dump lần trước), §9.1 (review độc lập), §7b (1 nhánh/nhiệm vụ).
