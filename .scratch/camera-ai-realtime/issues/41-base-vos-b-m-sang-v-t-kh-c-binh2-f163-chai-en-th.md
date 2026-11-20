# 41: Base VOS bám SANG VẬT KHÁC ở binh2 (f163: chai đen thay vì chai trắng; f228 ô co còn 30×65) — 9/9 lần chạy, mọi max_mad

**Status:** claimed

**Type:** research

**Blocked by:** None (can start immediately)

## Question

**What to build (điều tra):** Trong A/B của ticket #40 (`data/ab_max_mad_binh2_2026-11-21_metrics.json`, 9 lần chạy = 3 cấu hình × 3 lần), **2/8 frame GT có IoU = 0,00 ở MỌI cấu hình**:

| frame | GT (hộp từ mask người tô) | ô hiển thị (max_mad 1,5 và 100) | hình |
|---|---|---|---|
| **163** | `[179,314,304,637]` (chai **trắng**) | `[428,300,546,678]` / `[456,275,574,654]` — **chai ĐEN** | `docs/media/gt/binh2_gt_khong_nhat_quan_vat.jpg`, ô giữa |
| **228** | `[20,240,155,582]` (vật to, gần mép trái) | `[126,436,156,501]` / `[40,536,56,596]` — co còn ~30×65 px, lệch xuống dưới | cùng file, không có trong ảnh — cần thêm |

Clip `binh2` có **2 chai** (đen + trắng); người dùng chọn ô chai trắng `330,330,150,360`. Ở frame 163 mô hình đang bám chai trắng (f131 IoU 0,81) rồi **nhảy sang chai đen**; đến f261 bám lại chai trắng (0,84). Frame 228 tương ứng lúc chai rời/trở lại khung (`docs/demo-clip-va-o-chon.md`: chai rời khung 165–240).

**Đây là lỗi chất lượng bám bắt (đề cương mục 3–5), KHÔNG phải lỗi ngưỡng**: nó xảy ra ở cả `max_mad` 1,5 · 6 · 100 và cả khi `lk_ok = true` lẫn `false`, nên **mọi** PR về `max_mad`/`lk_scale` đều không chạm tới.

**Việc phải làm (điều tra, không sửa mặc định):**
1. Lấy **ô VOS** (base) và **ô LK** ở đúng frame 163/228: chạy `tools/live_worker.py --dump-shown-csv` + `status.json` (`chan_doan_lk`, từ ticket #39) và/hoặc dump mask VOS của frame 162–163 — cần biết **ô VOS đã sai trước khi LK bước** hay LK kéo sang.
2. Xác định cơ chế: (a) SAM 2 mất dấu rồi **re-acquire nhầm** vật khác cùng khung; (b) ô chọn ban đầu `330,330,150,360` phủ **một phần** chai đen nên mask trôi; (c) ô bị nhiễu do tay che (frame 228: vật to gần mép trái, prompt bbox lệch).
3. Đo **tỉ lệ** lỗi này trên ≥ 2 clip có GT (binh1 `b1b`, binh2 `binh2_tay`) với định nghĩa tường minh: `IoU(ô, GT) < 0,1` **và** tâm ô cách tâm GT > 1 chiều rộng vật ⇒ "bám sang vật khác".
4. Nêu rõ **ảnh hưởng tới báo cáo/demo**: nếu tỉ lệ này đáng kể thì mọi con số IoU trung bình trên `binh2` bị kéo xuống bởi 2 frame này (xem log #40 §4B: 1,5 → 0,4466, bỏ 2 frame → 0,5931).

**Nghiệm thu có số:** bảng `frame × (ô VOS, ô LK, ô GT, IoU_vos, IoU_lk)` cho 163/228 (+ vài frame đối chứng tốt); kết luận **VOS sai trước hay LK kéo sai**; tỉ lệ "bám sang vật khác" trên 2 clip; đề xuất (nếu có) tách thành ticket sửa.

**Không** được: "chữa" bằng cách đổi `DEFAULT_MAX_MAD` (đã chốt giữ 1,5 ở #38/#40) hoặc bật `lk_scale` (chưa chứng minh tốt hơn, PR #65); không được loại frame 163/228 khỏi báo cáo mà không nói rõ (đó là **che số liệu**).
