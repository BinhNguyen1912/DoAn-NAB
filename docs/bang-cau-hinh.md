# Bảng cấu hình — sinh tự động, đừng sửa tay

> Sinh bởi `python scripts/bang_cau_hinh.py`. Số trên **máy này**: cpu, checkpoint theo configs/default.yaml, clip binh1.mp4. Commit `af00303f3944c99f762ecf7ab078edac076a9cd9` (cây BẨN: số không tái lập).
> Mỗi cấu hình chạy **3 lần**; `±` là độ lệch chuẩn giữa các lần ⇒ **chênh lệch nhỏ hơn `±` thì ghi 'không phân biệt được', cấm ghi 'tốt hơn'**.

| image_size | vos_every | FPS phát | Nhịp mask | vos_ms | tuổi mask p95 | lần | lỗi |
|---|---|---|---|---|---|---|---|
| 192 | 2 | 29.83 ± 0.06 | 9.33 ± 0.15 | 91.27 ± 10.46 | 247.53 ± 17.41 | 3 | 0 |
| 192 | 3 | 29.87 ± 0.06 | 8.87 ± 0.4 | 91.07 ± 7.36 | 279.13 ± 19.02 | 3 | 0 |
| 192 | 6 | 29.83 ± 0.06 | 5.17 ± 0.06 | 97.63 ± 7.82 | 300.67 ± 0.23 | 3 | 0 |
| 256 | 2 | 29.73 ± 0.15 | 4.73 ± 0.81 | 190.73 ± 39.07 | 448.07 ± 79.44 | 3 | 0 |
| 256 | 3 | 29.33 ± 0.06 | 4.03 ± 0.06 | 185.7 ± 12.93 | 581.33 ± 14.54 | 3 | 0 |
| 256 | 6 | 29.2 ± 0.2 | 4.1 ± 0.17 | 221.37 ± 53.08 | 631.4 ± 50.6 | 3 | 0 |
| 320 | 2 | 29.77 ± 0.06 | 3.47 ± 0.15 | 270.07 ± 25 | 582.23 ± 19.81 | 3 | 0 |
| 320 | 3 | 29.83 ± 0.06 | 3.57 ± 0.06 | 272.2 ± 26.06 | 613.83 ± 22.52 | 3 | 0 |
| 320 | 6 | 29.8 ± 0 | 3.53 ± 0.06 | 278.33 ± 8.18 | 679.9 ± 19.5 | 3 | 0 |

**CẤM trích**:

- `FPS phát` là nhịp **vẽ** frame (LK lấp giữa các lần VOS) — không phải nhịp model.
- `Nhịp mask` mới là số lần model chạy/giây; cấm viết "mask 30 FPS".
- `vos_ms` chỉ là phần model; nói "một frame tốn bao lâu" thì phải cộng `pre_ms` (~12 ms) — xem cột trong artifact.
- Tuổi mask p95 = `None` khi chưa đủ mẫu; **`None` không phải `0`**.
