# Ngày 08-11-2026 — Rule review độc lập + plan 3 ý kiến; review bắt 1 lỗi P1 và 4 lỗi P2 (đã fix)

## 🎯 Mục tiêu
- Đưa hai quy trình thành **luật** trong `AGENTS.md`: (1) làm xong vấn đề nào thì chạy **1 con review
  độc lập** để kiểm chứng và fix; (2) việc lớn thì **3 con độc lập đưa ý kiến, tranh luận**, rồi chốt.
- Áp dụng ngay: review độc lập PR #5, fix hết phát hiện P1/P2, và chạy 3 cố vấn để chọn việc tiếp theo.

## 📥 Input
- PR #5 vừa merge (`fb842fb`): Phase 4d — minh bạch nhịp mask + fix bbox.
- Yêu cầu người dùng: thêm rule review độc lập + plan 3 ý kiến; "mở lại 2 thằng kia, chọn default
  deepseek 1017".

## 🔨 Công việc đã thực hiện
1. **Sửa tooling trước khi dùng** (nếu không, cả quy trình không chạy được):
   - 5 agent bundled khai báo `skills:` không tồn tại trên máy (`pi-laws`, `interface-and-module-design`,
     `code-review-and-quality`, `development-lifecycle`, `test-driven-development`) ⇒ mọi task lỗi
     `Declared subagent skill(s) not found`. Đã map sang skill đang có (`code-review`,
     `codebase-design`, `tdd`, `verification-before-completion`, `memory`).
   - Đặt `model: ollama-cloud/deepseek-v4.1-flash:1017` cho 5 agent (bỏ khối `models:` của `advisor`
     vì nó đẩy sang backend HerdR và chết).
   - Ghi cách xử lý vào `AGENTS.md` §9.3 để lần sau không mất thời gian.
2. **`AGENTS.md`**: thêm **mục 9** (9.1 review độc lập trước khi merge, 9.2 plan 3 ý kiến + phản biện
   chéo + lưu `docs/plan/`, 9.3 xử lý khi tool lỗi, 9.4 checklist kết thúc phiên) và sửa mục 5
   (quy trình phiên) để hai bước này là điều kiện hoàn thành. Thêm `docs/plan/_template.md`.
3. **Review độc lập PR #5** (agent `reviewer`, model deepseek): 1 lỗi **P1**, 5 lỗi **P2**, 5 **P3**;
   đồng thời **bác bỏ đúng** 6 nghi ngờ của mình (race, mask None, `INTER_NEAREST`, `isinstance`
   Protocol, thứ tự ưu tiên mặc định…) — tức không bịa lỗi.
4. **Fix toàn bộ P1 + P2** (chi tiết ở mục Output) + test hồi quy cho từng lỗi.
5. **3 cố vấn lập plan song song** (chất lượng&số đo / sản phẩm&bằng chứng / độ bền&hiệu năng) + 1 vòng
   phản biện chéo; chốt thành `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md`.
6. Vòng 2 phát hiện thêm **1 lỗi thật**: `_stats` bị serialize **không lock** trong khi luồng VOS ghi
   ⇒ snapshot **lẫn thế hệ** (`vos_runs` của lần N đi với `vos_ms`/`stability` của lần N−1). Đã sửa
   bằng `_stats_lock` + `dataclasses.replace` khi ghi status.

## 📤 Output / Kết quả
- **Lỗi P1 (thật, đã fix + đo lại trên dữ liệu thật):** `_smooth()` dịch bộ tích luỹ mask theo **bbox
  của engine**, nhưng khi model mất vật engine trả `bbox = (0,0,0,0)` (`src/tracker_engine.py`) ⇒
  bộ tích luỹ bị "teleport" về góc khung: `shown_area = 0` nên nhánh **hold không bao giờ chạy**
  (mask tắt ngay lần "chớp" đầu — đúng ca bộ lọc sinh ra để chặn), và nếu mask cũ gần gốc khung thì
  hold trả **mask ở sai vị trí**.
  Đo trên `data/binh1_simloss.mp4` (`vos_every=3`, `--mask-smoothing 0.5`, 600 frame):

  | | `empty_runs` | `mask_holds` | `mask_drops` |
  |---|---|---|---|
  | Trước fix | (không có trường) | **0** | **0** |
  | Sau fix | 14 | **4** | 2 |

  ⇒ Bộ lọc từ "không bao giờ kích hoạt" thành "kích hoạt đúng chỗ"; `empty_runs=14` chứng minh model
  thật sự có lúc mất vật (nên trước đây mask tắt ngay 14 lần mà không ai biết).
- **Các lỗi P2 đã fix:**
  1. `stability` = **1,0 khi cả hai mask đều rỗng** (`mask_iou(rỗng, rỗng) = 1,0`) ⇒ mất dấu hoàn toàn
     lại báo "độ ổn định 100 %". Nay mask rỗng **không vào mẫu** IoU, đếm riêng `empty_runs`, và UI
     hiện "mất dấu: N lần".
  2. **Hợp đồng `mask_smoothing` lệch**: schema cho `0.0`, `MaskSmoother` ném `ValueError`, CLI lại
     **clamp im lặng** thành 0,05. Nay validate ở **một chỗ** (`LiveTrackConfig.__post_init__`),
     schema `gt=0.0` (0 ⇒ 422), CLI `parser.error` với thông báo rõ.
  3. **Hai nghĩa cho một cái tên `measured_fps`**: API đọc `frame.jpg` ở `target_fps=15` ⇒ FPS trần
     15, trong khi status.json của worker ghi 29,9 ⇒ UI hiện 15 cạnh "mask 8,6". Nay `LIVE_READ_FPS=30`
     khớp `--max-fps`, và `display_fps` (số do **chính worker** đo) được phơi qua
     `LiveTelemetry`/`LiveStatus`/response; UI ưu tiên số của worker (`shownFps()` có test).
  4. **Lỗi trong luồng VOS bị nuốt im lặng** (engine ném lỗi ⇒ thread chết, vòng chính phát mask đứng
     yên mãi với `state=tracking`). Nay `_VosWorker` bọc `try/except` → `_on_worker_error` đặt
     `state=error` + message, vòng chính dừng và **không ghi đè** thành `stopped`; test bắt được.
  5. **`_stats` lẫn thế hệ** (vòng 2 phát hiện) — đã mô tả ở trên.
- **P3 đã fix kèm:** `status.json` có **một nguồn schema** (`status_payload()` dùng chung cho trạng
  thái "loading" và phiên chạy — trước đây hai tác giả, hai tập khoá); `_start_worker` đặt mốc
  `_vos_state` **trước** `submit()`; bỏ `.copy()` thừa mỗi lần hold; `_interp_base_result` khởi tạo
  an toàn trong `__init__`; sửa 2 trích dẫn log **không tồn tại** (`docs/task/10-11-2026-*` →
  `08-11-2026-*`); `status()` không còn nuốt im lặng lỗi số liệu (ghi `logger.warning`).
- **Test mới:** `TestLoiReviewDocLap` (9 test: P1 giữ mask đúng vị trí, tắt sau `max_hold`, hybrid
  thật sự làm mượt, `stability` không = 1,0 khi mất dấu, lỗi luồng VOS → `state=error`, validate
  `mask_smoothing`/`vos_every`, `status.json` một nguồn schema, LK mất dấu không bịa vị trí),
  `TestCoLenhWorker` (2 test truyền cờ), 3 test API (`mask_smoothing` ngoài khoảng → 422, truyền
  xuống nhà máy nguồn, telemetry), 4 test frontend (`shownFps`, "mất dấu: N lần").
- File thay đổi:
  - `AGENTS.md` — mục 9 (rule mới) + mục 5 + cây thư mục `docs/plan/`
  - `docs/plan/_template.md`, `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md`
  - `src/live_tracking.py` — P1/P2/P3 (shift hợp lệ, `empty_runs`, `_stats_lock`, `status_payload`,
    `_on_worker_error`, `__post_init__`)
  - `src/mask_filter.py` — bỏ copy thừa, sửa trích dẫn log
  - `src/api/{domain,ports,schemas,routes,live,main}.py`, `src/api/adapters/worker_source.py` —
    `display_fps`, `empty_runs`, `LIVE_READ_FPS=30`, `logger.warning` khi số liệu hỏng
  - `tools/live_worker.py` — validate tham số, dùng `status_payload()`
  - `web/src/{api.ts,live.ts,live.test.ts,components/LivePanel.tsx}` — `shownFps`, "mất dấu: N lần"
  - `tests/test_live_tracking.py`, `tests/test_api_live.py`

## 🐞 Vấn đề gặp phải & cách xử lý
- **Agent tool hỏng trước khi làm được việc**: (a) skill khai báo không tồn tại, (b) `advisor` bị đẩy
  sang HerdR và chết pane, (c) 2 task chết vì `429 GoUsageLimitError`. Xử lý: map skill → skill thật,
  đặt `model: …deepseek-v4.1-flash:1017` cho mọi agent, mở lại 2 task đã chết. Ghi vào AGENTS §9.3.
- **Review bị chạy trên working tree đang thay đổi**: vòng 2 đọc code giữa lúc mình đang sửa nên báo
  "working tree bẩn" và bắt được một nửa diff (`empty_runs` mới có trong status.json, chưa lên
  `LiveTelemetry`). Đó cũng là **lỗi thật** (số mới "chết trong adapter") — đã sửa. Bài học: review
  sau khi commit, hoặc chấp nhận review trên diff dở và đọc kỹ cảnh báo.
- **Test của mình che mất lỗi P1**: `_BlinkingEngine` cũ trả mask rỗng nhưng **giữ bbox thật**, trong
  khi engine thật trả `bbox=(0,0,0,0)` ⇒ test xanh mà lỗi vẫn còn. Nay `_LostObjectEngine` mô phỏng
  đúng hợp đồng của `tracker_engine`.
- **Try/except nuốt lỗi lại tái diễn**: `status()` bọc `telemetry()` trong `except Exception` im lặng;
  khi thêm `empty_runs` vào `LiveTelemetry` mà quên field, số liệu về 0 **mà test vẫn xanh** (vì test
  của mình monkeypatch nguồn). Đã thêm `logger.warning` + sửa field.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Thực hiện 6 việc đã chốt trong `docs/plan/08-11-2026-review-doc-lap-va-plan-tiep-theo.md`
      (bắt đầu: `scripts/measure_live.py` ghi artifact có `git_rev`).
- [ ] **Người dùng** quay 2 clip: vật bị che một phần; vật ra khỏi khung rồi vào lại.
- [ ] Transcode H.264 cho `--record` (recorder đang `mp4v` — Chrome không phát được video demo).
- [ ] Gắn nhãn P3 còn lại: đổi `8.6` → `8,6` (vi-VN) trên UI nếu muốn khớp tài liệu.

## 📚 Tài liệu tham khảo
- `AGENTS.md` §9 (rule review độc lập + plan 3 ý kiến).
- Kết quả 3 cố vấn + phản biện chéo: `.pi/artifacts/tasks/mw7h6bwx-7be4.md` (review),
  `mw7h725b-d439.md` (A), `mw7h79ce-1b07.md` (B), `mw7hhfoi-2702.md` (phản biện).
- `docs/task/08-11-2026-minh-bach-nhip-mask-va-fix-bbox-live.md` (Phase 4d).
