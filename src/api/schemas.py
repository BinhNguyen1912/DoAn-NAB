"""
Schemas Pydantic — NGUỒN SỰ THẬT DUY NHẤT của hợp đồng API.

Chức năng: khai báo kiểu dữ liệu request/response; FastAPI dùng để validate và sinh
           `/openapi.json` (frontend sinh type TypeScript từ đó).
Input  : dữ liệu HTTP (JSON body / form field) do client gửi.
Output : model đã validate, hoặc lỗi 422 tự động của FastAPI.
Lưu ý  : đổi tên khoá ở đây là ĐỔI HỢP ĐỒNG với `web/` — sửa phải sửa cả hai phía.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Trạng thái vòng đời của một job xử lý video
JobState = Literal["uploaded", "queued", "running", "done", "error"]

# Cue tái nhận diện: khuôn mặt / đặc trưng vật thể / thử mặt trước rồi tới vật thể
ReidCue = Literal["face", "object", "both"]


class BBox(BaseModel):
    """Ô chọn đối tượng theo pixel của frame đầu video."""

    x: int = Field(ge=0, description="toạ độ x góc trên-trái")
    y: int = Field(ge=0, description="toạ độ y góc trên-trái")
    w: int = Field(gt=0, description="chiều rộng ô")
    h: int = Field(gt=0, description="chiều cao ô")


class TrackParams(BaseModel):
    """Tham số truyền xuống pipeline (tương ứng flag của tools/run_live.py)."""

    image_size: Optional[int] = Field(
        default=None, ge=64, le=1024,
        description="độ phân giải đầu vào của model; 192 ≈ 10 FPS, 256 ≈ 6,5 FPS trên CPU",
    )
    max_frames: Optional[int] = Field(default=None, ge=1, description="giới hạn số frame xử lý")
    max_trajectory: Optional[int] = Field(default=None, ge=1, description="số điểm quỹ đạo tối đa")
    reid: bool = Field(default=False, description="bật tái nhận diện khi mất dấu")
    cue: ReidCue = Field(default="object", description="cue tái nhận diện (mặc định bám VẬT)")


class JobCreateResponse(BaseModel):
    """Trả về ngay sau khi upload xong — chưa xử lý gì."""

    job_id: str
    state: JobState


class SelectRequest(BaseModel):
    """Chọn đối tượng cần bám trên frame đầu → bắt đầu xử lý."""

    bbox: BBox


class JobStatusResponse(BaseModel):
    """Trạng thái đầy đủ của một job (frontend poll mỗi giây).

    Lưu ý: tên khác `JobStatus` của tầng miền (`src/api/domain.py`) là CỐ Ý — DTO của hợp đồng
    HTTP không được lẫn với thực thể miền.
    """

    job_id: str
    state: JobState
    progress: int = Field(ge=0, le=100, description="phần trăm tiến trình")
    message: str
    created_at: str
    bbox: Optional[list[int]] = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    summary: Optional[dict] = None


class JobListItem(BaseModel):
    """Một dòng trong danh sách job (không kèm summary cho nhẹ)."""

    job_id: str
    state: JobState
    progress: int = Field(ge=0, le=100)
    message: str
    created_at: str
