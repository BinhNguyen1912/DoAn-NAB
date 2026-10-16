"""Helper chia sẻ giữa các test: ghi chuỗi frame (fixture) thành file video tạm."""
import cv2
import pytest


@pytest.fixture
def write_video():
    """Trả về hàm write(path, frames, fps) — ghi frames (N,H,W,3 uint8) thành file video MJPG."""

    def _write(path, frames, fps=30):
        h, w = frames.shape[1], frames.shape[2]
        out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
        assert out.isOpened(), f"Không ghi được video tới {path}"
        for frame in frames:
            out.write(frame)
        out.release()
        return path

    return _write