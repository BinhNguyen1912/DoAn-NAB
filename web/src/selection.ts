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

/** Hộp có đủ lớn để chọn đối tượng không. */
export function isUsableBox(box: Box | null): box is Box {
  return box !== null && box.w >= MIN_BOX_SIDE && box.h >= MIN_BOX_SIDE
}

/** Mô tả ngắn để hiện dưới canvas. */
export function describeBox(box: Box | null): string {
  return box ? `${box.x}, ${box.y}, ${box.w}×${box.h}` : 'chưa có'
}
