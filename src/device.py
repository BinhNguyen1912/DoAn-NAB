"""
Chọn thiết bị chạy model (`cpu` | `cuda`) — hàm THUẦN, **không** import torch.

Chức năng: chuẩn hoá + kiểm tra tên thiết bị ở CỬA VÀO (CLI `tools/live_worker.py`, biến môi
           trường `CAMERA_AI_DEVICE` của API, lệnh worker do `src/worker/command.py` dựng) để lỗi
           gõ sai / thiếu GPU hiện ra **trước** khi nạp checkpoint 156 MB.
Input  : tên thiết bị người dùng (`None` = mặc định `cpu`) và, tuỳ chọn, `cuda_available`.
Output : `"cpu"` hoặc `"cuda"`; ném `ValueError` kèm câu nói rõ cách sửa khi không hợp lệ.
Lưu ý  : module này KHÔNG kiểm tra CUDA thật — ai có torch thì truyền `cuda_available` (lấy từ
         `torch.cuda.is_available()`), còn API (tiến trình nhẹ, không có torch) chỉ cần chuẩn hoá
         tên rồi chuyển tiếp xuống worker.

Vì sao cần: đường live (web demo) trước 10-11 gọi `TrackerEngine.build_default()` mà **không**
truyền `device` ⇒ dù máy có GPU vẫn chạy model trên CPU (155 ms/frame @256). Đường CLI của
`tools/run_live.py` đã có `--device` từ trước; đường live thì chưa.
"""

import os

DEFAULT_DEVICE = "cpu"
VALID_DEVICES = ("cpu", "cuda")
# Biến môi trường cho đường LIVE qua web: `./run web` (build frontend) rồi
# `CAMERA_AI_DEVICE=cuda ./run api` (API đọc biến lúc khởi động
# rồi chuyển tiếp xuống worker). Đặt tên theo môi trường để không phải đổi hợp đồng HTTP.
ENV_VAR = "CAMERA_AI_DEVICE"

_HINT_CUDA = (
    "cuda cần GPU NVIDIA + torch bản CUDA. Trên Colab: Runtime → Change runtime type → T4 GPU "
    "(rồi Runtime → Restart). Kiểm tra nhanh: ./run env  → dòng 'torch ... | CUDA: True'"
)


def normalize_device(name) -> str:
    """`None`/""→`cpu`; chuỗi hợp lệ viết thường, có khoảng trắng cũng nhận; còn lại ném ValueError."""
    if name is None:
        return DEFAULT_DEVICE
    text = str(name).strip().lower()
    if not text:
        return DEFAULT_DEVICE
    if text not in VALID_DEVICES:
        raise ValueError(
            f"device phải là một trong {VALID_DEVICES} — nhận {name!r} "
            "(ví dụ: --device cuda | cpu)"
        )
    return text


def validate_device(name, *, cuda_available=None) -> str:
    """Như `normalize_device`, và nếu xin `cuda` thì kiểm tra máy có CUDA không.

    `cuda_available=None` ⇒ bỏ qua phép kiểm (dùng ở nơi không có torch, ví dụ API chỉ dựng lệnh).
    `cuda_available is False` ⇒ ném ValueError với câu hướng dẫn — KHÔNG âm thầm rơi về CPU: chạy
    CPU mà tưởng GPU sẽ khiến mọi số FPS trong báo cáo bị gán sai thiết bị.
    """
    device = normalize_device(name)
    if device == "cuda" and cuda_available is False:
        raise ValueError(f"đã xin device='cuda' nhưng máy này không thấy GPU CUDA — {_HINT_CUDA}")
    return device


def device_from_env(environ=None) -> str:
    """Thiết bị mặc định của đường live lấy từ `$CAMERA_AI_DEVICE` (không đặt ⇒ `cpu`)."""
    environ = os.environ if environ is None else environ
    return normalize_device(environ.get(ENV_VAR))
