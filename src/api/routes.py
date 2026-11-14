"""
Tầng HTTP — router mỏng: parse request → gọi service → ánh xạ sang DTO.

Chức năng: khai báo endpoint, validate đầu vào bằng Pydantic, chuyển JobView (miền) thành
           model response. Không chứa nghiệp vụ, không đụng đĩa, không chạy subprocess.
Input  : HTTP request.
Output : JSON theo `src/api/schemas.py`, file artifact, ảnh JPEG.
Lưu ý  : lỗi miền (JobNotFound, JobConflict, ...) do `main.register_error_handlers` ánh xạ sang
         mã HTTP — ở đây KHÔNG bắt exception của service để tránh lặp đi lặp lại try/except.
"""

import logging

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from src.api.domain import JobView
from src.api.schemas import (
    JobCreateResponse,
    JobListItem,
    JobStatusResponse,
    LiveSourceCandidate,
    LiveSourcesResponse,
    LiveStartRequest,
    LiveStatusResponse,
    ReidCue,
    SelectRequest,
    TrackParams,
)
from src.api.service import JobService

APP_VERSION = "0.1.0"

logger = logging.getLogger("doan.api.routes")


def _to_status_response(view: JobView) -> JobStatusResponse:
    """Chuyển thực thể miền → DTO của hợp đồng API (một chiều, không phụ thuộc ngược)."""
    return JobStatusResponse(
        job_id=view.job.job_id,
        state=view.status.state.value,
        progress=view.status.progress,
        message=view.status.message,
        created_at=view.job.created_at,
        bbox=list(view.job.bbox) if view.job.bbox else None,
        artifacts=view.artifacts,
        summary=view.summary,
    )


def _to_list_item(view: JobView) -> JobListItem:
    return JobListItem(
        job_id=view.job.job_id,
        state=view.status.state.value,
        progress=view.status.progress,
        message=view.status.message,
        created_at=view.job.created_at,
    )


def build_router(service: JobService, live, sources=None) -> APIRouter:
    """Dựng router với service + live service (+ bộ dò nguồn) được tiêm vào.

    `sources` là callable trả dict `{"suggested", "candidates"}`; None = không có bộ dò (test cũ,
    hoặc môi trường không muốn dò) ⇒ endpoint trả danh sách rỗng thay vì lỗi.
    """
    router = APIRouter()

    @router.get("/health")
    def health() -> dict:
        """Kiểm tra sống/chết — frontend gọi khi mở trang."""
        return {"status": "ok", "version": APP_VERSION}

    @router.post("/api/jobs", response_model=JobCreateResponse, status_code=201)
    async def create_job(
        file: UploadFile = File(..., description="video cần xử lý (mp4/avi/mov/mkv)"),
        image_size: int | None = Form(default=None, ge=64, le=1024),
        max_frames: int | None = Form(default=None, ge=1),
        max_trajectory: int | None = Form(default=None, ge=1),
        reid: bool = Form(default=False),
        cue: ReidCue = Form(default="object"),
    ) -> JobCreateResponse:
        """Nhận video, lưu ra đĩa theo từng MB, tạo job ở trạng thái `uploaded`."""
        params = TrackParams(
            image_size=image_size,
            max_frames=max_frames,
            max_trajectory=max_trajectory,
            reid=reid,
            cue=cue,
        ).model_dump()
        try:
            job = service.create_job(
                original_name=file.filename or "video",
                stream=file.file,
                params=params,
            )
        finally:
            await file.close()
        return JobCreateResponse(job_id=job.job_id, state="uploaded")

    @router.get("/api/jobs", response_model=list[JobListItem])
    def list_jobs(limit: int | None = Query(default=None, ge=1, le=200)) -> list:
        """Danh sách job mới nhất trước (không kèm summary)."""
        return [_to_list_item(view) for view in service.listing(limit)]

    @router.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
    def get_job(job_id: str) -> JobStatusResponse:
        """Trạng thái + tiến trình + URL artifact + summary của một job."""
        return _to_status_response(service.status(job_id))

    @router.get("/api/jobs/{job_id}/preview")
    def preview(job_id: str, index: int = Query(default=0, ge=0)) -> Response:
        """Ảnh JPEG một frame của video gốc — frontend vẽ lên canvas để chọn đối tượng."""
        data = service.preview(job_id, index)
        if data is None:
            raise HTTPException(status_code=404, detail="Không đọc được frame này của video")
        return Response(content=data, media_type="image/jpeg")

    @router.post("/api/jobs/{job_id}/select", status_code=202)
    def select_object(job_id: str, payload: SelectRequest) -> dict:
        """Nhận ô chọn đối tượng và khởi chạy pipeline ở nền."""
        box = payload.bbox
        service.select(job_id, (box.x, box.y, box.w, box.h))
        return {"job_id": job_id, "state": "queued"}

    @router.get("/api/jobs/{job_id}/artifacts/{name}")
    def get_artifact(job_id: str, name: str) -> FileResponse:
        """Tải một artifact (whitelist cứng ở tầng runner) — chống path traversal."""
        path = service.artifact_path(job_id, name)
        if path is None:
            raise HTTPException(status_code=404, detail="Không có file này")
        return FileResponse(path, filename=name)

    @router.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str) -> Response:
        """Xoá job (từ chối khi pipeline đang chạy)."""
        service.delete(job_id)
        return Response(status_code=204)

    # ------------------------------------------------------------------ live (Phase 4a)
    def _live_status(status) -> LiveStatusResponse:
        return LiveStatusResponse(
            state=status.state.value,
            source=status.source,
            device=status.device,
            frames=status.frames,
            measured_fps=status.measured_fps,
            display_fps=status.display_fps,
            mask_fps=status.mask_fps,
            stability=status.stability,
            stability_n=status.stability_n,
            latency_ms=status.latency_ms,
            empty_runs=status.empty_runs,
            empty_frac_window=status.empty_frac_window,
            empty_window_n=status.empty_window_n,
            drift_p05=status.drift_p05,
            drift_n=status.drift_n,
            mask_age_total_ms=status.mask_age_total_ms,
            mask_age_p95=status.mask_age_p95,
            age_n=status.age_n,
            message=status.message,
        )

    @router.get("/api/live/sources", response_model=LiveSourcesResponse,
                responses={200: {"headers": {"Cache-Control": {"schema": {"type": "string"}}}}})
    def live_sources(response: Response) -> LiveSourcesResponse:
        """Nguồn frame backend dò được, kèm nguồn GỢI Ý — UI tự điền để không phải dán URL.

        Dò có thể mở webcam/chờ HTTP ⇒ adapter `SourceProbe` tự cache (`CACHE_TTL_S`), và hàm này
        là `def` đồng bộ nên FastAPI chạy nó trong threadpool (không chặn event loop).
        """
        response.headers["Cache-Control"] = "no-store"    # kết quả dò là trạng thái SỐNG
        # Dựng DTO nằm TRONG try: một dict ứng viên thiếu khoá cũng không được biến thành 500.
        try:
            data = sources() if callable(sources) else {}
            candidates = []
            for raw in data.get("candidates", []):
                try:
                    candidates.append(LiveSourceCandidate(**raw))
                except Exception:         # noqa: BLE001 — bỏ ứng viên hỏng, giữ phần còn lại
                    logger.warning("bỏ ứng viên nguồn không hợp lệ: %r", raw, exc_info=True)
            return LiveSourcesResponse(
                suggested=data.get("suggested", ""),
                suggested_kind=data.get("suggested_kind", ""),
                checked_at=data.get("checked_at", ""),
                budget_ms=int(data.get("budget_ms", 0) or 0),
                candidates=candidates,
            )
        except Exception:                 # noqa: BLE001 — dò nguồn là TIỆN ÍCH, không được làm 500
            logger.warning("dò nguồn frame thất bại", exc_info=True)
            return LiveSourcesResponse()

    @router.post("/api/live/start", response_model=LiveStatusResponse)
    def start_live(payload: LiveStartRequest) -> LiveStatusResponse:
        """Mở nguồn frame và bắt đầu phát (nguồn lỗi → 400 qua lỗi miền SourceUnavailable)."""
        bbox = None
        if payload.bbox is not None:
            bbox = (payload.bbox.x, payload.bbox.y, payload.bbox.w, payload.bbox.h)
        return _live_status(
            live.start(payload.source, mode=payload.mode, bbox=bbox,
                       image_size=payload.image_size, vos_every=payload.vos_every,
                       mask_smoothing=payload.mask_smoothing)
        )

    @router.post("/api/live/stop", response_model=LiveStatusResponse)
    def stop_live() -> LiveStatusResponse:
        """Dừng phát và đóng nguồn (giải phóng webcam)."""
        return _live_status(live.stop())

    @router.get("/api/live/status", response_model=LiveStatusResponse)
    def live_status() -> LiveStatusResponse:
        """Trạng thái + số frame + FPS thực đo của phiên live."""
        return _live_status(live.status())

    @router.get("/api/live/frame")
    def live_frame() -> Response:
        """Một frame JPEG mới nhất (dùng để chụp ảnh/chọn đối tượng trên live)."""
        data = live.latest_jpeg()
        if data is None:
            # Đang nạp nguồn thì "hãy bật phát trước" là câu SAI ngữ cảnh (đã bật rồi) — ticket 16.
            if live.status().state.value == "loading":
                raise HTTPException(status_code=404,
                                    detail="Đang mở phiên live — chưa có frame")
            raise HTTPException(status_code=404, detail="Chưa có frame nào — hãy bật phát trước")
        return Response(content=data, media_type="image/jpeg")

    @router.get("/api/live/stream")
    def live_stream() -> StreamingResponse:
        """Luồng MJPEG (multipart/x-mixed-replace) — hiện trực tiếp bằng <img src>."""
        status = live.status()
        if status.state.value != "running":
            # Phân biệt "phiên lỗi" với "chưa bật": trước đây cả hai cùng một câu ⇒ khi watchdog báo
            # worker chết, client chỉ thấy "Chưa có phiên live nào đang chạy" (review 09-11, P3).
            if status.state.value == "error":
                raise HTTPException(
                    status_code=409,
                    detail=f"Phiên live đã dừng vì lỗi: {status.message or 'không rõ nguyên nhân'}",
                )
            if status.state.value == "loading":
                # Đang nạp nguồn (worker `track` 20–240 s): KHÔNG phải lỗi — câu này không được
                # đọc thành "phiên đã chết" (ticket 16).
                raise HTTPException(status_code=409,
                                    detail=f"Đang mở phiên live — chưa có frame: {status.message or ''}".strip())
            raise HTTPException(status_code=409, detail="Chưa có phiên live nào đang chạy")
        return StreamingResponse(
            live.frames(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store"},
        )

    return router
