# 24-11-2026 — "Vật rời khung rồi vào lại" KHÔNG phải "đổi đối tượng" (cổng nghi tự khoá phiên)

## 1. Mục tiêu

Người dùng báo (phiên `demoip_1124-193026`, 60 s):

> "nếu ra khung khoảng 10 s, khi đưa vào khung lại sẽ bị nghi, từ đó **không nhận diện lại nữa**"

Yêu cầu: vật rời khung rồi vào lại thì hệ **phải bám lại được**, không được kẹt ở trạng thái nghi.

## 2. Input

- `data/demoip_1124-193026_metrics.csv` (404 frame, `git_rev=14140ca`, mean 141 ms / p95 205 ms,
  `mất dấu 92/404 = 23 %`) + `data/demoip_1124-193026_web.mp4` (HUD).
- Code: `src/identity_guard.py` (`IdentityWatch`), `src/smooth_display.py` (đường `./run demoip`),
  `src/live_pipeline.py` (đường web), `scripts/eval_gate_rules.py`, `scripts/replay_latch_settle.py`.

## 3. Công việc đã thực hiện

### 3.1. Chẩn đoán bằng số (không đoán)

| đại lượng | số đo |
|---|---|
| frame `nghi_doi_tuong = 1` | **8** frame (f264–271) = 2,0 % |
| frame `chua_xac_minh` (ô nét đứt, không tô, không quỹ đạo) | **132** frame = **32,7 %** phiên |
| đoạn `mask_area = 0` dài | 6 đoạn 8–22 frame: `72–79`, `117–125`, **`158–179`**, **`248–262`**, `340–351`, `387–394` |
| frame bật cổng | **f264** — cách đoạn vắng `248–262` đúng **2 frame** |

Chuỗi thật ở cú báo:

- f248–262: **15 frame `mask_area = 0`** (vật ngoài khung).
- f263: model trả mask đầu tiên nhưng chỉ **559 px** — `bbox_area_ratio = 0,346` × tham chiếu ⇒ **mẩu rác**.
- f264: mask thật **24 100 px** ở vùng khác ⇒ cổng chấm "tâm nhảy 209 px" **giữa MẨU RÁC và VẬT** ⇒ báo nghi.
- f264 → hết phiên: latch không có đường xoá (re-ID TẮT) ⇒ **132 frame** chỉ còn ô nét đứt.

⇒ Lỗi **không phải ngưỡng**: cổng đang lấy **mẩu rác của lần dò lại** làm mốc so sánh. Ảnh
`m330` (cắt từ `_web.mp4`) xác nhận song song: sau cú báo ô bám sang **tường trống** (chai vẫn ở dưới,
nhoè) ⇒ vấn đề thứ hai (trôi dần) là **mù có từ trước**, không phải thứ sửa trong phiên này (§5).

### 3.2. Sửa: "vắng mặt" ≠ "đổi đối tượng" (một chỗ, cả 2 đường dùng chung)

`src/identity_guard.py`:

- `DEFAULT_LOST_RESET_STREAK = 3` — 3 bước **liên tiếp** không có mask ⇒ **vật đã rời khung**.
- `DEFAULT_REACQ_GRACE_STEPS = 2` — 2 bước đầu của phiên bám mới **miễn chấm nhảy** (mốc chưa đáng tin).
- `update(...)`: vắng ≥ 3 bước rồi có mask ⇒ `reset()` (về `ok`) + grace. Grace được kiểm **trước**
  phán quyết nhảy ⇒ bước 2 của phiên mới không lấy mẩu rác f263 làm mốc.
- `vua_bao` — cờ "bước này cổng **thật sự** kết luận đổi đối tượng". `_switch_warning` trước đây tự gọi
  `is_suspect_switch` **lần thứ hai** ⇒ sửa state machine mà console vẫn in WARN + banner (bắt được
  ngay trong lần chạy đầu). Nay cả `smooth_display` và `live_pipeline` chỉ in khi `watch.vua_bao`.

Vì sao ngưỡng **3**: 1–2 frame rỗng là **nhấp nháy** — 6/7 ca báo ĐÚNG của repo không có đoạn rỗng nào
trước đó, ca thứ 7 (`125109#137`) chỉ rỗng **1** frame ⇒ ngưỡng 3 **giữ nguyên 7/7** (đo ở §4).

### 3.3. Test (11 case mới, khoá đúng hành vi)

`tests/test_identity_guard.py::TestTaiBamSauKhiVatRoiKhung` — vắng dài rồi vào lại **không báo**; hết
grace thì **chấm lại như cũ** (chống "sửa" bằng cách tắt cổng); vắng 1–2 frame **vẫn chấm**; tái bám
**xoá latch**; `lost_reset_streak=0` tái lập được hành vi trước 24-11.
`tests/test_smooth_display.py::test_canh_bao_chi_in_khi_cong_that_su_cham`.

## 4. Output / Kết quả

### 4.1. Phiên người dùng báo (404 frame) — replay bằng **chính** `IdentityWatch`

| | báo | ẩn mask | chưa xác minh |
|---|---|---|---|
| trước (`lost_reset_streak=0`) | 1 lần (f264) | 8 | **132 (32,7 %)** |
| **nay** (`=3`) | **0** | **0** | **0** |

### 4.2. Không mất ca báo đúng nào — `scripts/eval_gate_rules.py`

Nhóm chi phí **10 phiên / 1 509 frame** (danh sách đóng băng `data/eval_gate_config_list.json`):

| luật | báo | ẩn | chưa xác minh | **không tin cậy** | bắt ca ĐÚNG |
|---|---|---|---|---|---|
| `hien_tai_truoc_khi_tai_bam` (cũ) | 6 | 3,71 % | **11,33 %** | 15,04 % | **7/7** |
| **`hien_tai` (nay)** | 6 | 3,71 % | **4,24 %** | **7,95 %** | **7/7** |

### 4.3. Toàn bộ pool — `scripts/replay_latch_settle.py` (26 phiên ĐO ĐƯỢC / 5 180 frame, `settle=8`)

| | báo | ẩn | chưa xác minh |
|---|---|---|---|
| `--lost-reset 0` (cũ) | 25 | 4,77 % | **29,77 %** (1 542 frame) |
| **`--lost-reset 3` (nay)** | **24** | **4,31 %** | **16,20 %** (839 frame) |

⇒ **−45,6 %** frame "chưa xác minh"; riêng chi phí latch kiểu cũ (`settle=0`) giảm **34,54 % → 20,50 %**.

### 4.4. Kiểm tra

- `./run lint` xanh · `./run test` **2 013 passed** (5 deselected).
- Artifact: `data/eval_gate_rules_2026-11-24_metrics.json`,
  `data/replay_latch_tai_bam_2026-11-24_metrics.json` (có `git_rev`, `git_dirty_code`, `lenh`, `do_luc`,
  `lost_reset_streak`).

## 5. Vấn đề & cách xử lý

1. **Không sửa bằng cách nới ngưỡng.** Bảng 4.2 xác nhận lại kết luận 24-11: mọi luật "giảm số lần báo"
   (`theo_dt` 3/7, `van_toc_lich_su` 6/7, `chi_khi_cham_*` 1–5/7) đều **mất ca đúng**. Thay đổi lần này
   không đụng ngưỡng px nào, chỉ đổi **điều kiện chấm**.
2. **Đánh đổi phải nói rõ:** sau khi vật rời khung rồi vào lại, hệ **tin** vùng mới (không còn dấu
   "chưa xác minh"). Ca 21-11 (bám sang cửa/tường be cùng tông) **không** bị ảnh hưởng vì vật **không**
   rời khung — nhưng ca "vật ra khung rồi một vật khác vào" thì không phân biệt được nếu không có re-ID.
   Đây là ranh giới đã biết, không phải bug mới.
3. **CÒN HỞ (không sửa trong phiên này): trôi dần.** Ảnh `m330` của chính phiên này cho thấy ô bám sang
   **tường** ~130 frame mà cổng **không** báo (đúng kết luận 23-11: cả hai cổng đều mù với trôi dần,
   biên quyết định chỉ 0,937→1,019 = 8 % ngưỡng). Muốn bắt phải có mô hình chuyển động/kiểm mask thật
   ⇒ việc > 4 h ⇒ **plan 3 ý kiến trước** (xem Tầng 2).

## 6. Next steps

- [ ] **Chạy lại `./run demoip`** với vật ra/vào khung ~10 s: kỳ vọng **0 WARN**, `chua_xac_minh_n = 0`,
      không còn ô nét đứt kéo dài. (Đây là bằng chứng live còn thiếu — số hiện có là replay trên CSV.)
- [ ] **Tầng 2 — Cutie / verified re-anchor**: trôi dần sang tường sau khi vật rời khung (§5.3) là thứ
      cần cơ chế mới, không phải ngưỡng. Trước khi tuyên bố "tốt hơn" phải đo **ngưỡng nhiễu mIoU**
      cho clip dùng để chấm.
- [ ] Người thứ 2 dán nhãn 7 ca để được TRÍCH "7/7" trong báo cáo (nợ từ plan 24-11).

## 7. Tài liệu tham khảo

- `docs/plan/24-11-2026-cong-nghi-bao-oan.md` (7/7 ca đúng, 7 luật bị bác, vì sao không nới ngưỡng)
- `docs/task/24-11-2026-cong-nghi-tu-ha-muc.md` (3 trạng thái `ok`/`nghi`/`chua_xac_minh`, settle 8)
- `docs/task/23-11-2026-phan-tich-phien-demoip-1123-bam-nham-remote.md` + `docs/plan/23-11-2026-chon-co-che-tu-tim-lai.md`
  (cổng mù với trôi dần; re-ID nhận lại sai)
- `src/identity_guard.py` · `scripts/eval_gate_rules.py` · `scripts/replay_latch_settle.py`
