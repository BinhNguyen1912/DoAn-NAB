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


# --------------------------------------------------------------------------- live


class LiveStartRequest(BaseModel):
    """Yêu cầu bắt đầu phát trực tiếp từ một nguồn frame."""

    source: str = Field(
        default="0",
        description="0 = webcam | rtsp://IP:554/stream | http://.../snapshot.jpg | đường dẫn video",
        min_length=1,
    )
    mode: Literal["raw", "track"] = Field(
        default="raw",
        description="raw = chỉ phát khung hình | track = bám đối tượng bằng model (cần bbox)",
    )
    bbox: Optional[BBox] = Field(
        default=None,
        description="ô chọn đối tượng cho mode=track (bắt buộc khi track)",
    )
    image_size: Optional[int] = Field(
        default=None, ge=64, le=1024,
        description="độ phân giải model cho mode=track (mặc định 192 ≈ 10 FPS trên CPU)",
    )
    mask_smoothing: Optional[float] = Field(
        default=None, gt=0.0, le=1.0,
        description="mode=track: trọng số mask MỚI khi trộn theo thời gian; 1.0 = tắt (mặc định, "
                    "đo 10-11: bật không cải thiện độ êm mà thêm trễ)",
    )
    vos_every: Optional[int] = Field(
        default=None, ge=1, le=30,
        description="mode=track: chạy model mỗi N frame, các frame còn lại dùng LK (mặc định 3). "
                    "1 = chạy model mọi frame (mask tươi nhất nhưng hình chậm)",
    )


class LiveStatusResponse(BaseModel):
    """Trạng thái phiên phát trực tiếp (frontend poll mỗi giây để hiện FPS/trạng thái)."""

    state: Literal["stopped", "running", "error"]
    source: str
    frames: int = Field(ge=0, description="số frame đã đọc từ khi bắt đầu")
    measured_fps: float = Field(ge=0, description="FPS THỰC ĐO trong 2 giây gần nhất")
    display_fps: float = Field(default=0, ge=0,
                               description="FPS PHÁT do chính worker đo (nguồn gốc số trong báo cáo); "
                                           "0 khi nguồn không báo")
    mask_fps: float = Field(default=0, ge=0,
                            description="nhịp MASK MỚI (số lần model chạy/giây) — nhỏ hơn "
                                        "measured_fps khi chạy hybrid VOS + LK")
    stability: float = Field(default=0, ge=0, le=1,
                             description="IoU trung bình giữa hai mask liên tiếp (1 = không nhấp nháy)")
    latency_ms: float = Field(default=0, ge=0, description="độ trễ suy luận gần nhất (ms)")
    empty_runs: int = Field(default=0, ge=0,
                            description="số lần model trả mask RỖNG (mất dấu thật) từ đầu phiên")
    message: str
