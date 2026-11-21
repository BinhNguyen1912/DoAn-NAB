"""Cảnh báo lúc CHỌN Ô: ô chọn có phủ KHUÔN MẶT không.

Vì sao có file này (đo 21-11-2026, hai phiên demo webcam liên tiếp): người dùng chọn một ô mà
**chính nó là khuôn mặt** rồi thắc mắc "hệ bám nhầm chỗ khác". Kiểm bằng YuNet trên frame đầu của
`data/demoip_1121-075227_web.mp4`:

    mặt YuNet  = (256, 208, 197, 228)   (x, y, w, h)
    ô đã chọn  = (258, 241, 212, 201)
    IoU        = 0,768   ⇒ CÙNG một vùng ⇒ hệ đang bám ĐÚNG thứ được chọn, chỉ là thứ đó là mặt.

Hệ quả kéo theo (phiên trước, `data/demoip_1120-224057`): đặc trưng của "vật" chọn cạnh mặt có tông
da ⇒ khi vật rời khung, re-ID khớp **khuôn mặt** với cosine 0,974 / ncc 0,545 và "nhận lại" sai.
Không cổng nào chữa được chuyện đó; chữa ở chỗ **chọn ô**.

Nguyên tắc: chỉ CẢNH BÁO, KHÔNG tự sửa ô của người dùng (bám mặt là hợp lệ nếu ai đó muốn bám mặt).
Chi phí: YuNet 28,9 ms một lần cho mỗi lần chọn (đo trên CPU máy này, 640×480) — không nằm trong vòng
lặp suy luận.
"""
from __future__ import annotations

import os
from typing import Sequence

# Ngưỡng "ô chọn phủ mặt": IoU với một khuôn mặt. Đo ca thật 0,768 (ô chọn lệch lên trên so với mặt).
# Đặt 0,35 để bắt cả ca ô chọn **to hơn mặt** (ô bao quanh cả người: IoU thấp nhưng mặt nằm trọn bên
# trong ⇒ vẫn nên cảnh báo). 0,35 cũng không bắt oan ô chọn một bàn tay/đồ vật đặt cạnh mặt.
NGUONG_IOU = 0.35


def iou_xywh(a: Sequence[float], b: Sequence[float]) -> float:
    """IoU hai ô `(x, y, w, h)`. Trả 0,0 khi một ô suy biến (rộng/cao ≤ 0)."""
    ax, ay, aw, ah = (float(v) for v in a[:4])
    bx, by, bw, bh = (float(v) for v in b[:4])
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return 0.0
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    return inter / (aw * ah + bw * bh - inter)


def mat_bi_phu(bbox_xywh: Sequence[float], faces: Sequence[Sequence[float]],
               nguong: float = NGUONG_IOU) -> tuple[tuple, float] | None:
    """Mặt nào (nếu có) bị ô chọn phủ. Hàm THUẦN — `faces` là `(x, y, w, h)`.

    Trả `(mặt, iou)` của mặt có IoU cao nhất vượt `nguong`, hoặc `None`.
    """
    tot_nhat: tuple[tuple, float] | None = None
    for face in faces or ():
        iou = iou_xywh(bbox_xywh, face)
        if iou >= nguong and (tot_nhat is None or iou > tot_nhat[1]):
            tot_nhat = (tuple(float(v) for v in face[:4]), iou)
    return tot_nhat


def _duong_detector() -> str:
    return os.path.join("models", "face", "face_detection_yunet_2023mar.onnx")


class BoDoMat:
    """Bọc YuNet để đếm mặt trong một frame. LƯỜI + KHÔNG BAO GIỜ NÉM.

    Vì sao không ném: đây là cảnh báo phụ trong đường demo — thiếu model/thiếu opencv phải làm cảnh
    báo im lặng, KHÔNG được làm chết phiên đang chạy (fail-open).
    """

    def __init__(self, model=None, min_score: float = 0.6):
        self._model = model or _duong_detector()
        self._min_score = float(min_score)
        self._det = None
        self._hong = False

    def detect(self, frame) -> list[tuple]:
        """`[(x, y, w, h), …]` trong hệ pixel của `frame`; rỗng khi không detect được."""
        if self._hong or frame is None:
            return []
        try:
            if self._det is None:
                import cv2

                if not os.path.isfile(self._model):
                    self._hong = True          # thiếu model ⇒ im lặng từ đây
                    return []
                self._det = cv2.FaceDetectorYN_create(self._model, "", (320, 320),
                                                      score_threshold=self._min_score,
                                                      nms_threshold=0.3, top_k=5000)
            h, w = frame.shape[:2]
            self._det.setInputSize((int(w), int(h)))
            _, faces = self._det.detect(frame)
            if faces is None:
                return []
            return [(float(f[0]), float(f[1]), float(f[2]), float(f[3])) for f in faces]
        except Exception:                      # fail-open: cảnh báo không được giết phiên
            self._hong = True
            return []


def canh_bao_chon_o(frame, bbox_xywh, bo_do: "BoDoMat | None" = None) -> str | None:
    """Câu cảnh báo (ASCII, in ra console) nếu ô chọn phủ khuôn mặt; `None` nếu không.

    ASCII vì console Windows (cp1258/cp437) làm hỏng dấu tiếng Việt — cùng quy ước HUD của repo.
    """
    if bbox_xywh is None:
        return None
    bo = bo_do or BoDoMat()
    mat = mat_bi_phu(bbox_xywh, bo.detect(frame))
    if mat is None:
        return None
    face, iou = mat
    return (f"[CANH BAO] o ban chon PHU KHUON MAT (IoU {iou:.2f} voi mat {tuple(int(v) for v in face)}).\n"
            "            Neu ban muon bam VAT: bam 'r' roi chon lai o CHI quanh vat (dung de mat trong o).\n"
            "            Ly do do duoc (21-11): vat cung tong mau da canh mat -> re-ID nhan lai vao MAT "
            "(cosine 0.974 / ncc 0.545) - khong nguong nao chan duoc.")
