# Bảng cấu hình — sinh tự động, đừng sửa tay

> Sinh bởi `python scripts/bang_cau_hinh.py`. Số trên **máy này**: cpu, checkpoint theo configs/default.yaml, clip binh1.mp4. Commit `e3fa78e156f355410d97d57321a6ec587ca646ae`.
> Mỗi cấu hình chạy **3 lần**; `±` là độ lệch chuẩn giữa các lần ⇒ **chênh lệch nhỏ hơn `±` thì ghi 'không phân biệt được', cấm ghi 'tốt hơn'**.

| image_size | vos_every | FPS phát | Nhịp mask | vos_ms | tuổi mask p95 | lần | lỗi |
|---|---|---|---|---|---|---|---|
| 192 | 2 | 29.73 ± 0.12 | 8.73 ± 0.12 | 94.9 ± 3.11 | 277.87 ± 17.52 | 3 | 0 |
| 192 | 3 | 29.87 ± 0.06 | 8.7 ± 0.1 | 87.9 ± 2.05 | 301.27 ± 0.32 | 3 | 0 |
| 192 | 6 | 29.77 ± 0.06 | 5.2 ± 0 | 95.2 ± 1.67 | 301.27 ± 0.61 | 3 | 0 |
| 256 | 2 | 29.87 ± 0.06 | 5.03 ± 0.06 | 186.57 ± 13.11 | 424.17 ± 19.29 | 3 | 0 |
| 256 | 3 | 29.8 ± 0 | 4.97 ± 0.06 | 186.47 ± 3.81 | 469.03 ± 0.76 | 3 | 0 |
| 256 | 6 | 29.8 ± 0 | 4.9 ± 0 | 188.83 ± 1.68 | 390.97 ± 18.94 | 3 | 0 |
| 320 | 2 | 29.83 ± 0.06 | 3.57 ± 0.06 | 253.63 ± 11.68 | 559.9 ± 16.37 | 3 | 0 |
| 320 | 3 | 29.77 ± 0.06 | 3.57 ± 0.06 | 275.77 ± 23.54 | 583.23 ± 16.69 | 3 | 0 |
| 320 | 6 | 29.77 ± 0.06 | 3.6 ± 0.1 | 314.93 ± 59.95 | 682.03 ± 21.54 | 3 | 0 |

**CẤM trích**:

- `FPS phát` là nhịp **vẽ** frame (LK lấp giữa các lần VOS) — không phải nhịp model.
- `Nhịp mask` mới là số lần model chạy/giây; cấm viết "mask 30 FPS".
- `vos_ms` chỉ là phần model; nói "một frame tốn bao lâu" thì phải cộng `pre_ms` (~12 ms) — xem cột trong artifact.
- Tuổi mask p95 = `None` khi chưa đủ mẫu; **`None` không phải `0`**.
