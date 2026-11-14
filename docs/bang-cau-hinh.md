# Bảng cấu hình — sinh tự động, đừng sửa tay

> Sinh bởi `python scripts/bang_cau_hinh.py`. Số trên **máy này**: cpu, checkpoint theo configs/default.yaml, clip binh1.mp4. Commit `ed80996b6fcd0949bdf2a458ee173a930a731723` (cây BẨN: số không tái lập).
> Mỗi cấu hình chạy **3 lần**; `±` là độ lệch chuẩn giữa các lần ⇒ **chênh lệch nhỏ hơn `±` thì ghi 'không phân biệt được', cấm ghi 'tốt hơn'**.

| image_size | vos_every | FPS phát | Nhịp mask | vos_ms | tuổi mask p95 | lần | lỗi |
|---|---|---|---|---|---|---|---|
| 192 | 2 | 29.87 ± 0.06 | 8.5 ± 0.4 | 110.6 ± 10.85 | 278.9 ± 18.71 | 3 | 0 |
| 192 | 3 | 29.8 ± 0 | 8.6 ± 0.36 | 94.43 ± 6.37 | 302.73 ± 35.27 | 3 | 0 |
| 192 | 6 | 29.7 | 5.2 | 92.7 | 301.2 | 3 | 2 |
| 256 | 2 | 29.8 | 4.8 | 189.9 | 406 | 3 | 2 |
| 256 | 3 | 29.8 ± 0 | 4.67 ± 0.21 | 191.3 ± 20.87 | 449.87 ± 41.4 | 3 | 0 |
| 256 | 6 | 29.77 ± 0.06 | 4.8 ± 0.17 | 173.63 ± 11.48 | 430.73 ± 73.79 | 3 | 0 |
| 320 | 2 | 29.8 ± 0 | 3.47 ± 0.06 | 270.7 ± 18.84 | 581.87 ± 18.57 | 3 | 0 |
| 320 | 3 | 29.6 ± 0.26 | 3.2 ± 0.26 | 294.9 ± 14.86 | 669.57 ± 55.39 | 3 | 0 |
| 320 | 6 | 29.77 ± 0.06 | 3.3 ± 0.26 | 294.5 ± 4.18 | 685.77 ± 52.58 | 3 | 0 |

**CẤM trích**:

- `FPS phát` là nhịp **vẽ** frame (LK lấp giữa các lần VOS) — không phải nhịp model.
- `Nhịp mask` mới là số lần model chạy/giây; cấm viết "mask 30 FPS".
- `vos_ms` chỉ là phần model; nói "một frame tốn bao lâu" thì phải cộng `pre_ms` (~12 ms) — xem cột trong artifact.
- Tuổi mask p95 = `None` khi chưa đủ mẫu; **`None` không phải `0`**.
