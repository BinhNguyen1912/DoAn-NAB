# Bảng cấu hình — sinh tự động, đừng sửa tay

> Sinh bởi `python scripts/bang_cau_hinh.py`. Số trên **máy này**: cpu, checkpoint theo configs/default.yaml, clip binh1.mp4. Commit `96b0c3ec67b624aa236c3e98eca4fb9aa8b18a39`.
> Mỗi cấu hình chạy **3 lần**; `±` là độ lệch chuẩn giữa các lần ⇒ **chênh lệch nhỏ hơn `±` thì ghi 'không phân biệt được', cấm ghi 'tốt hơn'**.

| image_size | vos_every | FPS phát | Nhịp mask | vos_ms | tuổi mask p95 | age_n | lần | lỗi |
|---|---|---|---|---|---|---|---|---|
| 192 | 2 | 29.6 ± 0.26 | 7.2 ± 1.31 | 120.83 ± 26.87 | 390.17 ± 111.31 | 59 | 3 | 0 |
| 192 | 3 | 29.67 ± 0.32 | 7.4 ± 1.11 | 100.77 ± 14 | 373.57 ± 97.85 | 59 | 3 | 0 |
| 192 | 6 | 29.8 ± 0.1 | 5.17 ± 0.06 | 105.3 ± 10.91 | 303.57 ± 1.44 | 59 | 3 | 0 |
| 256 | 2 | 29.8 ± 0 | 4.77 ± 0.12 | 187.5 ± 10.33 | 436.4 ± 1.3 | 59 | 3 | 0 |
| 256 | 3 | 29.83 ± 0.06 | 4.77 ± 0.12 | 187.8 ± 6.93 | 447.6 ± 18.34 | 59 | 3 | 0 |
| 256 | 6 | 29.73 ± 0.12 | 3.97 ± 1.01 | 232.13 ± 59.51 | 699.67 ± 337.73 | 59 | 3 | 0 |
| 320 | 2 | 29.8 ± 0 | 3.37 ± 0.15 | 281.27 ± 2.54 | 603.6 ± 30.77 | 59 | 3 | 0 |
| 320 | 3 | 29.57 ± 0.49 | 3.2 ± 0.2 | 262.3 ± 12.9 | 656.53 ± 65.09 | 59 | 3 | 0 |
| 320 | 6 | 29.8 ± 0 | 3.43 ± 0.06 | 295.2 ± 26.53 | 707.17 ± 32.42 | 59 | 3 | 0 |

**CẤM trích**:

- `FPS phát` là nhịp **vẽ** frame (LK lấp giữa các lần VOS) — không phải nhịp model.
- `Nhịp mask` mới là số lần model chạy/giây; cấm viết "mask 30 FPS".
- `vos_ms` chỉ là phần model; nói "một frame tốn bao lâu" thì phải cộng `pre_ms` (~12 ms) — xem cột trong artifact.
- Tuổi mask p95 = `None` khi chưa đủ mẫu; **`None` không phải `0`**.
