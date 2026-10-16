"""
TrackerEngine — seam trung tâm: bọc SAM 2 video predictor (config SAMURAI) thành
streaming per-frame.

Chức năng: nhận frame gốc (H, W, 3) BGR theo thứ tự thời gian; frame đầu chọn đối tượng
bằng bbox; từ frame thứ 2 trở đi chỉ cần `process()` — engine tự nạp frame vào
inference_state và propagate đúng 1 bước (temporal propagation của SAM 2 + logic
Kalman/memory-bank của SAMURAI chạy nguyên bản bên dưới).

Input  : frame BGR uint8 (H, W, 3) từ VideoSource; bbox (x1, y1, x2, y2) theo toạ độ frame gốc.
Output : TrackingResult(mask bool (H, W), bbox (x1,y1,x2,y2), score, elapsed_ms, frame_idx).
Lưu ý  : streaming theo hướng nghiên cứu `docs/research/03` (SAMURAI issue #128) —
         init_state chỉ chứa frame 0, frame mới được nạp bằng cách sửa `num_frames`
         và gọi `propagate_in_video(start_frame_idx=i, max_frame_num_to_track=1)`;
         preprocessing frame sao chép đúng `_load_img_as_tensor` của SAM 2
         (PIL resize, RGB, /255, trừ mean, chia std) để đảm bảo cùng một phân phối đầu vào.
"""
import os
import tempfile
import time
from dataclasses import dataclass

import numpy as np
import torch
from PIL import Image

# Chuẩn hoá đầu vào giống mặc định của SAM 2 (load_video_frames)
_IMG_MEAN = (0.485, 0.456, 0.406)
_IMG_STD = (0.229, 0.224, 0.225)

MODEL_CFG = "configs/samurai/sam2.1_hiera_t.yaml"
DEFAULT_CKPT = os.path.join("samurai", "sam2", "checkpoints", "sam2.1_hiera_tiny.pt")


@dataclass
class TrackingResult:
    """Kết quả 1 frame: mask gốc, bbox suy ra, điểm tin cậy, thời gian xử lý."""

    frame_idx: int
    mask: np.ndarray    # (H, W) bool — kích thước frame gốc
    bbox: tuple         # (x1, y1, x2, y2) theo toạ độ frame gốc; (0,0,0,0) nếu mask rỗng
    score: float        # object_score_logits của đối tượng (>0 thường là tin cậy)
    elapsed_ms: float


class _StreamingImages:
    """View thay `inference_state["images"]`: giữ tensor frame đã preprocess theo index,
    cho phép dự thêm frame mới vô hạn (streaming)."""

    def __init__(self, first: torch.Tensor):
        self._frames = [first]

    def append(self, t: torch.Tensor) -> None:
        self._frames.append(t)

    def free(self, idx: int) -> None:
        """Giải phóng tensor frame đã xử lý xong (giữ RAM, đặc biệt quan trọng khi live)."""
        if 0 <= idx < len(self._frames):
            self._frames[idx] = None

    def __getitem__(self, idx: int) -> torch.Tensor:
        img = self._frames[idx]
        if img is None:
            raise RuntimeError(f"frame {idx} đã được giải phóng — không nên bị truy cập lại")
        return img

    def __len__(self) -> int:
        return len(self._frames)


class TrackerEngine:
    """Streaming per-frame trên 1 đối tượng (single object, theo ADR-0001)."""

    def __init__(self, predictor):
        self._predictor = predictor
        self._state = None
        self._images = None
        self._tmpdir = None
        self._frame_count = 0   # số frame đã nạp (0-index; frame 0 = start)
        self._video_hw = None   # (H, W) của frame gốc — tham chiếu resize mask đầu ra

    @classmethod
    def build_default(cls, device="cpu", checkpoint=DEFAULT_CKPT,
                      model_cfg=MODEL_CFG) -> "TrackerEngine":
        """Dựng predictor SAMURAI (mặc định tiny trên CPU; ~20-60s).

        model_cfg: đường dẫn YAML của SAM 2 — có thể đè qua config YAML (ticket 08).
        Test dùng fixture session-scoped để build 1 lần.
        """
        from sam2.build_sam import build_sam2_video_predictor

        ckpt = checkpoint
        if not os.path.isfile(ckpt):
            ckpt = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ckpt)
        predictor = build_sam2_video_predictor(model_cfg, ckpt, device=device)
        return cls(predictor)

    # ---------- preprocessing (đối chiếu _load_img_as_tensor của SAM 2) ----------

    def _to_input_tensor(self, frame_bgr: np.ndarray) -> torch.Tensor:
        if frame_bgr.dtype != np.uint8 or frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
            raise ValueError(f"frame phải là (H, W, 3) uint8, nhận được {frame_bgr.dtype}/{frame_bgr.shape}")
        rgb = frame_bgr[:, :, ::-1]  # BGR (OpenCV) → RGB
        pil = Image.fromarray(np.ascontiguousarray(rgb)).convert("RGB")
        arr = np.array(pil.resize((self._predictor.image_size, self._predictor.image_size)))
        t = torch.from_numpy(arr).permute(2, 0, 1).float() / 255.0
        t -= torch.tensor(_IMG_MEAN, dtype=torch.float32)[:, None, None]
        t /= torch.tensor(_IMG_STD, dtype=torch.float32)[:, None, None]
        return t

    # ---------- API công khai ----------

    def start(self, frame_bgr: np.ndarray, bbox: tuple) -> TrackingResult:
        """Bắt đầu phiên track: frame đầu + bbox chọn đối tượng (toạ độ gốc)."""
        if self._state is not None:
            self.reset()
        self._video_hw = (frame_bgr.shape[0], frame_bgr.shape[1])

        # init_state cần một thư mục JPG — chỉ chứa frame 0 (streaming nạp phần còn lại)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="tracker_engine_")
        rgb = frame_bgr[:, :, ::-1]
        Image.fromarray(np.ascontiguousarray(rgb)).save(
            os.path.join(self._tmpdir.name, "00000.jpg")
        )
        t0 = time.time()
        self._state = self._predictor.init_state(
            self._tmpdir.name, offload_video_to_cpu=True, offload_state_to_cpu=False
        )
        tensor0 = self._state["images"][0]
        if self._state["video_height"] != self._video_hw[0] or self._state["video_width"] != self._video_hw[1]:
            raise ValueError(
                f"kích thước frame không khớp: {self._video_hw} vs nguồn {(self._state['video_height'], self._state['video_width'])}"
            )
        # Thay images bằng view streaming (giữ đúng tensor frame 0 đã chuẩn hoá)
        self._images = _StreamingImages(tensor0)
        self._state["images"] = self._images
        self._frame_count = 1

        self._predictor.add_new_points_or_box(self._state, box=tuple(bbox), frame_idx=0, obj_id=0)
        # Propagate riêng frame 0 (đã consolidate trong preflight — không tính lại)
        result = self._propagate_one(0, t0)
        # tensor frame 0 đã xử lý xong — giải phóng để tiết kiệm RAM (cond memory đã encode sẵn)
        self._images.free(0)
        return result

    def process(self, frame_bgr: np.ndarray) -> TrackingResult:
        """Nạp frame kế tiếp và propagate đúng 1 bước."""
        if self._state is None:
            raise RuntimeError("Gọi start() trước khi process()")
        if self._video_hw != (frame_bgr.shape[0], frame_bgr.shape[1]):
            raise ValueError(
                f"kích thước frame đổi giữa phiên: nhận {frame_bgr.shape[:2]}, kỳ vọng {self._video_hw}"
            )
        idx = self._frame_count
        self._images.append(self._to_input_tensor(frame_bgr))
        self._frame_count = len(self._images)
        self._state["num_frames"] = self._frame_count
        t0 = time.time()
        result = self._propagate_one(idx, t0)
        self._images.free(idx)  # đã xử lý xong — không còn dùng tensor gốc
        return result

    def reset(self) -> None:
        """Dọn phiên hiện tại (khi chọn lại đối tượng)."""
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None
        self._state = None
        self._images = None
        self._frame_count = 0
        self._video_hw = None

    # ---------- nội bộ ----------

    def _propagate_one(self, frame_idx: int, t0: float) -> TrackingResult:
        """Propagate đúng frame_idx (sau khi num_frames đã cập nhật)."""
        with torch.inference_mode():
            gen = self._predictor.propagate_in_video(
                self._state, start_frame_idx=frame_idx, max_frame_num_to_track=1
            )
            yielded = next(gen, None)
            gen.close()
        if yielded is None:
            raise RuntimeError(f"propagate không trả kết quả cho frame {frame_idx}")
        out_idx, obj_ids, video_res_masks = yielded
        assert out_idx == frame_idx, f"thứ tự frame lệch: kỳ vọng {frame_idx}, nhận {out_idx}"

        mask_bool, bbox = self._mask_to_bbox(video_res_masks[0])
        score = self._object_score(frame_idx)
        elapsed_ms = (time.time() - t0) * 1000.0
        return TrackingResult(
            frame_idx=frame_idx,
            mask=mask_bool,
            bbox=bbox,
            score=score,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _mask_to_bbox(mask_scores):
        """Video_res mask (1, H, W) float → (mask bool, bbox gọn)."""
        mask = (mask_scores[0] > 0.0).cpu().numpy()
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            return mask, (0, 0, 0, 0)
        x1, x2 = int(xs.min()), int(xs.max())
        y1, y2 = int(ys.min()), int(ys.max())
        return mask, (x1, y1, x2, y2)

    def _object_score(self, frame_idx: int) -> float:
        """object_score_logits của đối tượng 0 ở frame_idx (trong state đầu ra)."""
        outputs = self._state["output_dict"]
        for key in ("cond_frame_outputs", "non_cond_frame_outputs"):
            entry = outputs[key].get(frame_idx)
            if entry is not None:
                return float(entry["object_score_logits"][0])
        raise RuntimeError(f"không tìm thấy output của frame {frame_idx} trong state")