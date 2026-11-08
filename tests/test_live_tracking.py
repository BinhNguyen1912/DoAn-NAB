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
        bat_buoc = {
            "state", "frames", "vos_runs", "measured_fps", "vos_fps", "vos_ms", "lk_ms",
            "stability", "stability_shown", "empty_runs", "mask_holds", "mask_drops",
            "drift_iou", "drift_iou_p05", "drift_n", "mask_age_ms", "mask_age_total_ms",
            "mask_age_p95", "age_n",
            "lost_streak", "bbox", "message"}
        # SUPERSET + ALLOWLIST: thêm chỉ số mới cho báo cáo không phải sửa test mỗi lần, NHƯNG
        # khoá lạ vẫn phải đỏ (typo `vos_fsp` bên cạnh `vos_fps` sẽ lọt nếu chỉ dùng superset —
        # adapter đọc theo tên nên typo = báo 0 im lặng; review 08-11).
        cho_phep = bat_buoc | set()          # thêm khoá mới vào đây khi mở rộng status.json
        assert bat_buoc <= set(status), f"thiếu khoá: {bat_buoc - set(status)}"
        la = set(status) - cho_phep
        assert not la, f"khoá lạ chưa khai báo trong allowlist: {la}"

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
        """`stability` phải NẰM TRONG khoảng và > 0 ở ca bình thường (metric bị gut = 0.0 phải đỏ)."""
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(FakeEngine(), LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=2,
            loop_files=True))
        session.run(stop_event=_StopAfter(12))

        status = json.loads((out / STATUS_NAME).read_text(encoding="utf-8"))
        assert 0.0 <= status["stability"] <= 1.0
        assert status["stability"] > 0.5, (
            "FakeEngine dịch mask 1 px/lần ⇒ IoU phải cao; = 0 nghĩa là metric không được tính")
        assert status["empty_runs"] == 0


class _LostObjectEngine(FakeEngine):
    """Engine giả mô phỏng ĐÚNG hợp đồng thật: mất vật ⇒ mask rỗng + bbox (0,0,0,0).

    Đây là ca làm lộ lỗi P1 (review độc lập 08-11): bộ lọc mask dịch bộ tích luỹ theo bbox
    (0,0,0,0) nên "teleport" và hold không bao giờ chạy.
    """

    def __init__(self, *, lost_at=(2, 3, 6), cost_s=0.0):
        super().__init__()
        self._lost_at = set(lost_at)
        self._cost_s = cost_s

    def process(self, frame):
        import time

        if self._cost_s:
            time.sleep(self._cost_s)
        result = super().process(frame)
        if self.processed in self._lost_at:
            result.mask = np.zeros(frame.shape[:2], dtype=bool)
            result.bbox = (0, 0, 0, 0)      # hợp đồng thật của src/tracker_engine.py
        return result


class TestLoiReviewDocLap:
    """Test hồi quy cho các lỗi do review độc lập tìm ra (P1 + nhóm P2)."""

    def test_p1_mask_rong_kem_bbox_0_khong_teleport_bo_loc(self, textured_video, tmp_path):
        """P1: VOS trả mask rỗng + bbox (0,0,0,0) ⇒ hold phải GIỮ mask ở ĐÚNG vị trí cũ."""
        engine = _LostObjectEngine(lost_at=(2,))
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(engine, LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=1,
            loop_files=True, mask_smoothing=0.5))
        drawn = []
        session._annotate = lambda frame, result, _d=drawn: (
            _d.append(getattr(result, "mask", None)), frame.copy())[1]
        stats = session.run(stop_event=_StopAfter(10))

        assert stats.mask_holds >= 1, "lần mask rỗng đầu tiên phải được GIỮ, không được tắt ngay"
        assert stats.mask_drops == 0, "một lần chớp không được tính là mất dấu"
        # KHÔNG được teleport: MỌI mask đã vẽ phải nằm quanh vị trí cũ, không nhảy về góc (0,0).
        # (Quét toàn bộ thay vì `drawn[2]`: index phụ thuộc frame start() nên test cũ xanh cả khi
        # revert fix — review lần 2 chỉ ra.)
        for index, mask in enumerate(drawn):
            assert mask is not None and mask.any(), f"frame {index}: mask bị tắt dù chưa quá max_hold"
            ys, xs = np.nonzero(mask)
            assert xs.min() > 5 and ys.min() > 5, (
                f"frame {index}: mask nhảy về góc khung (x={xs.min()}, y={ys.min()}) — bộ lọc bị teleport")

    def test_p1_mat_dau_lien_tuc_thi_van_tat_sau_max_hold(self, textured_video, tmp_path):
        engine = _LostObjectEngine(lost_at=(2, 3, 4, 5, 6, 7))
        out = tmp_path / "live"
        _pre_select(out)
        stats = LiveTrackingSession(engine, LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=1,
            loop_files=True, mask_smoothing=0.5)).run(stop_event=_StopAfter(9))

        assert stats.mask_drops >= 1, "mất dấu thật (nhiều lần liên tiếp) phải tắt mask"

    def test_p2_duong_hybrid_that_su_co_lam_muot(self, textured_video, tmp_path):
        """P2: bug cũ là `_store_vos` không gọi `_smooth` ⇒ hybrid KHÔNG hề làm mượt mà CI vẫn xanh."""
        engine = _LostObjectEngine(lost_at=tuple(range(2, 9)), cost_s=0.01)
        out = tmp_path / "live"
        _pre_select(out)
        stats = LiveTrackingSession(engine, LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=2,
            loop_files=True, mask_smoothing=0.5)).run(stop_event=_StopAfter(20))

        assert stats.vos_runs > 1 and stats.frames > stats.vos_runs
        assert stats.mask_holds >= 1, "đường hybrid phải áp dụng bộ lọc (nếu không là tái phát bug P2)"
        assert stats.mask_drops >= 1

    def test_p2_stability_khong_bao_100_phan_tram_khi_mat_dau(self, textured_video, tmp_path):
        """P2: hai mask RỖNG liên tiếp có IoU = 1,0 ⇒ UI báo 'ổn định 100 %' khi mất dấu hoàn toàn."""
        engine = _LostObjectEngine(lost_at=tuple(range(2, 30)))
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(engine, LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=1, loop_files=True))
        stats = session.run(stop_event=_StopAfter(12))

        status = json.loads((out / STATUS_NAME).read_text(encoding="utf-8"))
        assert status["empty_runs"] >= 2, "phải đếm số lần VOS trả mask rỗng"
        assert status["stability"] < 0.999, "mất dấu mà báo stability = 1,0 là số liệu sai"
        assert stats.empty_runs >= 2

    def test_p2_loi_trong_luong_vos_phai_thanh_state_error(self, textured_video, tmp_path):
        class _BrokenEngine(FakeEngine):
            def process(self, frame):
                if self.processed >= 2:
                    raise RuntimeError("hết RAM (giả lập)")
                return super().process(frame)

        out = tmp_path / "live"
        _pre_select(out)
        stats = LiveTrackingSession(_BrokenEngine(), LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=2,
            loop_files=True)).run(stop_event=_StopAfter(50))

        status = json.loads((out / STATUS_NAME).read_text(encoding="utf-8"))
        assert status["state"] == STATE_ERROR, "luồng VOS chết mà báo 'tracking' là phát mask chết"
        assert "model lỗi" in status["message"]
        assert stats.state == STATE_ERROR

    def test_p2_loi_trong_callback_luong_vos_cung_phai_bao_error(self, textured_video, tmp_path):
        """Lỗi ở `_store_vos`/`_smooth` (dữ liệu model bất thường) — không chỉ `process` — cũng phải
        thành `state=error`; trước đây `_on_result` nằm NGOÀI try/except nên thread chết im lặng."""
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(_LostObjectEngine(lost_at=(1, 2, 3), cost_s=0.01),
                                       LiveTrackConfig(source=textured_video, out_dir=out,
                                                       display_fps=100, vos_every=2,
                                                       loop_files=True))
        calls = {"n": 0}
        original = session._smooth

        def exploding(result):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise RuntimeError("dữ liệu model bất thường (giả lập)")
            return original(result)

        session._smooth = exploding
        stats = session.run(stop_event=_StopAfter(40))

        status = json.loads((out / STATUS_NAME).read_text(encoding="utf-8"))
        assert status["state"] == STATE_ERROR
        assert "model lỗi" in status["message"]
        assert stats.state == STATE_ERROR

    def test_p2_stability_shown_khong_bao_100_phan_tram_khi_trong(self, textured_video, tmp_path):
        """`stability_shown` là metric anh em của `stability` — phải cùng guard (review lần 2)."""
        engine = _LostObjectEngine(lost_at=tuple(range(2, 30)))
        out = tmp_path / "live"
        _pre_select(out)
        LiveTrackingSession(engine, LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=1,
            loop_files=True, mask_smoothing=0.5)).run(stop_event=_StopAfter(14))

        status = json.loads((out / STATUS_NAME).read_text(encoding="utf-8"))
        assert status["empty_runs"] >= 2
        assert status["stability_shown"] < 0.999, "màn hình trống mà báo IoU 1,0 là số liệu sai"

    def test_p3_o_bao_mong_1px_van_duoc_coi_la_hop_le(self):
        from src.live_tracking import _bbox_hop_le

        assert _bbox_hop_le((10, 10, 10, 40))     # mask 1 cột
        assert _bbox_hop_le((10, 10, 40, 10))     # mask 1 hàng
        assert not _bbox_hop_le((0, 0, 0, 0))     # mask rỗng
        assert not _bbox_hop_le((5, 5, 3, 9))     # toạ độ đảo
        assert not _bbox_hop_le(None)

    def test_p2_mask_smoothing_0_bi_tu_choi_ro_rang(self, textured_video, tmp_path):
        with pytest.raises(ValueError, match="mask_smoothing"):
            LiveTrackConfig(source=textured_video, out_dir=tmp_path / "x", mask_smoothing=0.0)

    def test_p2_vos_every_0_bi_tu_choi(self, textured_video, tmp_path):
        with pytest.raises(ValueError, match="vos_every"):
            LiveTrackConfig(source=textured_video, out_dir=tmp_path / "x", vos_every=0)

    def test_p3_trang_thai_loading_cung_bo_khoa_voi_phien_chay(self, textured_video, tmp_path):
        """P3: hai tác giả của status.json ⇒ người đọc trong lúc nạp model thấy schema khác."""
        from src.live_tracking import LiveTrackStats, status_payload
        from tools.live_worker import _write_loading

        out = tmp_path / "live"
        out.mkdir(parents=True, exist_ok=True)
        _write_loading(out, "Đang nạp model...")
        loading = json.loads((out / STATUS_NAME).read_text(encoding="utf-8"))

        assert set(loading) == set(status_payload(LiveTrackStats()))
        assert loading["state"] == "loading"

    def test_p3_lk_mat_dau_thi_tra_ve_o_bao_cu_khong_bia(self, textured_video, tmp_path):
        """LK fail (nền phẳng) không được crash và không được bịa vị trí mới."""
        from src.light_tracker import LkBoxTracker

        class _FlatEngine(_LostObjectEngine):
            def __init__(self):
                super().__init__(lost_at=())

        class _BlindLk(LkBoxTracker):
            def update(self, gray):
                return None, False

        out = tmp_path / "live"
        _pre_select(out)
        stats = LiveTrackingSession(_FlatEngine(), LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=3,
            loop_files=True), lk_tracker=_BlindLk()).run(stop_event=_StopAfter(12))

        assert stats.frames > 0
        assert stats.bbox[2] > stats.bbox[0]        # ô bao vẫn hợp lệ (lấy từ lần VOS)


class TestCoLenhWorker:
    """`build_live_worker_command` phải chuyển đúng tham số hybrid xuống CLI (P2 review 08-11)."""

    def test_truyen_vos_every_va_mask_smoothing(self, tmp_path):
        from src.worker import build_live_worker_command

        argv = build_live_worker_command("0", tmp_path, vos_every=3, mask_smoothing=0.5,
                                         repo_root=tmp_path)
        joined = " ".join(argv)
        assert "--vos-every 3" in joined
        assert "--mask-smoothing 0.5" in joined

    def test_khong_truyen_thi_de_mac_dinh_cua_cli(self, tmp_path):
        """None = để CLI quyết định (vos_every 3, mask_smoothing 1.0 = tắt) — không ghi đè."""
        from src.worker import build_live_worker_command

        joined = " ".join(build_live_worker_command("0", tmp_path, repo_root=tmp_path))
        assert "--vos-every" not in joined
        assert "--mask-smoothing" not in joined


class TestVeSinhWorkerCu:
    """Worker mồ côi (uvicorn --reload) phải bị dọn trước khi mở phiên mới (review 08-11 vòng đời)."""

    def _spawn_fake_worker(self, tmp_path):
        """Tiến trình giả có 'live_worker' trong cmdline (đúng điều kiện nhận diện)."""
        import subprocess
        import sys

        # argv giống worker thật: có phần tử tên `live_worker.py` + cờ `--out-dir <dir>`
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)", "live_worker.py",
             "--out-dir", str(tmp_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        return proc

    def test_reap_worker_cu_con_song(self, tmp_path):
        from src.api.adapters.worker_source import PID_NAME, WorkerFrameSource

        proc = self._spawn_fake_worker(tmp_path)
        try:
            (tmp_path / PID_NAME).write_text(str(proc.pid), encoding="utf-8")
            WorkerFrameSource("0", out_dir=tmp_path)._prepare_dir()

            assert proc.poll() is not None, "worker cũ còn sống phải bị dọn"
            assert not (tmp_path / PID_NAME).exists()
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)

    def test_khong_giet_pid_bi_tai_su_dung(self, tmp_path):
        """pidfile trỏ vào tiến trình KHÔNG phải live_worker (pid reuse) ⇒ không được kill."""
        import subprocess
        import sys

        from src.api.adapters.worker_source import PID_NAME, WorkerFrameSource

        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        try:
            (tmp_path / PID_NAME).write_text(str(proc.pid), encoding="utf-8")
            WorkerFrameSource("0", out_dir=tmp_path)._prepare_dir()
            assert proc.poll() is None, "không được giết tiến trình lạ trùng pid"
        finally:
            proc.kill()
            proc.wait(timeout=5)

    def test_khong_giet_tien_trinh_chi_khop_chuoi_live_worker(self, tmp_path):
        """`grep live_worker` / `vim tools/live_worker.py` cũng khớp substring ⇒ phải bị chặn."""
        import subprocess
        import sys

        from src.api.adapters.worker_source import PID_NAME, WorkerFrameSource

        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                                  "grep", "live_worker", "--out-dir", str(tmp_path)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        try:
            (tmp_path / PID_NAME).write_text(str(proc.pid), encoding="utf-8")
            WorkerFrameSource("0", out_dir=tmp_path)._prepare_dir()
            assert proc.poll() is None, "chỉ khớp CHUỖI 'live_worker' thì không được coi là worker"
        finally:
            proc.kill()
            proc.wait(timeout=5)

    def test_khong_giet_worker_cua_thu_muc_khac(self, tmp_path):
        """Hai instance API dùng chung /dev/shm: không được giết worker của instance kia."""
        import subprocess
        import sys

        from src.api.adapters.worker_source import PID_NAME, WorkerFrameSource

        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                                 "live_worker.py", "--out-dir", str(tmp_path / "khac")],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        try:
            (tmp_path / PID_NAME).write_text(str(proc.pid), encoding="utf-8")
            WorkerFrameSource("0", out_dir=tmp_path)._prepare_dir()
            assert proc.poll() is None, "worker của thư mục KHÁC phải được để yên"
        finally:
            proc.kill()
            proc.wait(timeout=5)

    def test_reap_khong_cho_zombie_5_giay(self, tmp_path):
        """Vòng chờ cũ coi zombie là 'còn sống' ⇒ luôn đợi đủ 5 s (review 08-11)."""
        import time

        from src.api.adapters.worker_source import PID_NAME, WorkerFrameSource

        proc = self._spawn_fake_worker(tmp_path)
        try:
            (tmp_path / PID_NAME).write_text(str(proc.pid), encoding="utf-8")
            began = time.perf_counter()
            WorkerFrameSource("0", out_dir=tmp_path)._prepare_dir()
            elapsed = time.perf_counter() - began

            assert proc.poll() is not None
            assert elapsed < 3.0, f"reap mất {elapsed:.1f} s (>2 s là dấu hiệu chờ zombie)"
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)

    def test_pidfile_hong_thi_bo_qua(self, tmp_path):
        from src.api.adapters.worker_source import PID_NAME, WorkerFrameSource

        (tmp_path / PID_NAME).write_text("không phải số", encoding="utf-8")
        WorkerFrameSource("0", out_dir=tmp_path)._prepare_dir()      # không được ném


class TestMaskLechKichThuoc:
    """Nguồn đổi độ phân giải giữa phiên (relay snapshot, điện thoại xoay) ⇒ không IndexError."""

    def test_annotate_bo_mask_sai_kich_thuoc(self):
        from src.live_tracking import _FrameResult, LiveTrackingSession

        class _Noop:
            def start(self, frame, bbox): ...
            def process(self, frame): ...

        cfg = LiveTrackConfig(source="x", out_dir="/tmp/khong-dung", vos_every=1)
        session = LiveTrackingSession(_Noop(), cfg)
        frame = np.zeros((48, 64, 3), np.uint8)
        wrong = np.zeros((100, 100), bool)          # mask của độ phân giải khác
        wrong[10:20, 10:20] = True

        image = session._annotate(frame, _FrameResult(1, (10, 10, 20, 20), wrong, 1.0))
        assert image.shape == frame.shape           # không ném, không vẽ mask sai


class TestDriftVaTuoiMask:
    """`drift_iou` (nội suy LK lệch bao nhiêu) + `mask_age` — câu hỏi nền của kiến trúc hybrid.

    Các test dưới đây cố tình khoá bằng **số literal / số đếm mẫu**, không so hai lần chạy với
    nhau: bản trước so `vos_every=1` với `vos_every=6` nên vẫn XANH khi xoá sạch tính năng (cả hai
    vế đều 0,0) — review 08-11 bắt đúng lỗi đó.
    """

    def test_iou_bbox_toa_do_bao_gom(self):
        from src.live_tracking import _bbox_iou

        assert _bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
        assert _bbox_iou((0, 0, 10, 10), (11, 11, 21, 21)) == 0.0
        # (0,0)-(10,10) ∩ (5,0)-(15,10): 6 cột × 11 hàng = 66; mỗi hộp 121 ⇒ 66/176
        assert _bbox_iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(66 / 176)

    def test_o_bao_suy_bien_tra_none_khong_tra_0(self):
        """Toạ độ bao gồm ⇒ hộp 1 px rộng vẫn CÓ diện tích (IoU 1,0 khi trùng nhau).

        Còn hộp đảo (`x2 < x1`) thì không đủ tin để chấm ⇒ trả `None` cho bên gọi BỎ mẫu, thay vì
        trả 0,0 (0,0 sẽ bị tính là "nội suy lệch hoàn toàn").
        """
        from src.live_tracking import _bbox_iou

        assert _bbox_iou((10, 10, 10, 40), (10, 10, 10, 40)) == 1.0
        assert _bbox_iou((10, 10, 5, 5), (10, 10, 5, 5)) is None

    def test_measure_drift_bang_iou_tinh_tay(self, tmp_path):
        """Đo drift = IoU(ô bao ĐÃ PHÁT ở frame đó, ô bao VOS sửa lại) — sai 1 đơn vị là đỏ."""
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(FakeEngine(), LiveTrackConfig(
            source="x.mp4", out_dir=out, display_fps=100, vos_every=3))
        session._shown_by_frame.append((7, (0, 0, 10, 10)))
        session._measure_drift(7, _Result(0, (5, 0, 15, 10), None))

        assert session._stats.drift_n == 1
        assert session._stats.drift_iou == pytest.approx(66 / 176, abs=1e-3)

    def test_drift_bo_qua_khi_frame_khong_co_trong_lich_su(self, tmp_path):
        """Không có ô bao đã phát ở frame đó ⇒ KHÔNG có mẫu (không suy ra từ frame khác)."""
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(FakeEngine(), LiveTrackConfig(
            source="x.mp4", out_dir=out, display_fps=100, vos_every=3))
        session._shown_by_frame.append((7, (0, 0, 10, 10)))
        session._measure_drift(8, _Result(0, (5, 0, 15, 10), None))

        assert session._stats.drift_n == 0
        assert session._stats.drift_iou is None

    def test_mask_rong_khong_vao_mau_drift(self, tmp_path):
        """Mask rỗng ⇒ bbox (0,0,0,0): bỏ mẫu, KHÔNG ghi điểm 0."""
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(FakeEngine(), LiveTrackConfig(
            source="x.mp4", out_dir=out, display_fps=100, vos_every=3))
        session._shown_by_frame.append((1, None))
        session._measure_drift(1, _Result(0, (0, 0, 0, 0), None))
        session._shown_by_frame.append((2, (5, 5, 15, 15)))
        session._measure_drift(2, _Result(0, (0, 0, 0, 0), None))

        assert session._stats.drift_n == 0

    def test_tat_lk_thi_khong_do_drift(self, tmp_path):
        """`vos_every=1`: không có nội suy ⇒ không được gọi đó là drift (nếu không "tắt LK" trông tốt hơn)."""
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(FakeEngine(), LiveTrackConfig(
            source="x.mp4", out_dir=out, display_fps=100, vos_every=1))
        session._shown_by_frame.append((3, (0, 0, 10, 10)))
        session._measure_drift(3, _Result(0, (5, 0, 15, 10), None))

        assert session._stats.drift_n == 0
        assert session._stats.drift_iou is None

    def test_tuoi_mask_literal_va_gom_ca_vos_ms(self, tmp_path):
        """10 mẫu 100 ms, `vos_ms=100` ⇒ age 100,0 ms, total 200,0 ms, p95 = 200,0 ms."""
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(FakeEngine(), LiveTrackConfig(
            source="x.mp4", out_dir=out, display_fps=100, vos_every=3))
        for _ in range(10):
            session._note_mask_age(0.100, vos_ms=100.0)

        assert session._stats.age_n == 10
        assert session._stats.mask_age_ms == pytest.approx(100.0)
        assert session._stats.mask_age_total_ms == pytest.approx(200.0)
        assert session._stats.mask_age_p95 == pytest.approx(200.0)

    def test_tuoi_mask_chua_du_mau_thi_p95_la_none(self, tmp_path):
        out = tmp_path / "live"
        _pre_select(out)
        session = LiveTrackingSession(FakeEngine(), LiveTrackConfig(
            source="x.mp4", out_dir=out, display_fps=100, vos_every=3))
        session._note_mask_age(0.050, vos_ms=10.0)

        assert session._stats.age_n == 1
        assert session._stats.mask_age_p95 is None       # 1 mẫu chưa đủ để nói p95

    @pytest.mark.parametrize("every, phai_do", [(1, False), (6, True)])
    def test_age_n_phan_biet_chua_do_voi_do_duoc(self, textured_video, tmp_path, every, phai_do):
        """`age_n = 0` ⇒ CHƯA ĐO. Xoá tính năng thì `vos_every=6` cũng ra 0 ⇒ test này đỏ."""
        out = tmp_path / f"live{every}"
        _pre_select(out)
        LiveTrackingSession(FakeEngine(), LiveTrackConfig(
            source=textured_video, out_dir=out, display_fps=100, vos_every=every,
            loop_files=True)).run(stop_event=_StopAfter(25))

        status = json.loads((out / STATUS_NAME).read_text(encoding="utf-8"))
        if phai_do:
            assert status["age_n"] > 0, "vos_every=6 phải đo được tuổi mask"
            assert status["mask_age_ms"] > 0
            assert 0 <= status["drift_iou"] <= 1
        else:
            assert status["age_n"] == 0 and status["mask_age_ms"] is None
            assert status["drift_n"] == 0 and status["drift_iou"] is None
