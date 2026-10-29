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
DEFAULT_OBJ_NCC_MIN = 0.0         # TAT: đo thật 29-10 cho thấy NCC rất mỏng manh (mẫu lệch 2px → 0,099)
# (ghi chú cũ, giữ để hiểu lịch sử) — đo thật 29-10: ca ĐÚNG (binh1) ncc 0,858;
#   ca ĐÚNG (binh1, vật quay lại đúng) ncc = 0,858; fixture đúng = 1,00
#   4 lần "nhận lại" SAI của người dùng (bám vào bóng đèn thay vì cái ly) ncc = 0,48–0,62
#   → cosine một mình không đủ (li 0,78–0,99 mà vẫn sai), phải có cổng NCC.
DEFAULT_SEARCH_GROW_FRAMES = 12    # số frame lost tìm trong vùng hẹp quanh vị trí cũ trước khi mở rộng
DEFAULT_SEARCH_GROW_STEP = 0.5     # bán kính tìm = max(w,h) * (1 + 0.5 * số frame lost)
DEFAULT_LOST_SCORE_THRESHOLD = 0.0   # score ≤ 0 → coi như KHÔNG thấy vật (mask hay bị "tưởng tượng")
DEFAULT_REACQUIRE_CONFIRM = 2         # số frame liên tiếp phải khớp cùng một chỗ mới nhận lại
DEFAULT_VERIFY_FRAMES = 2             # số frame kiểm chứng sau khi bám lại (chống bám nhầm nền)

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


def _iou(a, b) -> float:
    """IoU 2 ô (x1, y1, x2, y2) — dùng để kiểm tra ứng viên có "cùng một chỗ" không."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _ncc(template, crop, size: int = 32) -> float:
    """Tương quan mẫu (NCC) giữa 2 ảnh BGR bất kỳ kích thước — về cùng size rồi tính.

    Dùng trong bước KIỂM CHỨNG sau khi bám lại: cosine đặc trưng có thể "đúng giả" với vật
    ít texture (đo 29-10: bám vào bóng đèn vẫn 0,78–0,99) nên phải kiểm thêm mẫu ảnh.
    """
    if template is None or crop is None or getattr(template, "size", 0) == 0 or getattr(crop, "size", 0) == 0:
        return 0.0
    a = cv2.resize(template, (size, size))
    b = cv2.resize(crop, (size, size))
    if a.ndim == 3:
        a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    if b.ndim == 3:
        b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    a = a.astype(np.float32) - float(np.mean(a))
    b = b.astype(np.float32) - float(np.mean(b))
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float((a * b).sum() / (na * nb)) if na > 0 and nb > 0 else 0.0


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
                 obj_scales=None, obj_ncc_min=DEFAULT_OBJ_NCC_MIN,
                 lost_score_threshold=DEFAULT_LOST_SCORE_THRESHOLD,
                 reacquire_confirm=DEFAULT_REACQUIRE_CONFIRM,
                 verify_frames=DEFAULT_VERIFY_FRAMES,
                 search_grow_frames=DEFAULT_SEARCH_GROW_FRAMES,
                 search_grow_step=DEFAULT_SEARCH_GROW_STEP):
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
        self.lost_score_threshold = float(lost_score_threshold)
        self.reacquire_confirm = max(1, int(reacquire_confirm))
        self.verify_frames = max(0, int(verify_frames))
        self.search_grow_frames = max(1, int(search_grow_frames))
        self.search_grow_step = float(search_grow_step)
        self._confirm_count = 0
        self._confirm_box = None
        self._verify_left = 0
        self._lost_age = 0          # đã mất dấu bao nhiêu frame (để mở rộng vùng tìm dần)
        self._last_center = None    # tâm vật ở lần thấy cuối (mốc để giới hạn vùng tìm)
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
        self._confirm_count = 0
        self._confirm_box = None
        self._verify_left = 0
        self._lost_age = 0
        self._last_center = None

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
            # "Còn thấy vật" = mask không rỗng **VÀ** score > ngưỡng. SAM 2 hay "tưởng tượng" ra
            # mask khi vật đã rời khung (đo thật 27-10: mask 782 px nhưng score = -4,98) — nếu chỉ
            # dựa vào mask rỗng thì hệ thống không bao giờ vào LOST và sẽ bám rác mãi mãi.
            seen = (result.mask is not None and result.mask.any()
                    and float(result.score) > self.lost_score_threshold)
            if not seen:
                self._lost_streak += 1
                if self._lost_streak >= self.lost_after_frames:
                    self._state = STATE_LOST
                    self._verify_left = 0
                    self._confirm_count = 0
            else:
                self._lost_streak = 0
                if self._verify_left > 0:
                    # Đang kiểm chứng một lần "nhận lại" → nếu không giống vật thì bỏ ngay,
                    # nếu không sẽ kẹt vĩnh viễn trên vùng bám nhầm (bug thật 27-10).
                    if self._verify_ok(frame, result):
                        self._verify_left -= 1
                    else:
                        return self._abandon_reacquire()
                if self.enabled and self._verify_left == 0:
                    self._collect_reference(frame, result.bbox, getattr(result, "mask", None))
            return Step(result=result, state=self._state)

        # LOST → chuyển sang tìm kiếm trong chính frame này
        self._state = STATE_REACQUIRING
        self._lost_age += 1
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
                if self._confirm(best_bbox):
                    return self._reacquire(frame, best_bbox, best_score)

        # Cue 2: đặc trưng vật thể — cascade: prefilter NCC rẻ → chấm điểm đắt cho top-K
        if self.object_on and self._obj_refs:
            score, bbox, ncc = self._match_object(frame)
            if bbox is not None:
                # Cổng NCC (mặc định tắt): với vật đen/ít texture, cosine không phân biệt
                # được (đo: 1,000 giữa hai vật đen khác nhau) nên phải có thêm điều kiện hình dạng.
                ncc_ok = self.obj_ncc_min <= 0.0 or ncc >= self.obj_ncc_min
                if score >= self.obj_threshold and ncc_ok:
                    if self._confirm(bbox):
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
        self._confirm_count = 0
        self._confirm_box = None
        self._verify_left = self.verify_frames      # chưa tin ngay: kiểm chứng mấy frame đầu
        self._lost_age = 0
        if self._verify_left == 0:
            self._collect_reference(frame, getattr(result, "bbox", bbox), getattr(result, "mask", None))
        return Step(result=result, state=self._state, reid_score=score, reacquired=True)

    def _confirm(self, bbox) -> bool:
        """Chỉ nhận lại khi ứng viên khớp Ở CÙNG MỘT CHỖ `reacquire_confirm` frame liên tiếp.

        Chống "khớp may rủi" một frame (đo thật 27-10: ứng viên nền khớp 0,50 → bám nhầm).
        """
        if self.reacquire_confirm <= 1:
            return True
        if self._confirm_box is not None and _iou(self._confirm_box, bbox) >= 0.3:
            self._confirm_count += 1
        else:
            self._confirm_count = 1
        self._confirm_box = tuple(bbox)
        return self._confirm_count >= self.reacquire_confirm

    def _filter_by_radius(self, pairs, frame_shape):
        """Chỉ giữ ứng viên trong bán kính nở dần quanh vị trí vật ở lần thấy cuối.

        Lý do (bug thật 29-10): ngay frame đầu mất dấu mà quét toàn khung thì ứng viên khớp mờ
        ở bất kỳ đâu (bóng đèn, tay nắm cửa...) sẽ được chọn. Vùng tìm bắt đầu hẹp (1× kích thước
        vật) rồi nở 0,5×/frame, hết `search_grow_frames` thì mở toàn khung.
        """
        if self._last_center is None or not self._last_obj_size:
            return pairs
        if self._lost_age > self.search_grow_frames:
            return pairs                      # đã tìm đủ lâu → cho phép quét toàn khung
        base = max(int(self._last_obj_size[0]), int(self._last_obj_size[1]), 1)
        radius = base * (1.0 + self.search_grow_step * (self._lost_age - 1))
        cx0, cy0 = self._last_center
        height, width = frame_shape[0], frame_shape[1]
        radius = min(radius, float((height ** 2 + width ** 2) ** 0.5))
        keep = []
        for box, ncc in pairs:
            cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
            if ((cx - cx0) ** 2 + (cy - cy0) ** 2) ** 0.5 <= radius:
                keep.append((box, ncc))
        return keep

    def _verify_ok(self, frame, result) -> bool:
        """Kiểm chứng sau khi bám lại: mask mới phải còn giống vật (cue vật thể).

        Với cue mặt thì chỉ cần "còn thấy" (score) — đã lọc ở nhánh TRACKING.
        """
        if not self.object_on or not self._obj_refs:
            return True
        if result.mask is None or not result.mask.any():
            return False
        sig = object_signature(frame, result.mask)
        if sig is None:
            return False
        if best_match(self._obj_refs, sig) < self.obj_threshold:
            return False
        # Kiểm cả mẫu ảnh (NCC) — cosine với vật ít texture rất dễ "đúng giả" (bug thật 29-10)
        if self.obj_ncc_min > 0.0 and self._obj_template is not None:
            x1, y1, x2, y2 = [int(v) for v in result.bbox]
            crop = frame[max(0, y1):y2, max(0, x1):x2]
            if _ncc(self._obj_template, crop) < 0.8 * self.obj_ncc_min:
                return False
        return True

    def _abandon_reacquire(self) -> Step:
        """Bỏ lần nhận lại sai: reset engine + về LOST để tìm tiếp (không kẹt trên vùng nhầm)."""
        try:
            self.engine.reset()
        except Exception:      # engine giả/duck-type có thể không có reset → vẫn phải thoát
            pass
        self._state = STATE_LOST
        self._lost_streak = max(self._lost_streak, self.lost_after_frames)
        self._verify_left = 0
        self._confirm_count = 0
        self._confirm_box = None
        return Step(result=self._lost_result(), state=self._state, reid_score=-1.0)

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

        # Vùng tìm nở DẦN: mấy frame đầu chỉ tìm quanh chỗ cũ → không nhảy sang vật khác
        # ở góc phòng (bug thật 29-10: dấu cái ly lại bám vào bóng đèn).
        pairs = self._filter_by_radius(pairs, frame.shape[:2])

        best_score, best_box, best_ncc = -1.0, None, -1.0
        best_choice = -1.0
        height, width = frame.shape[:2]
        target_area = (self._last_obj_size[0] * self._last_obj_size[1]) if self._last_obj_size else None
        for (x1, y1, x2, y2), prefilter_ncc in pairs:
            # Điểm NCC của prefilter chỉ để ĐỀ XUẤT ứng viên: nó tính trên frame thu nhỏ 4× nên rất
            # nhiễu (đo thật 29-10: ô ĐÚNG chỉ 0,267 còn ô sai 0,632). Cổng quyết định phải dùng NCC
            # FULL-RES giữa mẫu gốc và chính vùng ứng viên.
            crop = frame[max(0, y1):y2, max(0, x1):x2]
            ncc = prefilter_ncc
            if self.obj_ncc_min > 0.0 and self._obj_template is not None:
                ncc = _ncc(self._obj_template, crop)
                if ncc < self.obj_ncc_min:
                    if ncc > best_ncc:
                        best_ncc = ncc      # ghi lại để hiệu chuẩn (kể cả khi bị loại)
                    continue
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
            self._last_center = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)   # mốc cho vùng tìm nở dần
