# 40: A/B max_mad trên VẬT THỨ 2 (binh2) — cổng 1,5 quá chặt đã đo được +0,1745 trên binh1, cần tái lập

**Status:** resolved

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

## Answer

**Trả lời: KHÔNG tái lập được lợi ích trên `binh2` ⇒ GIỮ `DEFAULT_MAX_MAD = 1,5`.**

Artifact: `data/ab_max_mad_binh2_2026-11-21_metrics.json` — `git_rev ea38a42`, **`git_dirty_code false`**, `schema 6`, `so_lan_chay_loi 0/0/0`, 3 lần/cấu hình **chèn kẽ**, GT `docs/gt/binh2_tay` (12 frame, **4 `gt_rong`** ⇒ chấm 8 frame), ô `330,330,150,360`.

| `max_mad` | IoU(ô hiển thị, ô GT) | `lk_ok_frac` |
|---|---|---|
| **1,5** | **0,4466 ± 0,1441** | **0,208** |
| 6,0 | 0,5629 ± 0,0343 | 0,500 |
| 100 | 0,5660 ± 0,0083 | **0,833** |

| cặp | chênh | nhiễu | `phan_biet_duoc` |
|---|---|---|---|
| 1,5 vs 6,0 | +0,1163 | 0,1441 | **false** |
| 1,5 vs 100 | +0,1194 | 0,1441 | **false** |
| 6,0 vs 100 | +0,0031 | 0,0343 | false |

⇒ **3/3 cặp "không phân biệt được"** ⇒ theo luật đăng ký trước (**AND trên mọi clip**) `binh2` **không đạt** ⇒ không đổi mặc định.

**Vì sao nhiễu lớn**: `iou_min = 0,000` ở **cả 9 lần chạy** — frame **163** (mô hình bám **sang chai đen**, GT là chai trắng; ô `[428,300,546,678]` vs GT `[179,314,304,637]`) và **228** (ô co còn 30×65 px). Đó là **lỗi base VOS**, không phải hiệu ứng `max_mad`. Ảnh kiểm: `docs/media/gt/binh2_gt_khong_nhat_quan_vat.jpg` (frame 98 · 163 · 261; GT xanh · ô hiển thị đỏ).

**Phân tích hậu nghiệm 6 frame dùng được** (nói rõ là hậu nghiệm): 1,5 → 0,5931 ± **0,1896** · 6,0 → 0,7475 ± 0,0441 · 100 → **0,7500 ± 0,0087**; chênh 1,5 vs 100 = **+0,1568 < 0,1896** ⇒ **vẫn** không phân biệt được. Nguyên nhân: ở 1,5 chỉ 21 % frame có LK ⇒ **79 % hiển thị ô VOS ĐÓNG BĂNG**, mà ô đóng băng lúc tốt (0,731) lúc tệ (0,377) ⇒ phương sai của chính 1,5 nuốt chênh lệch. Ở 100, sd nhỏ hơn **22×**.

**Cái đo được chắc chắn là HÀNH VI, không phải ĐỘ ĐÚNG**: nới cổng làm ô **chuyển động** (LK nhận 21 % → 83 %) và **ổn định hơn** (sd 0,19 → 0,009), cùng chiều với `binh1` (+0,1745, sd hiệu 0,0205) nhưng trên `binh2` **chưa** chứng minh chính xác hơn.

**Cách viết báo cáo**: ✅ "nới cổng làm ô chuyển động + ổn định; trên `binh1` còn cho IoU cao hơn +0,1745". ❌ "nới cổng bám chính xác hơn" (chưa chứng minh trên `binh2`). ❌ "1,5 tốt hơn" (không có bằng chứng nào cho chiều đó — giữ 1,5 chỉ vì **chưa đủ bằng chứng để đổi**).

**Kiểm ảnh (điều kiện bác bỏ của ticket)**: ở cả 3 mức, ô **không** trượt vào nền ở các frame dùng được (98, 261); cái hỏng là **đổi vật** ở 163 — xảy ra cả ở 1,5 nên không phải do nới cổng.

**Chuyển sang ticket mới** (phát hiện phụ, quan trọng hơn `max_mad`): base VOS **bám sang vật khác** ở f163 và **co ô** ở f228, ở cả 9 lần chạy — lỗi chất lượng bám bắt, cần điều tra riêng.
