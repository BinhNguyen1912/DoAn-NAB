# 19-11-2026 — `p05` **theo khung** (tái lập được bằng 1 lệnh) + mở khoá ticket 14

## Mục tiêu

1. Vá lỗ hổng do PR #46 tạo ra: phụ lục báo cáo công bố *"`p05` **trong khung** của `binh1` = 0,000
   với n = 60"*, nhưng **không công cụ nào tính được** đại lượng đó (`low_p05_low_empty` chạy trên cả
   dãy; `thong_ke_mau` chỉ có `mean`). Số không tái lập được bằng lệnh = đúng thứ repo này cấm.
2. Kiểm lại **điều kiện tiên quyết của ticket 14** ("có clip `p05 thấp` mà `empty ≈ 0`") — hoá ra
   **đã đạt** trên dữ liệu có sẵn, nếu lọc theo khung vật còn trong khung.

## Input

- `data/drift_samples_binh1_2026-11-14_*.csv` (19 file) + `.meta.json` bên cạnh.
- Khung frame theo `docs/demo-clip-va-o-chon.md`: `binh1` = `0:110` ∪ `165:262`.
- `scripts/analyze_drift_samples.py --frame-window` (đã có từ PR #18), hàm `tach_theo_cac_khung`.

## Công việc đã thực hiện

1. `src/drift_samples.py`:
   - `thong_ke_mau()` thêm `drift_iou_p05` (**đi qua `phan_vi`** ⇒ `None` khi < `MIN_SAMPLES` = 30),
     `drift_iou_p05_n`, `drift_iou_p05_nguong`;
   - hàm thuần mới `_dieu_kien_ticket_14(nhom)` → `{dat, ly_do}` với **3 trạng thái**;
   - `tach_theo_cac_khung()` trả thêm `dieu_kien_ticket_14.{trong_khung,ngoai_khung,ghi_chu}`.
2. `scripts/analyze_drift_samples.py`: in `p05` + `n_drift` cho cả hai bên khung, và in điều kiện
   ticket 14 với nhãn **`ĐẠT` / `không đạt` / `CHƯA ĐO`** (`None` **không** được in thành "không đạt").
3. Test: 5 test mới (`TestP05TheoKhung`) + 1 test cấp lệnh (`test_in_dieu_kien_ticket_14_theo_khung_
   ba_trang_thai`), 3 test cũ cập nhật kỳ vọng dict (không nới assert).

## Output / Kết quả

Lệnh tái lập (một dòng, không cần tính tay):

```
python scripts/analyze_drift_samples.py --frame-window 0:110 --frame-window 165:262 \
    data/drift_samples_binh1_2026-11-14_141609.csv
→ trong n=63 rỗng=0.016 p05=0.0 (n_drift=60) drift_tb=0.4929 · ngoài n=40 rỗng=0.9 p05=None
  · điều kiện ticket 14 ở trong_khung: ĐẠT
```

| nhóm (binh1, trong khung `0:110` ∪ `165:262`) | số lần chạy | `empty_frac` | `drift_iou_p05` | `n_drift` |
|---|---|---|---|---|
| ô **chai** | **8** | **1,6–3,6 %** | **0,000** | 54–61 |
| ô **khuôn mặt** | 4 | 0,0 % | **0,725–0,730** | 55–60 |

⇒ **điều kiện tiên quyết của ticket 14 ĐẠT**: có `p05 < 0,30` **và** `empty_frac < 3 %` cùng lúc, nên
cờ chẩn đoán nói được điều `empty_frac_window` **không** nói. Kết luận cũ ("p05 và empty đi cùng nhau
1:1", 13-11) là do tính **cả phiên** — ngoài khung thì chai đã rời khung nên `empty` cao.

- `./run lint` xanh · `./run test` **1410 passed** (5 deselected).

## Vấn đề & cách xử lý

- **Ba test cũ so sánh dict nguyên khối** ⇒ thêm khoá làm đỏ. Sửa bằng **cập nhật kỳ vọng đầy đủ**
  (kèm chú thích vì sao `p05` là `None` với 3 mẫu), **không** đổi sang `>=`/`in` để né.
- **Test cấp lệnh có nguy cơ "cổng danh nghĩa"** (assert chỉ khớp một chuỗi luôn được in). Đã diễn tập
  ngược **2 mutant**: (a) nhãn luôn `"không đạt"`; (b) in `p05=None` — **2/2 test đỏ**, khôi phục rồi
  xanh lại.
- ⚠ **Chưa chứng minh được ai sai** ở các mẫu `drift_iou = 0` (frame 57/69/75/105/108/171/255): CSV
  ghi `bbox = result.bbox` = ô của **VOS**, nên số liệu chỉ nói *ô hiển thị (LK) và ô VOS không giao
  nhau*, **chưa** nói LK sai. Tên cờ "LK nội suy lệch" của plan 09-11 **chưa được dùng** cho tới khi có
  phiên `--dump-mask-frames` phủ frame 50–110.

## Next steps

- Ticket 14 (đã claim, đã comment số): chốt lại `drift_n ≥ 100` — `n_drift` trong khung chỉ **54–61**/11 s
  ⇒ giữ 100 thì cờ **không bao giờ bật**; đề xuất cờ dùng **cửa sổ trượt 20–50 mẫu, ≥ 30 mẫu đo được**
  (ngưỡng công bố p05 của repo), còn `≥ 100` giữ cho p05 cấp phiên.
- Chứng minh attribution (LK vs VOS) bằng `--dump-mask-frames` ⇒ rồi mới đặt tên cờ.

## Tài liệu tham khảo

- `docs/plan/09-11-2026-chan-doan-chat-luong-bam.md` · `.scratch/camera-ai-realtime/issues/14-*.md`
- `docs/demo-clip-va-o-chon.md` (ô + khung frame) · `AGENTS.md` §6 (ngưỡng 30 mẫu, `0/None ≠ đã đo`)
