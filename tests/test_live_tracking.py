"""Test `src/live_tracking.py` (phiên bám trực tiếp) + `tools/live_worker.py` (dựng lệnh).

Dùng engine GIẢ (FakeEngine duck-type start/process) — không cần torch, không cần checkpoint.
"""

import json

import numpy as np
import pytest

from src.live_tracking import (
    BBOX_NAME,
    FRAME_NAME,
    STATE_ERROR,
    STATE_STOPPED,
    STATE_TRACKING,
    STATE_WAITING,
    STATUS_NAME,
    LiveTrackConfig,
    LiveTrackingSession,
    read_bbox,
)


class _Result:
    """Giống `TrackingResult` của src/tracker_engine (duck-type)."""

    def __init__(self, frame_idx, bbox, mask):
        self.frame_idx = frame_idx
        self.bbox = bbox
        self.mask = mask
        self.elapsed_ms = 12.5


class FakeEngine:
    """Engine giả: start() cần bbox, process() trả mask chữ nhật dịch dần."""

    def __init__(self):
        self.started_with = None
        self.processed = 0

    def start(self, frame, bbox):
        self.started_with = tuple(int(v) for v in bbox)
        self.processed = 1
        return self._result(0, self.started_with, frame.shape)

    def process(self, frame):
        self.processed += 1
        x = self.started_with[0] + self.processed
        bbox = (x, self.started_with[1], x + 10, self.started_with[1] + 10)
        return self._result(self.processed, bbox, frame.shape)

    @staticmethod
    def _result(index, bbox, shape):
        mask = np.zeros(shape[:2], bool)
        mask[bbox[1]:bbox[3], bbox[0]:bbox[2]] = True
        return _Result(index, bbox, mask)


@pytest.fixture
def video_source(write_video, tmp_path):
    frames = np.full((6, 48, 64, 3), 90, np.uint8)
    return str(write_video(tmp_path / "live.mp4", frames, fps=10))


def _config(source, tmp_path, **kwargs):
    return LiveTrackConfig(source=source, out_dir=tmp_path / "live", max_fps=100, **kwargs)


class TestLiveTrackingSession:
    def test_chua_co_bbox_thi_phat_khung_hinh_va_o_waiting(self, video_source, tmp_path):
        # Chưa có bbox thì vòng lặp CHỜ vô hạn (đúng ý đồ: người dùng còn đang chọn) →
        # test phải tự dừng bằng stop_event, giống worker thật dừng bằng SIGTERM.
        session = LiveTrackingSession(FakeEngine(), _config(video_source, tmp_path))
        stats = session.run(stop_event=_StopAfter(4))

        # không có bbox → engine không bao giờ start, nhưng vẫn có frame để UI hiện
        assert stats.state == STATE_STOPPED
        assert stats.frames == 0
        assert (tmp_path / "live" / FRAME_NAME).is_file()
        assert json.loads((tmp_path / "live" / STATUS_NAME).read_text(encoding="utf-8"))["state"] \
            == STATE_STOPPED

    def test_co_bbox_thi_bam_va_ghi_frame_overlay(self, video_source, tmp_path):
        engine = FakeEngine()
        out = tmp_path / "live"
        out.mkdir(parents=True, exist_ok=True)
        (out / BBOX_NAME).write_text(json.dumps({"x": 5, "y": 5, "w": 20, "h": 16}),
                                     encoding="utf-8")

        stats = LiveTrackingSession(engine, _config(video_source, tmp_path,
                                                     stop_after_frames=3)).run()

        # SAM 2 dùng prompt dạng (x, y, w, h) — giữ nguyên, không đổi sang x1y1x2y2
        assert engine.started_with == (5, 5, 20, 16)
        assert stats.frames == 3
        assert stats.measured_fps > 0
        assert stats.bbox and len(stats.bbox) == 4
        frame = (out / FRAME_NAME).read_bytes()
        assert frame[:2] == b"\xff\xd8"                    # JPEG hợp lệ

    def test_status_duoc_ghi_moi_frame(self, video_source, tmp_path):
        out = tmp_path / "live"
        out.mkdir(parents=True, exist_ok=True)
        (out / BBOX_NAME).write_text(json.dumps({"x": 5, "y": 5, "w": 20, "h": 16}),
                                     encoding="utf-8")
        LiveTrackingSession(FakeEngine(), _config(video_source, tmp_path,
                                                  stop_after_frames=1)).run()
        status = json.loads((out / STATUS_NAME).read_text(encoding="utf-8"))
        assert set(status) == {"state", "frames", "measured_fps", "inference_ms",
                               "lost_streak", "bbox", "message"}

    def test_file_duoc_lap_lai_khi_chay_lien_tuc(self, video_source, tmp_path):
        """Video 6 frame nhưng chạy liên tục → phải lặp lại, không dừng ở frame 6."""
        out = tmp_path / "live"
        out.mkdir(parents=True, exist_ok=True)
        (out / BBOX_NAME).write_text(json.dumps({"x": 5, "y": 5, "w": 20, "h": 16}),
                                     encoding="utf-8")
        stats = LiveTrackingSession(FakeEngine(), _config(video_source, tmp_path)).run(
            stop_event=_StopAfter(15)
        )
        assert stats.frames >= 10

    def test_stop_event_dung_vong_lap(self, video_source, tmp_path):
        stats = LiveTrackingSession(FakeEngine(), _config(video_source, tmp_path)).run(
            stop_event=_StopAfter(3)
        )
        assert stats.state == STATE_STOPPED


class _StopAfter:
    """stop_event giả: set sau N lần kiểm tra (để test vòng lặp có đường thoát)."""

    def __init__(self, checks):
        self._left = checks

    def is_set(self):
        self._left -= 1
        return self._left <= 0


class TestReadBbox:
    @pytest.mark.parametrize("payload", [
        {}, {"x": 0, "y": 0, "w": 0, "h": 5}, {"x": "a"}, None,
    ])
    def test_bbox_hong_tra_none(self, tmp_path, payload):
        path = tmp_path / BBOX_NAME
        if payload is not None:
            path.write_text(json.dumps(payload), encoding="utf-8")
        assert read_bbox(path) is None

    def test_bbox_hop_le(self, tmp_path):
        path = tmp_path / BBOX_NAME
        path.write_text(json.dumps({"x": 1, "y": 2, "w": 30, "h": 40}), encoding="utf-8")
        assert read_bbox(path) == (1, 2, 30, 40)


class TestHangSoTrangThai:
    def test_cac_trang_thai_duoc_dung_dung_ten(self):
        assert (STATE_WAITING, STATE_TRACKING, STATE_ERROR, STATE_STOPPED) == (
            "waiting_selection", "tracking", "error", "stopped",
        )


class TestLenhWorker:
    def test_lenh_chua_source_outdir_va_image_size(self, tmp_path):
        from src.worker import build_live_worker_command

        argv = build_live_worker_command("0", tmp_path, image_size=192, repo_root=tmp_path)
        cmd = argv[2]
        assert argv[0] == "bash"
        assert "conda activate samurai" in cmd
        assert "tools/live_worker.py" in cmd
        assert "--source 0" in cmd
        assert "--out-dir" in cmd
        assert "--image-size 192" in cmd

    def test_khong_truyen_image_size_khi_none(self, tmp_path):
        from src.worker import build_live_worker_command

        assert "--image-size" not in build_live_worker_command("0", tmp_path,
                                                               repo_root=tmp_path)[2]
