"""
JobService — toàn bộ use case của hệ thống, chỉ phụ thuộc PORT (không biết hạ tầng).

Chức năng: tạo job từ luồng upload, chọn đối tượng rồi khởi chạy pipeline, tổng hợp trạng thái
           (kể cả suy ra % tiến trình thật), liệt kê/xoá job, lấy ảnh preview.
Input  : JobStore + PipelineRunner + VideoProbe + ApiSettings (tiêm qua constructor).
Output : Job / JobView hoặc ném lỗi miền (JobNotFound, JobConflict, InvalidBBox, ...).
Lưu ý  : KHÔNG import fastapi/cv2/subprocess ở đây. Nhờ vậy service test được bằng adapter giả,
         và có thể tái sử dụng từ CLI sau này mà không cần dựng HTTP server.
"""

import logging
from pathlib import Path
from typing import BinaryIO

from src.api.config import ApiSettings
from src.api.domain import (
    ACTIVE_STATES,
    Job,
    JobConflict,
    JobNotFound,
    JobState,
    JobStatus,
    JobView,
    PayloadTooLarge,
    RunnerStartFailed,
    UnsupportedMedia,
    assert_bbox_inside,
    can_select,
    clamp_percent,
    progress_percent,
)
from src.api.ports import JobStore, PipelineRunner, VideoProbe

logger = logging.getLogger("doan.api.service")

MSG_RUNNING = "Đang bám đối tượng..."
MSG_DONE = "Xong — đã có video kết quả"
MSG_UPLOADED = "Đã nhận video, chờ chọn đối tượng"
MSG_START_FAILED = "Không chạy được pipeline: {error}"
MSG_DIED = "Pipeline dừng mà không có kết quả — xem worker.log"
MSG_PIPELINE_ERROR = "Pipeline lỗi (mã {code}) — xem worker.log"

ALLOWED_CUES = ("face", "object", "both")


class JobService:
    """Điều phối use case; mọi I/O đi qua port được tiêm vào."""

    def __init__(self, store: JobStore, runner: PipelineRunner, probe: VideoProbe,
                 settings: ApiSettings) -> None:
        self._store = store
        self._runner = runner
        self._probe = probe
        self._settings = settings

    # ------------------------------------------------------------------ lệnh (commands)

    def create_job(self, *, original_name: str, stream: BinaryIO, params: dict) -> Job:
        """Tạo job + lưu video. Ném UnsupportedMedia / PayloadTooLarge."""
        self._assert_supported(original_name)
        self._assert_cue(params.get("cue"))

        job = self._store.create(original_name=original_name, params=params)
        try:
            size = self._store.save_video(job.job_id, stream)
        except PayloadTooLarge:
            # Không để lại rác: job chưa dùng được thì xoá luôn
            self._store.delete(job.job_id)
            raise
        self._store.save_status(job.job_id, JobStatus(JobState.UPLOADED, 0, MSG_UPLOADED))
        logger.info("nhận video %r cho job %s (%.1f MB)", original_name, job.job_id, size / 1e6)
        return job

    def select(self, job_id: str, bbox: tuple[int, int, int, int]) -> JobStatus:
        """Chọn đối tượng rồi khởi chạy pipeline ở nền. Ném JobNotFound/JobConflict/InvalidBBox."""
        job = self._require(job_id)
        status = self._store.read_status(job_id)
        if not can_select(status):
            raise JobConflict("Job đang chạy hoặc đã xong")

        assert_bbox_inside(bbox, self._probe.probe_size(self._store.path(job_id)))
        self._store.save_bbox(job_id, bbox)

        # Ghi RUNNING TRƯỚC khi start: nếu pipeline xong rất nhanh, callback on_exit sẽ ghi
        # DONE sau đó — không bị dòng RUNNING ghi đè ngược lại (race thật gặp ở bản MVP).
        started = self._store.save_status(job_id, JobStatus(JobState.RUNNING, 0, MSG_RUNNING))
        try:
            self._runner.start(
                job.job_id,
                self._store.path(job_id),
                params=job.params,
                bbox=bbox,
                on_exit=lambda code: self._on_exit(job_id, code),
            )
        except OSError as exc:
            self._store.save_status(
                job_id, JobStatus(JobState.ERROR, 0, MSG_START_FAILED.format(error=exc))
            )
            raise RunnerStartFailed(str(exc)) from exc
        return started

    def delete(self, job_id: str) -> None:
        """Xoá job; ném JobConflict nếu pipeline đang chạy."""
        self._require(job_id)
        if self._runner.is_running(job_id):
            raise JobConflict("Job đang chạy — không xoá được")
        self._store.delete(job_id)

    # ------------------------------------------------------------------ truy vấn (queries)

    def status(self, job_id: str) -> JobView:
        """Trạng thái mới nhất + artifact + summary (tự cập nhật từ tiến trình thật)."""
        job = self._require(job_id)
        status = self._refresh(job_id)
        return JobView(
            job=job,
            status=status,
            artifacts=self._artifact_urls(job_id),
            summary=self._runner.load_summary(self._store.path(job_id)),
        )

    def listing(self, limit: int | None = None) -> list[JobView]:
        """Các job mới nhất trước (không kèm summary cho nhẹ)."""
        views: list[JobView] = []
        for job_id in self._store.list_ids(limit or self._settings.list_limit):
            job = self._store.get(job_id)
            if job is None:          # job vừa bị xoá giữa lúc liệt kê
                continue
            views.append(
                JobView(job=job, status=self._refresh(job_id),
                        artifacts=self._artifact_urls(job_id))
            )
        return views

    def preview(self, job_id: str, index: int = 0) -> bytes | None:
        """Ảnh JPEG một frame của video gốc; None nếu không đọc được."""
        self._require(job_id)
        return self._probe.frame_jpeg(self._store.path(job_id), index)

    def artifact_path(self, job_id: str, name: str) -> str | None:
        """Đường dẫn artifact hợp lệ; None nếu tên ngoài whitelist hoặc chưa có file."""
        self._require(job_id)
        return self._runner.artifact_path(self._store.path(job_id), name)

    # ------------------------------------------------------------------ nội bộ

    def _require(self, job_id: str) -> Job:
        job = self._store.get(job_id)
        if job is None:
            raise JobNotFound(job_id)
        return job

    def _assert_supported(self, original_name: str) -> None:
        suffix = Path(original_name or "").suffix.lower()
        if suffix not in self._settings.allowed_extensions:
            allowed = ", ".join(sorted(self._settings.allowed_extensions))
            raise UnsupportedMedia(
                f"định dạng không hỗ trợ ({suffix or 'không rõ'}) — chỉ nhận {allowed}"
            )

    @staticmethod
    def _assert_cue(cue: str | None) -> None:
        if cue is not None and cue not in ALLOWED_CUES:
            raise UnsupportedMedia("cue phải là face | object | both")

    def _artifact_urls(self, job_id: str) -> dict:
        """{tên file: URL} cho artifact đã tồn tại — frontend hiện nút tải."""
        job_path = self._store.path(job_id)
        return {
            name: f"/api/jobs/{job_id}/artifacts/{name}"
            for name in self._runner.artifact_names()
            if self._runner.artifact_path(job_path, name) is not None
        }

    def _refresh(self, job_id: str) -> JobStatus:
        """Suy trạng thái thật từ tiến trình/kết quả rồi lưu lại.

        Thứ tự kiểm tra RẤT quan trọng: `summary.json` được pipeline ghi TRƯỚC khi tiến trình
        thoát, còn bản H.264 cho web được xuất SAU đó. Nếu thấy summary là báo done ngay thì
        UI sẽ hiện player khi chưa có `out_web.mp4` → Chrome không phát được video.
        Vì vậy: chỉ `done` khi runner đã thực sự xong (is_running = False).
        """
        status = self._store.read_status(job_id)
        if status.state not in ACTIVE_STATES:
            return status

        job_path = self._store.path(job_id)
        summary = self._runner.load_summary(job_path)

        percent = clamp_percent(status.progress)
        progress = self._runner.read_progress(job_path)
        if progress:
            computed = progress_percent(progress.get("frames") or 0, progress.get("total"))
            if computed is not None:
                percent = computed

        if self._runner.is_running(job_id):
            return self._store.save_status(
                job_id, JobStatus(JobState.RUNNING, percent, MSG_RUNNING)
            )

        if summary is not None:
            return self._store.save_status(job_id, JobStatus(JobState.DONE, 100, MSG_DONE))

        # Tiến trình không còn chạy và không có kết quả (server restart, bị kill...)
        return self._store.save_status(job_id, JobStatus(JobState.ERROR, percent, MSG_DIED))

    def _on_exit(self, job_id: str, returncode: int) -> None:
        """Callback khi pipeline kết thúc (chạy trong thread của runner)."""
        logger.info("pipeline job %s kết thúc với mã %s", job_id, returncode)
        if returncode == 0:
            self._store.save_status(job_id, JobStatus(JobState.DONE, 100, MSG_DONE))
        else:
            current = self._store.read_status(job_id)
            self._store.save_status(
                job_id,
                JobStatus(JobState.ERROR, current.progress,
                          MSG_PIPELINE_ERROR.format(code=returncode)),
            )
