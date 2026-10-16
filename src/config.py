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
}

# Key kiểu int — validate khi YAML ghi chuỗi nhầm (VD: max_trajectory: ten-frames)
_INT_KEYS = ("max_trajectory", "max_frames")   # source có thể int (webcam) hoặc str (file/RTSP)
_FLOAT_KEYS = ("record_fps",)


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