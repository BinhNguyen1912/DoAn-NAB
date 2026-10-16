"""Helper chia sẻ giữa các test: ghi chuỗi frame (fixture) thành file video tạm + engine SAMURAI."""
import os

import cv2
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CKPT_TINY = os.path.join(REPO_ROOT, "samurai", "sam2", "checkpoints", "sam2.1_hiera_tiny.pt")


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


@pytest.fixture(scope="session")
def samurai_engine():
    """Engine SAMURAI dựng 1 lần cho cả session (build model ~20–60s). Chỉ dùng trong test slow."""
    if not os.path.isfile(CKPT_TINY):
        pytest.skip("checkpoint sam2.1_hiera_tiny chưa tải")

    # Tắt progress bar tqdm của predictor khi chạy test
    import sam2.sam2_video_predictor as vp

    real_tqdm = vp.tqdm
    vp.tqdm = lambda it, *a, **k: it
    try:
        from src.tracker_engine import TrackerEngine

        yield TrackerEngine.build_default()
    finally:
        vp.tqdm = real_tqdm