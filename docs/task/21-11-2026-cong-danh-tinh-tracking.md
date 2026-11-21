# Ngày 21-11-2026 — Cổng danh tính tracking (PR-1: NEO + cos, LOG-ONLY)

## 🎯 Mục tiêu
- Trả lời câu hỏi "hệ có biết mình đang bám SAI vật không?" bằng **số đo**, không bằng cảm tính.
- Bối cảnh: phiên `demoip_1121-103854` bám sang **máy lạnh trắng** ~9 s (f110–f173) mà `score` còn **tăng**
  (5,85–6,02); hai cổng đã có (nhảy tâm, re-ID) **mù** với kiểu sai này — nhảy tâm cần 200/451 px trong khi
  cú nhảy thật 114 px, và **đường web không có re-ID**.
- Ship **PR-1 LOG-ONLY**: đo `cos(mask đang bám, NEO danh tính)` mỗi frame VOS, ghi ra CSV + `status.json`,
  **không hành động gì**. Cổng thật (PR-2) chỉ mở khi có số.

## 📥 Input
- Plan theo AGENTS §9.2 (3 ý kiến độc lập + phản biện chéo): `docs/plan/21-11-2026-cong-danh-tinh-tracking.md`.
- Clip có GT sẵn: `data/binh1.mp4` (ô chai `300,275,150,410`), `data/binh2.mp4` (`330,330,150,360`).
- Máy: CPU only (Iris Xe), `image_size 192`, checkpoint SAM 2.1 tiny. Không có GPU rời (AGENTS §6).
- Artifact trước đó về ngưỡng re-ID: `docs/task/21-11-2026-veto-nhan-lai-vao-mat-va-nguong-reid.md`.

## 🔨 Công việc đã thực hiện

### 1. Plan 3 ý kiến (bắt buộc vì > 4 h)
- 3 agent độc lập (chất lượng & số đo / sản phẩm & bằng chứng / độ bền & hiệu năng) → vòng 2 phản biện chéo
  → chốt: **3/3 bác** hướng "re-prompt SAM 2 bằng bbox cũ" (không có bằng chứng nó sửa được), chọn
  **NEO danh tính + cos** làm kênh phát hiện, và **chỉ LOG** ở PR-1.

### 2. Code PR-1 (commits `9e2acfa`, `214e74b`, `9e00d9d`)
- `src/track_identity.py` (**mới**): `NeoDanhTinh` — lấy **3–5 mẫu ĐẦU** từ **MASK** (không phải bbox), qua
  cổng chất lượng `signature_quality_ok` **+ cắt dải mép khung** như `ReIdSession._collect_reference`;
  `cos = MAX(dot(neo, mask hiện tại))`; **fail-open 2 lớp**; `None` = **CHƯA ĐO**, không phải 0.
  Tự tính max-dot tại chỗ để **không** tạo import vòng `reid ⇄ track_identity`.
- `src/reid.py`: `Step.track_cos` + `Step.neo`; chấm ở nhánh TRACKING; `neo.xoa()` trong `reset()`.
- `src/live_tracking.py`: `LiveTrackStats` + `bbox_w/bbox_h/mask_area/track_cos/track_cos_n`;
  `_cap_nhat_danh_tinh()` gọi ở **CẢ HAI** đường VOS (`_after_vos` inline và `_store_vos` có luồng);
  `_VosWorker` truyền **frame màu** xuống callback (trước đó chỉ `gray` ⇒ `object_signature` lỗi im lặng).
- `src/metrics_logger.py`: CSV +4 cột ở **cuối** (`bbox_w`, `bbox_h`, `mask_area`, `track_cos`) — CSV cũ vẫn
  đọc được bằng `csv.DictReader`.
- `src/drift_samples.py`: CSV **đường LIVE** +4 cột (xem mục review P1-1 — thiếu nó thì tiêu chí không đo được).

### 3. Hai bug tự bắt trong phiên (nhờ ĐO, không nhờ đọc code)
1. Neo đặt inline trong `_after_vos` ⇒ `--vos-every 3` đi qua `_store_vos` ⇒ `track_cos = None, n = 0`
   **6/6 lần chạy**. Tách `_cap_nhat_danh_tinh()` gọi ở cả hai đường.
2. `_store_vos` chỉ nhận `gray` ⇒ `object_signature` cần BGR→HSV ⇒ lỗi im lặng, `None` vĩnh viễn.

### 4. Review độc lập (AGENTS §9.1) — agent `reviewer`, 2 vòng
- **Vòng 1**: `NOT mergeable as-is` — **3 P1 + 8 P2 + 5 P3**.
- **P1-1**: đường **live** không có CSV nào mang `track_cos` (`drift_samples.csv` thiếu cột, `_worker_telemetry`
  lọc mất khoá) ⇒ tiêu chí "`track_cos` trong CSV live" mà plan tự đặt **không thể đạt**; mọi số công bố
  trước đó là **đường CLI**.
- **P1-2**: 6/6 `run_info` ghi `git_dirty_code = true` trong khi plan lại khẳng định `false`.
- **P1-3**: log ngày (file này) **không tồn tại** dù plan trỏ tới.
- **P2 đáng chú ý**: frame `start()` bị **chấm 2 lần** (neo #1 ≡ #2 ⇒ "đủ neo" sau 1 frame); neo **không**
  lọc dải mép khung; `MIN_ANCHORS = 2` nhưng docstring/plan nói 3; neo lấy `object_signature` **2 lần/frame**
  trên đường CLI (~1,5 ms) chứ không phải "tái dùng"; **4/108 mẫu 1,0 cấu trúc** (frame so với chính nó);
  3 lần chạy **bit-identical** ⇒ "gộp n = 324" không tăng thông tin; `p05` là **quy ước phân vị thứ 4**
  trong repo; `_smooth` thay mask bằng mask **giữ** ⇒ `track_cos` mù đúng lúc model mất vật.
- **Đã sửa toàn bộ P1 + 8 P2** (commit `9e00d9d`), thêm **test giết được mutant**:
  - bỏ call `_cap_nhat_danh_tinh` ở `_store_vos` ⇒ test `vos_every=3` **đỏ** (đúng bug `214e74b`);
  - test 2 neo ⇒ `cos is None` (khoá bất biến 3 neo);
  - test dải rác sát mép **không** được làm neo;
  - test `drift_samples.csv` có 4 cột, `None` ⇒ ô **trống** (không phải 0).
- Xoá 1 assert **chết** trong `tests/test_metrics_logger.py` (`... or True`).

### 5. Đo lại trên **cây SẠCH** (`git_dirty_code = false` 7/7 lần chạy)
- CLI: 3 lần × 2 clip, ô chai đúng (lần đầu tôi quên `--bbox` ⇒ ô mặc định giữa frame 78×84 ⇒ số vô nghĩa;
  phát hiện bằng cách so `bbox_w/bbox_h` giữa CSV cũ và mới).
- LIVE: `scripts/measure_live_relay.py --source data/binh1.mp4 --bbox 300,275,150,410 --vos-every 3 --seconds 45`
  (worker thật qua API, không phải CLI).

## 📤 Output / Kết quả

### Số đo (artifact `data/track_cos_2026-11-21_metrics.json`, `git_dirty_code = false`)
| Đường | clip / cửa sổ | n | median | p05 | **min** | < 0,75 |
|---|---|---|---|---|---|---|
| CLI | `binh1` (ô chai) | 106 | 0,9604 | 0,9126 | **0,8588** | **0** |
| CLI | `binh2` | 106 | 0,9267 | 0,8141 | **0,8080** | **0** |
| **LIVE** | vật trong khung `0:110` | 26 | 0,9531 | `None` (n<30) | **0,8901** | **0** |
| LIVE | sau khi vật rời khung | 196 | 0,9591 | — | 0,4637 | 13 |

- **98,2 %** frame live có `mask_area > 0` có `track_cos` (222/226) ⇒ đạt tiêu chí ≥95 % đã đặt trước.
- 3 lần chạy CLI **bit-identical** về `track_cos` (latency khác nhau 107/110 dòng) ⇒ mask/ngoại hình tái lập
  trên clip cố định (**không** suy ra "SAM 2 tất định" nói chung — AGENTS §6 vẫn đúng cho ô bao cuối).
- **θ = 0,75 chặn oan 0/238 mẫu** khi vật trong khung.
- 13 mẫu < 0,75 (live, sau khi vật rời khung) đều có `mask_area` **22–3 767 px** ⇒ **mask sụp**, không phải
  "bám sang vật khác".

### Kết luận trung thực (quan trọng cho báo cáo)
- θ ≈ 0,75 **chứng minh được** là bắt trạng thái **mask sụp**.
- **CHƯA chứng minh** θ bắt được ca "bám sang máy lạnh": các số 0,510–0,719 của ca đó là **BOX-cos**
  (mask = cả hình chữ nhật, lẫn nền) — **không so được** với phân bố mask-cos. Đã **rút lại** câu này trong plan.
- **Chưa mở cổng PR-2**: khung cửa cùng tông cho cos **0,912** (nằm trong dải ca đúng) ⇒ kênh ngoại hình
  **không** phân biệt được cùng tông. Cần 1 clip quay đúng cảnh bằng `scripts/record_raw.py` để chấm mask-cos
  của vùng sai.

### File thay đổi
- `src/track_identity.py` — **mới**: NEO + cos, fail-open, lọc dải mép, `MIN_ANCHORS = 3`
- `src/reid.py` — `Step.track_cos`/`Step.neo`, chấm TRƯỚC khi nạp neo
- `src/live_tracking.py` — 5 khoá `LiveTrackStats`, `_cap_nhat_danh_tinh` ở cả 2 đường VOS, chống chấm 2 lần
- `src/metrics_logger.py`, `src/drift_samples.py` — 4 cột danh tính (CSV CLI + CSV live)
- `src/live_pipeline.py`, `src/smooth_display.py` — truyền `track_cos`
- `tests/test_track_identity.py` (+12), `tests/test_live_tracking.py` (+2, giết mutant), `tests/test_drift_samples.py` (+1), `tests/test_metrics_logger.py` (xoá assert chết)
- `docs/plan/21-11-2026-cong-danh-tinh-tracking.md` — đính chính số + rút lại claim AC
- `data/track_cos_2026-11-21_metrics.json`, `data/sach_*`, `data/drift_samples_binh1_2026-11-21_113612.csv`, `data/live_danhtinh_sach_2026-11-21_metrics.json`

### Kiểm
- `./run lint` xanh · `./run test` **1688 passed**, 5 deselected (117 s).
- Review độc lập: **P0 = 0**, 3 P1 → đã sửa hết, 8 P2 → đã sửa, còn 2 P2/P3 ghi ở Next steps.

## 🐞 Vấn đề gặp phải & cách xử lý
- **Neo không chạy ở đường có luồng** (`--vos-every 3`): đo ra `track_cos = None` 6/6 lần. Sửa: tách hàm,
  gọi ở **cả** `_after_vos` và `_store_vos`, cộng test giết mutant.
- **`object_signature` lỗi im lặng** trên `gray` ⇒ `None` vĩnh viễn. Sửa: truyền frame màu xuống callback.
- **Lần đo đầu vô nghĩa vì quên `--bbox`** (ô mặc định 78×84 giữa frame): phát hiện bằng cách so `bbox_w/h`
  giữa CSV cũ/mới, không phải bằng cách tin vào con số median.
- **Lệch hệ thống do quy ước mask**: nghi neo ký bằng mask đã cắt mép trong khi `cos` ký bằng mask đầy đủ ⇒
  đo 2 biến thể, số **giống hệt** ⇒ bác giả thuyết, nguyên nhân thật là `--bbox` thiếu. (Ghi lại vì đã
  suýt "sửa" một thứ không hỏng.)
- **Xoá nhầm artifact đã commit** (`rm -f data/sach_*` quét cả `data/sach_chai_binh1_1vong_metrics.json`) ⇒
  `git checkout --` phục hồi; đã kiểm `git status` sạch trước khi commit.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **PR-2 (cổng hành động)** — chỉ sau khi có clip quay đúng cảnh: `python scripts/record_raw.py --source 0 --seconds 40 --out data/remote_bg.mp4` (giơ remote → hạ → giơ lại cạnh **máy lạnh** → xoay 90° → lại gần/xa).
- [ ] **P2 còn nợ**: `object_signature` tính **2 lần/frame** trên đường CLI (`_collect_reference` + neo) — tái dùng `sig` để tiết kiệm ~1,5 ms; đo A/B wall-clock 3 lần chèn kẽ (CSV `latency_ms` = thời gian engine, **không** thấy chi phí này).
- [ ] **P2 còn nợ**: `post_ms` bao gồm chi phí neo ở đường có luồng nhưng **không** ở đường inline ⇒ `mask_age_total_ms` giữa 2 đường không so trực tiếp được; cần tách `identity_ms` riêng vào `status.json`.
- [ ] **P3**: `track_cos` gắn frame VOS còn `bbox` trong `status.json` là frame hiển thị ⇒ lệch thế hệ; thêm `vos_frame_idx` (đã defer ở V2 của plan).
- [ ] **P3**: `_auto_recover`/`_abandon_reacquire`/`_reacquire` trả `Step` **không** có `track_cos` — đúng những frame cần hiệu chuẩn θ nhất.
- [ ] `neo_n`/`track_cos_none_n` vào `status.json` để phân biệt "chưa đủ neo" với "mask rỗng mọi lần".

## 📚 Tài liệu tham khảo
- `docs/plan/21-11-2026-cong-danh-tinh-tracking.md` — plan 3 ý kiến + phản biện + đính chính số.
- `docs/task/21-11-2026-veto-nhan-lai-vao-mat-va-nguong-reid.md` — ngưỡng re-ID, veto khuôn mặt.
- `docs/demo-clip-va-o-chon.md` — ô chọn đúng cho `binh1`/`binh2`.
- AGENTS §6 (ngưỡng nhiễu, `git_dirty_code`, `p05` một cửa), §9.1 (review độc lập), §9.2 (plan 3 ý kiến).
