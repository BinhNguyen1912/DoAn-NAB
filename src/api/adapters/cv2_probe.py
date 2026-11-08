"""
Adapter đọc video bằng OpenCV — hiện thực `VideoProbe`.

Chức năng: lấy (rộng, cao) để kiểm tra ô chọn, và xuất 1 frame thành JPEG cho canvas chọn đối tượng.
Input  : thư mục job (chứa source.mp4), chỉ số frame.
Output : tuple kích thước / bytes JPEG; None khi không đọc được.
Lưu ý  : đây là NƠI DUY NHẤT của tầng API import cv2 — service và routes không biết OpenCV.
"""

from pathlib import Path

import cv2

from src.api.ports import VideoProbe
from src.worker.command import SOURCE_NAME


class Cv2VideoProbe(VideoProbe):
    """Đọc thông tin video gốc của job bằng cv2.VideoCapture."""

    def __init__(self, *, source_name: str = SOURCE_NAME, jpeg_quality: int = 85) -> None:
        self._source_name = source_name
        self._quality = int(jpeg_quality)

    def probe_size(self, job_dir: Path):
        cap = cv2.VideoCapture(str(self._video_path(job_dir)))
        try:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        finally:
            cap.release()
        return (width, height) if width > 0 and height > 0 else None

    def frame_jpeg(self, job_dir: Path, index: int = 0):
        path = self._video_path(job_dir)
        if not path.is_file():
            return None
        cap = cv2.VideoCapture(str(path))
        try:
            if index > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = cap.read()
        finally:
            cap.release()
        if not ok or frame is None:
            return None
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self._quality])
        return bytes(buffer) if ok else None

    def _video_path(self, job_dir: Path) -> Path:
        return Path(job_dir) / self._source_name
