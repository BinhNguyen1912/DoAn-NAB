# 24-11-2026 — Cờ cổng nghi là cờ THẬT, `frame_shape` vào provenance, Caps Lock, và nhãn ĐẢO 2 lần

## Mục tiêu
Người dùng báo *"vật trắng trơn (remote) di chuyển nhanh quá thì bị nghi đổi đối tượng"*. Phiên này:
(1) xác định **có báo oan thật hay không** bằng số đo, (2) chốt có sửa thuật toán cổng hay không, (3) sửa
các lỗi provenance/UX mà 3 vòng review độc lập bắt được.

## Input
- 39 file `data/demoip_*_metrics.csv` + `_run_info.json` + `_web.mp4` (phiên thật trên laptop CPU).
- Mã liên quan: `src/identity_guard.py`, `src/live_pipeline.py`, `src/smooth_display.py`,
  `src/metrics_logger.py`, `tools/run_live.py`.
- Kịch bản: AGENTS §9.2 (plan 3 ý kiến, 2 vòng) + §9.1 (review độc lập trước merge).

## Công việc đã thực hiện
1. **Dựng bộ chấm luật** `scripts/eval_gate_rules.py` (không nạp model): phát lại chuỗi ô từ CSV qua
   **chính** `IdentityWatch` (thêm tham số `nhay=` để không phải chép lại state machine) và chấm 8 luật:
   hiện tại · `theo_dt` · `van_toc_lich_su` · `theo_dt_va_dien_tich` · `chi_khi_cham_{600,900,1200,1500}`.
2. **Đóng băng danh sách phiên so sánh** (`data/eval_gate_config_list.json`): chỉ phiên có replay khớp
   100 % cột `nghi_doi_tuong` — nếu để code đang chấm tự chọn thì đổi luật là mẫu số tự rẻ đi.
3. **Nhãn bằng ảnh**: cắt frame theo `Σ latency_ms` rồi **vẽ ô bbox từ CSV lên frame** (tên file theo
   `frame_idx`, `data/tmp_an/v2_*`, `v3_*`). Đọc thêm video HUD của 3 phiên có sự kiện.
4. **Plan 3 ý kiến 2 vòng** → `docs/plan/24-11-2026-cong-nghi-bao-oan.md`.
5. **Sửa lỗi** (commit `2338c43` + phần sau review): `--settle-steps`/`--max-jump-ratio` là cờ thật,
   `frame_shape` + `frame_shape_doi` vào `run_info`, `chuan_hoa_phim` cho Caps Lock, headless ghi
   `settle_steps/max_jump_ratio = None` (không bịa cổng chưa chạy).

## Output / Kết quả
**Nhãn (đọc video HUD, 3 phiên có sự kiện)** — **6/6 lần báo là ĐÚNG**, `0` ca báo oan xác nhận:
- `144057`: `prompt_bbox=[397,79,491,462]` = **thìa GỖ**; người dùng rút thìa gỗ, đưa **thìa NHỰA trắng**
  vào ⇒ SAM 2 bám thìa nhựa ⇒ **danh tính đã đổi** ⇒ cổng báo đúng.
- `141352`: cùng kịch bản. `144226`: báo khi **tay người khác** vào khung.

**8 luật, nhóm đóng băng 10 phiên / 1 509 frame** (`data/eval_gate_rules_2026-11-24_metrics.json`,
`git_rev 243e146`, `git_dirty_code=false`):

| luật | báo | không tin cậy | đuôi | bắt ca ĐÚNG |
|---|---|---|---|---|
| **hiện tại** | 6 | 15,04 % | 9,68 % | **7/7** |
| `theo_dt` | 4 | 14,84 % | 10,54 % | 3/7 |
| `van_toc_lich_su` | 9 | 26,57 % | 18,56 % | 6/7 |
| `theo_dt_va_dien_tich` | 3 | 14,84 % | 11,20 % | 2/7 |
| `chi_khi_cham_600/900/1200/1500` | 1/2/3/4 | 0,20–13,32 % | ≤ 11,20 % | 1/7 · 3/7 · 4/7 · 5/7 |

⇒ **Mọi luật "giảm báo" đều giảm RECALL.** Số quyết định: biên `|Δtâm|/bán kính` chỉ **0,937** (không
báo cao nhất) → **1,019** (báo thấp nhất) = **8 % ngưỡng**; cổng **mù** với dịch chuyển 127–172 px.
**Quyết định: KHÔNG sửa thuật toán cổng trước bảo vệ.**

**Chi phí (cùng nhóm):** ẩn 3,71 % · chưa xác minh 11,33 % · **đuôi 9,68 %** (frame sau lần báo cuối —
`chua_xac_minh` không tự xoá). Baseline take sạch: `110536` = 200 frame, `nghi = 0`.

**Test:** thêm 11 case; `./run lint` xanh, `./run test` **1 997 passed, 5 deselected**. Kiểm bằng đột
biến: m1 `_settle_steps` trả hằng 8 · m2 bỏ truyền `settle_steps` xuống runner · m4 bỏ `chuan_hoa_phim`
ở call-site · m5 bỏ `note_frame_shape` headless · m6 `frame_shape=None` — **cả 5 đều làm test ĐỎ**.

## Vấn đề & cách xử lý
| vấn đề | cách xử lý |
|---|---|
| Tôi kết luận sai 2 lần vì đọc **ô vàng trên HUD** (HUD vẽ kết quả của bước KHÁC) | Vẽ **ô bbox từ CSV** lên frame đúng thời điểm (`Σ latency_ms`) ⇒ nhãn cuối |
| "11 phiên khớp 100 %" là **rỗng nghĩa** ở phiên không có cột `nghi_doi_tuong` | Cột thiếu ⇒ `khop = None` (CHƯA ĐO), không phải 100 %; danh sách còn 10 phiên |
| Script trộn **3 mẫu số** (24 phiên vs tập con) | Mọi số cùng một nhóm; in rõ `so_phien/so_frame` |
| Review vòng 3: `--settle-steps 0` bị `or default` nuốt thành 8 | `None` vs `0` phân biệt; kẹp âm về 0 tại chỗ ghi `run_info` |
| Review vòng 3: headless ghi `frame_shape: null` + bịa `settle_steps=8` | Headless gọi `note_frame_shape`; `settle_steps/max_jump_ratio = None` |
| Review vòng 3: 8 test mới **không khoá dây nối** | Thêm 3 test qua runner/`_run_display`/`run_info`; kiểm bằng 6 đột biến |

## Next steps
1. **Đóng băng replay thành test** (`tests/test_eval_gate_frozen.py`) — 10 phiên ⇒ `(6, 56, 171, 146)`
   + assert **"KHÔNG báo"** cho 4 ca mù (169,1 · 172,0 · 127,1 · 149,2 px).
2. **Người thứ 2 dán nhãn 6 ca** (điều kiện để trích "7/7" trong báo cáo — hiện 1 người).
3. **Diễn tập 3 lần + video dự phòng**: `nghi ≤ 5 %`, đuôi ≤ 20 frame, `ti_le_thoi_luong ≥ 0,95`.
4. Ticket: đường web chưa nhận 2 cờ (P2-1); scorer chưa đọc `frame_shape` từ `run_info` (P2-2).
5. Sửa gốc (việc lớn): **mask tràn nền khi vật đi nhanh** ⇒ ô trôi ⇒ cổng báo.

## Tài liệu tham khảo
- `docs/plan/24-11-2026-cong-nghi-bao-oan.md` (3 ý kiến + 2 vòng phản biện + 4 điểm tranh chấp)
- `data/eval_gate_rules_2026-11-24_metrics.json`, `data/eval_gate_config_list.json`
- Ảnh nhãn: `data/tmp_an/v2_*`, `v3_*`, `l9.6.jpg`, `l12.6.jpg`
- AGENTS §6 (bullet cổng nghi 24-11), memory `@event.cong-nghi-bao-dung-7-7-loi-la-recall`
