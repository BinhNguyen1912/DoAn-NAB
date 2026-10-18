"""Test chế độ hiển thị mượt (tách luồng) — webcam realtime thật trên CPU.

Vấn đề: SAM 2 trên CPU mất 0.4–3 s/frame. Nếu đọc–suy luận–hiển thị tuần tự thì video
giật đúng bằng tốc độ model (0.3–2 FPS). Giải pháp: 3 luồng —
  (1) capture: liên tục đọc frame mới nhất,
  (2) inference: lấy frame mới nhất đem suy luận (bỏ qua frame nếu đang bận),
  (3) display (main thread, vì OpenCV chỉ cho 1 luồng dùng GUI): vẽ frame mới nhất
      + overlay của lần suy luận gần nhất, HUD ghi rõ "overlay cách đây bao lâu".
"""
import threading
import time

import numpy as np

from src.smooth_display import InferenceWorker, LatestFrameSource
from src.tracker_engine import TrackingResult  # import Ở MAIN THREAD (torch) trước khi chạy thread


class FakeSource:
    """Nguồn frame giả: mỗi lần read() trả một frame mới, có thể chậm tuỳ ý."""

    def __init__(self, size=(120, 160), delay=0.01, limit=200):
        self._n = 0
        self._delay = delay
        self._limit = limit
        self.closed = False
        self._lock = threading.Lock()
        self.size = size

    def read(self):
        time.sleep(self._delay)
        with self._lock:
            self._n += 1
            n = self._n
        if n > self._limit:
            return None
        frame = np.full((self.size[0], self.size[1], 3), n % 256, dtype=np.uint8)
        return frame

    def close(self):
        self.closed = True


class FakeEngine:
    def __init__(self, delay=0.05):
        self.calls = []
        self._delay = delay
        self._idx = -1
        self.lock = threading.Lock()

    def start(self, frame, bbox):
        time.sleep(self._delay)
        with self.lock:
            self.calls.append("start")
            self._idx = 0
        return self._res(0, bbox)

    def process(self, frame):
        time.sleep(self._delay)
        with self.lock:
            self.calls.append("process")
            self._idx += 1
        return self._res(self._idx, (10, 10, 50, 50))

    def reset(self):
        with self.lock:
            self.calls.append("reset")
            self._idx = -1

    def _res(self, i, bbox):
        mask = np.zeros((120, 160), dtype=bool)
        mask[10:50, 10:50] = True
        return TrackingResult(frame_idx=i, mask=mask, bbox=tuple(bbox),
                              score=1.0, elapsed_ms=self._delay * 1000)


class TestLatestFrameSource:
    def test_luon_tra_frame_moi_nhat_va_so_frame_tang(self):
        src = LatestFrameSource(FakeSource(delay=0.005))
        src.start()
        try:
            f1 = src.latest()
            time.sleep(0.08)
            f2 = src.latest()
        finally:
            src.stop()
        assert f1 is not None and f2 is not None
        assert src.frames_captured > 1
        # frame mới nhất phải KHÁC frame đầu (giá trị pixel đổi theo số thứ tự)
        assert not np.array_equal(f1, f2)

    def test_stop_dong_nguon_va_join_thread(self):
        fake = FakeSource(delay=0.005)
        src = LatestFrameSource(fake)
        src.start()
        time.sleep(0.05)
        src.stop()
        assert fake.closed is True
        assert not any(t.name == "capture" for t in threading.enumerate())


class TestInferenceWorker:
    def test_start_roi_process_lien_tuc_va_dung_sach(self, monkeypatch):
        src = LatestFrameSource(FakeSource(delay=0.005))
        src.start()
        engine = FakeEngine(delay=0.03)
        worker = InferenceWorker(engine, src)
        worker.start()
        try:
            worker.set_bbox((10, 10, 50, 50))
            time.sleep(0.25)
            calls = list(engine.calls)
            res = worker.latest_result()
        finally:
            worker.stop()
            src.stop()

        assert calls[:2] == ["reset", "start"]      # set_bbox reset rồi start
        assert calls.count("process") >= 2          # đã suy luận nhiều frame
        assert res is not None and res.result is not None
        assert res.age_ms >= 0

    def test_set_bbox_lai_thi_reset_va_start_lai(self):
        src = LatestFrameSource(FakeSource(delay=0.005))
        src.start()
        engine = FakeEngine(delay=0.01)
        worker = InferenceWorker(engine, src)
        worker.start()
        try:
            worker.set_bbox((10, 10, 50, 50))
            time.sleep(0.1)
            worker.set_bbox((20, 20, 60, 60))     # chọn lại đối tượng
            time.sleep(0.15)
            calls = list(engine.calls)
        finally:
            worker.stop()
            src.stop()
        assert calls.count("start") >= 2
        assert "reset" in calls

    def test_khong_co_bbox_thi_chua_suy_luan(self):
        src = LatestFrameSource(FakeSource(delay=0.005))
        src.start()
        engine = FakeEngine(delay=0.01)
        worker = InferenceWorker(engine, src)
        worker.start()
        try:
            time.sleep(0.1)
            assert engine.calls == []          # chưa chọn đối tượng → không chạy model
            assert worker.latest_result() is None
        finally:
            worker.stop()
            src.stop()


class TestVisualizerConsumeRender:
    """consume() 1 lần/kết quả; render() nhiều lần/frame hiển thị → không nhân đôi quỹ đạo."""

    def test_render_nhieu_lan_khong_them_diem_quy_dao(self):
        from src.visualizer import Visualizer

        frame = np.zeros((120, 160, 3), np.uint8)
        viz = Visualizer()
        res = InferenceWorker  # noqa: F841  (chỉ để rõ ngữ cảnh)
        from src.tracker_engine import TrackingResult

        mask = np.zeros((120, 160), bool)
        mask[10:50, 10:50] = True
        r = TrackingResult(frame_idx=0, mask=mask, bbox=(10, 10, 50, 50),
                           score=1.0, elapsed_ms=100.0)
        viz.consume(r)
        for _ in range(5):
            img = viz.render(frame, r, overlay_age_ms=120.0, display_fps=30.0)
        assert len(viz.trajectory_points) == 1
        assert img.shape == (120, 160, 3)
        assert viz.lost_frames == 0

    def test_hud_co_tuoi_overlay(self):
        from src.visualizer import Visualizer
        from src.tracker_engine import TrackingResult

        frame = np.zeros((120, 300, 3), np.uint8)
        viz = Visualizer()
        mask = np.zeros((120, 300), bool)
        r = TrackingResult(frame_idx=0, mask=mask, bbox=(0, 0, 0, 0),
                           score=0.0, elapsed_ms=50.0)
        img = viz.render(frame, r, overlay_age_ms=321.0, display_fps=30.0)
        # dòng "Overlay: 321 ms truoc" ở y≈80 → phải có pixel khác nền
        assert not np.array_equal(img[74:92, :220], frame[74:92, :220])


class TestRunSmoothDisplay:
    def _engine(self):
        from src.tracker_engine import TrackingResult

        class Eng:
            def __init__(self):
                self.calls = 0

            def start(self, frame, bbox):
                self.calls += 1
                return self._res()

            def process(self, frame):
                self.calls += 1
                time.sleep(0.12)     # model thật CHẬM hơn nhịp vẽ (~33 ms) — đúng thực tế
                return self._res()

            def reset(self):
                pass

            def _res(self):
                mask = np.zeros((120, 160), bool)
                mask[10:50, 10:50] = True
                return TrackingResult(frame_idx=0, mask=mask, bbox=(10, 10, 50, 50),
                                      score=1.0, elapsed_ms=20.0)

        return Eng()

    def test_hien_thi_nhieu_hon_suy_luan_va_thoat_bang_q(self, tmp_path, write_video):
        """Bằng chứng 'mượt': số lần VẼ > số lần SUY LUẬN (video 30 FPS, model chậm)."""
        from src.live_pipeline import QUIT_KEYS
        from src.prompt_selector import PromptSelector
        from src.smooth_display import run_smooth_display
        from src.synthetic_video import generate_tracking_sequence

        fx = generate_tracking_sequence(num_frames=20, frame_size=(120, 200),
                                        square_size=40, start=(10, 10))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        engine = self._engine()
        selector = PromptSelector(frame_shape=(120, 200, 3))
        state = {"display": 0, "infer": 0}

        def display(img, mode):
            state["display"] += 1
            # chỉ thoát khi ĐÃ có ít nhất 1 suy luận và đã vẽ đủ 12 frame
            if state["infer"] >= 1 and state["display"] >= 12:
                return list(QUIT_KEYS)[0]      # q
            return -1

        summary = run_smooth_display(source=str(path), engine=engine, selector=selector,
                                     display=display, preselect_bbox=(10, 10, 50, 50),
                                     on_result=lambda r: state.__setitem__("infer",
                                                                           state["infer"] + 1))
        assert state["display"] >= 12
        assert summary.processed >= 1
        assert state["display"] > summary.processed     # vẽ nhiều hơn suy luận → mượt
