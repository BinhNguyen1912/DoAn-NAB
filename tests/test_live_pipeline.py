"""Test seam live pipeline — nối VideoSource → TrackerEngine → overlay + metrics (ticket 04).

Màn hình hiển thị tiêm qua callback `on_frame` để test headless (không cần cửa sổ).
Chạy chậm (propagation thật) — đánh dấu `slow`.
"""
import numpy as np
import pytest

from src.synthetic_video import generate_tracking_sequence
from src.live_pipeline import run_tracking


@pytest.mark.slow
class TestLivePipeline:
    def test_chay_qua_video_fixture_dem_du_frame_va_overlay_co_tac_dong(
        self, samurai_engine, tmp_path, write_video
    ):
        fx = generate_tracking_sequence(num_frames=6, frame_size=(240, 320), square_size=40, start=(60, 60))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)

        shown = []
        summary = run_tracking(
            source=str(path),
            engine=samurai_engine,
            bbox=fx.bboxes[0],
            on_frame=lambda img, res: shown.append((img, res)),
        )

        # Đủ 6 frame xử lý + hiển thị từng frame
        assert summary.total_frames == 6
        assert len(shown) == 6
        # Thứ tự frame đúng (result.frame_idx tăng dần)
        assert [res.frame_idx for _, res in shown] == [0, 1, 2, 3, 4, 5]
        # Overlay thêm nét — frame hiển thị phải khác frame gốc đọc từ file (tô mask + vẽ ô)
        img0, res0 = shown[0]
        assert img0.shape == (240, 320, 3)
        assert not np.array_equal(img0, fx.frames[0])
        # Metrics trung thực: danh sách latency đủ N, mean > 0, fps hiệu dụng > 0
        assert len(summary.latencies_ms) == summary.total_frames
        assert summary.mean_ms > 0
        assert summary.effective_fps > 0

class TestReanchor:
    """Tối ưu tốc độ: re-anchor định kỳ (reset + chọn lại bbox hiện tại).

    Đo thật 18-10 trên fixture 20 frame (ô vuông + che 5 frame):
      baseline      : 5340 ms/frame, IoU sau che 0.981, mất dấu 5/19
      re-anchor 3   : 3053 ms/frame (2.2x nhanh hơn), IoU sau che 0.969, mất dấu 0/19
    Vì vậy đây là TUỲ CHỌN (mặc định tắt) — đánh đổi memory dài hạn lấy tốc độ.
    """

    def _engine(self):
        from src.tracker_engine import TrackingResult

        class FakeEngine:
            def __init__(self):
                self.calls = []
                self._idx = -1

            def start(self, frame, bbox):
                self.calls.append(("start", tuple(bbox)))
                self._idx = 0
                return self._res(0, bbox)

            def process(self, frame):
                self._idx += 1
                self.calls.append(("process",))
                x = 60 + 4 * self._idx
                return self._res(self._idx, (x, 60, x + 40, 100))

            def reset(self):
                self.calls.append(("reset",))
                self._idx = -1

            @staticmethod
            def _res(i, bbox):
                import numpy as np

                mask = np.zeros((240, 320), dtype=bool)
                x1, y1, x2, y2 = bbox
                mask[y1:y2, x1:x2] = True
                return TrackingResult(frame_idx=i, mask=mask, bbox=tuple(bbox),
                                      score=0.9, elapsed_ms=50.0)

        return FakeEngine()

    def test_reanchor_dung_nhip_va_dung_bbox_cuoi(self, tmp_path, write_video):
        from src.live_pipeline import run_tracking

        fx = generate_tracking_sequence(num_frames=7, frame_size=(240, 320),
                                        square_size=40, start=(60, 60))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        engine = self._engine()

        run_tracking(source=str(path), engine=engine, bbox=fx.bboxes[0], reanchor_every=3)

        names = [c[0] for c in engine.calls]
        # frame 0 start, f1 process, f2 process, f3 re-anchor (reset+start), ...
        assert names.count("reset") >= 2
        assert names.count("start") >= 3
        # bbox truyền vào lần re-anchor phải là bbox của frame NGAY TRƯỚC (không phải bbox gốc)
        starts = [c[1] for c in engine.calls if c[0] == "start"]
        assert starts[0] == tuple(fx.bboxes[0])
        assert starts[1] != starts[0]              # đã tiến theo quỹ đạo
        assert starts[1][0] == 60 + 4 * 2          # bbox của frame 2 (trước re-anchor ở frame 3)

    def test_mac_dinh_khong_reanchor(self, tmp_path, write_video):
        from src.live_pipeline import run_tracking

        fx = generate_tracking_sequence(num_frames=5, frame_size=(240, 320),
                                        square_size=40, start=(60, 60))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        engine = self._engine()

        run_tracking(source=str(path), engine=engine, bbox=fx.bboxes[0])
        names = [c[0] for c in engine.calls]
        assert names.count("reset") == 0
        assert names.count("start") == 1


class TestPipelineReId:
    """Wiring re-ID ở mức pipeline: mất dấu thì ĐÓNG BĂNG, không gọi engine.process nữa."""

    def _engine(self, empty_after=1):
        from src.tracker_engine import TrackingResult
        calls = {"process": 0, "start": []}

        class FakeEngine:
            def start(self, frame, bbox):
                calls["start"].append(tuple(bbox))
                return TrackingResult(frame_idx=0, mask=np.ones((240, 320), bool),
                                      bbox=(20, 20, 80, 80), score=1.0, elapsed_ms=1.0)

            def process(self, frame):
                calls["process"] += 1
                empty = calls["process"] >= empty_after
                mask = np.zeros((240, 320), bool) if empty else np.ones((240, 320), bool)
                return TrackingResult(frame_idx=calls["process"], mask=mask,
                                      bbox=(20, 20, 80, 80), score=1.0, elapsed_ms=1.0)

            def reset(self):
                pass

        return FakeEngine(), calls

    def _session(self, engine):
        from src.reid import ReIdSession

        class NoFaceEmbedder:
            def detect(self, frame):
                return []

        return ReIdSession(engine, NoFaceEmbedder(), threshold=0.5, lost_after_frames=1)

    def test_mat_dau_thi_khong_goi_process_nua_va_co_cot_trang_thai(self, tmp_path, write_video):
        from src.metrics_logger import MetricsLogger
        from src.synthetic_video import generate_tracking_sequence

        fx = generate_tracking_sequence(num_frames=8, frame_size=(240, 320),
                                        square_size=40, start=(60, 60))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        engine, calls = self._engine(empty_after=1)
        session = self._session(engine)
        metrics = MetricsLogger()

        run_tracking(source=str(path), engine=engine, bbox=fx.bboxes[0],
                     reid_session=session, metrics=metrics)

        # Frame đầu process trả mask rỗng → chuyển LOST; các frame sau KHÔNG process nữa
        assert calls["process"] == 1
        states = [r.state for r in metrics.records]
        assert states[0] == "tracking"
        assert "lost" in states or "reacquiring" in states
        assert states[-1] == "reacquiring"
        # Record mất dấu được ghi nhận trung thực
        assert any(r.lost for r in metrics.records)
        assert metrics.summary()["lost_count"] >= 1


class TestCoVetoToiHudOHaiDuong:
    """P1 review vòng 2 (21-11): `run_interactive` (đường `--display --reid`, KHÔNG `--smooth`)

    từng KHÔNG gán `reid_vetoed` từ `step` ⇒ nhánh HUD nói lý do veto không bao giờ chạy, và vì
    `reid_score = -1` khi mọi ứng viên bị bỏ, HUD còn in "chua co ung vien — kiem tra vat chon co
    cham mep khung" (chẩn đoán SAI). Test khoá cả hai đường.
    """

    def _step(self, vetoed):
        from src.reid import Step
        from src.tracker_engine import TrackingResult
        r = TrackingResult(
            frame_idx=1,
            mask=np.ones((240, 320), dtype=bool),
            bbox=(60, 60, 100, 100),
            score=5.0,
            elapsed_ms=10.0,
        )
        return Step(result=r, state="reacquiring", reid_score=0.90, reacquired=False,
                    ncc=0.42, vetoed=vetoed)

    class _Session:
        def __init__(self, step):
            self._step_obj = step
            self.state = step.state

        def step(self, _frame):
            return self._step_obj

        def reset(self):
            pass

        def start(self, _frame, _bbox):
            return self._step_obj.result

    def test_run_interactive_truyen_co_veto_toi_hud(self, tmp_path, write_video, monkeypatch):
        from src.live_pipeline import run_interactive
        fx = generate_tracking_sequence(num_frames=3, frame_size=(240, 320), square_size=40,
                                        start=(60, 60))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)

        seen = []

        class Viz:
            def update(self, frame, result, **kw):
                seen.append(kw.get("reid_vetoed"))
                return frame.copy()

            def reset(self):
                pass

            def close_recorder(self):
                pass

            def consume(self, _r):
                pass

            def render(self, frame, result, **kw):
                seen.append(kw.get("reid_vetoed"))
                return frame.copy()

        monkeypatch.setattr("src.live_pipeline.cv2.imshow", lambda *a, **k: None)
        monkeypatch.setattr("src.live_pipeline.cv2.waitKey", lambda *a, **k: 0)
        from src.prompt_selector import PromptSelector
        run_interactive(
            source=str(path), engine=object(), selector=PromptSelector(frame_shape=(240, 320, 3)),
            display=lambda img, mode: "q",
            preselect_bbox=fx.bboxes[0],
            reid_session=self._Session(self._step(True)),
            visualizer=Viz(),
        )
        assert seen and any(v is True for v in seen)   # HUD PHẢI nhận được cờ veto


class TestLivePipelineIdentityLatchFix:
    """Test fix cho deadlock IdentityWatch trong run_interactive."""

    def test_reacquired_va_mat_dau_pipeline(self):
        import inspect

        from src import live_pipeline as lp

        src = inspect.getsource(lp.run_interactive)
        assert "if reacquired:" in src
        assert "watch.reset()" in src
        assert "last_bbox = (0, 0, 0, 0)" in src
        pos_reacq = src.index("if reacquired:")
        pos_reset = src.index("watch.reset()", pos_reacq)
        assert pos_reacq < pos_reset



class TestCoNghiEpTimLaiInline:
    """23-11-2026: cùng luật với đường MƯỢT — cổng nghi phải báo xuống `ReIdSession` (đường

    `run_interactive`, tức `./run view`/`--reid` không `--smooth`), không chỉ ẩn overlay.
    """

    def test_cong_nghi_bao_xuong_reid_session(self):
        import inspect

        from src import live_pipeline as lp

        src = inspect.getsource(lp.run_interactive)
        assert "_bao_nghi(watch.nghi)" in src
        assert "reid_session.set_suspicious(co)" in src
        # `c` và `r` phải xoá cờ (nếu không bước track kế tiếp lại bị bỏ ⇒ quay vòng)
        for khoa in ('if key == CONTINUE_KEY and watch.nghi:', 'if key == RESET_KEY:'):
            pos = src.index(khoa)
            assert "_bao_nghi(False)" in src[pos:pos + 400], khoa

    def test_phim_c_neo_lai_engine(self):
        """`c` = "vẫn đúng" nhưng session đã bị bỏ track ⇒ phải `start()` lại ở ô vừa bị nghi."""
        import inspect

        from src import live_pipeline as lp

        src = inspect.getsource(lp.run_interactive)
        pos_c = src.index("if key == CONTINUE_KEY and watch.nghi:")
        assert src.index("reid_session.start(frame, bbox_luc_nghi)", pos_c) > pos_c


class TestCoNghiEpTimLaiThatSu:
    """P2 review 23-11: đường `run_interactive` (KHÔNG `--smooth`) trước đây chỉ có test đọc source.

    Một regression thật — không gọi `set_suspicious`, gọi sai giá trị, hay `c` neo sai ô — vẫn xanh.
    Test này chạy vòng lặp thật với session giả GHI LẠI lời gọi.
    """

    def test_cong_nghi_goi_set_suspicious_va_c_neo_lai(self, tmp_path, write_video):
        from src.live_pipeline import CONTINUE_KEY, QUIT_KEYS, run_interactive
        from src.prompt_selector import PromptSelector
        from src.synthetic_video import generate_tracking_sequence
        from src.tracker_engine import TrackingResult

        A, B = (10, 10, 50, 50), (80, 10, 120, 50)     # nhảy 70 px

        def _res(bbox):
            m = np.zeros((120, 200), bool)
            m[bbox[1]:bbox[3], bbox[0]:bbox[2]] = True
            return TrackingResult(frame_idx=0, mask=m, bbox=bbox, score=5.0, elapsed_ms=1.0)

        class Engine:
            def __init__(self):
                self.jump = False

            def start(self, frame, bbox):
                return _res(A)

            def process(self, frame):
                return _res(B if self.jump else A)

            def reset(self):
                pass

        class Session:
            """Session giả: đủ API mà `run_interactive` dùng, ghi lại mọi lời gọi."""

            state = "tracking"

            def __init__(self):
                self.suspicious_calls = []
                self.start_calls = []
                self.n = 0

            def step(self, frame):
                self.n += 1
                bbox = B if self.jump else A
                return Step(result=_res(bbox), state="tracking")

            jump = False

            def start(self, frame, bbox):
                self.start_calls.append(tuple(bbox))
                return _res(tuple(bbox))

            def reset(self):
                pass

            def set_suspicious(self, co):
                self.suspicious_calls.append(bool(co))

        from src.reid import Step

        fx = generate_tracking_sequence(num_frames=30, frame_size=(120, 200),
                                        square_size=40, start=(10, 10), velocity=(0, 0))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        engine = Engine()
        session = Session()
        session.jump = engine.jump
        selector = PromptSelector(frame_shape=(120, 200, 3))
        state = {"n": 0, "da_bam_c": False}

        def display(img, mode):
            state["n"] += 1
            if state["n"] >= 5 and not engine.jump:
                engine.jump = True          # bật cú nhảy SAU khi đã có mốc cũ
                session.jump = True
            if True in session.suspicious_calls and not state["da_bam_c"]:
                state["da_bam_c"] = True     # cổng đã báo nghi ⇒ bấm `c` = "vẫn đúng"
                return CONTINUE_KEY
            return list(QUIT_KEYS)[0] if state["n"] >= 40 else -1

        run_interactive(source=str(path), engine=engine, selector=selector, display=display,
                        preselect_bbox=A, reid_session=session)

        assert session.suspicious_calls[:1] == [True], (
            "cổng nghi phải báo xuống Re-ID (nếu không, session vẫn 'tracking' vùng sai)"
        )
        assert session.suspicious_calls[-1] is False, "bấm `c` phải xoá cờ nghi"
        assert B in session.start_calls, (
            "`c` phải neo lại engine ở ô LÚC NGHI (ô B của cú nhảy), không phải ô cũ"
        )
