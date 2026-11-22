/**
 * selection.ts — toán học chọn đối tượng trên canvas. Hàm THUẦN, không đụng DOM.
 *
 * Chức năng: quy đổi toạ độ chuột → pixel gốc của video, dựng hộp từ 2 điểm, kiểm tra hộp dùng được.
 * Input  : toạ độ chuột + kích thước hiển thị (getBoundingClientRect) + kích thước nội tại canvas.
 * Output : Point/Box theo pixel gốc của video.
 * Lưu ý  : đây là chỗ dễ sai nhất của UI — ảnh 1920px hiển thị ở 600px mà quên nhân tỉ lệ thì
 *          ô chọn lệch 3,2 lần và mask bám sai vật. Vì là hàm thuần nên test được bằng vitest,
 *          KHÔNG cần trình duyệt.
 */

export interface Point {
  x: number
  y: number
}

export interface Box {
  x: number
  y: number
  w: number
  h: number
}

/** Cạnh nhỏ nhất (px gốc) để coi là ô chọn thật — nhỏ hơn là click nhầm. */
export const MIN_BOX_SIDE = 4

/**
 * Ngưỡng phân biệt CLICK với KÉO, tính bằng **CSS px** (pixel người dùng thật sự di chuột).
 *
 * VÌ SAO KHÔNG dùng px ảnh: khung 1920 hiển thị ở 600 CSS px thì 4 px ảnh = **1,25 CSS px** — tay
 * người rung 2 px là vượt ngưỡng, thao tác bị hiểu thành KÉO và **xoá mất ô đang chọn** (review độc
 * lập 22-11, P0). Ngưỡng phải ở không gian người dùng, rồi mới quy đổi sang px ảnh.
 */
export const CLICK_TOLERANCE_CSS = 5

/** Bán kính (CSS px) để coi hai điểm prompt là CÙNG một chỗ (click đè = thay điểm cũ). */
export const POINT_MERGE_CSS = 7

/** Kẹp số về [min, max] rồi làm tròn. NaN → biên dưới (an toàn); ±Infinity → kẹp đúng biên. */
export function clampInt(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) return min
  return Math.round(Math.max(min, Math.min(max, value)))
}

export interface DisplayRect {
  left: number
  top: number
  width: number
  height: number
}

export interface CanvasSize {
  width: number
  height: number
}

/**
 * Quy đổi toạ độ chuột (clientX/clientY) → pixel gốc của video.
 *
 * Lưu ý: dùng riêng tỉ lệ X và Y vì CSS có thể làm méo nếu khung không giữ tỉ lệ;
 * rect.width = 0 (chưa layout) được chặn để không chia cho 0.
 */
export function toImagePoint(
  clientX: number,
  clientY: number,
  rect: DisplayRect,
  canvas: CanvasSize,
): Point {
  if (rect.width <= 0 || rect.height <= 0) {
    return { x: 0, y: 0 }
  }
  return {
    x: clampInt(((clientX - rect.left) * canvas.width) / rect.width, 0, canvas.width),
    y: clampInt(((clientY - rect.top) * canvas.height) / rect.height, 0, canvas.height),
  }
}

/** Dựng hộp từ 2 điểm bất kỳ (kéo ngược chiều vẫn đúng). */
export function boxFromPoints(a: Point, b: Point): Box {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    w: Math.abs(a.x - b.x),
    h: Math.abs(a.y - b.y),
  }
}

/**
 * Ngưỡng click/kéo quy đổi sang **px ảnh** theo tỉ lệ hiển thị hiện tại.
 *
 * rect.width <= 0 (chưa layout) ⇒ trả `MIN_BOX_SIDE` thay vì chia cho 0.
 */
export function clickToleranceImagePx(rect: DisplayRect, canvas: CanvasSize): number {
  if (rect.width <= 0) return MIN_BOX_SIDE
  // Sàn là 1 PX ẢNH (không phải `MIN_BOX_SIDE`): ngưỡng phải nhất quán trong KHÔNG GIAN NGƯỜI DÙNG.
  // Lấy sàn 4 px ảnh thì trên khung 160 hiển thị rộng, 4 px ảnh ≈ 15 CSS px — kéo ngắn bị coi là click.
  return Math.max(1, (CLICK_TOLERANCE_CSS * canvas.width) / rect.width)
}

/** Bán kính gộp điểm, quy đổi sang px ảnh (cùng lý do với `clickToleranceImagePx`). */
export function pointMergeRadiusImagePx(rect: DisplayRect, canvas: CanvasSize): number {
  if (rect.width <= 0) return MIN_POINT_DIST
  // Cùng lý do: sàn 1 px ảnh. Với khung 160 hiển thị 600 CSS px, `MIN_POINT_DIST = 8` px ảnh là
  // ~30 CSS px ⇒ hai điểm cách nhau 20 CSS px bị gộp (không thể đặt 2 điểm trên vật nhỏ).
  return Math.max(1, (POINT_MERGE_CSS * canvas.width) / rect.width)
}

/**
 * Kẹp điểm vào TRONG khung (trừ 1 px cuối).
 *
 * `toImagePoint` kẹp tới `canvas.width` (bao gồm cả biên) vì ô chọn dùng `x+w`; nhưng
 * `tracker_engine.start` đòi `0 <= x < w`, nên một điểm ở px cuối cùng làm cả phiên live chết
 * (`ValueError: point … nằm ngoài khung hình`). Điểm phải kẹp chặt hơn ô (review độc lập 22-11, P2).
 */
export function clampPointInCanvas(point: Point, canvas: CanvasSize): Point {
  return {
    x: Math.max(0, Math.min(canvas.width - 1, point.x)),
    y: Math.max(0, Math.min(canvas.height - 1, point.y)),
  }
}

/** Hộp có đủ lớn để chọn đối tượng không. */
export function isUsableBox(box: Box | null): box is Box {
  return box !== null && box.w >= MIN_BOX_SIDE && box.h >= MIN_BOX_SIDE
}

/** Mô tả ngắn để hiện dưới canvas. */
export function describeBox(box: Box | null): string {
  return box ? `${box.x}, ${box.y}, ${box.w}×${box.h}` : 'chưa có'
}

// ─── Điểm prompt dương/âm (khôi phục 22-11) ─────────────────────────────────────────────────────
// VÌ SAO PHẢI CÓ: ca thật 21-11 — vật be trơn, VOS bám sang CỬA/TƯỜNG be cùng tông. Đo mask-cos:
// vùng sai 0,752–0,989 vs ca đúng 0,905 ⇒ KHÔNG tồn tại ngưỡng cos nào tách được (AGENTS §6), nên
// không thể chữa bằng "cổng cos" hay bằng đổi model. Cách rẻ nhất và hiệu quả nhất là cho người dùng
// chỉ ra vùng SAI bằng một cú click âm — SAM 2 loại vùng đó ngay tại bước prompt.
//
// Hợp đồng dữ liệu đã có sẵn ở backend (`PointPrompt.label`: 1 = dương, 0 = âm); phần này chỉ là
// toán học THUẦN cho UI nên test được bằng vitest, không cần trình duyệt.

export interface PromptPoint {
  x: number
  y: number
  /** 1 = điểm dương (thuộc vật), 0 = điểm âm (thuộc nền/vùng bám sai) */
  label: 0 | 1
}

/** Trần số điểm gửi kèm: nhiều hơn thì prompt rối và SAM 2 không còn "ưu tiên" được vùng nào. */
export const MAX_PROMPT_POINTS = 8

/** Hai điểm gần hơn ngần này (px gốc) coi là CÙNG một chỗ ⇒ điểm mới THAY điểm cũ. */
export const MIN_POINT_DIST = 8

/**
 * Thêm một điểm prompt. Điểm mới thay điểm cũ nằm cùng chỗ (bất kể nhãn) để người dùng "sửa lại"
 * bằng cách click đè, và tổng số điểm bị chặn ở `MAX_PROMPT_POINTS` (bỏ điểm CŨ NHẤT).
 *
 * `radius` (px ảnh) phải lấy từ `pointMergeRadiusImagePx` — dùng hằng số px ảnh cố định thì trên
 * khung 1920 "click đè để sửa" là không thể (8 px ảnh chỉ là 2,5 CSS px).
 */
export function addPoint(
  points: PromptPoint[],
  point: PromptPoint,
  radius: number = MIN_POINT_DIST,
): PromptPoint[] {
  const giu = points.filter((p) => Math.hypot(p.x - point.x, p.y - point.y) >= radius)
  const ra = [...giu, point]
  return ra.length > MAX_PROMPT_POINTS ? ra.slice(ra.length - MAX_PROMPT_POINTS) : ra
}

/** Bỏ điểm thêm sau cùng (nút "Xoá điểm" bấm nhiều lần = hoàn tác từng điểm). */
export function removeLastPoint(points: PromptPoint[]): PromptPoint[] {
  return points.slice(0, -1)
}

/** Đếm điểm dương/âm để hiện dưới canvas — người dùng cần biết mình đã đặt gì. */
export function countPoints(points: PromptPoint[]): { duong: number; am: number } {
  return {
    duong: points.filter((p) => p.label === 1).length,
    am: points.filter((p) => p.label === 0).length,
  }
}

/** Mô tả ngắn để hiện dưới canvas. */
export function describePoints(points: PromptPoint[]): string {
  const { duong, am } = countPoints(points)
  if (duong === 0 && am === 0) return 'chưa có điểm nào'
  return `${duong} điểm dương (xanh), ${am} điểm âm (đỏ)`
}

/**
 * Chuột nhấn rồi nhả gần như cùng chỗ = CLICK (đặt điểm), không phải KÉO (vẽ ô).
 *
 * Cần thiết vì nếu coi mọi thao tác chuột là kéo thì một cú click sẽ tạo ô 0×0 ⇒ `isUsableBox` sai
 * và ô đã chọn trước đó bị xoá mất (đúng lỗi cũ: click lạc làm mất ô đang có).
 */
export function isClickNotDrag(
  start: Point,
  end: Point,
  threshold: number = MIN_BOX_SIDE,
): boolean {
  return Math.hypot(end.x - start.x, end.y - start.y) < threshold
}
