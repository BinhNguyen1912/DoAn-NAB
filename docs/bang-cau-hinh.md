# Bảng cấu hình — sinh tự động, đừng sửa tay

> Sinh bởi `python scripts/bang_cau_hinh.py`. Số trên **máy này**: cpu, checkpoint theo configs/default.yaml, clip binh1.mp4. Commit `548e99b151c1627aaca78357cea5faaa69cbecc1`.
> Mỗi cấu hình chạy **3 lần**; `±` là độ lệch chuẩn giữa các lần ⇒ **chênh lệch nhỏ hơn `±` thì ghi 'không phân biệt được', cấm ghi 'tốt hơn'**.

| image_size | vos_every | FPS phát | Nhịp mask | vos_ms | tuổi mask p95 | lần | lỗi |
|---|---|---|---|---|---|---|---|
| 192 | 2 | 29.9 ± 0 | 9.1 ± 0 | 107.53 ± 6.95 | 266.6 ± 0.87 | 3 | 0 |
| 192 | 3 | 29.8 ± 0 | 8.6 ± 0.44 | 96 ± 1.61 | 304.23 ± 35.4 | 3 | 0 |
| 192 | 6 | 29.8 ± 0 | 5.17 ± 0.06 | 105.8 ± 13.59 | 301.93 ± 0.65 | 3 | 0 |
| 256 | 2 | 29.83 ± 0.06 | 5.03 ± 0.12 | 174.6 ± 17.01 | 424.37 ± 19.35 | 3 | 0 |
| 256 | 3 | 29.77 ± 0.06 | 4.83 ± 0.38 | 189.63 ± 9.41 | 470.13 ± 30.46 | 3 | 0 |
| 256 | 6 | 29.77 ± 0.06 | 4.93 ± 0.06 | 182.27 ± 5.8 | 391.53 ± 19.08 | 3 | 0 |
| 320 | 2 | 29.83 ± 0.12 | 3.57 ± 0.06 | 250.4 ± 7.97 | 559.53 ± 19.58 | 3 | 0 |
| 320 | 3 | 29.83 ± 0.06 | 3.53 ± 0.12 | 259.77 ± 11.04 | 605.1 ± 32.05 | 3 | 0 |
| 320 | 6 | 29.7 ± 0.26 | 3.23 ± 0.64 | 338.87 ± 87.07 | 769.07 ± 168.23 | 3 | 0 |

**CẤM trích**:

- `FPS phát` là nhịp **vẽ** frame (LK lấp giữa các lần VOS) — không phải nhịp model.
- `Nhịp mask` mới là số lần model chạy/giây; cấm viết "mask 30 FPS".
- `vos_ms` chỉ là phần model; nói "một frame tốn bao lâu" thì phải cộng `pre_ms` (~12 ms) — xem cột trong artifact.
- Tuổi mask p95 = `None` khi chưa đủ mẫu; **`None` không phải `0`**.
