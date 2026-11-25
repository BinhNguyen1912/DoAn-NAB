# 49: Đường web chưa nhận --settle-steps/--max-jump-ratio và status.json không ghi 2 giá trị đó

**What to build:** Review độc lập 24-11 (P2-1). `src/live_tracking.py:798` dựng `IdentityWatch()` **trần**, `tools/live_worker.py` không có 2 cờ; `status.json`/CSV drift của phiên web cũng không ghi `settle_steps`/`max_jump_ratio`. Hệ quả: `chua_xac_minh_n` của phiên web phụ thuộc `settle_steps=8` mà **không file nào ghi lại** ⇒ phiên web vẫn không tái lập được (đúng lỗi P1 gốc, chỉ đổi chỗ).

Không phải P0/P1 vì artifact đang chấm là `demoip_*` = đường CLI.

Cách sửa: truyền 2 giá trị qua `build_live_worker_command` **hoặc** ghi vào `status_payload` (`src/live_tracking.py:545-556`); nếu đưa ra API thì nhớ đủ 6 chỗ theo AGENTS §6 (telemetry/status/routes/DTO).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `status.json` của phiên web có `settle_steps` và `max_jump_ratio` đúng giá trị ĐÃ DÙNG
- [ ] `tools/live_worker.py` nhận `--settle-steps`/`--max-jump-ratio` và chuyển vào `IdentityWatch`
- [ ] Test: chạy live_worker với `--settle-steps 2` ⇒ `status.json.settle_steps == 2` và số frame ẩn giảm so với 8
- [ ] e2e Chrome kiểm phiên web vẫn chạy (không hồi quy)
