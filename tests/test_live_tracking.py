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
    # vos_every=1: chạy VOS mỗi frame để test logic cũ (hybrid có test riêng bên dưới)
    return LiveTrackConfig(source=source, out_dir=tmp_path / "live", display_fps=100,
                           vos_every=1, **kwargs)


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

        # bbox.json là (x, y, w, h); SAM 2 nhận (x1, y1, x2, y2) ⇒ (5,5,5+20,5+16)
        assert engine.started_with == (5, 5, 25, 21)
        assert stats.frames == 3
        assert stats.measured_fps > 0
        assert stats.bbox and len(stats.bbox) == 4
        frame = (out / FRAME_NAME).read_bytes()
        assert frame[:2] == b"\xff\xd8"                    # JPEG hợp lệ

    def test_o_chon_xywh_duoc_doi_sang_xyxy_truoc_khi_start(self, video_source, tmp_path):
        """`bbox.json` là (x, y, w, h) nhưng SAM 2 nhận (x1, y1, x2, y2) — bug thật 10-11."""
        engine = FakeEngine()
        out = tmp_path / "live"
        _pre_select(out, (10, 12, 20, 24))          # x=10, y=12, w=20, h=24
        LiveTrackingSession(engine, LiveTrackConfig(
            source=video_source, out_dir=out, display_fps=100, vos_every=1,
            loop_files=True)).run(stop_event=_StopAfter(3))

        assert engine.started_with == (10, 12, 30, 36), "phải là (x1,y1,x2,y2), không phải (x,y,w,h)"

    def test_status_duoc_ghi_moi_frame(self, video_source, tmp_path):
        out = tmp_path / "live"
        out.mkdir(parents=True, exist_ok=True)
        (out / BBOX_NAME).write_text(json.dumps({"x": 5, "y": 5, "w": 20, "h": 16}),
                                     encoding="utf-8")
        LiveTrackingSession(FakeEngine(), _config(video_source, tmp_path,
                                                  stop_after_frames=1)).run()
        status = json.loads((out / STATUS_NAME).read_text(encoding="utf-8"))
        assert set(status) == {"state", "frames", "vos_runs", "measured_fps", "vos_fps",
                               "vos_ms", "lk_ms", "stability", "stability_shown", "mask_holds",
                               "mask_drops", "lost_streak", "bbox", "message"}

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


def _pre_select(out_dir, bbox=(20, 12, 10, 10)):
    """Ghi sẵn ô chọn (như người dùng đã kéo trên UI) để vào thẳng chế độ bám."""
    out_dir = out_dir if isinstance(out_dir, __import__("pathlib").Path) else __import__("pathlib").Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / BBOX_NAME).write_text(
        json.dumps({"x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3]}), encoding="utf-8"
    )


class _SlowFakeEngine(FakeEngine):
    """Engine giả ĐẮT như SAM 2 thật: mỗi lần process "tốn" thời gian để lộ chi phí thật."""

    def __init__(self, cost_s=0.05):
        super().__init__()
        self.cost_s = cost_s

    def process(self, frame):
        import time

        time.sleep(self.cost_s)
        return super().process(frame)


@pytest.fixture
def textured_video(write_video, tmp_path):
    """Video có TEXTURE + ô sáng dịch dần: LK cần gradient mới bám được (nền phẳng thì LK bó tay)."""
    rng = np.random.default_rng(11)
    frames = []
    for step in range(12):
        frame = rng.integers(50, 110, size=(48, 64, 3), dtype=np.uint8)
        x = 20 + step
        frame[12:22, x:x + 10] = 230
        frames.append(frame)
    return str(write_video(tmp_path / "textured.mp4", np.stack(frames), fps=10))


class TestHybridVosAndLk:
    """Phase 4c: VOS cách quãng + LK lấp frame giữa (mask chỉ mới ở nhịp VOS)."""

    def test_chi_chay_vos_moi_n_frame(self, textured_video, tmp_path):
        engine = FakeEngine()
        out = tmp_path / "live"
        _pre_select(out)
        config = LiveTrackConfig(source=textured_video, out_dir=out,
                                 display_fps=100, vos_every=3, loop_files=True)
        stats = LiveTrackingSession(engine, config).run(stop_event=_StopAfter(24))

        # literal: start() 1 lần + process() cho các frame index chia hết cho 3
        assert stats.frames >= 11
        assert stats.vos_runs == engine.processed
        assert stats.vos_runs < stats.frames, "VOS phải chạy ÍT hơn số frame phát"
        assert stats.vos_runs <= stats.frames // 2

    def test_frame_lk_van_co_o_bao_va_mask(self, textured_video, tmp_path):
        """Frame LK phải cho ra ô bao + mask DỊCH theo (không phải mask cũ đứng yên)."""
        engine = FakeEngine()
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(engine, LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=4, loop_files=True))
        stats = session.run(stop_event=_StopAfter(24))

        assert stats.bbox[0] > 0            # ô bao vẫn tiến theo thời gian nhờ LK
        assert stats.lk_ms > 0             # có frame LK thật
        assert stats.vos_ms > 0            # và có frame VOS thật
        assert stats.lost_streak == 0

    def test_vos_every_1_thi_tat_lk(self, textured_video, tmp_path):
        engine = FakeEngine()
        out = tmp_path / "live"
        _pre_select(out)
        stats = LiveTrackingSession(engine, LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=1,
            loop_files=True)).run(stop_event=_StopAfter(8))

        assert stats.vos_runs == stats.frames      # VOS mỗi frame, không có frame LK
        assert stats.lk_ms == 0.0

    def test_hud_va_status_co_so_lieu_hai_nhip(self, textured_video, tmp_path):
        engine = FakeEngine()
        out = tmp_path / "live"
        _pre_select(out)
        LiveTrackingSession(engine, LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=3,
            loop_files=True)).run(stop_event=_StopAfter(20))

        status = json.loads((out / STATUS_NAME).read_text(encoding="utf-8"))
        assert status["vos_runs"] > 0
        assert status["frames"] > status["vos_runs"]
        assert status["vos_ms"] > 0
        # HUD phải tách nhịp VOS khỏi nhịp phát — không được gộp thành một con số FPS
        assert set(status) >= {"vos_fps", "vos_ms", "lk_ms"}

    def test_engine_dat_thi_display_fps_cao_hon_vos_fps(self, textured_video, tmp_path):
        """Bằng chứng cho mục tiêu Phase 4c: model tốn 50 ms nhưng vòng phát vẫn nhanh hơn."""
        engine = _SlowFakeEngine(cost_s=0.05)
        out = tmp_path / "live"
        _pre_select(out)
        stats = LiveTrackingSession(engine, LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=4,
            loop_files=True)).run(stop_event=_StopAfter(24))

        assert stats.measured_fps > stats.vos_fps, (
            f"hybrid không có tác dụng: display {stats.measured_fps} vs VOS {stats.vos_fps}")


class _BlinkingEngine(FakeEngine):
    """Engine giả NHẤP NHÁY: cứ mỗi lần gọi lại trả mask rỗng (mô phỏng model "chớp" mất vật)."""

    def __init__(self):
        super().__init__()
        self._blink = False

    def process(self, frame):
        result = super().process(frame)
        self._blink = not self._blink
        if self._blink:
            result.mask = np.zeros(frame.shape[:2], dtype=bool)
        return result


class TestMaskStability:
    """Phase 4d: làm mượt mask + đo độ ổn định (IoU giữa hai mask VOS liên tiếp)."""

    def _run(self, tmp_path, engine, smoothing):
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(engine, LiveTrackConfig(
            source=str(tmp_path / "x.mp4"), out_dir=out, display_fps=100, vos_every=1,
            loop_files=True, mask_smoothing=smoothing))
        drawn = []
        session._annotate = lambda frame, result, _d=drawn: (
            _d.append(getattr(result, "mask", None)), frame.copy())[1]
        stats = session.run(stop_event=_StopAfter(10))
        return stats, drawn

    def test_lam_muot_khong_de_mask_chop_tat(self, textured_video, tmp_path, monkeypatch):
        monkeypatch.setattr(LiveTrackConfig, "source", str(textured_video), raising=False)
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(_BlinkingEngine(), LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=1,
            loop_files=True, mask_smoothing=0.5))
        drawn = []
        session._annotate = lambda frame, result, _d=drawn: (
            _d.append(getattr(result, "mask", None)), frame.copy())[1]
        session.run(stop_event=_StopAfter(12))

        assert drawn, "phải có frame được vẽ"
        # bỏ frame đầu (chưa có mẫu để trộn) — các frame sau không được TẮT hẳn
        assert all(m is not None and m.any() for m in drawn[1:]), \
            "mask chớp tắt lọt ra màn hình dù đã bật làm mượt"

    def test_tat_lam_muot_thi_mask_chop_van_lo_ra(self, textured_video, tmp_path):
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(_BlinkingEngine(), LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=1,
            loop_files=True, mask_smoothing=1.0))
        drawn = []
        session._annotate = lambda frame, result, _d=drawn: (
            _d.append(getattr(result, "mask", None)), frame.copy())[1]
        stats = session.run(stop_event=_StopAfter(12))

        assert any(m is not None and not m.any() for m in drawn), \
            "tắt làm mượt thì phải thấy đúng hiện tượng nhấp nháy (test đối chứng)"
        assert stats.stability < 1.0, "mask nhấp nháy ⇒ stability < 1"

    def test_status_co_do_on_dinh(self, textured_video, tmp_path):
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(FakeEngine(), LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=2,
            loop_files=True))
        session.run(stop_event=_StopAfter(12))

        status = json.loads((out / STATUS_NAME).read_text(encoding="utf-8"))
        assert 0.0 <= status["stability"] <= 1.0
