# Ngày 21-11-2026 — Nâng cấp giao diện Web: Chấm điểm Positive/Negative trực tiếp trên Canvas

> Log công việc theo quy định `AGENTS.md` mục 2 & 9.1 cho việc nâng cấp Web UI (Hướng 1).

## 🎯 Mục tiêu
- Nâng cấp thành phần giao diện `SelectionCanvas` (React + TypeScript) và `LivePanel` để người dùng có thể tương tác trực quan: vừa kéo ô bao (BBox), vừa click chấm điểm Positive (xanh lá) ở thân vật và điểm Negative (đỏ) ở nền ngoài.
- Kết nối dữ liệu điểm đã chấm xuống backend qua `startLive` và `selectLive` (`POST /api/live/select`).

## 📥 Input
- Tính năng backend Ticket 01 đã hoàn thành (API hỗ trợ `points: PointPrompt[]`).
- File giao diện: `web/src/components/SelectionCanvas.tsx`, `web/src/components/LivePanel.tsx`, `web/src/selection.ts`.

## 🛠️ Công việc đã thực hiện
1. **Mở rộng toán học lựa chọn (`web/src/selection.ts`):**
   - Thêm hàm thuần `isPointInsideBox(point, box)` phục vụ kiểm tra tương quan vị trí.
   - Bổ sung unit test trong `web/src/selection.test.ts`.

2. **Nâng cấp Canvas tương tác (`web/src/components/SelectionCanvas.tsx`):**
   - Hỗ trợ vẽ điểm trực quan:
     - Điểm Positive (`label: 1`): Vòng tròn màu xanh lá sáng (`#00e676`) kèm viền trắng.
     - Điểm Negative (`label: 0`): Vòng tròn màu đỏ tươi (`#ff1744`) kèm viền trắng.
   - Thao tác chuột:
     - Kéo rê chuột (`drag > 6 px`): Vẽ ô chữ nhật mới, tự động reset điểm cũ.
     - Click chuột khi đã có ô: Click trái thêm điểm (+) vật thể; Shift + Click hoặc Click phải (`contextmenu`) thêm điểm (-) nền ngoài.
   - Bộ điều khiển nút bấm dưới Canvas:
     - Nút toggle chuyển chế độ: `(+) Thân vật` / `(-) Nền ngoài` (thuận tiện khi dùng trackpad laptop).
     - Nút `Xoá N điểm`.
     - Dòng hướng dẫn người dùng trực quan.

3. **Tích hợp vào LivePanel (`web/src/components/LivePanel.tsx`):**
   - Lưu trữ state `points: PointPrompt[]`.
   - Khi bấm "Bám đối tượng", tự động gửi `points` cùng `bbox` xuống `startLive`.

## 📊 Output / Kết quả
- Kiểm tra toàn diện hệ thống:
  - `./run webtest`: **81 passed** (100% xanh).
  - `cd web && npm run build`: Vite build thành công không lỗi typecheck.
  - `./run lint`: All checks passed.
  - `./run test`: **1735 passed**, 5 deselected (100% xanh).
- File thay đổi:
  - `web/src/selection.ts`: thêm `isPointInsideBox`
  - `web/src/selection.test.ts`: test kiểm tra điểm
  - `web/src/components/SelectionCanvas.tsx`: tương tác điểm xanh/đỏ và controls
  - `web/src/components/LivePanel.tsx`: tích hợp state `points` và gửi API

## 🔍 Kết quả Review độc lập (theo AGENTS.md §9.1)
- **Standards:** Đạt chuẩn. Code React tuân thủ hooks rule (`useCallback`, `useEffect`), không có memory leak, type safe.
- **Spec:** Người dùng chọn được điểm âm/dương trực tiếp trên Web. Phân loại lỗi: **P0 = 0, P1 = 0**.

## ⏭️ Việc cần làm tiếp (Next steps)
- [ ] Chạy demo live thực tế bằng webcam hoặc IP camera điện thoại trên trình duyệt (`./run api 8010` và mở web).
