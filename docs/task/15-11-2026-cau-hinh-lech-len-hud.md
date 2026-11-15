# 15-11-2026 — Đưa cờ "cấu hình yêu cầu ≠ hiệu lực" lên API live + HUD (ticket #28)

## 1. Mục tiêu

`status.json` từ 15-11 đã có `cau_hinh` + `cau_hinh_lech` (worker tự kiểm "yêu cầu == hiệu lực"),
nhưng **không đi qua API**: người ngồi xem UI không biết phiên đang chạy sai cấu hình; cảnh báo chỉ
nằm trong `worker.log`. Việc này đưa **cờ lệch** lên `/api/live/status` và hiện cảnh báo trên HUD.

Vì sao quan trọng: nếu buổi demo chạy `--image-size 192` mà override không được áp, model chạy 1024
và **mọi số của phiên** (FPS, độ trễ, tuổi mask) gắn với một cấu hình khác cấu hình người dùng chọn —
đúng loại "xanh giả" mà repo đang cố chặn. Đây là hiển thị cho **người vận hành**, **không đổi kết
luận số đo** nào.

## 2. Input

- Ticket `.scratch/camera-ai-realtime/issues/28-*.md`.
- Producer: `tools/live_worker.py` + `src/live_tracking.py::so_khop_cau_hinh()` (trả danh sách khoá
  lệch; `[]` = không khoá nào lệch, **kể cả khi không đọc được `image_size_hieu_luc`**).
- Quy ước AGENTS §6: `None` = chưa biết/chưa đo, cấm đổi thành `0`/`"khớp"`.

## 3. Công việc đã thực hiện

**Backend (ports & adapters, không đổi kiến trúc):**

| File | Thay đổi |
|---|---|
| `src/api/adapters/worker_source.py` | `telemetry()` đọc thêm `cau_hinh_lech` + `cau_hinh.image_size_hieu_luc` qua helper mới `_lech_cau_hinh`, `_gia_tri_cau_hinh`, `_so_nguyen_hoac_none` |
| `src/api/domain.py` | `LiveStatus`/`LiveTelemetry` thêm `cau_hinh_lech: tuple[str, ...] \| None`, `image_size_hieu_luc: int \| None` |
| `src/api/live.py` | chuyển tiếp từ telemetry sang `LiveStatus` |
| `src/api/schemas.py` | DTO `LiveStatusResponse` thêm 2 trường + mô tả 3 trạng thái |
| `src/api/routes.py` | `tuple → list`, giữ `None` nguyên là `null` |

Ba trạng thái **không gộp** (bẫy `None` vs `0` của AGENTS §6):

| giá trị | nghĩa | HUD |
|---|---|---|
| `null` | CHƯA BIẾT (worker bản cũ, hoặc khoá có mặt nhưng `null`) | không in gì |
| `[]` + `image_size_hieu_luc` có số | đã kiểm, không khoá nào lệch | không in gì |
| `[]` + `image_size_hieu_luc == null` | **CHƯA KIỂM ĐƯỢC** (predictor không khai `image_size`) | hint |
| có phần tử | **LỆCH thật** | cảnh báo đỏ `role="alert"` |

**Frontend:** `web/src/api.ts` (kiểu), `web/src/live.ts` (`configMismatchLine`, `configMismatchIsAlert`),
`web/src/components/LivePanel.tsx` (dòng `data-testid="config-mismatch"`, `class=error` + `role="alert"`
chỉ khi lệch; hint khi chưa kiểm được), `README.md` (mục `/api/live/status`).

**Test:** 5 test backend mới (`tests/test_api_live.py`: adapter lệch/khớp/vắng khoá/khoá `null`/số vô
lý + 3 test HTTP), 7 vitest (`web/src/live.test.ts`), 3 check e2e mới (`scripts/e2e_web.js`).

## 4. Output / Kết quả

Lệnh + kết quả (chạy trên máy này, WSL, 15-11):

```
./run lint      → All checks passed
./run test      → 1217 passed, 5 deselected (78,32 s)   [trước: 1212]
./run webtest   → 54 passed                             [trước: 52]
npm run build   → built in 768 ms
./run e2e       → KẾT LUẬN: PASS  (3 check mới đều ✓)
```

HUD khi lệch (chữ thật lấy từ log e2e):

```
CẤU HÌNH LỆCH (image_size) (model đang chạy 1024 px): số của phiên này gắn với cấu hình KHÁC
cấu hình đã chọn — dừng và bật lại với đúng tham số trước khi trích số      [role=alert]
```

Ca âm đã kiểm: `cau_hinh_lech: []` + `image_size_hieu_luc: 192` ⇒ **0 dòng** `config-mismatch` (một
hồi quy kiểu `lech.length >= 0` sẽ render khung rỗng và trước đây không ai bắt).

## 5. Vấn đề & cách xử lý

**Review độc lập (mục 9.1, agent `reviewer`, nhánh `feat/cau-hinh-lech-hud`):** 0 P0, 0 P1,
4 P2 + 11 P3. Đã sửa **3 P2 + 8 P3** trong cùng nhánh:

- **P2-1 (ngữ nghĩa):** cả 4 chỗ (schemas/domain/api.ts/live.ts) viết "`[]` = đã kiểm và khớp" —
  **sai**: `so_khop_cau_hinh()` trả `[]` cả khi `image_size_hieu_luc is None`, và giai đoạn `loading`
  cũng ghi `[]` + `image_size_kiem_duoc: false`. Đã sửa mô tả + thêm nhánh **hint "CHƯA kiểm được"**
  (chỉ khi `state == running`, để không báo oan trong 20–240 s nạp model).
- **P2-2 (test mắt xích cuối):** xoá 2 dòng `live.py`/`routes.py` thì **toàn bộ** 1217 test + 54
  vitest + e2e vẫn xanh (e2e stub `/api/live/status` phía trình duyệt) ⇒ thêm 3 test HTTP theo đúng
  mẫu `_TelemetrySource` + `monkeypatch._make_source` đã dùng cho `mask_age_*`.
- **P2-3:** `status.get("cau_hinh_lech") or []` biến khoá có mặt nhưng `null` thành `()` = "đã khớp";
  nay `null ⇒ None` + test.
- P3 đã sửa: `Array.isArray` guard dùng chung (một giá trị không phải mảng sẽ ném trong lúc render),
  `OverflowError` cho `Infinity` trong `status.json`, "số ở trên" → "số của phiên này" (dòng cảnh báo
  render **trước** các dòng số), nhãn e2e không hứa "yêu cầu 192" khi UI không in, ca âm e2e,
  README, bỏ `?` trong `api.ts` (backend luôn gửi khoá), gộp `status.get("cau_hinh")` về một helper.
- P3 **không sửa, ghi lại**: (a) chưa đưa `image_size_yeu_cau` lên DTO nên câu cảnh báo chỉ nói được
  vế "đang chạy 1024", không nói "yêu cầu 192" — làm được nhưng phải thêm 1 trường nữa; (b) chưa
  kiểm trên screen reader thật khi **2** `role="alert"` cùng xuất hiện (cấu hình lệch + mask cũ).

**Bài học giữ lại:** `[]` là giá trị **hai nghĩa** y như `0` — với `cau_hinh_lech` nó vừa là "đã kiểm
và khớp" vừa là "không đọc được để kiểm"; phân biệt chỉ có được nhờ trường đi kèm
(`image_size_hieu_luc`). Đừng thêm một khoá kiểu này mà không có trường chứng minh "đã kiểm".

## 6. Next steps

- (tuỳ chọn) Thêm `image_size_yeu_cau` vào DTO để câu cảnh báo nói được cả hai vế "yêu cầu 192, chạy
  1024" — rẻ, nhưng cần bàn có nên mở rộng HUD hay không.
- Ticket #29 (ẩn `userinfo` khỏi chuỗi nguồn trước khi trả HTTP) vẫn `ready-for-agent`.
- Chờ người dùng tô 12 frame silhouette (`docs/gt/binh1_silhouette/`) để chấm **mIoU mask vs GT** trên
  video thật — số 0,6464 hiện có là của **hộp bao**, không phải phân đoạn.

## 7. Tài liệu tham khảo

- `.scratch/camera-ai-realtime/issues/28-*.md` (ticket)
- `docs/task/15-11-2026-status-json-echo-cau-hinh-hieu-luc.md` (producer của `cau_hinh_lech`)
- `AGENTS.md` §6 (bẫy `None` vs `0`; "số 0,0 trong artifact là cạm bẫy"), §9.1 (review độc lập)
