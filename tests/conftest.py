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


# ---------------------------------------------------------------------------
# Adapter GIẢ cho tầng API — chứng minh service chỉ phụ thuộc port (DIP).
# Không dùng model SAM 2, không chạy subprocess, không cần video thật.
# ---------------------------------------------------------------------------


class FakeRunner:
    """Hiện thực `PipelineRunner` trong bộ nhớ, cho phép test điều khiển "pipeline" kết thúc."""

    def __init__(self):
        self.started = []          # [(job_id, params, bbox)]
        self.running = set()       # job_id đang "chạy"
        self.progress = {}         # {job_id: {"frames", "total"}}
        self.summaries = {}        # {job_id: dict}
        self._on_exit = {}         # {job_id: callback}
        self.fail_start = False

    def start(self, job_id, job_dir, *, params, bbox, on_exit=None):
        if self.fail_start:
            raise OSError("không chạy được bash")
        self.started.append((job_id, dict(params), tuple(bbox)))
        self.running.add(job_id)
        if on_exit is not None:
            self._on_exit[job_id] = on_exit
        return object()

    def complete(self, job_id, code=0, summary=None):
        """Giả lập pipeline kết thúc: chạy callback như adapter thật."""
        if summary is not None:
            self.summaries[job_id] = summary
        self.running.discard(job_id)
        callback = self._on_exit.pop(job_id, None)
        if callback is not None:
            callback(code)

    def is_running(self, job_id):
        return job_id in self.running

    def artifact_names(self):
        # Dùng đúng whitelist của production để test không bị lệch khi thêm artifact mới
        from src.worker import ARTIFACT_NAMES

        return tuple(ARTIFACT_NAMES)

    def read_progress(self, job_dir):
        return self.progress.get(os.path.basename(str(job_dir)))

    def load_summary(self, job_dir):
        return self.summaries.get(os.path.basename(str(job_dir)))

    def artifact_path(self, job_dir, name):
        if name not in self.artifact_names() or "/" in name or ".." in name:
            return None
        path = os.path.join(str(job_dir), name)
        return path if os.path.isfile(path) else None


class FakeProbe:
    """Hiện thực `VideoProbe` cố định — không cần OpenCV."""

    def __init__(self, size=(64, 48), jpeg=b"\xff\xd8fake-jpeg"):
        self.size = size
        self.jpeg = jpeg
        self.requests = []

    def probe_size(self, job_dir):
        return self.size

    def frame_jpeg(self, job_dir, index=0):
        self.requests.append((str(job_dir), index))
        return self.jpeg


@pytest.fixture
def api_settings(tmp_path):
    """Cấu hình API trỏ vào tmp_path — không bao giờ ghi vào data/jobs thật."""
    from src.api.config import ApiSettings

    return ApiSettings(jobs_root=tmp_path / "jobs")


@pytest.fixture
def fs_store(api_settings):
    from src.api.adapters import FileSystemJobStore

    return FileSystemJobStore(
        api_settings.jobs_root,
        max_upload_bytes=api_settings.max_upload_bytes,
        chunk_bytes=api_settings.chunk_bytes,
    )


@pytest.fixture
def fake_runner():
    return FakeRunner()


@pytest.fixture
def fake_probe():
    return FakeProbe()


@pytest.fixture
def make_probe():
    """Trả về LỚP FakeProbe để test tạo biến thể (VD jpeg=None)."""
    return FakeProbe


@pytest.fixture
def service(fs_store, fake_runner, fake_probe, api_settings):
    """JobService lắp bằng adapter giả — chứng minh service không phụ thuộc hạ tầng."""
    from src.api.service import JobService

    return JobService(fs_store, fake_runner, fake_probe, api_settings)


class FakeFrameSource:
    """Hiện thực `FrameSource` trong bộ nhớ — không cần webcam, không cần OpenCV."""

    def __init__(self, source, *, jpeg=b"\xff\xd8fake-frame", fail_on_start=False):
        self.source = source
        self._jpeg = jpeg
        self._fail = fail_on_start
        self.started = False
        self.stopped = False
        self._seq = 0

    def start(self):
        if self._fail:
            raise OSError("nguồn đang bận (giả lập)")
        self.started = True

    def read_jpeg(self):
        """Mỗi lần đọc trả frame KHÁC nhau (giống camera) — service chỉ đếm frame MỚI."""
        if not self.started:
            return None
        self._seq += 1
        return self._jpeg + b"#" + str(self._seq).encode()

    def stop(self):
        self.stopped = True

    @property
    def label(self):
        return f"giả:{self.source}"


@pytest.fixture
def make_frame_source():
    """Nhà máy FrameSource giả; giữ danh sách nguồn đã tạo để test kiểm tra đã đóng chưa."""
    created = []

    def factory(source, mode="raw", bbox=None, image_size=None, vos_every=None,
                mask_smoothing=None):
        item = FakeFrameSource(source)
        item.mode = mode
        item.bbox = bbox
        item.image_size = image_size
        item.vos_every = vos_every
        item.mask_smoothing = mask_smoothing
        created.append(item)
        return item

    factory.created = created
    return factory


@pytest.fixture
def live_service(make_frame_source):
    from src.api.live import LiveStreamService

    return LiveStreamService(make_frame_source, target_fps=50)


@pytest.fixture
def live_client(service, live_service, api_settings):
    """TestClient có cả JobService giả và LiveStreamService giả."""
    from fastapi.testclient import TestClient

    from src.api.main import create_app

    return TestClient(create_app(settings=api_settings, service=service, live=live_service))


@pytest.fixture
def failing_source():
    """Nhà máy trả về nguồn LUÔN lỗi khi start — test nhánh lỗi mở nguồn."""

    def factory(source="0", *args, **kwargs):
        return FakeFrameSource(source, fail_on_start=True)

    return factory
