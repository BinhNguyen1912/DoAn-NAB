"""
Config loader — tham số hoá hệ thống qua file YAML trong `configs/` (ticket 08, story 18).

Chức năng: đọc cấu hình (checkpoint, model cfg, nguồn mặc định, bật/tắt ghi video,
metrics...) để đổi model/máy mà không sửa code; hợp nhất theo thứ tự ưu tiên:
  defaults  <  YAML (configs/*.yaml)  <  CLI (--flag chỉ định).

Input  : đường dẫn YAML (--config; None → chỉ defaults) + dict override từ CLI.
Output : dict cấu hình đã hợp nhất; checkpoint đường dẫn tương đối được giải
         theo REPO_ROOT, báo lỗi FileNotFound kèm hướng dẫn tải checkpoint.
Lưu ý  : thuần — không đụng model; validation kiểu số báo ValueError dễ hiểu.
"""
import os

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Giá trị mặc định — file YAML chỉ cần ghi key muốn khác mặc định
DEFAULTS = {
    "checkpoint": os.path.join("samurai", "sam2", "checkpoints", "sam2.1_hiera_tiny.pt"),
    "model_cfg": os.path.join("configs", "samurai", "sam2.1_hiera_t.yaml"),
    "source": 0,                   # nguồn mặc định: webcam index 0 | rtsp:// | file
    "max_trajectory": 100,
    "record_enabled": False,
    "record_path": "data/demo_hud.mp4",
    "record_fps": None,            # None → lấy từ nguồn (headless) / 30 (display)
    "metrics_csv": None,
    "metrics_summary": None,
    "max_frames": None,
    # Tối ưu tốc độ (tuỳ chọn): reset + chọn lại bbox mỗi N frame.
    # None = tắt. Đo thật: N=3 → 2.2x nhanh hơn, IoU sau che 0.969 vs 0.981.
    "reanchor_every": None,
    # Độ phân giải đầu vào của model: null = giữ 1024 (chính xác nhất, chậm);
    # 512 = nhanh ~5-6x trên CPU (đo thật) — đánh đổi chi tiết với vật thể nhỏ.
    "image_size": None,
    # Thiết bị chạy model: "cpu" (mặc định) hoặc "cuda" (Colab GPU / máy có NVIDIA).
    "device": "cpu",
    # Hiển thị tách luồng (~30 FPS video, overlay cập nhật mỗi lần suy luận) — cho demo mượt.
    "smooth_display": False,
    # Vẽ đường quỹ đạo (màu tím) trên HUD — tắt nếu thấy rối mắt khi demo.
    "show_trajectory": True,
    # Ngưỡng logit của mask: 0.0 = lấy đúng như model trả (dễ "ăn" tóc/viền);
    # 0.5–2.0 = chỉ giữ phần model tự tin → mask co lại.
    "mask_threshold": 0.0,
    # ---- Tái nhận diện khuôn mặt (ADR-0003, buổi 6 + 9 đề cương) ----
    # Tắt mặc định để không đổi hành vi cũ; bật trong configs/default.yaml.
    "reid_enabled": False,
    "reid_detector_model": os.path.join("models", "face", "face_detection_yunet_2023mar.onnx"),
    "reid_recognizer_model": os.path.join("models", "face", "face_recognition_sface_2021dec.onnx"),
    "reid_threshold": 0.363,        # cosine SFace tối thiểu để coi là cùng người (phải hiệu chỉnh)
    "lost_after_frames": 2,         # mask rỗng liên tiếp bao nhiêu frame thì ĐÓNG BĂNG
    "reid_min_face_px": 40,         # cạnh nhỏ nhất của ô mặt để dùng làm mẫu/ứng viên
    "reid_min_detect_score": 0.8,   # điểm phát hiện mặt tối thiểu
    "reid_ref_max": 8,              # số mẫu tham chiếu giữ lại (deque)
    # ---- Tái nhận diện VẬT THỂ (ticket 10) — dùng được cho vật không có khuôn mặt ----
    # cue: "face" (mặc định, hành vi cũ) | "object" | "both"
    "reid_cue": "face",
    "reid_obj_threshold": 0.6,      # cosine đặc trưng vật thể tối thiểu (phải hiệu chỉnh)
    "reid_obj_ref_max": 8,          # số mẫu đặc trưng vật thể giữ lại
    "reid_obj_min_side": 8,         # cạnh NGẮN tối thiểu (px) — vật mảnh như bút vẫn lưu được mẫu
    "reid_obj_min_fill": 0.5,       # tỉ lệ mask/ô tối thiểu (chặn vật bị che phần lớn)
    "reid_obj_top_k": 20,           # số ứng viên được chấm descriptor đắt mỗi frame lost
    # Cổng NCC cho vật ÍT texture-màu (chai đen): 0.0 = TẮT (mặc định). Đo thật 27-10:
    # hai vật đen khác nhau cho cosine 1,000 nhưng NCC 0,897; cùng vật NCC 1,000.
    # Chỉ bật sau khi hiệu chuẩn trên clip thật (vd 0,95).
    "reid_obj_ncc_min": 0.0,      # cổng CHÍNH (dùng NCC của prefilter). Đo thật 29-10 có nhãn người dùng:
    # 4 lần nhận lại SAI (dấu ly → bám bóng đèn) chỉ 0,48–0,62 dù cosine 0,78–0,99.
    "reid_search_grow_frames": 12,  # số frame lost tìm trong vùng hẹp quanh chỗ cũ trước khi mở rộng
    "reid_search_grow_step": 0.25,  # bán kính tìm = max(w,h) × (0,75 + 0,25 × số frame lost)
    # ---- Chống "bám nhầm rồi kẹt" (bug thật 27-10) ----
    # SAM 2 hay "tưởng tượng" mask khi vật đã rời khung (đo: mask 782 px nhưng score = -4,98)
    "lost_score_threshold": 0.0,   # score ≤ ngưỡng này → coi như KHÔNG thấy vật
    "reid_reacquire_confirm": 2,   # số frame liên tiếp khớp CÙNG MỘT CHỖ mới nhận lại
    "reid_verify_frames": 2,       # số frame kiểm chứng sau khi bám lại (fail → về LOST)
}

# Key kiểu int — validate khi YAML ghi chuỗi nhầm (VD: max_trajectory: ten-frames)
_INT_KEYS = ("max_trajectory", "max_frames", "reanchor_every", "image_size",
             "lost_after_frames", "reid_min_face_px", "reid_ref_max",
             "reid_obj_ref_max", "reid_obj_min_side", "reid_obj_top_k",
             "reid_reacquire_confirm", "reid_verify_frames",
             "reid_search_grow_frames")   # source có thể int (webcam) hoặc str (file/RTSP)
_FLOAT_KEYS = ("record_fps", "mask_threshold", "reid_threshold", "reid_min_detect_score")


def _validate(cfg: dict) -> dict:
    out = dict(cfg)
    for key in _INT_KEYS:
        if out.get(key) is not None and not isinstance(out[key], int):
            raise ValueError(f"config '{key}' phải là số nguyên, nhận được {out[key]!r}")
    for key in _FLOAT_KEYS:
        if out.get(key) is not None and not isinstance(out[key], (int, float)):
            raise ValueError(f"config '{key}' phải là số, nhận được {out[key]!r}")
    return out


def load_config(path: str = None) -> dict:
    """Đọc YAML và hợp nhất vào defaults. path=None → trả defaults (không bắt buộc file)."""
    if path is None:
        return dict(DEFAULTS)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Không tìm thấy file cấu hình '{path}' (kiểm tra lại --config hoặc tạo "
            f"configs/default.yaml từ mẫu)"
        )
    with open(path, encoding="utf-8") as f:
        user_cfg = yaml.safe_load(f) or {}
    unknown = set(user_cfg) - set(DEFAULTS)
    if unknown:
        raise ValueError(
            f"YAML chứa key lạ {sorted(unknown)} — chỉ nhận các key của defaults "
            f"({', '.join(DEFAULTS)})"
        )
    return _validate({**DEFAULTS, **user_cfg})


def merge_cli_overrides(cfg: dict, cli_args: dict) -> dict:
    """Đè giá trị config bằng CLI — chỉ khi CLI khác None (flag không truyền → YAML thắng)."""
    out = dict(cfg)
    for key, value in cli_args.items():
        if value is not None and key in out:
            out[key] = value
    return out


def resolve_checkpoint(checkpoint: str) -> str:
    """Tương đối → tuyệt đối theo REPO_ROOT; báo lỗi có hướng dẫn nếu file chưa tải."""
    path = checkpoint if os.path.isabs(checkpoint) else os.path.join(REPO_ROOT, checkpoint)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Checkpoint không tồn tại: '{checkpoint}' → resolved '{path}'. "
            f"Vui lòng tải checkpoint (xem README mục cài đặt — script/link sam2.1_hiera_tiny.pt)"
        )
    return path