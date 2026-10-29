"""
Đặc trưng vật thể dùng cho tái nhận diện khi đối tượng KHÔNG có khuôn mặt (ticket 10).

Chức năng: biến vùng mask của đối tượng (từ SAM 2) thành một vector "dấu vân tay" để so
    khớp cosine giữa các frame, và sinh danh sách ô ứng viên để tìm lại khi mất dấu.
    Vector gồm 2 khối bù trừ nhau (đo tại `docs/research/06` §4.2):
      - covariance 5x5 trên [x, y, B, G, R] — bắt cấu trúc/hoa văn (tách "cùng màu khác
        hoa văn" rất mạnh: cosine 0.061);
      - histogram HSV trong mask — bắt màu (tách "khác màu": 0.382, chỗ covariance yếu).
Input : frame BGR uint8 (H, W, 3) + mask bool/uint8 cùng kích thước frame.
Output: `object_signature` → vector float32 chuẩn hoá L2 (None nếu mask rỗng);
        `candidate_boxes` → list ô (x1, y1, x2, y2) để quét khi mất dấu;
        `mask_to_bbox` → ô bao của mask; `signature_quality_ok` → cổng chất lượng mẫu.
Lưu ý : hàm THUẦN, không dùng model/checkpoint → test chạy ở làn nhanh. KHÔNG import
        `src.reid` (chiều phụ thuộc là reid → appearance) để tránh import vòng.
"""
from typing import Optional, Sequence, Tuple

import cv2
import numpy as np

# Số bin histogram HSV (H x S) — 8x8 đủ mịn cho vùng nhỏ mà vẫn nhẹ (đo ~1 ms/vùng).
DEFAULT_HIST_BINS = 8
# Cổng chất lượng: cạnh nhỏ nhất của ô (px) và tỉ lệ mask/ô tối thiểu (chặn vật bị che).
DEFAULT_MIN_SIDE = 24
DEFAULT_MIN_FILL = 0.5
# Quét lưới khi mất dấu: bước = 0.5 cạnh vật, 3 tỉ lệ quanh kích thước đã biết.
DEFAULT_STRIDE_FRAC = 0.5
DEFAULT_SCALES: Tuple[float, ...] = (0.75, 1.0, 1.5)
# Trọng số 2 khối trong vector ghép (bằng nhau: chưa có số đo biện minh cho lệch).
DEFAULT_WEIGHT_COV = 0.5
DEFAULT_WEIGHT_HIST = 0.5
# Tầng 1 của cascade tìm lại: NCC trên frame thu nhỏ, chỉ giữ top-K cho tầng đắt.
# Chấm descriptor cho cả 348 ô đo được 323 ms → lọc trước để chỉ còn ~20 ô (mục tiêu < 50 ms).
DEFAULT_PREFILTER_TOP_K = 20
DEFAULT_PREFILTER_DOWNSCALE = 4
DEFAULT_PREFILTER_MIN_SCORE = 0.05


def mask_to_bbox(mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """Ô bao (x1, y1, x2, y2) của mask; None nếu mask rỗng.

    Dùng `nonzero` thay `cv2.boundingRect` để không phụ thuộc kiểu dữ liệu mask
    (bool từ SAM 2 hay uint8 0/255) và để test thuần numpy.
    """
    ys, xs = np.nonzero(np.asarray(mask).astype(bool))
    if xs.size == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def signature_quality_ok(bbox, mask, min_side: int = DEFAULT_MIN_SIDE,
                         min_fill: float = DEFAULT_MIN_FILL) -> bool:
    """Cổng chất lượng mẫu/ứng viên: ô đủ lớn VÀ mask chiếm đủ tỉ lệ trong ô.

    `min_fill` chặn trường hợp vật bị che phần lớn: đặc trưng tính trên phần còn thấy
    sẽ mô tả "vật cản" chứ không phải vật (bài học từ ngưỡng mặt ở ADR-0003).
    """
    if bbox is None:
        return False
    x1, y1, x2, y2 = [int(v) for v in bbox]
    if x2 - x1 < min_side or y2 - y1 < min_side:
        return False
    m = np.asarray(mask).astype(bool)
    h, w = m.shape[:2]
    x1c, y1c = max(0, x1), max(0, y1)
    x2c, y2c = min(w, x2), min(h, y2)
    if x2c <= x1c or y2c <= y1c:
        return False
    sub = m[y1c:y2c, x1c:x2c]
    return bool(sub.mean() >= float(min_fill))


def object_signature(frame: np.ndarray, mask: np.ndarray,
                     hist_bins: int = DEFAULT_HIST_BINS,
                     weight_cov: float = DEFAULT_WEIGHT_COV,
                     weight_hist: float = DEFAULT_WEIGHT_HIST) -> Optional[np.ndarray]:
    """Vector đặc trưng (float32, chuẩn hoá L2) của vùng mask trong frame; None nếu rỗng.

    Toạ độ x/y được chuẩn hoá theo ô bao (chia cạnh) nên đặc trưng BẤT BIẾN với vị trí
    và tỉ lệ: cùng vật ở xa camera hay chỗ khác trong khung vẫn cho vector gần nhau.
    """
    bbox = mask_to_bbox(mask)
    if bbox is None:
        return None
    m_full = np.asarray(mask).astype(bool)
    x1, y1, x2, y2 = bbox
    m = m_full[y1:y2, x1:x2]
    if not m.any():
        return None
    roi = frame[y1:y2, x1:x2]

    # --- Khối 1: covariance 5x5 của [x_norm, y_norm, B, G, R] trên các pixel thuộc mask ---
    ys, xs = np.nonzero(m)
    h, w = roi.shape[:2]
    feats = np.stack([
        xs / max(w - 1, 1),
        ys / max(h - 1, 1),
        roi[..., 0][m] / 255.0,
        roi[..., 1][m] / 255.0,
        roi[..., 2][m] / 255.0,
    ]).astype(np.float32)
    cov = np.cov(feats).ravel()
    cov = _l2(cov)

    # --- Khối 2: histogram HSV trong mask ---
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], (m.astype(np.uint8) * 255),
                        [hist_bins, hist_bins], [0, 180, 0, 256]).ravel().astype(np.float32)
    hist = _l2(hist)

    sig = np.concatenate([cov * float(weight_cov), hist * float(weight_hist)])
    return _l2(sig).astype(np.float32)


def candidate_boxes(frame_shape, size: Sequence[int],
                    stride_frac: float = DEFAULT_STRIDE_FRAC,
                    scales: Sequence[float] = DEFAULT_SCALES
                    ) -> list:
    """Danh sách ô ứng viên (x1, y1, x2, y2) phủ khắp frame để tìm lại đối tượng.

    `size` = (rộng, cao) của vật ở lần thấy cuối; quét nhiều tỉ lệ quanh kích thước đó vì
    khi quay lại vật có thể gần/xa camera hơn. Ô luôn nằm trọn trong frame.
    """
    height, width = int(frame_shape[0]), int(frame_shape[1])
    w0, h0 = max(1, int(size[0])), max(1, int(size[1]))
    boxes = []
    for scale in scales:
        w = min(width, max(1, int(round(w0 * float(scale)))))
        h = min(height, max(1, int(round(h0 * float(scale)))))
        step_x = min(w, max(1, int(round(w * float(stride_frac)))))
        step_y = min(h, max(1, int(round(h * float(stride_frac)))))
        xs = list(range(0, max(width - w, 0) + 1, step_x))
        ys = list(range(0, max(height - h, 0) + 1, step_y))
        if xs[-1] != width - w:      # thêm ô sát mép phải để không bỏ sót vật ở biên
            xs.append(max(width - w, 0))
        if ys[-1] != height - h:     # tương tự cho mép dưới
            ys.append(max(height - h, 0))
        boxes.extend((x, y, x + w, y + h) for y in ys for x in xs)
    return boxes


def _l2(v: np.ndarray) -> np.ndarray:
    """Chuẩn hoá L2; vector toàn 0 giữ nguyên (tránh chia 0)."""
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v if n == 0.0 else (v / n).astype(np.float32)


def _response_peaks(resp: np.ndarray, k: int, sep: int) -> list:
    """Lấy tối đa `k` đỉnh NCC cách nhau ít nhất `sep` pixel (NMS thủ công, không cần scipy)."""
    flat = resp.ravel()
    order = np.argsort(flat)[::-1]
    picked = []
    width = resp.shape[1]
    for idx in order[:max(k * 8, 32)]:
        y, x = divmod(int(idx), width)
        if all(abs(x - px) > sep or abs(y - py) > sep for _, px, py in picked):
            picked.append((float(flat[idx]), x, y))
        if len(picked) >= k:
            break
    return picked


def prefilter_candidates(frame: np.ndarray, template: np.ndarray,
                         top_k: int = DEFAULT_PREFILTER_TOP_K,
                         scales: Sequence[float] = DEFAULT_SCALES,
                         downscale: int = DEFAULT_PREFILTER_DOWNSCALE,
                         min_score: float = DEFAULT_PREFILTER_MIN_SCORE,
                         with_scores: bool = False
                         ) -> list:
    """Tầng 1 của cascade tìm lại: ô ứng viên RẺ bằng NCC trên frame thu nhỏ.

    Ý tưởng mượn từ SPLT (skim cascade), TLD (cascade lọc rẻ trước) và KeepTrack (lấy cực
    đại cục bộ của score map): chấm descriptor đắt cho toàn bộ lưới là quá phí (đo 323 ms
    cho 348 ô), nên lọc bằng tương quan mẫu (rất rẻ trên ảnh xám đã thu nhỏ) rồi chỉ giữ
    `top_k` ô cho tầng chấm điểm đắt (`object_signature`).

    Input : frame BGR/gray; template = ảnh cắt của vật ở lần thấy cuối (cùng số kênh frame).
    Output: list ô (x1, y1, x2, y2) sắp giảm dần theo điểm NCC; nếu `with_scores=True`
            trả list (ô, điểm NCC) — điểm này dùng được cho vật ít texture-màu (vật đen)
            vì nó dựa trên **hình dạng/hoa văn** chứ không dựa trên histogram màu.
            List rỗng nếu template rỗng hoặc lớn hơn frame ở mọi tỉ lệ.
    """
    if template is None or getattr(template, "size", 0) == 0:
        return []
    height, width = frame.shape[:2]
    step = max(1, int(downscale))
    # Frame nhỏ (vd fixture 96x96 trong test): thu nhỏ 4x thì còn <60 px → NCC vô nghĩa
    # (đo: ô đúng chỉ 0,63 thay vì ~1,0). Giảm mức thu nhỏ để giữ độ phân giải tương đối.
    if min(height, width) < 200:
        step = max(1, step // 2)
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    tpl_gray = template if template.ndim == 2 else cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (max(1, width // step), max(1, height // step)),
                       interpolation=cv2.INTER_AREA)
    tpl_h, tpl_w = tpl_gray.shape[:2]
    scales = tuple(scales) or (1.0,)
    # Mỗi tỉ lệ một suất riêng: điểm NCC giữa các tỉ lệ KHÔNG so sánh được với nhau (template đã
    # bị resize), nên nếu gộp rồi NMS xuyên tỉ lệ thì ứng viên đúng cỡ có thể bị ứng viên tỉ lệ
    # khác chồng lên và bị loại oan (đã gặp thật: ô đúng 40x40 bị ô 30x30 loại, lệch 14 px).
    per_scale_k = max(1, int(np.ceil(int(top_k) / len(scales))))
    found = []          # (điểm NCC, ô ở toạ độ gốc)
    for scale in scales:
        bw = int(round(tpl_w * float(scale)))
        bh = int(round(tpl_h * float(scale)))
        sw, sh = max(1, bw // step), max(1, bh // step)
        if sw < 2 or sh < 2 or sw > small.shape[1] or sh > small.shape[0]:
            continue
        tmpl_small = cv2.resize(tpl_gray, (sw, sh), interpolation=cv2.INTER_AREA)
        resp = cv2.matchTemplate(small, tmpl_small, cv2.TM_CCOEFF_NORMED)
        for score, x, y in _response_peaks(resp, per_scale_k, max(2, sw // 2)):
            if score < float(min_score):
                continue
            found.append((score, (x * step, y * step, x * step + bw, y * step + bh)))
    found.sort(key=lambda t: -t[0])
    top = found[: int(top_k)]
    if with_scores:
        return [(box, score) for score, box in top]
    return [box for _score, box in top]
