"""Client mỏng cho Hive AI (thehive.ai) — moderation / AI-generated content detection.

Repo DoAn-NAB vốn KHÔNG cần Hive cho việc bám đối tượng; module này được thêm theo yêu cầu để có
một cổng gọi ngoài đúng chuẩn. Không tự hardcode loại task: caller truyền `tasks` theo đúng schema
của Hive (vd ``{"type": "moderation"}``, ``{"type": "visual_moderation"}``,
``{"type": "ai_generated_image_detection"}``).

Auth: header ``authorization: token <HIVE_API_KEY>``. Key đọc từ biến môi trường ``HIVE_API_KEY``;
nếu chưa có thì đọc `.env` ở ROOT repo (chỉ setdefault — biến môi trường thật luôn thắng).
Key KHÔNG BAO GIỜ commit (xem `.env.example`).

Base URL đã kiểm tra chạy thật (POST không kèm key trả 400 "Invalid Auth Method" ⇒ host+path đúng):
    https://api.thehive.ai/api/v2/task/sync
    https://api.thehive.ai/api/v2/task/async
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

API_KEY_ENV = "HIVE_API_KEY"
SYNC_URL = "https://api.thehive.ai/api/v2/task/sync"
ASYNC_URL = "https://api.thehive.ai/api/v2/task/async"

# File `.env` đọc khi biến môi trường chưa có. Đặt thành hằng số để test trỏ sang file giả.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class HiveError(RuntimeError):
    """Lỗi khi gọi Hive: thiếu key / HTTP lỗi / trả về JSON không hợp lệ."""


def _ensure_dotenv() -> None:
    """Nạp `.env` nếu tồn tại — chỉ `setdefault` nên KHÔNG ghi đè biến môi trường thật."""
    if not _ENV_PATH.exists():
        return
    try:
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _api_key() -> str:
    _ensure_dotenv()
    key = os.environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise HiveError(f"thiếu {API_KEY_ENV} — đặt biến môi trường (xem .env.example)")
    return key


def submit_sync(payload: dict, *, api_key: str | None = None, url: str = SYNC_URL) -> dict:
    """Gửi MỘT task đồng bộ tới Hive, trả kết quả JSON (đã parse).

    `payload` theo đúng schema của Hive, ví dụ::

        {"url": "https://.../anh.jpg", "tasks": [{"type": "moderation"}]}

    Thiếu key ⇒ `HiveError` (KHÔNG im lặng trả kết quả rỗng — bẫy "không có key mà tưởng chạy").
    """
    key = api_key or _api_key()
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"token {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise HiveError(f"Hive HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise HiveError(f"không tới được Hive: {exc.reason}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise HiveError(f"Hive trả JSON không hợp lệ: {body[:200]!r}") from exc
