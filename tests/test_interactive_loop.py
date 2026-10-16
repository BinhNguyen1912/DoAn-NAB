"""Test vòng lặp tương tác run_interactive — chọn ô → track → r chọn lại → q thoát (ticket 05).

Dùng FakeEngine (không model) + display callback trả phím kịch bản để test headless
không cần cửa sổ/camera. Phần kéo chuột thật kiểm thủ công (WSL không GUI).
"""
import cv2
import numpy as np

from src.live_pipeline import run_interactive
from src.prompt_selector import PromptSelector
from src.tracker_engine import TrackingResult


class FakeEngine:
    """Engine giả: ghi lại lệnh gọi, trả TrackingResult không cần model."""

    def __init__(self, frame_shape=(240, 320, 3)):
        self._shape = frame_shape
        self.calls = []  # list of (method, *args)
        self._frame_idx = -1

    def start(self, frame, bbox):
        self.calls.append(("start", tuple(bbox)))
        self._frame_idx = 0
        return self._result(0)

    def process(self, frame):
        self._frame_idx += 1
        self.calls.append(("process",))
        return self._result(self._frame_idx)

    def reset(self):
        self.calls.append(("reset",))
        self._frame_idx = -1

    def _result(self, idx):
        h, w = self._shape[:2]
        mask = np.zeros((h, w), dtype=bool)
        mask[10:50, 10:50] = True
        return TrackingResult(
            frame_idx=idx, mask=mask, bbox=(10, 10, 50, 50),
            score=1.0, elapsed_ms=1.0,
        )


def _write_video(path, frames, fps=30):
    h, w = frames.shape[1], frames.shape[2]
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    for f in frames:
        out.write(f)
    out.release()
    return path


def _make_video(tmp_path, n=4):
    from src.synthetic_video import generate_tracking_sequence
    fx = generate_tracking_sequence(num_frames=n, frame_size=(240, 320),
                                    square_size=40, start=(60, 60))
    return _write_video(tmp_path / "seq.avi", fx.frames, fps=30), fx


def _count_by_name(calls, name):
    """Đếm số lệnh gọi theo tên phương thức (start/process/reset)."""
    return sum(1 for c in calls if c[0] == name)


class TestRunInteractive:
    def test_chon_bang_chuot_roi_track_het_video(self, tmp_path):
        path, fx = _make_video(tmp_path, n=4)
        engine = FakeEngine()
        sel = PromptSelector(frame_shape=(240, 320, 3))

        keys = iter([-1, -1, -1, -1, -1, -1])
        shown = []

        def display(img, mode):
            shown.append(mode)
            # như người dùng kéo chuột: lần select đầu, arm bbox
            if mode == "select" and not engine.calls and not sel.has_bbox():
                sel.on_mouse(cv2.EVENT_LBUTTONDOWN, 60, 60, 0, None)
                sel.on_mouse(cv2.EVENT_LBUTTONUP, 100, 100, 0, None)
                assert sel.has_bbox()
            try:
                return next(keys)
            except StopIteration:
                return ord("q")

        summary = run_interactive(
            source=str(path), engine=engine, selector=sel,
            display=display,
        )

        # engine.start gọi đúng 1 lần với bbox đã chọn; process cho 3 frame còn lại
        assert engine.calls[0] == ("start", (60, 60, 100, 100))
        assert engine.calls.count(("process",)) == 3
        assert ("reset",) not in engine.calls
        # đã qua cả select lẫn track
        assert "select" in shown and "track" in shown
        assert summary.processed == 4

    def test_phim_r_dung_track_quay_ve_select_va_chon_doi_tuong_moi(self, tmp_path):
        path, fx = _make_video(tmp_path, n=10)
        engine = FakeEngine()
        sel = PromptSelector(frame_shape=(240, 320, 3))

        # select(arm bbox 1) → track → r → select lại (arm bbox 2) → track → q
        pressed_r = False
        states = []

        def display(img, mode):
            nonlocal pressed_r
            states.append(mode)
            n_start = _count_by_name(engine.calls, "start")
            # lần select đầu: arm bbox 1 như người dùng kéo chuột
            if mode == "select" and n_start == 0 and not sel.has_bbox():
                sel.on_mouse(cv2.EVENT_LBUTTONDOWN, 60, 60, 0, None)
                sel.on_mouse(cv2.EVENT_LBUTTONUP, 100, 100, 0, None)
                return -1
            # lần track đầu tiên (start #1) → bấm r để chọn lại
            if mode == "track" and n_start == 1 and not pressed_r:
                pressed_r = True
                return ord("r")
            # lần select sau reset: arm bbox 2
            if mode == "select" and n_start == 1 and pressed_r:
                if not sel.has_bbox():
                    sel.on_mouse(cv2.EVENT_LBUTTONDOWN, 20, 20, 0, None)
                    sel.on_mouse(cv2.EVENT_LBUTTONUP, 80, 80, 0, None)
                return -1
            # lần track sau khi chọn lại (start #2) → thoát
            if mode == "track" and n_start == 2:
                return ord("q")
            return -1

        run_interactive(source=str(path), engine=engine, selector=sel, display=display)

        # start gọi 2 lần (bbox 1 rồi bbox 2), reset gọi 1 lần
        assert _count_by_name(engine.calls, "start") == 2
        assert _count_by_name(engine.calls, "reset") == 1
        assert engine.calls[0] == ("start", (60, 60, 100, 100))
        assert engine.calls[-1][0] == "start"
        assert engine.calls[-1][1] == (20, 20, 80, 80)
        # có cả select → track → select → track
        assert states[0] == "select"
        assert "track" in states

    def test_preselect_bbox_track_ngay_khong_can_keo_chuot(self, tmp_path):
        """--bbox chỉ định sẵn: track khởi động ngay sau bind, như đã kéo chuột."""
        path, fx = _make_video(tmp_path, n=4)
        engine = FakeEngine()
        sel = PromptSelector(frame_shape=(240, 320, 3))

        results = []

        def display(img, mode):
            # hết video (4 frame: 1 start + 3 process) → thoát
            if _count_by_name(engine.calls, "process") == 3:
                return ord("q")
            return -1

        summary = run_interactive(
            source=str(path), engine=engine, selector=sel, display=display,
            preselect_bbox=(60, 60, 100, 100), on_result=results.append,
        )
        assert engine.calls[0] == ("start", (60, 60, 100, 100))
        assert _count_by_name(engine.calls, "process") == 3
        assert summary.processed == 4
        # on_result gọi đúng 4 lần (1 start + 3 process), frame_idx tăng dần
        assert [r.frame_idx for r in results] == [0, 1, 2, 3]

    def test_phim_q_thoat_sach_tu_select(self, tmp_path):
        path, fx = _make_video(tmp_path, n=4)
        engine = FakeEngine()
        sel = PromptSelector(frame_shape=(240, 320, 3))  # không arm — chọn mode

        def display(img, mode):
            return ord("q")  # thoát ngay

        summary = run_interactive(
            source=str(path), engine=engine, selector=sel, display=display,
        )
        assert engine.calls == []  # chưa track gì
        assert summary.processed == 0

    def test_phim_esc_thoat_sach_tu_track(self, tmp_path):
        path, fx = _make_video(tmp_path, n=4)
        engine = FakeEngine()
        sel = PromptSelector(frame_shape=(240, 320, 3))

        def display(img, mode):
            # arm bbox ở select đầu, rồi ESC ngay ở track đầu tiên
            if mode == "select" and not engine.calls and not sel.has_bbox():
                sel.on_mouse(cv2.EVENT_LBUTTONDOWN, 60, 60, 0, None)
                sel.on_mouse(cv2.EVENT_LBUTTONUP, 100, 100, 0, None)
                return -1
            return 27  # ESC

        run_interactive(source=str(path), engine=engine, selector=sel, display=display)
        # start gọi rồi, process chưa kịp
        assert engine.calls[0] == ("start", (60, 60, 100, 100))
        assert engine.calls.count(("process",)) == 0