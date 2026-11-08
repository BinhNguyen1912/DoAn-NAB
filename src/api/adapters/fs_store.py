"""
Adapter lưu trữ trên filesystem — hiện thực `JobStore` (không cần database cho đồ án).

Chức năng: tạo/đọc/ghi job + trạng thái + video upload, liệt kê và xoá job.
Input  : jobs_root (Path), max_upload_bytes, chunk_bytes.
Output : Job / JobStatus; file trong `<jobs_root>/<job_id>/`.
Lưu ý  : job_id sinh theo `%Y%m%d-%H%M%S-<6hex>` và được VALIDATE bằng regex trước mọi thao tác
         đĩa (chống path traversal). Ghi JSON luôn atomic (file tạm + os.replace).
         Muốn đổi sang SQLite/S3: viết class khác cùng chữ ký `src.api.ports.JobStore`.
"""

import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from src.api.domain import Job, JobState, JobStatus, PayloadTooLarge, parse_state
from src.worker.command import LOG_NAME, SOURCE_NAME

_JOB_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")

# File cố định trong thư mục job
JOB_FILE = "job.json"
STATUS_FILE = "status.json"


class FileSystemJobStore:
    """Hiện thực JobStore bằng thư mục + file JSON (mỗi job một thư mục)."""

    def __init__(self, root: Path, *, max_upload_bytes: int, chunk_bytes: int) -> None:
        self._root = Path(root)
        self._max_bytes = max_upload_bytes
        self._chunk = chunk_bytes

    # ------------------------------------------------------------------ đường dẫn

    def path(self, job_id: str) -> Path:
        """Thư mục job; ném ValueError nếu job_id sai định dạng (hàng rào traversal)."""
        if not _JOB_ID_RE.match(job_id or ""):
            raise ValueError(f"job_id không hợp lệ: {job_id!r}")
        return self._root / job_id

    # ------------------------------------------------------------------ ghi

    def create(self, *, original_name: str, params: dict) -> Job:
        self._root.mkdir(parents=True, exist_ok=True)
        job_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        path = self.path(job_id)
        path.mkdir(parents=True, exist_ok=False)

        job = Job(
            job_id=job_id,
            # mili-giây: hai job tạo trong cùng một giây vẫn phân biệt được thứ tự
            created_at=datetime.now().isoformat(timespec="milliseconds"),
            original_name=original_name,
            params=dict(params or {}),
        )
        self._write_job(job)
        self.save_status(job_id, JobStatus(JobState.UPLOADED, 0, ""))
        return job

    def save_video(self, job_id: str, stream) -> int:
        """Ghi luồng upload ra source.mp4 theo từng chunk (không nạp cả video vào RAM)."""
        target = self.path(job_id) / SOURCE_NAME
        total = 0
        with open(target, "wb") as out:
            while True:
                chunk = stream.read(self._chunk)
                if not chunk:
                    break
                total += len(chunk)
                if total > self._max_bytes:
                    out.close()
                    target.unlink(missing_ok=True)
                    raise PayloadTooLarge(
                        f"video vượt quá {self._max_bytes // (1024 * 1024)} MB"
                    )
                out.write(chunk)
        return total

    def save_status(self, job_id: str, status: JobStatus) -> JobStatus:
        data = {
            "state": status.state.value,
            "progress": max(0, min(100, int(status.progress))),
            "message": status.message,
            "updated_at": float(status.updated_at or datetime.now().timestamp()),
        }
        self._write_json(self.path(job_id) / STATUS_FILE, data)
        return JobStatus(
            state=status.state, progress=data["progress"],
            message=status.message, updated_at=data["updated_at"],
        )

    def save_bbox(self, job_id: str, bbox: tuple[int, int, int, int]) -> None:
        job = self.get(job_id)
        if job is None:
            return
        self._write_job(
            Job(job_id=job.job_id, created_at=job.created_at, original_name=job.original_name,
                params=job.params, bbox=tuple(int(v) for v in bbox))
        )

    # ------------------------------------------------------------------ đọc

    def get(self, job_id: str) -> Job | None:
        try:
            path = self.path(job_id) / JOB_FILE
        except ValueError:
            return None
        data = self._read_json(path)
        if not isinstance(data, dict):
            return None
        bbox = data.get("bbox")
        return Job(
            job_id=job_id,
            created_at=str(data.get("created_at", "")),
            original_name=str(data.get("original_name", "")),
            params=dict(data.get("params") or {}),
            bbox=tuple(int(v) for v in bbox) if bbox else None,
        )

    def read_status(self, job_id: str) -> JobStatus:
        try:
            data = self._read_json(self.path(job_id) / STATUS_FILE)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            return JobStatus(JobState.UPLOADED, 0, "", 0.0)
        return JobStatus(
            state=parse_state(data.get("state")),
            progress=int(data.get("progress", 0) or 0),
            message=str(data.get("message", "")),
            updated_at=float(data.get("updated_at", 0.0) or 0.0),
        )

    def list_ids(self, limit: int) -> list[str]:
        """Id các job, MỚI NHẤT TRƯỚC — sắp theo `created_at` (không theo tên thư mục).

        Lưu ý: tên thư mục chỉ có độ phân giải 1 giây + 6 hex ngẫu nhiên ⇒ sắp theo tên sẽ
        cho thứ tự không xác định với các job tạo cùng giây (bug thật 08-11).
        """
        if not self._root.is_dir():
            return []
        entries = []
        for path in self._root.iterdir():
            if not path.is_dir() or not _JOB_ID_RE.match(path.name):
                continue
            data = self._read_json(path / JOB_FILE) or {}
            entries.append((str(data.get("created_at", "")), path.name))
        # Sắp giảm dần; tên làm khoá phụ để kết quả luôn xác định
        entries.sort(reverse=True)
        return [name for _created_at, name in entries[:limit]]

    # ------------------------------------------------------------------ xoá

    def delete(self, job_id: str) -> None:
        path = self.path(job_id)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)

    # ------------------------------------------------------------------ tiện ích

    def log_path(self, job_id: str) -> Path:
        """Đường dẫn log của pipeline (adapter runner dùng để ghi stdout/stderr)."""
        return self.path(job_id) / LOG_NAME

    def _write_job(self, job: Job) -> None:
        self._write_json(
            self.path(job.job_id) / JOB_FILE,
            {
                "job_id": job.job_id,
                "created_at": job.created_at,
                "original_name": job.original_name,
                "params": job.params,
                "bbox": list(job.bbox) if job.bbox else None,
            },
        )

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    @staticmethod
    def _read_json(path: Path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
