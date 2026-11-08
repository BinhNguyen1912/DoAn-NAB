"""
Xuất bản video PHÁT ĐƯỢC TRÊN TRÌNH DUYỆT (H.264) từ bản ghi của OpenCV (mp4v).

Chức năng: chuyển `out.mp4` (fourcc FMP4/mp4v do cv2.VideoWriter ghi) sang `out_web.mp4`
           H.264 + yuv420p + faststart — thứ Chrome/Edge/Firefox giải mã được.
Input  : đường dẫn file nguồn, đích (mặc định cùng thư mục), ffmpeg (tuỳ chọn), timeout.
Output : đường dẫn file web, hoặc None nếu không có ffmpeg / chuyển mã thất bại.
Lưu ý  : đo 08-11 bằng Chrome headless thật — `canPlayType('video/mp4; codecs="mp4v.20.9"')`
         trả về "" và videoWidth = 0, tức bản mp4v KHÔNG phát được trên web. Vì vậy bước này
         là bắt buộc cho UI, nhưng KHÔNG được làm hỏng pipeline: mọi lỗi chỉ trả None.
         ffmpeg lấy theo thứ tự: biến môi trường DOAN_FFMPEG → imageio-ffmpeg (pip, có libx264)
         → ffmpeg trong PATH. Không cần sudo.
"""

import os
import shutil
import subprocess
from pathlib import Path

WEB_NAME = "out_web.mp4"
FFMPEG_ENV = "DOAN_FFMPEG"
DEFAULT_TIMEOUT_S = 300


def find_ffmpeg() -> str | None:
    """Tìm ffmpeg có libx264; None nếu không có bản nào dùng được."""
    override = os.environ.get(FFMPEG_ENV)
    if override and Path(override).is_file():
        return override
    try:                                  # imageio-ffmpeg: binary tĩnh kèm libx264, cài bằng pip
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:                     # noqa: BLE001 — thiếu package không phải lỗi nghiêm trọng
        pass
    return shutil.which("ffmpeg")


def build_transcode_command(ffmpeg: str, src: Path, dst: Path) -> list[str]:
    """Lệnh chuyển mã: H.264 (libx264) + yuv420p + faststart để phát ngay trên web."""
    return [
        ffmpeg, "-y", "-loglevel", "error",
        "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",        # Chrome/Safari không giải mã yuv444p
        "-movflags", "+faststart",   # đặt moov ở đầu file → phát được ngay, không cần tải hết
        str(dst),
    ]


def transcode_for_web(src, dst=None, *, ffmpeg: str | None = None,
                      timeout: int = DEFAULT_TIMEOUT_S) -> str | None:
    """Tạo bản H.264 cạnh file gốc; trả đường dẫn bản web hoặc None nếu không làm được."""
    source = Path(src)
    if not source.is_file():
        return None
    target = Path(dst) if dst is not None else source.with_name(WEB_NAME)
    if target.exists():
        target.unlink()               # tránh đọc nhầm bản cũ khi chuyển mã thất bại

    exe = ffmpeg or find_ffmpeg()
    if not exe:
        return None
    try:
        result = subprocess.run(
            build_transcode_command(exe, source, target),
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        target.unlink(missing_ok=True)
        return None
    if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        return None
    return str(target)
