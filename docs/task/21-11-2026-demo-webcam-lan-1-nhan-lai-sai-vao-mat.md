# Ngày 21-11-2026 — Phân tích phiên demo WEBCAM ĐẦU TIÊN: re-ID nhận lại **vào mặt người**

## 🎯 Mục tiêu
Phân tích phiên `./run demoip` người dùng vừa chạy trên webcam thật (relay `/snapshot.jpg`) để trả lời:
(1) đường demo đã chạy chưa, (2) số nào xấu và vì sao, (3) phải sửa gì **trước buổi bảo vệ**.

## 📥 Input
- Phiên thật: `data/demoip_1120-224057{,_metrics.csv,_summary.json,_run_info.json,_web.mp4}` (`git_rev bba279a`).
- Log console của người dùng (73 frame in ra, `[WARN] nghi ngờ ĐỔI ĐỐI TƯỢNG` ở f15→f16).
- Nhánh `feat/nhan-lai-vat-live` (vừa qua review vòng 4: P0 = 0, P1 = 0).

## 🔨 Công việc đã thực hiện
1. Đọc `_run_info.json` + `_summary.json` + 73 dòng CSV ⇒ dựng lại diễn biến trạng thái theo từng frame.
2. Trích 10 frame từ `_web.mp4` (436 frame @30 fps) → xem **ảnh thật** ở f15/f16/f18/f30/f43/f44/f45/f60/f72.
3. Ghép lưới ảnh bằng chứng: `docs/media/reid/demoip_1120_nhan_lai_vao_mat.jpg`.
4. Trích số của ca sai ra artifact: `data/reid_ca_sai_vao_mat_2026-11-20_calib.json`.
5. Ghi phát hiện vào ticket **#11** (hiệu chuẩn cổng): ca sai thứ hai làm **NCC không còn tách được**.

## 📤 Output / Kết quả

### Số của phiên (từ `_summary.json`, không suy diễn)
| Đại lượng | Số | Ghi chú |
|---|---|---|
| `total_frames` | **73** | video ghi 436 frame @30 fps (phần lớn là frame nội suy) |
| `mean_latency_ms` / `p95` | **378,8 / 430,0** (n = 48) | `image_size = 320` — đo trên máy này 192 chỉ ~87–118 ms |
| `effective_fps` (suy luận) | **2,64** | ⇒ mask mới ~2,6 lần/giây; hình vẫn 30 FPS nhờ LK |
| `lost_ratio` | **36 %** (26/73) | **toàn bộ** là MỘT cơn: f18–f43 |
| `reacquiring_frames` / `frozen_frames` | 24 / 25 | f20→f43 đang tìm lại |
| `reacquired_count` | **1** | tại **f44**, `reid_score = 0,9739`, `ncc = 0,5449` |

### Diễn biến (CSV, từng frame)
- f0–f17 `tracking` (**đúng vật**: vật màu vàng cạnh mặt).
- f15→f16 `[WARN] nghi ngờ ĐỔI ĐỐI TƯỢNG` (ô nhảy 373→124 px). **Xem ảnh: cảnh báo này là BÁO OAN** — tay đưa vật sang ngang nhanh, ô vẫn trên vật.
- f18–f19 `lost` (vật ra khỏi khung; f17 ô đã bám mép `x=0`).
- f20–f43 `reacquiring` (24 frame ≈ 9 s ở 2,64 FPS) — **quét toàn khung** vì `lost_age > search_grow_frames` (12).
- **f44 `reacquired` → bám vào MẶT NGƯỜI**; f45–f72 tiếp tục bám mặt. Ảnh: `docs/media/reid/demoip_1120_nhan_lai_vao_mat.jpg`.

### Kết luận (đọc đúng, không tô hồng)
1. **Đường ống chạy đúng**: relay → chọn ô → mask + ô + quỹ đạo → ghi mp4 → xuất H.264 → provenance
   (`git_rev`), `ncc_min=0.35` in ra đúng như thiết kế. Không crash, không `state=error`.
2. **Ca nhận lại là SAI**: vật được chọn có **tông màu da/vàng**, nằm cạnh mặt ⇒ khi vật rời khung, bộ mô tả
   khớp **khuôn mặt** với cosine **0,974** và ncc **0,545**. Đây là lỗi *bản chất đặc trưng*, không phải lỗi
   ngưỡng: **không ngưỡng nào tách được** (muốn chặn 0,545 phải đặt > 0,545 ⇒ chặn cả ca đúng 0,415).
3. **`lost_ratio 36 %` không phải "hệ thống không ổn định"** — đó là **một** sự kiện vật rời khung, kéo dài
   vì (a) vật không quay lại, (b) mỗi lần VOS 379 ms nên 24 lần thử = ~9 s. Cấm trích "36 % mất dấu" như
   chất lượng bám (AGENTS §6: phải tách "vật đã rời khung" khỏi "model mất dấu").
4. **`image_size 320` là nút thắt lớn nhất của buổi demo**: 379 ms/frame. Bảng cấu hình đã commit
   (`data/bang_cau_hinh_2026-11-15_metrics.json`) cho 192 ⇒ ~87–118 ms ⇒ **nhanh gấp 3–4 lần**.

### Việc phải làm trước khi bảo vệ (theo thứ tự)
1. `./run demoip --image-size 192` (cờ của người dùng đứng sau nên đè được) — đo lại `mean_latency_ms`,
   kỳ vọng **~90–120 ms**; nếu vẫn > 250 ms thì dừng lại kiểm máy (relay/CPU khác lúc đo).
2. **Chọn vật demo KHÁC TÔNG với bối cảnh**: vật có hoa văn/chữ in, không dùng tay/vật màu da, không đặt cạnh
   mặt. Sàng bằng số trước khi diễn: `object_signature` của vật vs (nền, mặt) và `ncc` của vật gây nhiễu.
3. **Kịch bản "vật ra khỏi khung"**: hoặc (a) đưa vật về **trong ≤ ~10 frame** (bán kính tìm còn hẹp, `search_grow_frames
   = 12`), hoặc (b) **bấm `r` chọn lại** và nói thẳng "đây là em chọn lại tay". Đừng để hệ tự "nhận lại" rồi
   trình bày như thành công.
4. Nếu vẫn muốn khoe ca nhận lại: chọn vật **khác tông**, quay lại **cùng vùng** ⇒ có ô lại trong ~0,8–1,2 s.

## 🐞 Vấn đề gặp phải & cách xử lý
- **`[WARN] nghi ngờ ĐỔI ĐỐI TƯỢNG` báo oan** (f15→f16): ngưỡng nhảy hiện so **tâm ô** với `1,5 ×` đường chéo ô;
  tay đưa vật nhanh qua ngang ⇒ vượt ngưỡng. Không sửa vội: báo oan còn rẻ hơn bỏ sót (ca f163 của `binh2` là
  bám sang **vật khác** thật). Ghi thành nợ, cần đo trên nhiều phiên tay nhanh trước khi nới.
- **Không kết luận gì về "NCC 0,35 giúp ích"**: trên phiên này cổng **không chặn** ca sai, và trên `binh2`
  trước đó cổng **không đổi gì**. Kết luận đúng: cổng chỉ lọc ca sai *khác tông hẳn*; đã ghi vào ticket #11.
- Ảnh f43/f44 cho thấy mask **phủ cả mặt + cổ** ⇒ nếu ai chỉ đọc `reid_score 0,974` sẽ tưởng "nhận lại tốt".
  Đây là lý do bắt buộc **xem ảnh**, không tin điểm số (đúng tinh thần AGENTS §6).

## 📌 Việc cần làm tiếp (Next steps)
- [ ] Người dùng chạy lại `./run demoip --image-size 192` + **vật khác tông**, gửi log; tôi chấm lại số.
- [ ] Sàng vật demo bằng số (`object_signature` vật vs nền/mặt, `ncc` vật gây nhiễu) — việc P4 trong plan,
      ~1,5 h, chưa làm.
- [ ] Ticket #11: cần **≥ 3 ca sai đa dạng** (khác tông + cùng tông) để chốt `ncc_min`; nay `max_bad` = 0,545.
- [ ] Ticket #42: nhận lại lặp ở mép khung + "ô ma" (vẫn mở).
- [ ] Web vẫn **chưa có** cơ chế tìm lại (P5 của plan) — beat này chỉ diễn trên `./run demoip`.

## 📚 Tài liệu tham khảo
- `data/demoip_1120-224057_{summary,run_info}.json`, `data/demoip_1120-224057_metrics.csv`
- `docs/media/reid/demoip_1120_nhan_lai_vao_mat.jpg` (ảnh bằng chứng: f15 đúng vật → f44 bám mặt)
- `data/reid_ca_sai_vao_mat_2026-11-20_calib.json` (số của ca sai, để ghép vào bộ hiệu chuẩn)
- `AGENTS.md` §6 (tách "vật rời khung" khỏi "mất dấu"; điểm số không phải bằng chứng)
- `docs/plan/21-11-2026-nhan-lai-vat-tren-live-va-demo-webcam.md` (việc 4: sàng vật demo bằng số)
