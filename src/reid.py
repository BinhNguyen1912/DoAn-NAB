"""
Tái nhận diện đối tượng — khuôn mặt (ADR-0003, ticket 09) VÀ đặc trưng vật thể (ticket 10).

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

from src.appearance import (candidate_boxes, mask_to_bbox, object_signature,
                            prefilter_candidates, signature_quality_ok)

DEFAULT_DETECTOR_PATH = "models/face/face_detection_yunet_2023mar.onnx"
DEFAULT_RECOGNIZER_PATH = "models/face/face_recognition_sface_2021dec.onnx"
# Ngưỡng khởi điểm theo tài liệu OpenCV cho FR_COSINE; PHẢI hiệu chỉnh trên video thật.
DEFAULT_REID_THRESHOLD = 0.363
DEFAULT_MIN_FACE_PX = 40          # cạnh nhỏ nhất của ô mặt để tin là đủ nét
DEFAULT_MIN_DETECT_SCORE = 0.8    # điểm phát hiện mặt tối thiểu
DEFAULT_REF_MAX = 8               # số mẫu tham chiếu giữ lại (deque)
DEFAULT_LOST_AFTER_FRAMES = 2     # mask rỗng liên tiếp bao nhiêu frame thì coi là mất dấu

# Cue tái nhận diện: khuôn mặt / vật thể / cả hai (ticket 10)
CUE_FACE = "face"
CUE_OBJECT = "object"
CUE_BOTH = "both"
DEFAULT_OBJ_THRESHOLD = 0.6       # cosine đặc trưng vật thể tối thiểu (khởi điểm, phải hiệu chỉnh)
DEFAULT_OBJ_REF_MAX = 8           # số mẫu đặc trưng vật thể giữ lại
DEFAULT_OBJ_MIN_SIDE = 24         # cạnh nhỏ nhất của vật để được làm mẫu
DEFAULT_OBJ_MIN_FILL = 0.5        # tỉ lệ mask/ô tối thiểu (chặn vật bị che phần lớn)
DEFAULT_OBJ_TOP_K = 20            # số ứng viên được chấm descriptor đắt mỗi frame lost
# Cổng NCC cho vật ÍT TEXTURE-MÀU (chai đen...): đo thật 27-10, hai vật đen KHÁC nhau cho
# cosine 1,000 (mù) nhưng NCC 0,897, còn cùng vật thì NCC 1,000. Đặt 0.0 = TẮT cổng (mặc định),
# chỉ bật sau khi hiệu chuẩn trên clip thật.
DEFAULT_OBJ_NCC_MIN = 0.0

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
    ncc: float = -1.0            # điểm NCC của ô được chọn (-1 = không dùng NCC / chưa có)


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
                 enabled=True, cue=CUE_FACE, obj_threshold=DEFAULT_OBJ_THRESHOLD,
                 obj_ref_max=DEFAULT_OBJ_REF_MAX, obj_min_side=DEFAULT_OBJ_MIN_SIDE,
                 obj_min_fill=DEFAULT_OBJ_MIN_FILL, obj_top_k=DEFAULT_OBJ_TOP_K,
                 obj_scales=None, obj_ncc_min=DEFAULT_OBJ_NCC_MIN):
        self.engine = engine
        self.embedder = embedder
        self.threshold = float(threshold)
        self.lost_after_frames = int(lost_after_frames)
        self.min_face_px = min_face_px
        self.min_score = min_score
        self.cue = cue if cue in (CUE_FACE, CUE_OBJECT, CUE_BOTH) else CUE_FACE
        self.obj_threshold = float(obj_threshold)
        self.obj_min_side = int(obj_min_side)
        self.obj_min_fill = float(obj_min_fill)
        self.obj_top_k = int(obj_top_k)
        self.obj_ncc_min = float(obj_ncc_min)
        self.obj_scales = tuple(obj_scales) if obj_scales else None
        # Cue mặt cần embedder; cue vật thể thì không → có thể chạy không có model mặt.
        self.face_on = bool(enabled) and embedder is not None and self.cue in (CUE_FACE, CUE_BOTH)
        self.object_on = bool(enabled) and self.cue in (CUE_OBJECT, CUE_BOTH)
        self.enabled = self.face_on or self.object_on
        self._refs = deque(maxlen=int(ref_max))
        self._obj_refs = deque(maxlen=int(obj_ref_max))
        self._obj_template = None      # ảnh cắt của vật ở lần thấy cuối (cho prefilter NCC)
        self._last_obj_size = None     # (rộng, cao) của vật — dùng khi chưa có template
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

    @property
    def object_ref_count(self) -> int:
        """Số mẫu đặc trưng VẬT THỂ đang giữ (tách khỏi `ref_count` của khuôn mặt)."""
        return len(self._obj_refs)

    def reset(self) -> None:
        """Xoá mẫu + về trạng thái ban đầu. Bộ đếm `frame_idx` **KHÔNG** reset.

        Lý do (bug thật 27-10): người dùng bấm `r` để chọn lại giữa video, hoặc engine tự
        `start()` khi nhận lại → trước đây bộ đếm về 0 làm CSV `smooth_metrics.csv` lùi số
        (f11..72 xuất hiện sau f180..186), biểu đồ quỹ đạo sai trục thời gian.
        Số frame phải đơn điệu trong suốt một lần chạy video/phiên.
        """
        self._refs.clear()
        self._obj_refs.clear()
        self._obj_template = None
        self._last_obj_size = None
        self._state = STATE_TRACKING
        self._lost_streak = 0

    # -- vòng đời --
    def start(self, frame, bbox) -> object:
        """Bắt đầu bám đối tượng; lưu mẫu tham chiếu (mặt và/hoặc vật thể) ngay nếu có.

        Không zero bộ đếm `frame_idx` — xem `reset()` (bug lùi số frame trong CSV, 27-10).
        """
        result = self.engine.start(frame, bbox)
        # engine.start() đặt lại bộ đếm của engine về 0 → phải đóng dấu theo bộ đếm của session,
        # nếu không CSV sẽ có frame_idx = 0 giữa video (bug thật 27-10).
        self._stamp_frame_idx(result)
        self._state = STATE_TRACKING
        self._lost_streak = 0
        self._collect_reference(frame, getattr(result, "bbox", bbox), getattr(result, "mask", None))
        return result

    def step(self, frame) -> Step:
        """Xử lý 1 frame theo trạng thái hiện tại."""
        self._frame_idx += 1

        if self._state == STATE_TRACKING:
            result = self.engine.process(frame)
            self._stamp_frame_idx(result)
            if result.mask is None or not result.mask.any():
                self._lost_streak += 1
                if self._lost_streak >= self.lost_after_frames:
                    self._state = STATE_LOST
            else:
                self._lost_streak = 0
                if self.enabled:
                    self._collect_reference(frame, result.bbox, getattr(result, "mask", None))
            return Step(result=result, state=self._state)

        # LOST → chuyển sang tìm kiếm trong chính frame này
        self._state = STATE_REACQUIRING
        if not self.enabled:
            return Step(result=self._lost_result(), state=self._state)

        best_score, best_bbox = -1.0, None
        best_ncc = -1.0

        # Cue 1: khuôn mặt (YuNet + SFace) — cần embedder
        if self.face_on:
            for hit in self.embedder.detect(frame):
                score = best_match(self._refs, hit.embedding)
                if score > best_score:
                    best_score, best_bbox = score, hit.bbox
            if best_bbox is not None and best_score >= self.threshold:
                return self._reacquire(frame, best_bbox, best_score)

        # Cue 2: đặc trưng vật thể — cascade: prefilter NCC rẻ → chấm điểm đắt cho top-K
        if self.object_on and self._obj_refs:
            score, bbox, ncc = self._match_object(frame)
            if bbox is not None:
                # Cổng NCC (mặc định tắt): với vật đen/ít texture, cosine không phân biệt
                # được (đo: 1,000 giữa hai vật đen khác nhau) nên phải có thêm điều kiện hình dạng.
                ncc_ok = self.obj_ncc_min <= 0.0 or ncc >= self.obj_ncc_min
                if score >= self.obj_threshold and ncc_ok:
                    step = self._reacquire(frame, bbox, score)
                    step.ncc = ncc
                    return step
            best_score = max(best_score, score)
            best_ncc = max(best_ncc, ncc)   # ghi cả khi BỊ LOẠI — để hiệu chuẩn ngưỡng

        return Step(result=self._lost_result(), state=self._state,
                    reid_score=best_score, ncc=best_ncc)

    def _reacquire(self, frame, bbox, score: float) -> Step:
        """Nhận lại đối tượng: khởi động bám lại từ ô vừa khớp (dùng chung cho mọi cue)."""
        result = self.engine.start(frame, bbox)
        # engine.start reset bộ đếm frame của nó → giữ frame_idx liên tục cho CSV/biểu đồ
        self._stamp_frame_idx(result)
        self._state = STATE_TRACKING
        self._lost_streak = 0
        self._collect_reference(frame, getattr(result, "bbox", bbox), getattr(result, "mask", None))
        return Step(result=result, state=self._state, reid_score=score, reacquired=True)

    def _match_object(self, frame):
        """Tìm lại vật: lọc rẻ bằng NCC (top-K) rồi chấm `object_signature` cho từng ô.

        Trả về (cosine tốt nhất, ô, ncc của ô được chọn). Ô = None khi không có ứng viên.
        Chi phí mỗi frame LOST: NCC ~vài ms + top-K × ~1,4 ms (đo) thay vì 348 ô = 323 ms.
        """
        scales = self.obj_scales or tuple()
        kwargs = {"top_k": self.obj_top_k, "with_scores": True}
        if scales:
            kwargs["scales"] = scales
        pairs = []
        if self._obj_template is not None:
            pairs = prefilter_candidates(frame, self._obj_template, **kwargs)
        if not pairs and self._last_obj_size:
            # Không có template (hoặc NCC thất bại) → quét lưới quanh kích thước đã biết
            grid_kwargs = {"stride_frac": 0.5}
            if scales:
                grid_kwargs["scales"] = scales
            boxes = candidate_boxes(frame.shape[:2], self._last_obj_size, **grid_kwargs)
            pairs = [(b, -1.0) for b in boxes[: self.obj_top_k]]

        best_score, best_box, best_ncc = -1.0, None, -1.0
        best_choice = -1.0
        height, width = frame.shape[:2]
        target_area = (self._last_obj_size[0] * self._last_obj_size[1]) if self._last_obj_size else None
        for (x1, y1, x2, y2), ncc in pairs:
            mask = np.zeros((height, width), bool)
            mask[max(0, y1):min(y2, height), max(0, x1):min(x2, width)] = True
            sig = object_signature(frame, mask)
            if sig is None:
                continue
            raw = best_match(self._obj_refs, sig)
            # Size prior: cosine một mình ưu tiên ô CẮT BÊN TRONG vật (đo thật: ô 30x30 trong
            # vật 40x40 được 0,930 còn ô đúng cỡ 40x40 chỉ 0,886). Vật không đổi kích thước
            # đột ngột giữa 2 frame, nên cân lại bằng prior mềm sqrt(tỉ lệ diện tích) để CHỌN ô;
            # còn ngưỡng chấp nhận vẫn xét cosine thô (để không phạt vật đến gần/ra xa).
            prior = 1.0
            if target_area:
                area = max(1, (x2 - x1) * (y2 - y1))
                prior = float(np.sqrt(min(area, target_area) / max(area, target_area)))
            choice = raw * prior
            if choice > best_choice:
                best_choice, best_score, best_box, best_ncc = choice, raw, (x1, y1, x2, y2), ncc
        return best_score, best_box, best_ncc

    # -- nội bộ --
    def _stamp_frame_idx(self, result) -> None:
        """Gán frame_idx theo bộ đếm của session (engine.start reset bộ đếm của engine).

        Phải làm ở MỌI frame, không chỉ frame nhận lại — nếu không, sau khi nhận lại CSV
        sẽ lùi số (lỗi thật 22-10: ... 213 → 1) và biểu đồ quỹ đạo bị sai.
        """
        try:
            result.frame_idx = self._frame_idx
        except AttributeError:  # engine giả/duck-type không cho ghi → bỏ qua
            pass

    def _lost_result(self) -> LostResult:
        return LostResult(frame_idx=self._frame_idx)

    def _collect_reference(self, frame, bbox, mask=None) -> None:
        """Lưu mẫu tham chiếu: khuôn mặt nằm trong bbox (nếu bật cue mặt) VÀ/hoặc
        đặc trưng ngoại hình của vùng mask (nếu bật cue vật thể). Cả hai đều qua cổng chất lượng.
        """
        if self.face_on:
            hit = pick_face_near(self.embedder.detect(frame), bbox)
            if hit is not None and face_quality_ok(hit.bbox, hit.score,
                                                   self.min_face_px, self.min_score):
                self._refs.append(hit.embedding)
        if self.object_on and mask is not None:
            obj_box = mask_to_bbox(mask)
            if obj_box is None or not signature_quality_ok(obj_box, mask, self.obj_min_side,
                                                           self.obj_min_fill):
                return
            sig = object_signature(frame, mask)
            if sig is None:
                return
            self._obj_refs.append(sig)
            x1, y1, x2, y2 = obj_box
            self._obj_template = np.array(frame[y1:y2, x1:x2], copy=True)
            self._last_obj_size = (int(x2 - x1), int(y2 - y1))
