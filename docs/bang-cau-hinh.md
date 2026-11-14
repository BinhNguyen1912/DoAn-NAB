# Bảng cấu hình — sinh tự động, đừng sửa tay

> Sinh bởi `python scripts/bang_cau_hinh.py`. Số trên **máy này**: cpu, checkpoint theo configs/default.yaml, clip binh1.mp4. Commit `b31009c6dffb05b82ef535aad66988bfe789e8c6` (cây BẨN: số không tái lập).
> Mỗi cấu hình chạy **3 lần**; `±` là độ lệch chuẩn giữa các lần ⇒ **chênh lệch nhỏ hơn `±` thì ghi 'không phân biệt được', cấm ghi 'tốt hơn'**.

| image_size | vos_every | FPS phát | Nhịp mask | vos_ms | tuổi mask p95 | lần | lỗi |
|---|---|---|---|---|---|---|---|
| 192 | 2 | 29.87 ± 0.06 | 8.83 ± 0.57 | 96.87 ± 16.48 | 261.17 ± 16.88 | 3 | 0 |
| 192 | 3 | 29.87 ± 0.06 | 8.47 ± 0.76 | 98.93 ± 16.58 | 300.4 ± 32.55 | 3 | 0 |
| 192 | 6 | 29.67 ± 0.23 | 5.17 ± 0.06 | 96.47 ± 1.59 | 313.37 ± 21.25 | 3 | 0 |
| 256 | 2 | 29.73 ± 0.21 | 4.7 ± 0.36 | 180.6 ± 9.69 | 477.77 ± 73.64 | 3 | 0 |
| 256 | 3 | 29.8 ± 0.1 | 5.17 ± 0.06 | 181.83 ± 26.97 | 423.8 ± 18.75 | 3 | 0 |
| 256 | 6 | 29.87 ± 0.06 | 4.93 ± 0.12 | 183.67 ± 8.48 | 403.23 ± 31.43 | 3 | 0 |
| 320 | 2 | 29.77 ± 0.06 | 3.57 ± 0.06 | 253.3 ± 3.52 | 557.6 ± 18.57 | 3 | 0 |
| 320 | 3 | 29.77 ± 0.06 | 3.57 ± 0.06 | 276.8 ± 21.4 | 603.23 ± 0.15 | 3 | 0 |
| 320 | 6 | 29.8 ± 0 | 3.53 ± 0.06 | 272.07 ± 31.46 | 674.43 ± 31.55 | 3 | 0 |

**CẤM trích**:

- `FPS phát` là nhịp **vẽ** frame (LK lấp giữa các lần VOS) — không phải nhịp model.
- `Nhịp mask` mới là số lần model chạy/giây; cấm viết "mask 30 FPS".
- `vos_ms` chỉ là phần model; nói "một frame tốn bao lâu" thì phải cộng `pre_ms` (~12 ms) — xem cột trong artifact.
- Tuổi mask p95 = `None` khi chưa đủ mẫu; **`None` không phải `0`**.
