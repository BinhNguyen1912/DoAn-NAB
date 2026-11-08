"""
Miền nghiệp vụ (domain) — trạng thái job, thực thể, quy tắc chuyển trạng thái, lỗi miền.

Chức năng: định nghĩa "job là gì" và "được phép làm gì" mà KHÔNG biết gì về HTTP,
           filesystem, subprocess hay OpenCV.
Input  : trạng thái + số liệu thô từ tầng ngoài.
Output : enum/dataclass/lỗi miền dùng chung cho service và routes.
Lưu ý  : mọi phụ thuộc ở đây phải là stdlib. Nếu cần import fastapi/cv2/numpy → SAI TẦNG.
"""

from dataclasses import dataclass
from enum import Enum


class JobState(str, Enum):
    """Vòng đời một job xử lý video.

    uploaded → queued → running → done
                            └──→ error
    """

    UPLOADED = "uploaded"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


# Trạng thái đang chiếm tài nguyên (không cho chọn lại/xoá)
ACTIVE_STATES = frozenset({JobState.QUEUED, JobState.RUNNING})

# --------------------------------------------------------------------------- lỗi miền


class DomainError(Exception):
    """Gốc của mọi lỗi nghiệp vụ — tầng HTTP tự ánh xạ sang mã trạng thái."""


class JobNotFound(DomainError):
    """Không có job với id này."""


class JobConflict(DomainError):
    """Thao tác không hợp lệ với trạng thái hiện tại (đang chạy / đã xong)."""


class InvalidBBox(DomainError):
    """Ô chọn không hợp lệ (rỗng hoặc vượt ra ngoài khung hình)."""


class UnsupportedMedia(DomainError):
    """Định dạng video không được hỗ trợ."""


class PayloadTooLarge(DomainError):
    """Video vượt quá giới hạn dung lượng."""


class RunnerStartFailed(DomainError):
    """Không khởi chạy được tiến trình pipeline."""


# --------------------------------------------------------------------------- thực thể


@dataclass(frozen=True)
class Job:
    """Một yêu cầu xử lý video (bất biến — sửa bằng cách tạo bản mới qua store)."""

    job_id: str
    created_at: str
    original_name: str
    params: dict
    bbox: tuple[int, int, int, int] | None = None


@dataclass(frozen=True)
class JobStatus:
    """Trạng thái quan sát được của job tại một thời điểm."""

    state: JobState
    progress: int = 0
    message: str = ""
    updated_at: float = 0.0


@dataclass(frozen=True)
class JobView:
    """Tổng hợp để tầng HTTP trả cho client (job + trạng thái + artifact + số liệu)."""

    job: Job
    status: JobStatus
    artifacts: dict
    summary: dict | None = None


# --------------------------------------------------------------------------- quy tắc


def parse_state(value: str | None) -> JobState:
    """Chuyển chuỗi (đọc từ JSON) thành JobState; giá trị lạ → UPLOADED (an toàn, không nổ)."""
    try:
        return JobState(value)
    except (ValueError, TypeError):
        return JobState.UPLOADED


def clamp_percent(value: int | float) -> int:
    """Ép phần trăm về khoảng 0..100."""
    return max(0, min(100, int(round(value))))


def progress_percent(frames: int, total: int | None) -> int | None:
    """Tính % từ số frame đã xử lý.

    Output: None khi chưa biết tổng (webcam/stream) — caller tự quyết định dùng giá trị nào.
    Lưu ý : chặn ở 99% khi đang chạy; chỉ tầng gọi mới được đặt 100 (khi đã có file kết quả).
    """
    if not total or total <= 0:
        return None
    return max(0, min(99, int(round(max(0, int(frames)) * 100.0 / int(total)))))


def can_select(status: JobStatus) -> bool:
    """Chỉ cho chọn đối tượng khi job chưa chạy và chưa xong."""
    return status.state not in ACTIVE_STATES and status.state is not JobState.DONE


def assert_bbox_inside(bbox: tuple[int, int, int, int], size: tuple[int, int] | None) -> None:
    """Kiểm tra ô chọn nằm trong khung hình; size=None (không đọc được video) thì bỏ qua."""
    x, y, w, h = bbox
    if w <= 0 or h <= 0 or x < 0 or y < 0:
        raise InvalidBBox("ô chọn phải có kích thước dương và toạ độ không âm")
    if size is None:
        return
    width, height = size
    if x >= width or y >= height or x + w > width or y + h > height:
        raise InvalidBBox(f"ô chọn vượt ra ngoài khung {width}x{height}")
