# 46: Mask tràn nền cùng tông: 32 % frame mask to gấp ≥2,5× vật (bắt ở f96, cổng hiện tại trễ 7,61 s)

**What to build:** Đo phiên `demoip_1123-144505` (re-ID tắt, 194 frame): mask **trôi sang nền be cùng tông** (tường/mặt bàn), không phải "mất dấu".

| chỉ số | số đo |
|---|---|
| frame `mask_area` > 2,5× vật thật (5 776 px) | **63/194 = 32 %**, bắt đầu f96 |
| ô bao chạm ≥1 mép khung | **115/181 = 63,5 %** — phân rã: **dưới 104 (57,5 %)** · phải 13 (7,2 %) · trái 5 (2,8 %) · trên **0** |
| `mask_area` p90 / max | 31 898 / 38 866 px (**5,5× / 6,7×** vật) |
| `bbox_area` | nhảy 4 655 → **29 110 px trong 1 bước** (f95→f96), max **83 082 = 14×** ô ban đầu |
| `score` | 52/63 frame TRÀN có `score > 0` ⇒ **KHÔNG dùng được** làm cổng chất lượng |
| cổng nhảy tâm hiện tại | báo ở **f144 = trễ 7,61 s** so với f96, chỉ phủ 28/63 frame tràn |

⚠️ HAI ĐIỀU PHẢI NHỚ TRƯỚC KHI SỬA (xem comment để có bằng chứng đầy đủ):
1. Trên **2 clip CÓ GT** (`binh1`, `clip_be2`) mask **luôn NHỎ HƠN hoặc bằng GT** (`dien_tich_pred/gt` 0,56–1,02; `mask_ngoai_gt` 0,006) ⇒ mọi fix "chặn nở / cắt bớt" **chỉ có thể làm mIoU giảm hoặc bằng**. Tiêu chí nghiệm thu phải là: fix chỉ-hiển-thị ⇒ `paired_miou` trên 2 clip đó **bằng 0**; hiệu quả chống tràn chấm trên **clip có GT tràn** (repo CHƯA có, phải dựng/quay).
2. Số "63,5 %" chỉ tái lập được khi xử lý đúng `center=((x1+x2)//2)` (lệch **nửa pixel** — dung sai 0 px cho 28,7 %, dung sai ≥1 px cho 63,5 %). Ghi kèm công thức khi publish.

Việc này đổi **thuật toán** (thêm ràng buộc hình học/diện tích lên mask) ⇒ theo AGENTS §9.2 phải lập plan 3 ý kiến trước khi code. Ticket này giữ chỗ cho plan + triển khai.

> (Bảng số CŨ ở đây đã xoá 23-11 15:30 vì sai: nó ghi `bbox_h` = 479 — đó là toạ độ `y2`, chiều cao thật max = 376. Bảng đúng là bảng ở đầu ticket + comment "CHỐT VỤ 63,5 % vs 28,7 %".)

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Plan `docs/plan/24-11-2026-*.md` có 3 ý kiến + vòng phản biện + quyết định kèm lý do bác phương án còn lại
- [ ] Fix chỉ-hiển-thị ⇒ `paired_miou` trên 2 clip GT (`binh1` 0,7794 · `clip_be2` 0,8754) **bằng 0** (mask dump y hệt) — KHÔNG dùng 2 clip này để chứng minh 'chống tràn tốt hơn' (mask ⊂ GT, xem comment)
- [ ] Dựng hoặc quay **clip CÓ GT TRÀN** rồi mới chấm hiệu quả (kill criterion: baseline phải có tỉ lệ diện tích > 2,5 trên ≥ 10 % frame)
- [ ] Đo lại được trên chính phiên `demoip_1123-144505` đã có CSV (32 % frame mask > 2,5× vật ⇒ phải giảm)

## Comments

ĐÍNH CHÍNH số (đối chiếu độc lập, 23-11 15:20):

1. **"63,5 % ô chạm mép khung" TÁI LẬP ĐƯỢC** — 115/181 frame, công thức `(cx±w/2, cy±h/2)`. Đã kiểm chéo 4 frame với log `run_live` (`f0 CSV→(171,319,247,395)` khớp đúng `[f0] bbox=(171,319,247,395)`; `f124 → (265,183,423,479)` khớp) ⇒ `center_x/center_y` ĐÚNG là tâm ô bao, công thức hợp lệ.

2. **Nhưng lý do tôi viết kèm là SAI**: tôi ghi "`bbox_h` = 479 = hết chiều cao khung". SAI — `bbox_h` **max = 376** (78 % chiều cao khung 480); số 479 là **toạ độ `y2`** in trong log `run_live`, không phải chiều cao. Cấm trích "bbox_h=479".

3. Phân rã theo mép (n=181 frame có mask) — **đây là số nên dùng**:
   - mép **dưới** `y2 ≥ 478`: **104 frame (57,5 %)**
   - mép phải `x2 ≥ 638`: 13 (7,2 %) · mép trái `x1 ≤ 2`: 5 (2,8 %) · mép trên `y1 ≤ 2`: **0 (0,0 %)**
   ⇒ tín hiệu gần như CHỈ là "mask ăn xuống mặt bàn phía dưới", không phải "lan mọi phía".

4. Một reviewer độc lập đo ra **28,7 % (52/181)** cho cùng câu hỏi ⇒ trước khi lên slide phải ghi rõ công thức + n. Dùng dòng phân rã ở mục 3 thay cho một con số tổng.

CHỐT VỤ "63,5 % vs 28,7 %" — AI ĐÚNG VÀ VÌ SAO (23-11 15:30):

`src/live_pipeline._record_from:131` ghi `center = ((x1+x2)//2, (y1+y2)//2)` = **tâm Ô BAO** (không phải tâm mask), `bbox_w = x2-x1` ⇒ dựng lại ô bằng `cx ± w/2` là ĐÚNG.

Nhưng `//` làm tròn **xuống**: khi `x1+x2` lẻ (≈ một nửa số frame), `cx + w/2 = x2 − 0,5`. Vì vậy:
- so `x2 >= W-1` với **dung sai 0 px** ⇒ 52/181 = **28,7 %** (đúng số hai agent kia ra — họ dùng `>= 639` mà không cộng lại 0,5),
- so với **dung sai ≥ 1 px** ⇒ 115/181 = **63,5 %**,
- dung sai 1/2/3/5 px đều cho **115** ⇒ không phải "nới ngưỡng cho vừa số", mà là **sửa lỗi nửa pixel**.

Cách kiểm lại độc lập: `x2 = cx + w/2` là số **bán nguyên**; so `x2 >= W - 1 - 0.5`. Số đúng để publish: **63,5 % (115/181)**, kèm phân rã: dưới **104 (57,5 %)** · phải 13 (7,2 %) · trái 5 (2,8 %) · trên **0**.

⚠️ **Tiêu chí nghiệm thu hiện tại của ticket này KHÔNG DÙNG ĐƯỢC** (đo độc lập, `data/miou_binh1_nofreeze_lan1..3` + `miou_be2_nofreeze_2026-11-23`):
- `dien_tich_pred/dien_tich_gt` từng frame = **0,56–1,02** (binh1: 0,56 · 0,78 · 0,83 · 0,83 · 0,80 · 0,85 · 0,87), `mask_ngoai_gt` mean **0,006**
- ⇒ trên 2 clip CÓ GT, mask **luôn NHỎ HƠN hoặc bằng** GT. Mọi fix "chặn nở / cắt bớt" **chỉ có thể làm mIoU giảm hoặc bằng** ⇒ không thể chứng minh "tốt hơn" bằng 0,7794 / 0,8754.

Tiêu chí phải đổi thành: (a) fix chỉ-hiển-thị ⇒ `paired_miou` trên 2 clip GT **bằng 0** (mask dump phải y hệt); (b) hiệu quả chống tràn phải chấm trên **clip CÓ GT TRÀN** — hiện repo CHƯA CÓ, phải dựng (`scripts/make_flood_gt_clip.py`, kill criterion: baseline `--smooth --no-reid --image-size 192` phải có tỉ lệ diện tích > 2,5 trên ≥ 10 % frame) hoặc quay clip thật + 10–12 frame GT.

Tín hiệu dự phòng đã đo được (trên chính phiên 144505, 1 frame = 0,159 s): `bbox_area > 3,0 × EMA(α=0,03)` báo ở **f96 (trễ 0,00 s)**, phủ **61/63** frame tràn, **0 lần báo oan** trên binh1-nofreeze ×3 + be2-nofreeze; cổng nhảy tâm hiện tại báo **f144 (trễ 7,61 s)** phủ 28/63. Còn `score` KHÔNG dùng được: 52/63 frame tràn có `score > 0`.
