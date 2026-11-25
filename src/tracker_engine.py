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


# Siêu tham số **motion-memory của SAMURAI** — bộ điều khiển "chọn ký ức nào" + Kalman filter.
# Vì sao cần danh sách trắng: hydra override một khoá SAI TÊN bị **bỏ qua im lặng** ⇒ thí nghiệm
# trông như đã chạy cấu hình mới mà thực ra chạy mặc định (đúng lớp lỗi AGENTS §6 ghi ở
# `docs/plan/24-11-2026-bam-bat-vat-bat-ky-duong-b.md`: copy config làm đổi hành vi, mIoU 0,6987→0,2486).
MODEL_OVERRIDE_CHO_PHEP = {
    "samurai_mode": bool,                  # bật/tắt toàn bộ motion-aware memory (đối chứng)
    "stable_frames_threshold": int,        # số frame "ổn định" trước khi tin (mặc định 15)
    "stable_ious_threshold": float,        # (mặc định 0,3)
    "kf_score_weight": float,              # trọng số dự đoán chuyển động khi chọn ký ức (0,25)
    "memory_bank_iou_threshold": float,    # (0,5)
    "memory_bank_obj_score_threshold": float,   # (0,0)
    "memory_bank_kf_score_threshold": float,    # (0,0)
}


def _dinh_dang_hydra(key: str, value) -> str:
    """`('kf_score_weight', 0.5)` → `'++model.kf_score_weight=0.5'`; bool → `True`/`False`."""
    loai = MODEL_OVERRIDE_CHO_PHEP[key]
    if loai is bool:
        return f"++model.{key}={bool(value)}"
    if loai is int:
        return f"++model.{key}={int(value)}"
    return f"++model.{key}={float(value)!r}"


def build_overrides(image_size=None, min_obj_score_logits=None, model_overrides=None):
    """Hydra override cho predictor: giảm `image_size` để nhanh hơn trên CPU.

    Đo thật (fixture 20 frame, ô vuông 60px + che 5 frame):
      1024 → 5492 ms/frame, IoU sau che 0.981, mất dấu 5/19
       512 →  733 ms (1.36 FPS), IoU 0.988, mất dấu 5/19
       512 + re-anchor mỗi 3 frame → 558 ms (1.79 FPS), IoU 0.977, mất dấu 0/19
    Đánh đổi: ảnh bị downsample mạnh hơn → đối tượng NHỎ có thể kém chính xác hơn;
    mặc định giữ 1024 của model, chỉ hạ khi cần demo mượt.
    """
    ra = []
    if image_size:
        ra.append(f"++model.image_size={int(image_size)}")
    # 24-11 (`docs/plan/24-11-2026-bam-bat-vat-bat-ky-duong-b.md`, P2): SAM 2 dùng **HAI ngưỡng lệch nhau**
    # cho cùng quyết định "có vật hay không":
    #   `samurai/.../sam2.1_hiera_t.yaml:126` → `min_obj_score_logits: -1` (ngưỡng ZERO-HOÁ mask,
    #                                            `sam2_base.py:398`), trong khi
    #   `sam2_base.py:867` → `object_score_logits > 0` (ngưỡng gắn `no_obj_embed_spatial` vào bộ nhớ).
    # Đo trên `data/fac_A.csv` (tiny @192, binh1, 333 frame): 113/113 frame mask RỖNG có score ≤ −1,086;
    # **15 frame CÓ mask 42–3 767 px nằm trong dải (−1, 0]**; frame có vật thật score ≥ 0,582.
    # ⇒ có khoảng trống ~0,58 logit. Override ở ĐÂY (hydra) chứ **không copy file config** — copy config
    # đã đo được là làm ĐỔI hành vi (mIoU 0,6987 → 0,2486 dù nội dung y nguyên).
    if min_obj_score_logits is not None:
        ra.append(f"++model.min_obj_score_logits={min_obj_score_logits}")
    # 24-11 (Tầng 1 "custom model"): 7 siêu tham số motion-memory của SAMURAI. Khoá lạ ⇒ NÉM
    # (không im lặng bỏ qua), vì cái bẫy thật là "chạy tưởng cấu hình X mà thực ra mặc định".
    for key, value in (model_overrides or {}).items():
        if key not in MODEL_OVERRIDE_CHO_PHEP:
            raise ValueError(
                f"model override {key!r} không có trong danh sách trắng "
                f"{sorted(MODEL_OVERRIDE_CHO_PHEP)} — hydra sẽ BỎ QUA khoá sai tên trong im lặng")
        ra.append(_dinh_dang_hydra(key, value))
    return ra


@dataclass
class TrackingResult:
    """Kết quả 1 frame: mask gốc, bbox suy ra, điểm tin cậy, thời gian xử lý."""

    frame_idx: int
    mask: np.ndarray    # (H, W) bool — kích thước frame gốc
    bbox: tuple         # (x1, y1, x2, y2) theo toạ độ frame gốc; (0,0,0,0) nếu mask rỗng
    score: float        # object_score_logits của đối tượng (>0 thường là tin cậy)
    elapsed_ms: float   # CHỈ phần model (propagate) — không gồm tiền xử lý
    # Thời gian tiền xử lý (resize sang `image_size` + stack tensor). Tách riêng vì `elapsed_ms`
    # luôn bỏ khoản này (đo 14-11: 14,25 ms/frame @192), nên tuổi mask thật và chu kỳ VOS không khép
    # được nếu không cộng nó. Mặc định **`None`** (= CHƯA ĐO) để engine khác không "vô tình" báo 0,0.
    pre_ms: float | None = None


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

    def __init__(self, predictor, mask_threshold=0.0, image_size=None):
        """mask_threshold: ngưỡng logit để cắt rìa mờ của mask (0.0 = lấy hết phần model cho là
        đối tượng; 0.5–2.0 = chỉ giữ phần tự tin → mask co lại, bớt "ăn" tóc/viền)."""
        self._predictor = predictor
        self._mask_threshold = float(mask_threshold)
        self._state = None
        self._images = None
        # `image_size` hiệu lực — CHỈ để truy nguyên (manifest của mask dump / báo cáo); None = mặc
        # định của model_cfg (1024). Trước đây engine không lưu ⇒ manifest ghi `null` dù đã chạy 192.
        self.image_size = image_size
        self._tmpdir = None
        self._frame_count = 0   # số frame đã nạp (0-index; frame 0 = start)
        self._video_hw = None   # (H, W) của frame gốc — tham chiếu resize mask đầu ra

    @property
    def image_size_hieu_luc(self) -> int | None:
        """`image_size` mà predictor THẬT SỰ dùng (None nếu predictor không khai báo).

        Khác `self.image_size` = giá trị **đã yêu cầu** qua hydra override. Nếu override không được
        áp (khoá đổi tên, `model_cfg` bỏ qua…) thì predictor chạy `image_size` của config (1024) mà
        không báo gì; so hai giá trị này là cách duy nhất phát hiện "cấu hình chạy ≠ cấu hình yêu
        cầu" (Next steps 14-11, góc "độ bền & hiệu năng").
        """
        return getattr(self._predictor, "image_size", None)

    @classmethod
    def build_default(cls, device="cpu", checkpoint=DEFAULT_CKPT,
                      model_cfg=MODEL_CFG, image_size=None,
                      apply_postprocessing=False, mask_threshold=0.0,
                      min_obj_score_logits=None, model_overrides=None) -> "TrackerEngine":
        """Dựng predictor SAMURAI (mặc định tiny trên CPU; ~20-60s).

        model_cfg: đường dẫn YAML của SAM 2 — có thể đè qua config YAML (ticket 08).
        image_size: độ phân giải đầu vào của model (None = giữ 1024 của config;
                    hạ xuống 512 nhanh hơn ~5-6 lần trên CPU — xem `build_overrides`).
        apply_postprocessing: bước `fill_holes_in_mask_scores` của SAM 2. Mặc định TẮT vì
                    (a) trên CPU thiếu extension `_C` nên bị bỏ qua kèm cảnh báo,
                    (b) trên GPU (Colab) extension CÓ nhưng nhận tensor CPU →
                    `INTERNAL ASSERT FAILED: inputs must be a CUDA tensor` (vô hại nhưng
                    ồn), (c) tắt ở cả hai nơi thì số đo CPU/GPU **so sánh được với nhau**.
        Test dùng fixture session-scoped để build 1 lần.
        """
        from sam2.build_sam import build_sam2_video_predictor

        ckpt = checkpoint
        if not os.path.isfile(ckpt):
            ckpt = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ckpt)
        predictor = build_sam2_video_predictor(
            model_cfg, ckpt, device=device,
            apply_postprocessing=apply_postprocessing,
            hydra_overrides_extra=build_overrides(image_size, min_obj_score_logits,
                                                  model_overrides),
        )
        return cls(predictor, mask_threshold=mask_threshold, image_size=image_size)

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

    def start(self, frame_bgr: np.ndarray, bbox: tuple,
              points: list[tuple[float, float]] | np.ndarray | None = None,
              labels: list[int] | np.ndarray | None = None) -> TrackingResult:
        """Bắt đầu phiên track: frame đầu + bbox chọn đối tượng (toạ độ gốc).

        points: danh sách toạ độ (x, y) gốc frame (tuỳ chọn)
        labels: 1 (positive: vật thể) hoặc 0 (negative: nền sát mép) (tuỳ chọn)
        """
        if self._state is not None:
            self.reset()
        self._xoa_trang_thai_kalman()
        self._video_hw = (frame_bgr.shape[0], frame_bgr.shape[1])
        h, w = self._video_hw

        pts_arr = None
        lbls_arr = None
        if points is not None or labels is not None:
            if points is None or labels is None:
                raise ValueError("points và labels phải được cung cấp cùng nhau")
            pts_arr = np.asarray(points, dtype=np.float32)
            lbls_arr = np.asarray(labels, dtype=np.int32)
            if pts_arr.ndim != 2 or pts_arr.shape[1] != 2:
                raise ValueError(f"points phải có dạng (N, 2), nhận được {pts_arr.shape}")
            if len(pts_arr) != len(lbls_arr):
                raise ValueError(f"số lượng points ({len(pts_arr)}) và labels ({len(lbls_arr)}) phải khớp nhau")
            if not np.all(np.isin(lbls_arr, [0, 1])):
                raise ValueError(f"mỗi label phải là 1 (positive) hoặc 0 (negative), nhận được {lbls_arr}")
            for x, y in pts_arr:
                if not (0 <= x < w and 0 <= y < h):
                    raise ValueError(f"point ({x}, {y}) nằm ngoài khung hình ({w}x{h})")

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

        prompt_kwargs = {"box": tuple(bbox)}
        if pts_arr is not None and len(pts_arr) > 0:
            prompt_kwargs["points"] = pts_arr
            prompt_kwargs["labels"] = lbls_arr

        self._predictor.add_new_points_or_box(
            self._state, frame_idx=0, obj_id=0, **prompt_kwargs
        )
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
        t_pre = time.time()
        self._images.append(self._to_input_tensor(frame_bgr))
        pre_ms = (time.time() - t_pre) * 1000.0
        self._frame_count = len(self._images)
        self._state["num_frames"] = self._frame_count
        t0 = time.time()
        result = self._propagate_one(idx, t0)
        self._images.free(idx)  # đã xử lý xong — không còn dùng tensor gốc
        result.pre_ms = pre_ms   # KHÔNG cộng vào `elapsed_ms` (giữ tương thích số cũ)
        return result

    def _xoa_trang_thai_kalman(self) -> bool:
        """Xoá **trạng thái Kalman của SAMURAI** trên model (25-11) — KHÔNG thuộc `inference_state`.

        Bug thật (đo trên máy này, 13 frame `data/binh1.mp4`, cùng engine, cùng ô `(300,275,450,685)`):
        phiên 2 chạy ngay sau phiên 1 **lệch từ frame thứ 6**, `IoU` xuống **0,8253**; zero 3 field
        `kf_mean`/`kf_covariance`/`stable_frames` rồi chạy lại ⇒ **13/13 frame IoU = 1,0000**.
        Nguyên nhân: `reset()`/`init_state()` chỉ dọn `inference_state`, còn `sam2_base.py:203-205`
        (`self.kf_mean`, `self.kf_covariance`, `self.stable_frames`) **nằm trên MODEL** và được dùng lại
        (`sam2_base.py:421-441`) nên phiên sau **mồi Kalman từ vật CŨ**.

        Hai hệ quả người dùng thấy được:
          1. **Bấm `r` chọn vật KHÁC** trong cùng phiên ⇒ Kalman mồi từ vật cũ (đúng thao tác của người
             dùng khi cổng báo nghi!).
          2. **Hai phiên trong cùng một process KHÔNG tái lập** ⇒ mọi A/B chạy nhiều phiên một process
             bị nhiễm, và `tests/conftest.py` dùng engine session-scoped ⇒ kết quả test phụ thuộc thứ tự.

        Trả `True` nếu đã xoá (model là thật), `False` nếu không có 3 field (engine giả trong test).
        """
        predictor = getattr(self, "_predictor", None)
        if predictor is None:
            return False
        da_xoa = False
        for ten in ("kf_mean", "kf_covariance", "stable_frames"):
            if hasattr(predictor, ten):
                setattr(predictor, ten, None if ten != "stable_frames" else 0)
                da_xoa = True
        return da_xoa

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
            if hasattr(gen, "close"):
                gen.close()
        if yielded is None:
            raise RuntimeError(f"propagate không trả kết quả cho frame {frame_idx}")
        out_idx, obj_ids, video_res_masks = yielded
        assert out_idx == frame_idx, f"thứ tự frame lệch: kỳ vọng {frame_idx}, nhận {out_idx}"

        mask_bool, bbox = self._mask_to_bbox(video_res_masks[0], self._mask_threshold)
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
    def _mask_to_bbox(mask_scores, threshold=0.0):
        """Video_res mask (1, H, W) logit float → (mask bool, bbox gọn).

        threshold: logit > threshold được coi là thuộc đối tượng. Nâng ngưỡng → mask co lại
        (cắt rìa mờ như tóc/viền), hạ về 0 → lấy đúng như model trả.
        """
        mask = (mask_scores[0] > threshold).cpu().numpy()
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