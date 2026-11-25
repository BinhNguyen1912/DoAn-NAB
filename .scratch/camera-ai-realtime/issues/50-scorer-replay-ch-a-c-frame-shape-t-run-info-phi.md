# 50: Scorer replay chưa đọc frame_shape từ run_info ⇒ phiên khung khác 640x480 bị chấm bằng trần 200 px

**What to build:** Review độc lập 24-11 (P2-2). `frame_shape` nay đã vào `run_info` (commit `9b00284`) nhưng **không consumer nào đọc**: `scripts/eval_gate_rules.py:57` vẫn `FRAME_SHAPE = (480, 640)` và `scripts/replay_latch_settle.py` mặc định `--frame-shape 480,640`. Ngưỡng cổng = `0,25 × đường chéo` ⇒ 1280×720 cần trần **367 px**, không phải 200 px ⇒ lý do gốc của P1 vẫn còn với mọi phiên không phải 640×480 (ví dụ phiên điện thoại `./run phone`).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `scripts/eval_gate_rules.py` đọc `*_run_info.json` cạnh CSV; có `frame_shape` ⇒ dùng khung đó, thiếu ⇒ 480x640 + ghi `frame_shape_nguon: "gia_dinh"` vào payload
- [ ] Payload có `frame_shape_dung` và `frame_shape_nguon` để người đọc biết số px dựa trên khung nào
- [ ] Test `tmp_path`: CSV + run_info `[720,1280]` ⇒ payload dùng 1280 (trần 367 px, không phải 200 px)
- [ ] Chạy lại trên corpus cũ: mọi phiên thiếu `frame_shape` vẫn cho số như trước (không hồi quy)
