# Ngày 22-11-2026 — Khôi phục điểm prompt DƯƠNG/ÂM (chữa "bám nhầm vật")

## 🎯 Mục tiêu
- Chữa đúng cái người dùng phàn nàn: **vật trơn cùng màu nền/cửa ⇒ bám nhầm vật**, và **mất dấu thì
  không bám lại được** — trên **máy không có GPU**.
- Trước khi code đã trả lời câu "có model khác không": **KHÔNG có model nhẹ nào chữa được ca này**
  (Cutie/XMem giỏi nhớ vật qua che khuất, không phân biệt hai vùng cùng tông; MobileSAM/EfficientTAM
  chỉ nhanh hơn chứ không khôn hơn), và Cutie trên CPU ước 0,5–2 s/frame ⇒ không live được,
  **chưa đo** nên không hứa. Bằng chứng: đo mask-cos vùng SAI 0,752–0,989 vs ca đúng 0,905 ⇒
  **không tồn tại ngưỡng cos nào tách được** (AGENTS §6) ⇒ cổng cos là hướng đã bị bác.

## 📥 Input
- Phát hiện khi khảo sát code: **backend đã hỗ trợ điểm dương/âm từ đầu** —
  `src/api/schemas.py` (`PointPrompt.label`), `src/api/live.py:start/select`, adapter
  `worker_source._write_bbox` (ghi `points`/`labels` vào `bbox.json`), `src/live_tracking.py:866-871`,
  `src/tracker_engine.py:176-217` (`prompt_kwargs = {"box": bbox}` **+** `points`/`labels` ⇒ SAM 2 nhận
  CẢ ô lẫn điểm).
- Thứ bị mất chỉ là **UI**: `SelectionCanvas` chỉ vẽ ô, `LivePanel` gọi `startLive({mode:'track',bbox})`
  không kèm điểm (commit `460cab6` bỏ phần chấm điểm thủ công khi chuyển sang YOLO-World tự động).
- `web/src/api.ts:selectLive(bbox, points?)` đã có sẵn.

## 🔨 Công việc đã thực hiện
1. `web/src/selection.ts` — thêm toán học THUẦN cho điểm prompt: `PromptPoint` (`label` 0|1),
   `MAX_PROMPT_POINTS = 8`, `MIN_POINT_DIST = 8`, `addPoint` (click đè = THAY, chặn trần, không sửa
   mảng vào), `removeLastPoint`, `countPoints`, `describePoints`, `isClickNotDrag`.
2. `web/src/components/SelectionCanvas.tsx`:
   - **Kéo** = vẽ ô (như cũ). **Click** = điểm DƯƠNG. **Ctrl/Shift/Alt + Click** = điểm ÂM.
   - Sửa luôn lỗi cũ: trước đây **một cú click lạc tạo ô 0×0 ⇒ XOÁ MẤT ô đang chọn**; nay click không
     đụng tới ô.
   - Vẽ điểm: xanh = dương, đỏ = âm, có dấu **+ / −** (người mù màu vẫn phân biệt được).
   - `points`/`onPointsChange` là prop **TUỲ CHỌN** vì đường job offline chưa nhận điểm (ticket #05).
3. `web/src/components/LivePanel.tsx`: state `points`, reset khi mở picker/huỷ (điểm của lần trước
   không dính sang vật mới), gửi `points` kèm khi bấm "Bám đối tượng" (rỗng ⇒ `undefined` để payload
   giống hệt trước), nút **"Xoá điểm cuối (N)"** để hoàn tác từng điểm.
4. `scripts/e2e_web.js` — thêm 4 kiểm tra trình duyệt thật (AGENTS §4 bắt buộc cho thay đổi UI).

## 📤 Output / Kết quả
- `./run lint` xanh · `./run test` **1794 passed** · `./run webtest` **96 passed** (24 → 96 test, thêm
  test cho ngưỡng theo tỉ lệ hiển thị / kẹp điểm / gộp điểm) · `npx tsc --noEmit` sạch · `npm run build` OK.
- **`./run e2e` PASS** với 4 kiểm tra mới:
  - canvas có gợi ý dương/âm;
  - **Ctrl+Click đặt 1 điểm ÂM và KHÔNG xoá ô đang chọn** (`32, 36, 48×48` giữ nguyên);
  - Click thường đặt thêm 1 điểm DƯƠNG (tổng 1 dương + 1 âm);
  - **payload `/api/live/start` có `points`** = `[{"x":136,"y":53,"label":0},{"x":56,"y":95,"label":1}]`
    ⇒ điểm âm đi hết chuỗi UI → API → `bbox.json` → SAM 2;
  - nhấn-nhả **rung 2 px KHÔNG làm đổi ô**; **chuột phải không đặt điểm**; **nút "Xoá điểm cuối" bấm
    thật sự bỏ điểm**; **trang job offline không hiện gợi ý điểm**.
- File thay đổi:
  - `web/src/selection.ts` — hàm thuần cho điểm prompt + `isClickNotDrag`
  - `web/src/selection.test.ts` — 13 test mới
  - `web/src/components/SelectionCanvas.tsx` — click = điểm, vẽ điểm, không xoá ô khi click lạc
  - `web/src/components/LivePanel.tsx` — state/nút xoá/gửi kèm payload
  - `scripts/e2e_web.js` — 4 kiểm tra E2E mới
  - `.scratch/textureless-tracking/issues/05-…` — ticket mới (đường job offline bỏ im lặng điểm)

## 🐞 Vấn đề gặp phải & cách xử lý
- **Không phải viết lại backend**: điểm dương/âm đã chạy hết chuỗi, chỉ thiếu UI ⇒ thay đổi chỉ ở
  `web/` + E2E, **không đụng model/pipeline** ⇒ rủi ro thấp, không cần GPU.
- **Lỗi kiểu `PointPrompt` (api) vs `PromptPoint` (selection)**: api khai `label?: number`, selection
  cần `0|1`. Lấy `PromptPoint` làm nguồn (nó gán được cho `PointPrompt` vì là kiểu con) — `tsc` sạch.
- **`SelectionCanvas` dùng chung 2 trang**: trang job offline **vẫn bỏ im lặng** `points`
  (`routes.select_object` chỉ chuyển bbox) ⇒ để prop tuỳ chọn + **tạo ticket #05**, không để người đọc
  tưởng offline cũng có điểm.
- **Chưa đo được hiệu quả**: phải chấm lại trên đúng ca sai (clip `binh2`, vùng cửa/tường be) bằng số
  "số lần bám sang vùng sai / 1000 frame" — **chưa làm trong phiên này**.

## 🔍 Review độc lập (AGENTS §9.1) — vòng 1 và cách xử lý

Agent `reviewer` độc lập (không phải phiên viết code) đọc đúng các file đã sửa. Kết quả: **1 P0 + 2 P1 +
5 P2 + 6 P3**. Đã sửa **P0, cả 2 P1, cả 5 P2** và 4 P3 trong cùng phiên.

| Mức | Phát hiện | Cách xử lý |
|---|---|---|
| **P0** | `isClickNotDrag` so **px ẢNH** với 4 ⇒ khung 1920 hiển thị 600 CSS px thì chỉ là **1,25 CSS px**; tay rung 2 px ⇒ bị coi là KÉO ⇒ **xoá/thay ô** | thêm `clickToleranceImagePx(rect, canvas)` (ngưỡng **5 CSS px** quy đổi), `pointMergeRadiusImagePx` (**7 CSS px**); vitest kiểm ngưỡng ≈5 CSS px ở mọi cỡ khung 160→3840; **E2E: nhấn-nhả rung 2 px ⇒ chuỗi `bbox-hint` KHÔNG đổi** |
| **P1** | Chuột phải/giữa cũng đặt **điểm dương**; không có `onContextMenu` | `if (event.button !== 0) return` + `onContextMenu` preventDefault + reset `startRef` khi `event.buttons === 0`; **E2E: click chuột phải không đặt điểm** |
| **P1** | `points-hint` hiện cả ở **trang job offline** (nơi `points` bị bỏ im lặng — ticket #05) | gợi ý chỉ render khi có `onPointsChange`; **E2E: trang job không có khối gợi ý** |
| **P2** | `toImagePoint` kẹp tới `canvas.width` (bao gồm biên) nhưng `engine.start` đòi `x < w` ⇒ click ở px cuối **làm chết cả phiên live** | thêm `clampPointInCanvas` (kẹp `w-1/h-1`), dùng khi tạo điểm + vitest |
| **P2** | Chưa có test nào chứng minh route chuyển `points` xuống factory (E2E chỉ **mock** `/start`) | `tests/test_api_live.py::test_diem_duong_am_di_tu_request_toi_nha_may_nguon` (spy nhận `**kwargs`, nếu thiếu thì `except TypeError` làm test xanh vì lý do sai) |
| **P2** | E2E chỉ kiểm "ô không bị XOÁ", không kiểm "ô không bị ĐỔI" | so **chuỗi** `bbox-hint` trước/sau (cả Ctrl+Click và cú rung 2 px) |
| **P2** | E2E chỉ **đếm** nút xoá điểm, không bấm | bấm thật + kiểm số điểm sau khi xoá + đặt lại được |
| **P3** | `PointPrompt.label` tuỳ chọn ⇒ quên `label` thành điểm **dương** trong im lặng; `label=2` lọt Pydantic rồi làm chết phiên | `label: 0\|1` bắt buộc ở `api.ts`; `Field(ge=0, le=1)` + test **422** |
| **P3** | `onStop`/`onStart` không xoá `points` (chưa gây lỗi vì chỉ `onTrack` gửi) | thêm `setPoints([])` |
| **P3** | Gợi ý ghi "Ctrl/Shift" nhưng code nhận cả **Alt/Meta** | sửa chữ thành "Ctrl/Shift/Alt" |
| P3 (không sửa) | Chưa có test E2E nào chạy trên khung ≥1280 (fixture là 160×120) | ghi vào Next steps; các ngưỡng nay đã tính theo tỉ lệ nên hành vi không còn phụ thuộc cỡ khung |
| P3 (không sửa) | `live_tracking` chỉ đọc `bbox.json` **trước** bước VOS đầu ⇒ `POST /api/live/select` trả 200 mà **không đổi gì** | ghi rõ ở Next steps: muốn "thêm điểm khi ĐANG bám" thì phải đọc lại `bbox.json` mỗi vòng |

**Hai lần E2E đỏ trong lúc sửa — cả hai là test của tôi sai, không phải code:** (a) cú "rung 2 px" giờ
đúng ngữ nghĩa là CLICK nên nó **thêm 1 điểm** ⇒ phải dọn điểm đó trong test; (b) "xoá điểm cuối" bỏ
**điểm vừa đặt** (là điểm dương), không phải điểm âm — kỳ vọng cũ của tôi ngược.

## 📌 Việc cần làm tiếp (Next steps)
- [ ] **Đo hiệu quả điểm âm**: chạy clip `binh2` với 0 điểm vs +1 điểm âm ở vùng cửa, chấm `mIoU` bằng
      `./run miou` + `scripts/paired_miou.py` (so cặp trên cùng frame). Không có số này thì **chưa được
      nói "đã chữa được"**.
- [ ] Cổng hình học khi bám lại (gần vị trí Kalman + tỉ lệ diện tích 0,5–2×) — **việc >4 giờ, phải lập
      plan 3 ý kiến (AGENTS §9.2)** trước khi code.
- [ ] Ticket #05: đường job offline hoặc nhận điểm, hoặc từ chối rõ ràng.
- [ ] Cho phép **thêm điểm âm khi ĐANG bám**: endpoint `/api/live/select` đã nhận điểm và trả 200,
      **nhưng** `live_tracking` chỉ đọc `bbox.json` trước bước VOS đầu (dòng ~840) ⇒ hiện **không có
      tác dụng**. Phải đọc lại `bbox.json` mỗi vòng (so `mtime`) trước khi hứa tính năng này.
- [ ] Thêm một E2E trên khung ≥1280 (fixture hiện là 160×120) để khoá hành vi canvas ở cỡ thật.

## 📚 Tài liệu tham khảo
- AGENTS §6: "cổng `track_cos` KHÔNG phân biệt được vùng sai cùng tông" (mask-cos 0,752–0,989 vs 0,905)
- `docs/task/21-11-2026-*` (ca bám sang cửa/tường be, `IdentityWatch` latch + nút "Vẫn đúng")
- `src/tracker_engine.py:176-217` — prompt = `{box} ∪ {points/labels}` (ô KHÔNG bị thay bởi điểm)
- SAM 2: https://github.com/facebookresearch/sam2 (multi-point prompts: positive/negative)
