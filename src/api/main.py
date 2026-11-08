"""
Composition root — nơi DUY NHẤT biết chọn hiện thực nào cho từng port.

Chức năng: `create_app()` dựng FastAPI, lắp adapter cụ thể vào JobService, gắn router, đăng ký
           ánh xạ lỗi miền → mã HTTP, và mount frontend đã build (nếu có).
Input  : ApiSettings (tuỳ chọn) và JobService (tuỳ chọn — test tiêm bản giả).
Output : FastAPI app; biến module `app` để `uvicorn src.api.main:app` dùng.
Lưu ý  : đổi sang SQLite/S3/GPU worker chỉ cần sửa `build_default_service` (hoặc tiêm app khác);
         service/routes/domain không phải sửa một dòng.
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.adapters import (
    Cv2VideoProbe,
    FileSystemJobStore,
    OpenCvFrameSource,
    SubprocessPipelineRunner,
    WorkerFrameSource,
)
from src.api.config import ApiSettings
from src.api.domain import (
    LiveBusy,
    InvalidBBox,
    JobConflict,
    JobNotFound,
    PayloadTooLarge,
    RunnerStartFailed,
    SourceUnavailable,
    UnsupportedMedia,
)
from src.api.live import LIVE_READ_FPS, LiveStreamService
from src.api.routes import APP_VERSION, build_router
from src.api.service import JobService
from src.worker import REPO_ROOT

logger = logging.getLogger("doan.api")

# Thư mục chứa bản build frontend (mount ở "/" khi tồn tại)
WEB_DIST = Path(REPO_ROOT) / "web" / "dist"

# Lỗi miền → (mã HTTP, thông điệp mặc định khi exception không có message)
_ERROR_MAP = (
    (JobNotFound, 404, "Không tìm thấy job"),
    (JobConflict, 409, "Thao tác không hợp lệ với trạng thái hiện tại của job"),
    (InvalidBBox, 400, "Ô chọn không hợp lệ"),
    (UnsupportedMedia, 400, "Định dạng không được hỗ trợ"),
    (PayloadTooLarge, 413, "Video quá lớn"),
    (RunnerStartFailed, 500, "Không chạy được pipeline"),
    (SourceUnavailable, 400, "Không mở được nguồn frame"),
    (LiveBusy, 409, "Đang mở một phiên live khác — chờ vài giây rồi thử lại"),
)


def build_default_service(settings: ApiSettings) -> JobService:
    """Lắp ghép hiện thực mặc định: filesystem + subprocess + OpenCV."""
    store = FileSystemJobStore(
        settings.jobs_root,
        max_upload_bytes=settings.max_upload_bytes,
        chunk_bytes=settings.chunk_bytes,
    )
    return JobService(
        store=store,
        runner=SubprocessPipelineRunner(REPO_ROOT),
        probe=Cv2VideoProbe(),
        settings=settings,
    )


def build_default_live() -> LiveStreamService:
    """Lắp ghép phiên live: mode "raw" = OpenCV tại chỗ, mode "track" = worker model riêng."""

    def make_source(source, mode="raw", bbox=None, image_size=None, vos_every=None,
                    mask_smoothing=None):
        if mode == "track":
            # Mặc định 192: đo trên máy này 192 ≈ 10 FPS, 256 ≈ 6,5 FPS, 1024 ≈ 0,4 FPS.
            return WorkerFrameSource(source, bbox=bbox, image_size=image_size or 192,
                                     vos_every=vos_every, mask_smoothing=mask_smoothing)
        return OpenCvFrameSource(source)

    # 30 Hz khớp `--max-fps` mặc định của worker: đọc chậm hơn nhịp ghi sẽ báo FPS sai (trần = nhịp đọc)
    return LiveStreamService(make_source, target_fps=LIVE_READ_FPS)


def register_error_handlers(app: FastAPI) -> None:
    """Ánh xạ lỗi miền sang mã HTTP — routes không phải try/except từng chỗ."""
    for exc_type, status, default_message in _ERROR_MAP:

        def _handler(_request: Request, exc: Exception, _status=status,
                     _default=default_message) -> JSONResponse:
            return JSONResponse(status_code=_status, content={"detail": str(exc) or _default})

        app.add_exception_handler(exc_type, _handler)


def mount_frontend(app: FastAPI) -> None:
    """Phục vụ frontend đã build ở "/" (mount SAU router để /api/... vẫn khớp trước)."""
    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
        return

    @app.get("/")
    def root_info() -> dict:
        return {
            "service": "Camera AI Tracking API",
            "version": APP_VERSION,
            "docs": "/docs",
            "note": "chưa có web/dist — chạy `./run web` để API phục vụ luôn giao diện",
        }


def create_app(settings: ApiSettings | None = None,
                service: JobService | None = None,
                live: LiveStreamService | None = None) -> FastAPI:
    """Application factory: điểm lắp ghép phụ thuộc duy nhất của tầng API."""
    settings = settings or ApiSettings.from_env(REPO_ROOT)
    service = service or build_default_service(settings)
    live = live or build_default_live()

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        """Tắt API (kể cả `uvicorn --reload`) phải dừng worker model — không để nó mồ côi."""
        yield
        try:
            # `live.stop()` là hàm blocking (join thread + killpg tới ~7 s) ⇒ chạy ngoài event loop
            await asyncio.to_thread(live.stop)
        except Exception:                       # noqa: BLE001 — dọn dẹp không được ném
            logger.warning("dừng live khi shutdown gặp lỗi", exc_info=True)

    app = FastAPI(
        lifespan=_lifespan,
        title="Camera AI Tracking API",
        version=APP_VERSION,
        description="Nhận video → chọn đối tượng → bám bằng SAM 2 (VOS) → trả mask, quỹ đạo, số liệu.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.service = service
    app.state.live = live
    app.include_router(build_router(service, live))
    register_error_handlers(app)
    mount_frontend(app)

    return app


app = create_app()
