# Plan 14-11-2026 — Năm việc còn lại của plan audit (#5 #6 #8 #9 #11)

> Việc lớn (≈ 1 ngày) theo **AGENTS.md §9.2**. Ghi cả phần **chưa làm được** (3 agent lập plan độc lập
> không trả kết quả trong phiên) để sau này không ai đọc thành "đã có 3 góc nhìn".

## 🎯 Câu hỏi cần quyết
Làm gì để **mọi tuyên bố trong báo cáo đều có thước đo đúng** (bám đúng — không chỉ "tự nhất quán"),
mà không tốn GPU và không cần dữ liệu ngoài máy? Ràng buộc: CPU-only (trần ~175 ms/frame @256), mọi
số phải kèm `git_rev` + ngưỡng nhiễu, `./run test` phải giữ ~1,5 phút.

## 🧭 Ba góc nhìn (vòng 1 — độc lập)
### A. Chất lượng & số đo — **không có kết quả** (agent không trả về)
### B. Sản phẩm & bằng chứng bảo vệ — **không có kết quả**
### C. Độ bền & hiệu năng — **không có kết quả**

**Trạng thái thật:** 3 agent được gọi song song với 3 prompt khác nhau (chất lượng/đo · sản phẩm/bảo vệ ·
độ bền/hiệu năng) nhưng **không agent nào trả kết quả trong phiên** (chỉ báo `running`).
⇒ Vòng 2 (phản biện chéo) **không thực hiện được**. Thay thế tạm thời: chính phiên cha tự đặt tiêu chí
nghiệm thu có số cho từng việc **trước khi** đo (xem "Quyết định"), và **review độc lập** (§9.1) đóng vai
trò phản biện cho phần code/số. Việc này KHÔNG đủ chất lượng của §9.2 — nếu cần plan đầy đủ thì chạy lại
3 agent ở phiên sau (việc còn lại, ~40 phút).

## ⚔️ Tranh chấp (vòng 2 — phản biện chéo)
Không có (xem trên). Các điểm *đáng lẽ* phải tranh luận, ghi lại để lần sau mở đúng chỗ:

| Điểm | Hai phía | Chốt tạm của phiên |
|---|---|---|
| Có làm GT gán tay cho video thật ngay không? | Chất lượng: phải có mIoU thật mới dám nói "bám đúng" · Sản phẩm: hội đồng không hỏi mIoU, hỏi "chạy được không" | Làm **đường gán + chấm** (tự động hoá được) + demo trên fixture; **gán tay để next step** (~30 phút) |
| Bảng cấu hình 9 cấu hình × 3 lần (~5 phút) có đáng? | Độ bền: mỗi lần chạy CI nặng · Chất lượng: không có ± thì mọi so sánh là cảm tính | Chạy tay (không vào CI), artifact commit; `--check` chỉ kiểm md khớp artifact |
| HUD có cần `mask_age` không (thêm 1 dòng nữa)? | Sản phẩm: HUD đã nhiều số · Chất lượng: đây là số duy nhất nói "ảnh bạn thấy cũ bao nhiêu" | Làm, kèm **ngưỡng nói TO** (1500 ms) thay vì chỉ in số |

## ✅ Quyết định
- **Chọn:** làm cả 5 việc, mỗi việc tối thiểu phải **đẻ ra được một con số kiểm chứng lại được**:
  bảng cấu hình có `±`, mIoU có quy tắc chấm rõ, HUD có ngưỡng cảnh báo, ảnh quỹ đạo có cảnh báo ô chọn
  sai, A/B có ngưỡng nhiễu.
- **Vì sao:** hiện toàn bộ số "chất lượng" là `drift_iou`/`stability` (độ tự nhất quán) — hội đồng hỏi
  "bám có đúng không?" thì repo **không có** câu trả lời. Đo trên máy này: mask chỉ ~9 lần/giây ở 192 và
  ~3,5 ở 320 ⇒ cần bảng để chọn cấu hình thi trong 1 phút thay vì tranh luận.
- **Bác:** (a) đề xuất *chỉ* làm bảng cấu hình rồi hết — bác vì nó vẫn không trả lời "bám đúng";
  (b) đề xuất chấm mIoU bằng mask do chính SAM 2 gợi ý — bác vì đó là **đo chính nó** (script từ chối GT
  như vậy); (c) đề xuất đưa bảng cấu hình vào CI — bác vì 5 phút/lần × 27 lần chạy model làm CI không còn
  "làn nhanh 30 s".
- **Tiêu chí nghiệm thu (có SỐ)** — tất cả đã đạt:
  - [x] `docs/bang-cau-hinh.md` có **9 dòng**, mỗi dòng `mean ± std` từ **3 lần** chạy worker thật;
        artifact `git_dirty_code = false`.
  - [x] 192 vs 256 vs 320 tách được bằng nhiễu: nhịp mask **7,5–7,6 / 4,3–4,4 / 3,2** lần/giây,
        `vos_ms` **101–132 / 212–221 / 285–287** ms (số sau khi đo lại trên cây sạch, xem
        `docs/bang-cau-hinh.md` — nguồn duy nhất, đừng chép tay từ đây).
  - [x] `scripts/score_miou.py` cho **mIoU = 0,9354** trên fixture tổng hợp và in cảnh báo `5/24 frame`.
  - [x] HUD in `Mask đang hiển thị: N ms tuổi` và **`role=alert`** "Mask CŨ" khi ≥ 1500 ms — e2e kiểm
        **cả chữ lẫn thuộc tính `role`** (đã bổ sung sau review 14-11: bản đầu chỉ so chữ).
  - [x] `scripts/ab_test.py` kết luận theo ngưỡng `max(spread_a, spread_b, sàn)`; A/B 192 vs 320:
        nhịp mask 7,5 ± 0,35 vs 3,1 ± 0,1 ⇒ **A tốt hơn** (chênh 4,4 ≫ nhiễu 0,6). Số đọc từ
        `data/ab_192_vs_320_2026-11-14_metrics.json` — **không** trích từ tài liệu này.
  - [x] `./run lint` xanh, `./run test` = 1126 passed, `./run webtest` 47, `./run e2e` PASS.

## 📌 Việc tách ra ticket
- [ ] Gán tay 10–20 frame `binh1` ⇒ mIoU **trên video thật** (quy trình: `docs/thuoc-do-bam-dung.md`).
- [ ] Đo `democheck --full` với webcam/relay thật (`source: 0`) — rủi ro "Device busy".
- [ ] Chạy lại **3 agent lập plan** đúng §9.2 cho việc lớn kế tiếp (lần này 3 agent không trả kết quả).
- [ ] Đoạn demo ≥ 20 s; chốt phạm vi với GVHD.

## 📚 Tham chiếu
- `docs/plan/14-11-2026-plan-3-y-kien-toi-uu-msi.md` — plan gốc (5 việc này nằm trong đó).
- `docs/task/14-11-2026-nam-viec-con-lai-cua-plan.md` — log thực hiện + số đo + review.
- `docs/bang-cau-hinh.md`, `docs/thuoc-do-bam-dung.md`, `docs/so-lieu-bao-cao.md` — sản phẩm của plan này.
- `AGENTS.md` §6 (§ố đã đo), §9.1 (review), §9.2 (plan 3 ý kiến).
