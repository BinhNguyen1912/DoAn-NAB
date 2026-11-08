# Plan 08-11-2026 — Review độc lập PR #5 và chọn việc tiếp theo (3 ý kiến + tranh luận)

> Làm theo `AGENTS.md` mục 9.2. Ba cố vấn độc lập, mỗi người một góc nhìn, không biết đề xuất của
> nhau; sau đó một vòng phản biện chéo (đóng vai C, người bảo vệ độ bền kiến trúc); cuối cùng agent
> chính chốt. Bản gốc của 3 cố vấn nằm ở `.pi/artifacts/tasks/*.md` (không commit).

## 🎯 Câu hỏi cần quyết
- Sau khi live đã đạt 29,9 FPS phát / mask 8,6 lần/giây, **3–5 việc tiếp theo là gì, theo thứ tự nào**?
- Ràng buộc: laptop CPU (không GPU rời), ~1 tuần, mọi số phải tái lập được từ file, không claim
  "mask 30 FPS", không dùng dữ liệu bịa.

## 🧭 Ba góc nhìn (vòng 1 — độc lập)

### A. Chất lượng bám & độ trung thực của số đo
- **Kết luận mạnh nhất:** repo đang đo sai thứ quan trọng nhất. `stability` = IoU của hai mask VOS
  *liên tiếp* chỉ đo **nhấp nháy**, không đo **đúng**; nó không trả lời câu mà kiến trúc hybrid cần:
  *bỏ 2/3 lần suy luận thì ô bao trôi bao nhiêu?* — hiện **0 số đo**.
- Đường live **chưa có re-ID** ⇒ yêu cầu "chịu che khuất" của đề cương chỉ đúng trên giấy với demo live.
- `29,9 FPS` là **chạm trần đặt (30)**, không phải năng lực; kết luận "smoothing không có lợi" nằm
  trong **nhiễu giữa hai lần chạy** ⇒ phải gọi là *inconclusive*, cần **ngưỡng nhiễu**.
- Việc chọn: (1) `lk_drift_iou` + `mask_age_ms` + CSV cho live; (2) noise floor; (3) GT nhãn tay;
  (4) clip che khuất trên đường live; (5) cổng chống số cũ (`git_rev`).

### B. Sản phẩm & bằng chứng bảo vệ
- Hội đồng sẽ hỏi 3 câu mà repo **chưa** trả lời bằng file: *số 29,9/8,6 lấy từ đâu, chạy lại được
  không* (không có CSV nào trong `data/`); *chất lượng phân đoạn trên video thật* (chưa có nhãn
  người nào); *camera thật đã chạy chưa* (đường relay→web chưa từng chạy, E2E chỉ dùng video 160×120
  tự sinh).
- Việc chọn: (1) số live & job phải có file; (2) bộ demo "không thể trượt" (preflight + kịch bản +
  video dự phòng); (3) nhãn tay 30 khung × 2 clip; (4) sơ đồ khối + bảng phần cứng; (5) chạy lại GPU.
- Cần **người dùng** quay 2 clip: che một phần, và ra/vào khung.

### C. Độ bền kiến trúc & hiệu năng
- (1) race/threading của live; (2) tái lập số đo (seed); (3) watchdog chống treo worker; (4) không
  ONNX/OpenVINO (đã đo chậm hơn); (5) không microservice.

## ⚔️ Tranh chấp (vòng 2 — phản biện chéo, đóng vai C)

| Điểm tranh chấp | A nói | B nói | C (sau phản biện) | Chốt |
|---|---|---|---|---|
| Việc gấp nhất tuần này | đo drift của LK | bộ demo không trượt | vá race | **Đo drift + số liệu có file** (A1+B1 gộp) — vì mọi thứ khác đứng trên tiền đề "LK giữ được ô bao" chưa từng được đo |
| `stability` có phải bằng chứng? | **Không** — chỉ đo nhấp nháy | dùng được cho báo cáo | đồng ý A | **Không** dùng làm thước đo độ chính xác; phải thêm `lk_drift_iou` |
| Race mặc định có thật? | — | — | **Hạ từ P0 → P1**: engine sinh mảng mask MỚI mỗi lần ⇒ không rách dữ liệu; race thật là **snapshot `_stats` lẫn thế hệ** | Sửa bằng `_stats_lock` + `replace()` (đã làm) |
| Seed cố định để tái lập? | — | — | **Bác**: repo không có `manual_seed` nào; SAM 2 + memory bank không tất định trên CPU. Tiêu chí "hoặc ghi rõ vì sao không" là mệnh đề không kiểm chứng được | **Bỏ**; thay bằng **ngưỡng nhiễu** (chạy 3 lần cùng cấu hình, in độ tản) |
| `mask_fps` vào CSV offline? | đề xuất | đề xuất | **Bác**: offline chạy VOS mỗi frame ⇒ `mask_fps ≡ effective_fps` (hai cột trùng nhau). `vos_every` là **cấu hình** ⇒ thuộc `run_info.json` | Bỏ cột, ghi `run_info` |
| Video demo 720p | — | đề xuất | **Bác** nếu là upscale từ 640×480: ghi đúng độ phân giải nguồn | Ghi đúng nguồn; **transcode H.264** (recorder đang `mp4v` — Chrome không phát được) |
| GT mask gán tay 10 frame | đề xuất | nhãn bbox 30 frame | GT mask giải tích đã có cho fixture ⇒ 10 mẫu không phải thống kê | Fixture: tính **mọi frame**; video thật: **bbox IoU** + nói rõ giới hạn |

**Rủi ro cả ba cùng bỏ qua (C nêu):** không ai định nghĩa **ngưỡng nhiễu** trước khi so A/B ⇒ mọi
kết luận "tốt hơn/xấu hơn" đều có thể là nhiễu. Đã đưa thành việc số 2.

> ⚠️ **Các tiêu chí dưới đây là ĐÍCH, chưa phải kết quả.** `lk_drift_iou`, `mask_age_ms`,
> `scripts/measure_live.py`, `scripts/repeatability.py`, watchdog — **chưa tồn tại** trong repo tại
> thời điểm lập plan (đã kiểm bằng `grep`). Không được trích dẫn chúng như số đo đã có.

## ✅ Quyết định

- **Chọn thứ tự:** (1) số liệu live **có file + `git_rev`** (gộp B1+A1) → (2) đo **giá của nội suy LK**
  (`lk_drift_iou`, `mask_age_ms`) + **ngưỡng nhiễu** → (3) **watchdog** worker chết (C3, thu nhỏ) →
  (4) **transcode H.264** cho video demo/recorder → (5) **nhãn GT** trên video thật (cần người dùng)
  → (6) sơ đồ khối + bảng phần cứng cho báo cáo.
- **Vì sao:** (1) là điều kiện để mọi số khác trích dẫn được (quy tắc "báo cáo kèm số từ CSV");
  (2) trả lời câu duy nhất mà kiến trúc hybrid cần và có luật quyết định **đăng ký trước**; (3) chống
  "hỏng mà trông như đang chạy" — thứ đắt nhất trong lúc demo; (4) rủi ro mở file demo bằng Chrome;
  (5)(6) nặng về người, làm sau vẫn kịp.
- **Bác:** seed tất định (không kiểm chứng được), `mask_fps` trong CSV offline (trùng nghĩa),
  upscale 720p (số liệu giả), mIoU pixel-level (không đủ nhãn), đổi model/ONNX (đã đo chậm hơn),
  bật `mask_smoothing` mặc định (đo chưa thấy lợi).
- **Tiêu chí nghiệm thu (có SỐ):**
  - [ ] `data/live_<date>_vos{1,3,6}.json` tồn tại, mỗi file có `git_rev` == `git rev-parse HEAD`
        lúc đo; README trỏ đúng file đó.
  - [ ] `vos_every=3` trên `binh1`: `lk_drift_iou` **p05 ≥ 0,70** và mean ≥ 0,85 (3 lần chạy);
        `mask_age_ms` **p95 ≤ 150 ms**. Không đạt ⇒ hạ mặc định `vos_every` về 2 và ghi lại số mới.
  - [ ] Ngưỡng nhiễu công bố (ví dụ "±8 % latency, IoU ±0,03") và mọi câu kết luận cũ được gắn nhãn
        lại (smoothing = *inconclusive*).
  - [ ] Watchdog: worker chết giữa phiên ⇒ API chuyển `error` ≤ 5 s, `/api/live/status` không treo.
  - [ ] Video demo phát được trong Chrome (`videoWidth > 0`), độ phân giải đúng nguồn.

## 📌 Việc tách ra ticket (không làm ngay)
- [ ] `scripts/measure_live.py` + artifact JSON (việc 1) — 3 h
- [ ] `lk_drift_iou`/`mask_age_ms` + `scripts/repeatability.py` (việc 2) — 5 h
- [x] **Vòng đời phiên live** (làm ngay vì phá số đo): khoá `start` + 409, dừng-được-khi-đang-nạp,
      reap worker mồ côi bằng pidfile (+ kiểm cmdline), `lifespan` shutdown — PR ngay sau plan này.
- [ ] Watchdog **sau** khi start (worker chết giữa phiên): đọc `state`/heartbeat `ts` từ
      `status.json` trong adapter ⇒ `LiveState.ERROR` ≤ 2 s + nút "Chạy lại” — 2–3 h
- [ ] Transcode H.264 cho `--record` (việc 4) — 1 h
- [ ] `scripts/label_bbox.py` + eval GT (việc 5) — 4 h + **người dùng gán nhãn**
- [ ] Sơ đồ khối + bảng phần cứng (việc 6) — 1,5 h
- [ ] **Người dùng:** quay 2 clip (vật bị che một phần; vật ra khỏi khung rồi vào lại)

## 📚 Tham chiếu
- Review độc lập PR #5 (P1 `smoother.shift` với bbox `(0,0,0,0)`; P2 `stability=1,0` khi cả hai mask
  rỗng, `measured_fps` của API trần 15, hợp đồng `mask_smoothing`, nuốt lỗi luồng VOS).
- Vòng 2: `_stats` lẫn thế hệ; test đa luồng "1.000 vòng" sẽ xanh vô nghĩa; seed không tất định.
- `docs/task/08-11-2026-review-doc-lap-va-fix-p1-p2.md` (log của ngày).
