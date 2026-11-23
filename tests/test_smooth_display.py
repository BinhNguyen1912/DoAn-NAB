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


class TestThreadSafety:
    """Bug thật 18-10: bấm `r` → main thread gọi engine.reset() trong khi luồng suy luận đang
    chạy model → `TypeError: 'NoneType' object is not subscriptable`, state hỏng, engine trả
    mãi frame cũ và KHÔNG chọn lại được. Sửa: main thread chỉ gửi yêu cầu, worker thực hiện.
    """

    def _setup(self, engine_cls=None):
        src = LatestFrameSource(FakeSource(delay=0.005)).start()
        engine = (engine_cls or FakeEngine)(delay=0.03)
        worker = InferenceWorker(engine, src).start()
        return src, engine, worker

    def test_set_bbox_khong_goi_engine_o_main_thread(self):
        src, engine, worker = self._setup()
        try:
            worker.set_bbox((10, 10, 50, 50))
            # NGAY sau khi gọi: main thread chưa được chạm vào engine
            assert engine.calls == []
            time.sleep(0.15)                      # worker mới là nơi reset+start
            assert engine.calls[:2] == ["reset", "start"]
        finally:
            worker.stop()
            src.stop()

    def test_clear_xoa_ket_qua_cu_va_ngung_suy_luan(self):
        src, engine, worker = self._setup()
        try:
            worker.set_bbox((10, 10, 50, 50))
            time.sleep(0.15)
            assert worker.latest_result() is not None
            worker.clear()                        # như bấm r
            assert worker.latest_result() is None, "phải xoá kết quả cũ để về chế độ chọn"
            assert worker.is_tracking() is False
            time.sleep(0.15)                      # để worker xử lý yêu cầu clear
            n = len(engine.calls)
            time.sleep(0.2)
            assert len(engine.calls) == n, "không được suy luận khi đã clear"
        finally:
            worker.stop()
            src.stop()

    def test_loi_suy_luan_quay_ve_che_do_chon_khong_loop(self, capsys):
        """Engine lỗi (state hỏng) → worker về chế độ chờ chọn, KHÔNG lặp lỗi vô hạn."""

        class LoiEngine(FakeEngine):
            def process(self, frame):
                with self.lock:
                    self.calls.append("process")
                raise TypeError("'NoneType' object is not subscriptable")

        src, engine, worker = self._setup(LoiEngine)
        try:
            worker.set_bbox((10, 10, 50, 50))
            time.sleep(0.3)
            assert worker.is_tracking() is False      # về chế độ chọn
            assert worker.latest_result() is None
            n_err = capsys.readouterr().out.count("[LOI]")
            assert n_err == 1, "chỉ báo lỗi 1 lần, không spam"
        finally:
            worker.stop()
            src.stop()

    def test_r_roi_chon_lai_duoc_trong_vong_lap(self, tmp_path, write_video):
        """Đúng kịch bản người dùng: chạy → bấm r → kéo ô mới → phải bám lại được."""
        from src.live_pipeline import RESET_KEY, QUIT_KEYS
        from src.prompt_selector import PromptSelector
        from src.smooth_display import run_smooth_display
        from src.synthetic_video import generate_tracking_sequence

        fx = generate_tracking_sequence(num_frames=20, frame_size=(120, 200),
                                        square_size=40, start=(10, 10))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        engine = FakeEngine(delay=0.05)
        selector = PromptSelector(frame_shape=(120, 200, 3))
        state = {"display": 0, "infer": 0, "pressed_r": False, "armed": False}

        def display(img, mode):
            import cv2 as _cv2

            state["display"] += 1
            if mode == "track" and state["infer"] >= 1 and not state["pressed_r"]:
                state["pressed_r"] = True
                return RESET_KEY                     # bấm r
            if (state["pressed_r"] and not state["armed"] and mode == "select"
                    and not selector.has_bbox()):
                state["armed"] = True                # kéo ô mới — CHỈ 1 lần
                selector.on_mouse(_cv2.EVENT_LBUTTONDOWN, 20, 20, 0, None)
                selector.on_mouse(_cv2.EVENT_LBUTTONUP, 60, 60, 0, None)
                return -1
            if state["pressed_r"] and state["infer"] >= 3:
                return list(QUIT_KEYS)[0]            # q
            return -1

        summary = run_smooth_display(
            source=str(path), engine=engine, selector=selector, display=display,
            preselect_bbox=(10, 10, 50, 50),
            on_result=lambda r: state.__setitem__("infer", state["infer"] + 1),
        )
        assert state["pressed_r"] is True
        starts = [c for c in engine.calls if c == "start"]
        assert len(starts) >= 2, "sau khi bấm r + kéo ô mới phải start lại"
        assert summary.processed >= 2


class TestWorkerVoiReId:
    """InferenceWorker nhận reid_session (ADR-0003): dùng máy trạng thái thay vì gọi engine trực tiếp."""

    def test_dung_may_trang_thai_va_bao_trang_thai_ra_ngoai(self):
        from src.reid import ReIdSession

        class NoFaceEmbedder:
            def detect(self, frame):
                return []

        src = LatestFrameSource(FakeSource(delay=0.005))
        src.start()
        engine = FakeEngine(delay=0.01)
        session = ReIdSession(engine, NoFaceEmbedder(), threshold=0.5, lost_after_frames=99)
        worker = InferenceWorker(engine, src, reid_session=session)
        worker.start()
        try:
            worker.set_bbox((10, 10, 50, 50))
            time.sleep(0.15)
            state, score, reacquired, ncc = worker.reid_status()
            res = worker.latest_result()
        finally:
            worker.stop()
            src.stop()

        assert state == "tracking"          # mask còn → vẫn đang bám
        assert res is not None and res.result is not None
        assert engine.calls[:2] == ["reset", "start"]
        assert engine.calls.count("process") >= 1


class TestKhongQuayVongHetTocKhiDongBang:
    """Đang đóng băng (mất dấu) thì vòng suy luận phải được hãm nhịp.

    Lỗi thật 22-10: khi LOST, vòng lặp chỉ chạy detect mặt nên quay ~50–100 lần/giây,
    frame_idx phình lên 213 trong khi chỉ 145 kết quả thật được hiển thị.
    """

    def test_so_buoc_suy_luan_bi_gioi_han_khi_mat_dau(self):
        from src.reid import ReIdSession
        from src.tracker_engine import TrackingResult

        class NoFace:
            def detect(self, frame):
                return []

        class LostEngine:
            """start → mask có; process → mask RỖNG (mất dấu ngay) để rơi vào LOST."""

            def __init__(self):
                self.calls = 0

            def start(self, frame, bbox):
                m = np.zeros((120, 160), bool)
                m[10:50, 10:50] = True
                return TrackingResult(frame_idx=0, mask=m, bbox=tuple(bbox),
                                      score=1.0, elapsed_ms=1.0)

            def process(self, frame):
                self.calls += 1
                return TrackingResult(frame_idx=self.calls, mask=np.zeros((120, 160), bool),
                                      bbox=(0, 0, 0, 0), score=0.0, elapsed_ms=0.0)

            def reset(self):
                self.calls = 0

        src = LatestFrameSource(FakeSource(delay=0.005))
        src.start()
        engine = LostEngine()
        session = ReIdSession(engine, NoFace(), threshold=0.5, lost_after_frames=1)
        worker = InferenceWorker(engine, src, reid_session=session, frozen_poll_interval=0.04)
        worker.start()
        try:
            worker.set_bbox((10, 10, 50, 50))
            time.sleep(0.1)                        # để rơi vào LOST (mask rỗng từ frame 1)
            start_count = worker.inference_count
            time.sleep(0.4)                        # 0,4 s ở nhịp 40 ms ⇒ tối đa ~10 vòng
            spun = worker.inference_count - start_count
        finally:
            worker.stop()
            src.stop()
        assert session.state in ("lost", "reacquiring")
        assert spun <= 20, f"vòng suy luận quay {spun} lần trong 0,4 s — chưa hãm nhịp?"


class TestCoVetoQuaInferenceWorker:
    """P3 review vòng 3 (21-11): đường `--smooth` (đường demo CHÍNH `./run demoip`) là đường **duy

    nhất** không có test chạm `reid_vetoed` — xoá `InferenceWorker.reid_vetoed()` hoặc dòng gán
    `_reid_vetoed` thì suite vẫn xanh, và HUD sẽ in lại "khop X / can Y" (hiểu ngược: đủ điểm mà
    không nhận). Test này khoá chuỗi worker → HUD.
    """

    def test_worker_bao_co_veto_ra_ngoai(self):
        from src.reid import Step
        from src.tracker_engine import TrackingResult

        class FakeSession:
            state = "reacquiring"

            def start(self, frame, bbox):
                return TrackingResult(frame_idx=0, mask=np.ones((20, 20), bool),
                                      bbox=(10, 10, 50, 50), score=5.0, elapsed_ms=1.0)

            def step(self, frame):
                return Step(result=TrackingResult(frame_idx=1, mask=np.zeros((20, 20), bool),
                                                  bbox=(0, 0, 0, 0), score=0.0, elapsed_ms=1.0),
                            state="reacquiring", reid_score=0.9, ncc=0.42, vetoed=True)

            def reset(self):
                pass

        src = LatestFrameSource(FakeSource(delay=0.005))
        src.start()
        engine = FakeEngine(delay=0.01)
        worker = InferenceWorker(engine, src, reid_session=FakeSession())
        worker.start()
        try:
            worker.set_bbox((10, 10, 50, 50))
            deadline = time.time() + 2.0
            seen = False
            while time.time() < deadline and not seen:
                time.sleep(0.02)
                seen = worker.reid_vetoed() is True
        finally:
            worker.stop()
            src.stop()

        assert seen, "HUD không nhận được cờ veto ⇒ sẽ in 'khop X / can Y' gây hiểu ngược"


class TestCongNhayCoNhoTrenDuongMuot:
    """21-11 (bug thật, bắt từ phiên `demoip_1121-131421`): `smooth_display` cập nhật `last_bbox`

    TRƯỚC khi gọi `watch.update(last_bbox, bbox)` ⇒ so ô với **chính nó** ⇒ nhảy = 0 ⇒ cổng CÓ NHỚ
    không bao giờ bật trên đúng đường `./run demoip` (chế độ MƯỢT). Hậu quả người dùng thấy: console
    in "nghi ngờ ĐỔI ĐỐI TƯỢNG" nhưng hệ **vẫn vẽ** mask của vùng sai (CSV ghi `nghi_doi_tuong` trống
    cả 334 dòng). Test này khoá THỨ TỰ đó.
    """

    def test_cong_nhay_bat_duoc_khi_o_nhay(self):
        import inspect

        from src import smooth_display as sd

        src = inspect.getsource(sd.run_smooth_display)
        cap_nhat = src.index("switch = watch.update(")
        gan_lai = src.index("last_bbox = stamped.result.bbox")
        assert cap_nhat < gan_lai, ("cổng nhảy phải được cập nhật TRƯỚC khi gán `last_bbox` = ô hiện "
                                    "tại, nếu không nó so ô với chính nó và không bao giờ bật")

    def test_reacquired_giai_phong_latch_nghi_doi_tuong(self):
        """22-11 (bug thật, phiên `demoip_1122-195623`): vật chạm mép nhảy ô ⇒ `IdentityWatch`

        latch nghi ngờ; sau đó Re-ID tìm lại được vật (khớp 98%), nhưng vì `reacquired` không
        reset `watch` nên ô bao bị giấu vĩnh viễn suốt 10 giây còn lại. Khi Re-ID đã nhận lại,
        hệ thống phải tin Re-ID, xoá cờ nghi và đặt lại mốc `last_bbox`.
        """
        import inspect

        from src import smooth_display as sd

        src = inspect.getsource(sd.run_smooth_display)
        assert "if reacquired:" in src
        pos_reacq = src.index("if reacquired:")
        pos_reset = src.index("watch.reset()", pos_reacq)
        pos_switch_false = src.index("switch = False", pos_reacq)
        assert pos_reacq < pos_reset < pos_switch_false

    def test_phim_c_giai_phong_deadlock_last_bbox(self):
        """Bấm 'c' = "vẫn đúng, tiếp tục" phải NEO LẠI engine ở ô vừa bị nghi.

        ĐÍNH CHÍNH 23-11: từ khi cờ nghi khiến `ReIdSession` **bỏ track** (đi tìm lại), `last_bbox`
        của kết quả mới là `(0,0,0,0)` ⇒ chỉ cập nhật `last_bbox = stamped.result.bbox` như bản 22-11
        là **không đủ**: hệ vẫn ở trạng thái tìm lại và người dùng tưởng đã xác nhận xong. Nay phím
        `c` gọi `worker.set_bbox(bbox_truoc_nghi)` — ô đã lưu TRƯỚC khi bỏ track.
        """
        import inspect

        from src import smooth_display as sd

        src = inspect.getsource(sd.run_smooth_display)
        pos_c = src.index("if key == CONTINUE_KEY and watch.nghi:")
        pos_neo = src.index("worker.reanchor(bbox_truoc_nghi)", pos_c)
        assert pos_c < pos_neo, "phím `c` phải neo lại engine ở ô vừa bị nghi"
        # và phải có biến lưu ô đó tại THỜI ĐIỂM cổng bật nghi (lúc `last_bbox` còn giá trị thật)
        assert "bbox_truoc_nghi = tuple(last_bbox)" in src

    def test_mat_dau_dat_moc_last_bbox_rong(self):
        """Khi mask rỗng (mất dấu), `last_bbox` phải được đặt `(0, 0, 0, 0)` để khi vật xuất hiện

        lại ở vị trí mới, `is_suspect_switch` không so với ô từ nhiều giây trước.
        """
        import inspect

        from src import smooth_display as sd

        src = inspect.getsource(sd.run_smooth_display)
        assert "last_bbox = (0, 0, 0, 0)" in src


class TestCongNghiEpTimLai:
    """23-11-2026 (phiên `demoip_1123-092343`): cổng nghi chỉ ẨN overlay, `ReIdSession` vẫn

    `tracking` 48/312 bước trên ÁO NGƯỜI ⇒ Re-ID không được gọi lần nào. Nay cổng nghi phải được
    BÁO XUỐNG luồng suy luận (đổi thành "bỏ track + tìm lại").
    """

    def test_cong_nghi_bao_xuong_session(self):
        import inspect

        from src import smooth_display as sd

        src = inspect.getsource(sd.run_smooth_display)
        assert "_bao_nghi(watch.nghi)" in src, "cổng nghi phải chuyển xuống luồng suy luận"
        # phải gọi TRƯỚC khi log/`continue` để cờ kịp tới worker ở vòng sau
        assert src.index("_bao_nghi(watch.nghi)") < src.index("if on_result is not None:")
        # `c` và `r` phải XOÁ cờ, nếu không bước tracking kế tiếp lại bị bỏ ⇒ quay vòng
        pos_c = src.index("if key == CONTINUE_KEY and watch.nghi:")
        assert "_bao_nghi(False)" in src[pos_c:pos_c + 400]
        pos_r = src.index("if key == RESET_KEY:")
        assert "_bao_nghi(False)" in src[pos_r:pos_r + 400]

    def test_worker_chuyen_co_nghi_vao_session(self):
        """Khoá đường worker → session (main thread không được chạm engine/session)."""
        from src.reid import Step

        calls = []

        class FakeSession:
            state = "tracking"

            def start(self, frame, bbox):
                return TrackingResult(frame_idx=0, mask=np.ones((20, 20), bool),
                                      bbox=(10, 10, 50, 50), score=5.0, elapsed_ms=1.0)

            def step(self, frame):
                return Step(result=TrackingResult(frame_idx=1, mask=np.ones((20, 20), bool),
                                                  bbox=(10, 10, 50, 50), score=5.0, elapsed_ms=1.0),
                            state="tracking")

            def reset(self):
                pass

            def set_suspicious(self, co):
                calls.append(bool(co))

        src = LatestFrameSource(FakeSource(delay=0.005))
        src.start()
        engine = FakeEngine(delay=0.01)
        worker = InferenceWorker(engine, src, reid_session=FakeSession())
        worker.start()
        try:
            worker.set_bbox((10, 10, 50, 50))
            deadline = time.time() + 2.0
            while time.time() < deadline and not worker.latest_result():
                time.sleep(0.02)
            worker.request_suspicious(True)
            deadline = time.time() + 2.0
            while time.time() < deadline and True not in calls:
                time.sleep(0.02)
            worker.request_suspicious(False)
            deadline = time.time() + 2.0
            while time.time() < deadline and False not in calls:
                time.sleep(0.02)
        finally:
            worker.stop()
            src.stop()

        assert True in calls, "cờ nghi phải tới được ReIdSession"
        assert False in calls, "hết nghi phải xoá cờ trong ReIdSession"


class TestCongNghiEpBoTrackThatSu:
    """Chứng minh END-TO-END (không chỉ đọc source): cổng nghi của vòng hiển thị làm

    `ReIdSession` **bỏ track** trong phiên thật.

    Cú nhảy chọn trong cửa sổ mà **chỉ cổng hiển thị** bắt được: 70 px, trong khi ngưỡng nội bộ
    `_is_suspicious_jump` là `1,5 × đường chéo ô` = 1,5 × 56,6 ≈ 85 px (đúng ca phiên 23-11: cổng
    hiển thị báo ở 204 px còn cổng nội bộ cần 446 px). Nhờ vậy test này KHÔNG thể xanh nhờ cổng
    nội bộ.
    """

    def test_cong_nghi_lam_session_bo_track(self, tmp_path, write_video):
        from src.live_pipeline import QUIT_KEYS
        from src.prompt_selector import PromptSelector
        from src.reid import ReIdSession
        from src.smooth_display import run_smooth_display
        from src.synthetic_video import generate_tracking_sequence
        from src.tracker_engine import TrackingResult

        A, B = (10, 10, 50, 50), (80, 10, 120, 50)     # nhảy 70 px (ngưỡng hiển thị ≈ 58 px)

        class NhayEngine:
            """Trả ô A; cú nhảy sang B được bật từ ngoài (sau khi đã tiêu thụ vài kết quả).

            Điều khiển bằng cờ chứ không bằng bộ đếm `process()`: luồng suy luận chạy NHANH hơn
            vòng vẽ rất nhiều, nên "nhảy sau N lần process" sẽ nhảy TRƯỚC khi vòng vẽ kịp thấy ô A
            ⇒ cổng không có mốc cũ để so và test thành vô nghĩa (đã gặp khi viết test này).
            """

            def __init__(self):
                self.jump = False
                self.calls = 0
                self.reset_calls = 0

            def _res(self, bbox):
                m = np.zeros((120, 200), bool)
                m[bbox[1]:bbox[3], bbox[0]:bbox[2]] = True
                return TrackingResult(frame_idx=0, mask=m, bbox=bbox, score=5.0, elapsed_ms=5.0)

            def start(self, frame, bbox):
                self.calls += 1
                return self._res(A)

            def process(self, frame):
                self.calls += 1
                return self._res(B if self.jump else A)

            def reset(self):
                self.reset_calls += 1

        fx = generate_tracking_sequence(num_frames=40, frame_size=(120, 200),
                                        square_size=40, start=(10, 10), velocity=(0, 0))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        engine = NhayEngine()
        # `lost_after_frames` lớn ⇒ session KHÔNG tự mất dấu; nếu bỏ track thì là do CỔNG HIỂN THỊ
        session = ReIdSession(engine=engine, embedder=None, cue="object",
                              lost_after_frames=99, reacquire_confirm=1, verify_frames=0)
        selector = PromptSelector(frame_shape=(120, 200, 3))
        bboxes = []
        state = {"n": 0}

        def display(img, mode):
            state["n"] += 1
            return list(QUIT_KEYS)[0] if state["n"] >= 90 else -1

        def on_result(r):
            bboxes.append(tuple(r.bbox))
            if len(bboxes) >= 5:            # đã thấy ô A vài lần ⇒ bật cú nhảy sang B
                engine.jump = True

        run_smooth_display(source=str(path), engine=engine, selector=selector,
                           display=display, preselect_bbox=A, reid_session=session,
                           on_result=on_result)

        assert B in bboxes, "giả lập phải thực sự tạo cú nhảy (nếu không test vô nghĩa)"
        assert engine.reset_calls >= 1, "cổng nghi phải làm session BỎ track (reset engine)"
        assert any(b == (0, 0, 0, 0) for b in bboxes[bboxes.index(B):]), (
            "sau cú nhảy, session phải vào trạng thái tìm lại (mask rỗng) chứ không tiếp tục "
            "'tracking' vùng sai — đúng lỗi 48 bước trên áo người của phiên demoip_1123-092343"
        )


def test_reanchor_giu_mau_tham_chieu_reid():
    """`c` = "vẫn đúng": neo lại engine nhưng KHÔNG được xoá ký ức đặc trưng của Re-ID.

    `set_bbox()` (chọn lại vật khác) thì phải xoá; `reanchor()` (xác nhận vùng hiện tại) thì không —
    nếu xoá, người dùng vừa xác nhận xong đã mất luôn khả năng nhận lại khi vật bị che.
    """
    calls = []

    class FakeSession:
        state = "tracking"

        def start(self, frame, bbox):
            calls.append(("start", tuple(bbox)))
            return TrackingResult(frame_idx=0, mask=np.ones((20, 20), bool),
                                  bbox=(10, 10, 50, 50), score=5.0, elapsed_ms=1.0)

        def step(self, frame):
            time.sleep(0.01)
            return Step(result=TrackingResult(frame_idx=1, mask=np.ones((20, 20), bool),
                                              bbox=(10, 10, 50, 50), score=5.0, elapsed_ms=1.0),
                        state="tracking")

        def reset(self):
            calls.append(("reset", None))

        def set_suspicious(self, co):
            pass

    from src.reid import Step

    src = LatestFrameSource(FakeSource(delay=0.005))
    src.start()
    engine = FakeEngine(delay=0.01)
    worker = InferenceWorker(engine, src, reid_session=FakeSession())
    worker.start()
    try:
        worker.set_bbox((10, 10, 50, 50))
        deadline = time.time() + 2.0
        while time.time() < deadline and not worker.latest_result():
            time.sleep(0.02)
        n_reset = sum(1 for c in calls if c[0] == "reset")
        worker.reanchor((12, 12, 52, 52))
        deadline = time.time() + 2.0
        while time.time() < deadline and ("start", (12, 12, 52, 52)) not in calls:
            time.sleep(0.02)
    finally:
        worker.stop()
        src.stop()

    assert ("start", (12, 12, 52, 52)) in calls, "phải bám lại từ ô vừa xác nhận"
    assert sum(1 for c in calls if c[0] == "reset") == n_reset, (
        "`reanchor` KHÔNG được reset Re-ID (xoá mẫu tham chiếu)"
    )
