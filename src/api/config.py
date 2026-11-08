"""
Cấu hình tầng API — tập trung một chỗ, đọc từ biến môi trường, bất biến.

Chức năng: gom mọi "con số chính trị" (thư mục job, giới hạn upload, đuôi file cho phép,
           CORS, chunk đọc file) vào một dataclass frozen để không rải rác trong code.
Input  : biến môi trường (tuỳ chọn) + repo_root.
Output : ApiSettings (bất biến) — truyền vào service/adapter qua constructor (DIP).
Lưu ý  : test đổi `DOAN_JOBS_ROOT` để không ghi vào data/jobs thật.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ALLOWED_EXTENSIONS = frozenset({".mp4", ".avi", ".mov", ".mkv"})
DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


@dataclass(frozen=True)
class ApiSettings:
    """Tham số cấu hình của API (không đọc env ở đây — dùng `from_env`)."""

    jobs_root: Path
    max_upload_bytes: int = 500 * 1024 * 1024        # 500 MB
    chunk_bytes: int = 1024 * 1024                   # 1 MB mỗi lần đọc khi lưu upload
    list_limit: int = 50
    allowed_extensions: frozenset = field(default=DEFAULT_ALLOWED_EXTENSIONS)
    cors_origins: tuple = DEFAULT_CORS_ORIGINS

    @classmethod
    def from_env(cls, repo_root: Path) -> "ApiSettings":
        """Dựng cấu hình từ biến môi trường (DOAN_JOBS_ROOT) — mặc định `<repo>/data/jobs`."""
        root = os.environ.get("DOAN_JOBS_ROOT")
        return cls(jobs_root=Path(root) if root else Path(repo_root) / "data" / "jobs")
