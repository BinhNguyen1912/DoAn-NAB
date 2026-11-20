# 40: A/B max_mad trên VẬT THỨ 2 (binh2) — cổng 1,5 quá chặt đã đo được +0,1745 trên binh1, cần tái lập

**Status:** claimed

**Type:** grilling

**Blocked by:** None (can start immediately)

## Question

**Question:** Phát hiện của PR #65 trên `binh1` (GT người tô `b1b`, 3 lần/cấu hình chèn kẽ, `git_dirty_code=false`): nới cổng `max_mad` **1,5 → 100** cho **+0,1745** IoU(ô đang hiển thị, ô GT) với sd hiệu **0,0205**, và **không** phụ thuộc frame flâke (bỏ f62 vẫn +0,1745). Đó là hiệu ứng **lớn nhất** đo được trong cả chuỗi 5 PR về LK.

Nhưng đó là **một clip, một vật** (chai trên `binh1`). Ticket #38 đã chốt **giữ `DEFAULT_MAX_MAD = 1,5`** với luật "phải tái lập trên clip thứ 2 trước khi đổi default". Câu hỏi của ticket này: **trên vật/clip thứ hai (`binh2`), nới cổng có còn lợi ích ≥ ngưỡng nhiễu không — hay lợi ích đó là đặc thù của chai-bị-tay-che trên `binh1`?**

**Vì sao không dùng lại số cũ:** 3 lần A/B trước (19-11, 20-11) đều đo `drift_iou` (khớp ô VOS) và cho "không phân biệt được"; chỉ đến khi có **GT người tô** mới thấy +0,1745. Nên phép đo bắt buộc là **IoU(ô hiển thị, ô GT người tô)**, dùng `scripts/ab_o_hien_thi_vs_gt.py --dump-shown-csv`, **không** phải `drift_iou`.

**Cần trước khi chạy (người):** GT người tô cho `binh2` ở các frame **giữa khe VOS** (`≡2 mod 3`), theo `./run gt --clip data/binh2.mp4 --ten binh2_<tay> --nguoi-gan <tên> --frames 2,32,62,92,182,212,242` (đúng quy trình ở `docs/thuoc-do-bam-dung.md`). Không có GT thì ticket này **không chạy được** — phải nói rõ "chưa đo", không được suy từ `binh1`.

**Cách chạy (sau khi có GT):**
```
./run gt ... --chi-sinh        # sinh file GT + ảnh kiểm
# rồi
python scripts/ab_o_hien_thi_vs_gt.py --clip data/binh2.mp4 --gt <ten_gt> --bbox <ô binh2> \
  --max-mad 1.5 6 100 --lan 3 --out data/ab_max_mad_binh2_2026-11-XX_metrics.json
```

**Nghiệm thu có số:**
1. Artifact có `git_dirty_code=false`, `so_lan_chay_loi = 0`, 3 lần/cấu hình **chèn kẽ**.
2. Bảng: `max_mad` × {IoU(ô hiển thị, ô GT) mean ± sd, tệ nhất, `lk_ok_frac`, số frame GT}.
3. `so_sanh_theo_cap` phải nêu `phan_biet_duoc: true/false/None` (None khi std None) — chênh ≤ `max(std_a, std_b)` ⇒ viết **"không phân biệt được"**.
4. Nếu 6,0 **và** 100 đều ≥ 1,5 + nhiễu trên `binh2` **và** trên `binh1` ⇒ **đổi `DEFAULT_MAX_MAD`** trong PR riêng, kèm cập nhật AGENTS §6.
5. Nếu chỉ `binh1` có lợi ích ⇒ **giữ 1,5** và ghi rõ trong log: lợi ích phụ thuộc vật bị che, **không** phổ quát.
6. Kiểm **ảnh** ≥ 3 frame ở mức nới: ô **không** trượt vào nền (điều kiện bác bỏ; `chốt MAD` sinh ra để chặn đúng lỗi này).

**Không** được: đổi default dựa trên `drift_iou` (nó **tăng** khi nới cổng trong khi độ đúng không đổi — bẫy AGENTS §6); hoặc trích mIoU của `./run miou` làm bằng chứng cho câu này (`vos_every 1` **tắt hẳn LK** nên `max_mad` không tham gia).
