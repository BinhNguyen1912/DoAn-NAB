"""
Tái nhận diện đối tượng bằng khuôn mặt (ADR-0003, ticket 09 — buổi 6 + buổi 9 đề cương).

Chức năng: giải quyết đúng lỗi demo 2 người — chọn mặt A, A rời khung thì hệ thống báo MẤT DẤU
và **đóng băng** (không để bộ nhớ SAM 2 bám sang mặt B), rồi khi A quay lại thì **tự bám lại đúng A**
nhờ so khớp embedding khuôn mặt.

Ba phần:
1. **Hàm thuần** (`cosine`, `best_match`, `face_quality_ok`, `pick_face_near`) — test không cần model.
2. **`FaceEmbedder`** — bọc YuNet (phát hiện mặt) + SFace (embedding 128-D) của OpenCV;
   model ONNX nằm trong `models/face/` (gitignored), **không thêm dependency Python**.
3. **`ReIdSession`** — máy trạng thái `tracking → lost → reacquiring → tracking`, bọc engine
   (duck-type `start/process`) + embedder (duck-type `detect`).

Input  : frame BGR uint8, bbox đối tượng; engine SAMURAI; embedder khuôn mặt.
Output : `Step(result, state, reid_score, reacquired)` mỗi frame.
Lưu ý  : lúc `lost` **không gọi `engine.process`** — đó chính là cơ chế chặn \"bám sang B\".
         Chỉ nhận lại khi cosine ≥ ngưỡng (ngưỡng phải hiệu chỉnh trên video thật — xem ADR-0003).
"""
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

DEFAULT_DETECTOR_PATH = "models/face/face_detection_yunet_2023mar.onnx"
DEFAULT_RECOGNIZER_PATH = "models/face/face_recognition_sface_2021dec.onnx"
# Ngưỡng khởi điểm theo tài liệu OpenCV cho FR_COSINE; PHẢI hiệu chỉnh trên video thật.
DEFAULT_REID_THRESHOLD = 0.363
DEFAULT_MIN_FACE_PX = 40          # cạnh nhỏ nhất của ô mặt để tin là đủ nét
DEFAULT_MIN_DETECT_SCORE = 0.8    # điểm phát hiện mặt tối thiểu
DEFAULT_REF_MAX = 8               # số mẫu tham chiếu giữ lại (deque)
DEFAULT_LOST_AFTER_FRAMES = 2     # mask rỗng liên tiếp bao nhiêu frame thì coi là mất dấu

STATE_TRACKING = "tracking"
STATE_LOST = "lost"
STATE_REACQUIRING = "reacquiring"


@dataclass
class FaceHit:
    """Một khuôn mặt phát hiện được: bbox (x1,y1,x2,y2), điểm phát hiện, embedding."""

    bbox: Tuple[int, int, int, int]
    score: float
    embedding: np.ndarray


@dataclass
class LostResult:
    """Kết quả giả khi đang mất dấu — duck-type `TrackingResult` để HUD/metrics dùng được."""

    frame_idx: int = 0
    mask: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=bool))
    bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
    score: float = 0.0
    elapsed_ms: float = 0.0


@dataclass
class Step:
    """Kết quả 1 frame của máy trạng thái."""

    result: object
    state: str
    reid_score: float = -1.0     # cosine tốt nhất frame này (-1 = không có ứng viên nào)
    reacquired: bool = False     # True ở đúng frame vừa nhận lại đối tượng


# ---------- hàm thuần (test không cần model) ----------

def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity giữa 2 vector; vector 0 → 0.0 (không chia cho 0)."""
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def best_match(refs: Sequence[np.ndarray], emb: np.ndarray) -> float:
    """Cosine lớn nhất giữa `emb` và tập tham chiếu; -1.0 nếu tập rỗng.

    Lấy max trên toàn tập là bắt buộc: đo thật cùng 1 người, mặt nhỏ 42x62px, cosine so
    một mốc chỉ 0.20-0.72 — so với 1 mẫu duy nhất sẽ trượt (xem ADR-0003).
    """
    if not refs:
        return -1.0
    return max(cosine(r, emb) for r in refs)


def face_quality_ok(bbox, score, min_face_px=DEFAULT_MIN_FACE_PX,
                    min_score=DEFAULT_MIN_DETECT_SCORE) -> bool:
    """Cổng chất lượng: mặt đủ lớn và đủ tin cậy mới dùng làm mẫu / ứng viên.

    Không có cổng này thì embedding của vùng mờ/nhỏ/nhiễu là vô nghĩa (ADR-0003).
    """
    x1, y1, x2, y2 = [float(v) for v in bbox]
    if min(x2 - x1, y2 - y1) < min_face_px:
        return False
    return float(score) >= float(min_score)


def pick_face_near(hits: Sequence[FaceHit], tracked_bbox) -> Optional[FaceHit]:
    """Chọn khuôn mặt có tâm nằm trong bbox đang bám (mẫu tham chiếu phải là của A, không phải B)."""
    if not hits or not tracked_bbox:
        return None
    x1, y1, x2, y2 = [float(v) for v in tracked_bbox]
    best, best_hit = -1.0, None
    for hit in hits:
        bx1, by1, bx2, by2 = [float(v) for v in hit.bbox]
        cx, cy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
        if x1 <= cx <= x2 and y1 <= cy <= y2 and hit.score > best:
            best, best_hit = hit.score, hit
    return best_hit


# ---------- bọc OpenCV (YuNet + SFace) ----------

class FaceEmbedder:
    """Phát hiện khuôn mặt (YuNet) + trích embedding (SFace). Model tải sẵn trong models/face/."""

    def __init__(self, detector_path=DEFAULT_DETECTOR_PATH, recognizer_path=DEFAULT_RECOGNIZER_PATH,
                 min_face_px=DEFAULT_MIN_FACE_PX, min_score=DEFAULT_MIN_DETECT_SCORE):
        self._min_face_px = min_face_px
        self._min_score = min_score
        # OpenCV 5 in cảnh báo "Targets are not supported by the new graph engine" — vô hại.
        self._detector = cv2.FaceDetectorYN_create(
            detector_path, "", (320, 320), score_threshold=min_score,
            nms_threshold=0.3, top_k=5000,
        )
        self._recognizer = cv2.FaceRecognizerSF_create(recognizer_path, "")

    def detect(self, frame) -> List[FaceHit]:
        """Trả danh sách khuôn mặt đạt cổng chất lượng (sort giảm dần theo điểm)."""
        h, w = frame.shape[:2]
        self._detector.setInputSize((int(w), int(h)))
        _, faces = self._detector.detect(frame)
        if faces is None:
            return []
        hits: List[FaceHit] = []
        for face in faces:
            x, y, fw, fh = [float(v) for v in face[:4]]
            bbox = (int(x), int(y), int(x + fw), int(y + fh))
            score = float(face[-1])
            if not face_quality_ok(bbox, score, self._min_face_px, self._min_score):
                continue
            aligned = self._recognizer.alignCrop(frame, face)
            emb = self._recognizer.feature(aligned).flatten().astype(np.float32)
            hits.append(FaceHit(bbox=bbox, score=score, embedding=emb))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits


# ---------- máy trạng thái ----------

class ReIdSession:
    """tracking → lost (đóng băng) → reacquiring → tracking. Bọc engine + embedder duck-type."""

    def __init__(self, engine, embedder, threshold=DEFAULT_REID_THRESHOLD,
                 lost_after_frames=DEFAULT_LOST_AFTER_FRAMES, ref_max=DEFAULT_REF_MAX,
                 min_face_px=DEFAULT_MIN_FACE_PX, min_score=DEFAULT_MIN_DETECT_SCORE,
                 enabled=True):
        self.engine = engine
        self.embedder = embedder
        self.threshold = float(threshold)
        self.lost_after_frames = int(lost_after_frames)
        self.min_face_px = min_face_px
        self.min_score = min_score
        self.enabled = bool(enabled) and embedder is not None
        self._refs = deque(maxlen=int(ref_max))
        self._state = STATE_TRACKING
        self._lost_streak = 0
        self._frame_idx = 0

    # -- trạng thái --
    @property
    def state(self) -> str:
        return self._state

    @property
    def ref_count(self) -> int:
        return len(self._refs)

    def reset(self) -> None:
        self._refs.clear()
        self._state = STATE_TRACKING
        self._lost_streak = 0
        self._frame_idx = 0

    # -- vòng đời --
    def start(self, frame, bbox) -> object:
        """Bắt đầu bám đối tượng; lưu mẫu tham chiếu khuôn mặt của A ngay nếu có."""
        result = self.engine.start(frame, bbox)
        self._state = STATE_TRACKING
        self._lost_streak = 0
        self._frame_idx = 0
        self._collect_reference(frame, bbox)
        return result

    def step(self, frame) -> Step:
        """Xử lý 1 frame theo trạng thái hiện tại."""
        self._frame_idx += 1

        if self._state == STATE_TRACKING:
            result = self.engine.process(frame)
            if result.mask is None or not result.mask.any():
                self._lost_streak += 1
                if self._lost_streak >= self.lost_after_frames:
                    self._state = STATE_LOST
            else:
                self._lost_streak = 0
                if self.enabled:
                    self._collect_reference(frame, result.bbox)
            return Step(result=result, state=self._state)

        # LOST → chuyển sang tìm kiếm trong chính frame này
        self._state = STATE_REACQUIRING
        if not self.enabled:
            return Step(result=self._lost_result(), state=self._state)

        hits = self.embedder.detect(frame)
        best_score, best_hit = -1.0, None
        for hit in hits:
            score = best_match(self._refs, hit.embedding)
            if score > best_score:
                best_score, best_hit = score, hit

        if best_hit is not None and best_score >= self.threshold:
            result = self.engine.start(frame, best_hit.bbox)
            # engine.start reset bộ đếm frame của nó → giữ frame_idx liên tục cho CSV/biểu đồ
            try:
                result.frame_idx = self._frame_idx
            except AttributeError:  # engine giả/duck-type không cho ghi → bỏ qua
                pass
            self._state = STATE_TRACKING
            self._lost_streak = 0
            self._collect_reference(frame, best_hit.bbox)
            return Step(result=result, state=self._state,
                        reid_score=best_score, reacquired=True)

        return Step(result=self._lost_result(), state=self._state, reid_score=best_score)

    # -- nội bộ --
    def _lost_result(self) -> LostResult:
        return LostResult(frame_idx=self._frame_idx)

    def _collect_reference(self, frame, bbox) -> None:
        """Lưu embedding của khuôn mặt nằm trong bbox đang bám (chỉ khi đạt cổng chất lượng)."""
        if not self.enabled:
            return
        hit = pick_face_near(self.embedder.detect(frame), bbox)
        if hit is not None and face_quality_ok(hit.bbox, hit.score,
                                               self.min_face_px, self.min_score):
            self._refs.append(hit.embedding)
