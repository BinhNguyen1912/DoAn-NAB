# Bảng cấu hình — sinh tự động, đừng sửa tay

> Sinh bởi `python scripts/bang_cau_hinh.py`. Số trên **máy này**: cpu, checkpoint theo configs/default.yaml, clip binh1.mp4. Commit `5b850772f6312aed8dea5c608fad01e8ba15afad`.
> Mỗi cấu hình chạy **3 lần**; `±` là độ lệch chuẩn giữa các lần ⇒ **chênh lệch nhỏ hơn `±` thì ghi 'không phân biệt được', cấm ghi 'tốt hơn'**.

| image_size | vos_every | FPS phát | Nhịp mask | vos_ms | tuổi mask p95 | age_n | lần | lỗi |
|---|---|---|---|---|---|---|---|---|
| 192 | 2 | 29.7 ± 0 | 7.53 ± 0.12 | 102.73 ± 16.61 | 306.57 ± 5.55 | 59 | 3 | 0 |
| 192 | 3 | 29.7 ± 0.1 | 7.57 ± 0.15 | 100.9 ± 6.46 | 315.8 ± 16.36 | 59 | 3 | 0 |
| 192 | 6 | 29.73 ± 0.06 | 5.07 ± 0.06 | 131.97 ± 10.68 | 334.67 ± 0.38 | 59 | 3 | 0 |
| 256 | 2 | 29.4 ± 0.61 | 4.3 ± 0.26 | 212.4 ± 19.66 | 508.07 ± 64.23 | 59 | 3 | 0 |
| 256 | 3 | 29.7 ± 0 | 4.43 ± 0.06 | 220.7 ± 18.12 | 484.13 ± 15.65 | 59 | 3 | 0 |
| 256 | 6 | 29.7 ± 0 | 4.37 ± 0.06 | 219.33 ± 10.89 | 557.5 ± 18.98 | 59 | 3 | 0 |
| 320 | 2 | 29.77 ± 0.06 | 3.23 ± 0.06 | 287.07 ± 14.12 | 625.07 ± 18.64 | 59 | 3 | 0 |
| 320 | 3 | 29.77 ± 0.06 | 3.2 ± 0 | 287.47 ± 8.13 | 637.43 ± 34.91 | 59 | 3 | 0 |
| 320 | 6 | 29.77 ± 0.06 | 3.23 ± 0.06 | 285.47 ± 2.56 | 674.47 ± 1.42 | 59 | 3 | 0 |

**CẤM trích**:

- `FPS phát` là nhịp **vẽ** frame (LK lấp giữa các lần VOS) — không phải nhịp model.
- `Nhịp mask` mới là số lần model chạy/giây; cấm viết "mask 30 FPS".
- `vos_ms` chỉ là phần model; nói "một frame tốn bao lâu" thì phải cộng `pre_ms` (~12 ms) — xem cột trong artifact.
- Tuổi mask p95 = `None` khi chưa đủ mẫu; **`None` không phải `0`**.
