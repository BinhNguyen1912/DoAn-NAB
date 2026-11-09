"""
Cổng (ports) — giao diện trừu tượng giữa service và hạ tầng.

Chức năng: khai báo Protocol cho 3 hạ tầng có thể thay thế: lưu trữ job, chạy pipeline,
           đọc thông tin video. Service chỉ biết các Protocol này.
Input  : (chỉ là chữ ký — không có code chạy).
Output : Protocol dùng để type-check và để viết adapter giả trong test.
Lưu ý  : KHÔNG import adapter cụ thể ở đây. Đổi filesystem → SQLite/S3, hay đổi pipeline
         CPU → GPU worker (Modal/RunPod) chỉ cần viết adapter mới cùng chữ ký này.
"""

from pathlib import Path
from typing import Any, BinaryIO, Callable, Protocol, runtime_checkable

from src.api.domain import Job, JobStatus, LiveTelemetry, SourceHealth


@runtime_checkable
class JobStore(Protocol):
    """Nơi lưu bền vững job + trạng thái (hiện thực: FileSystemJobStore)."""

    def create(self, *, original_name: str, params: dict) -> Job:
        """Tạo job mới ở trạng thái uploaded."""

    def get(self, job_id: str) -> Job | None:
        """Đọc job; None nếu không tồn tại."""

    def path(self, job_id: str) -> Path:
        """Thư mục chứa file của job."""

    def save_video(self, job_id: str, stream: BinaryIO) -> int:
        """Lưu video upload; trả số byte. Ném PayloadTooLarge nếu vượt giới hạn."""

    def read_status(self, job_id: str) -> JobStatus:
        """Trạng thái hiện tại (mặc định an toàn nếu thiếu/hỏng)."""

    def save_status(self, job_id: str, status: JobStatus) -> JobStatus:
        """Ghi trạng thái mới (atomic)."""

    def save_bbox(self, job_id: str, bbox: tuple[int, int, int, int]) -> None:
        """Lưu ô chọn đối tượng vào job."""

    def list_ids(self, limit: int) -> list[str]:
        """Id các job, mới nhất trước."""

    def delete(self, job_id: str) -> None:
        """Xoá toàn bộ dữ liệu job."""


@runtime_checkable
class PipelineRunner(Protocol):
    """Nơi chạy pipeline bám bắt và đọc kết quả (hiện thực: SubprocessPipelineRunner)."""

    def start(self, job_id: str, job_dir: Path, *, params: dict,
              bbox: tuple[int, int, int, int],
              on_exit: Callable[[int], None] | None = None) -> Any:
        """Khởi chạy pipeline ở nền; `on_exit(returncode)` gọi khi kết thúc."""

    def is_running(self, job_id: str) -> bool:
        """Pipeline của job còn chạy?"""

    def artifact_names(self) -> tuple[str, ...]:
        """Danh sách artifact hợp lệ (hợp đồng với pipeline: out.mp4, metrics.csv, ...)."""


    def read_progress(self, job_dir: Path) -> dict | None:
        """{"frames","total","updated_at"} hoặc None."""

    def load_summary(self, job_dir: Path) -> dict | None:
        """summary.json hoặc None."""

    def artifact_path(self, job_dir: Path, name: str) -> str | None:
        """Đường dẫn artifact nếu tên hợp lệ và file đã có."""


@runtime_checkable
class VideoProbe(Protocol):
    """Đọc thông tin cơ bản từ file video (hiện thực: Cv2VideoProbe)."""

    def probe_size(self, path: Path) -> tuple[int, int] | None:
        """(rộng, cao) hoặc None nếu không đọc được."""

    def frame_jpeg(self, path: Path, index: int = 0) -> bytes | None:
        """Ảnh JPEG của frame thứ `index`, None nếu không đọc được."""


@runtime_checkable
class FrameSource(Protocol):
    """Nguồn frame trực tiếp cho chế độ live (hiện thực: OpenCvFrameSource).

    Tách khỏi `VideoProbe` vì vòng đời khác hẳn: probe chỉ đọc 1 frame rồi đóng,
    còn FrameSource mở liên tục và bị đọc theo nhịp từ thread phát sóng.
    """

    def start(self) -> None:
        """Mở nguồn; ném lỗi nếu không kết nối được."""

    def read_jpeg(self) -> bytes | None:
        """Frame mới nhất dạng JPEG, None nếu chưa có."""

    def stop(self) -> None:
        """Đóng nguồn, giải phóng thiết bị."""

    @property
    def label(self) -> str:
        """Mô tả nguồn để hiện trên UI."""


@runtime_checkable
class LiveTelemetrySource(Protocol):
    """Nguồn frame có SỐ LIỆU CHI TIẾT (hiện thực: WorkerFrameSource đọc status.json của worker).

    Tách thành port riêng: nguồn chỉ đưa frame (webcam, file) không cần biết gì về nhịp model.
    Service kiểm `isinstance(source, LiveTelemetrySource)` để quyết định có đọc số liệu hay không.
    """

    def telemetry(self) -> "LiveTelemetry":
        """Số liệu mới nhất của nguồn (rỗng/0 nếu worker chưa ghi)."""


@runtime_checkable
class HealthReportingSource(Protocol):
    """Nguồn frame có khả năng TỰ KHAI mình đã chết/treo (hiện thực: `WorkerFrameSource`,
    `OpenCvFrameSource`).

    Tách thành port riêng như `LiveTelemetrySource`: không phải nguồn nào cũng biết mình chết thế
    nào (`WorkerFrameSource` dựa vào tiến trình worker + tuổi `frame.jpg`; `OpenCvFrameSource` dựa
    vào số lần liên tiếp không đọc được frame). Service kiểm `isinstance` để quyết định có gọi
    `health()` hay không; adapter nào chưa cài thì `_read_safely` chỉ chặn thread đọc chết chứ
    không kết luận được nguồn hỏng. Xem AGENTS §6 — kiểu "hỏng mà trông như đang chạy" là lỗi đắt
    nhất lúc demo.
    """

    def health(self) -> SourceHealth | None:
        """None nếu nguồn còn khoẻ; SourceHealth kèm lý do nếu đã chết/treo/kết thúc."""
