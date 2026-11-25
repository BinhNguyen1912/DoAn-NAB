"""Test seam live pipeline — nối VideoSource → TrackerEngine → overlay + metrics (ticket 04).

Màn hình hiển thị tiêm qua callback `on_frame` để test headless (không cần cửa sổ).
Chạy chậm (propagation thật) — đánh dấu `slow`.
"""
import numpy as np
import pytest

from src.synthetic_video import generate_tracking_sequence
from src.live_pipeline import InteractiveSummary, run_tracking


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
        for khoa in ('if key == CONTINUE_KEY and (watch.nghi or watch.chua_xac_minh):',
                     'if key == RESET_KEY:'):
            pos = src.index(khoa)
            nhanh = src[pos:src.index("continue", pos)]     # cắt theo `continue` của chính nhánh
            assert "_bao_nghi(False)" in nhanh, khoa

    def test_phim_c_neo_lai_engine(self):
        """`c` = "vẫn đúng" nhưng session đã bị bỏ track ⇒ phải `start()` lại ở ô vừa bị nghi."""
        import inspect

        from src import live_pipeline as lp

        src = inspect.getsource(lp.run_interactive)
        pos_c = src.index("if key == CONTINUE_KEY and (watch.nghi or watch.chua_xac_minh):")
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


class TestPromptBboxTrongSummary:
    """23-11-2026 (review 3 ý kiến): `./run demoip` KHÔNG truyền `--bbox` — người dùng kéo chuột.

    Trước đây ô chọn không được lưu ở ĐÂU CẢ ⇒ `run_info` không có bbox ⇒ **không replay được
    phiên nào** (video `--record` lại đã cháy HUD nên không dùng làm nguồn thô). Nay summary mang
    `prompt_bbox` (ô ĐẦU TIÊN) + `reselect_n`.
    """

    def test_summary_ghi_o_chon_dau_tien_va_dem_lan_chon_lai(self):
        summary = InteractiveSummary()
        assert summary.prompt_bbox is None and summary.reselect_n == 0
        # mô phỏng luật trong vòng lặp: lần đầu lưu, các lần sau đếm
        for bbox in [(10, 10, 50, 50), (20, 20, 60, 60)]:
            if summary.prompt_bbox is None:
                summary.prompt_bbox = tuple(bbox)
            else:
                summary.reselect_n += 1
        assert summary.prompt_bbox == (10, 10, 50, 50)
        assert summary.reselect_n == 1

    def test_run_smooth_display_ghi_prompt_bbox(self, tmp_path, write_video):
        """Đường `--smooth` (đường demo CHÍNH): ô chọn phải tới được summary."""
        from src.live_pipeline import QUIT_KEYS
        from src.prompt_selector import PromptSelector
        from src.smooth_display import run_smooth_display
        from src.synthetic_video import generate_tracking_sequence
        from src.tracker_engine import TrackingResult

        class Eng:
            def start(self, frame, bbox):
                m = np.zeros((120, 200), bool)
                m[10:50, 10:50] = True
                return TrackingResult(frame_idx=0, mask=m, bbox=(10, 10, 50, 50), score=5.0,
                                      elapsed_ms=1.0)

            def process(self, frame):
                return self.start(frame, None)

            def reset(self):
                pass

        fx = generate_tracking_sequence(num_frames=20, frame_size=(120, 200),
                                        square_size=40, start=(10, 10), velocity=(0, 0))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        st = {"n": 0}

        def display(img, mode):
            st["n"] += 1
            return list(QUIT_KEYS)[0] if st["n"] >= 10 else -1

        summary = run_smooth_display(source=str(path), engine=Eng(),
                                     selector=PromptSelector(frame_shape=(120, 200, 3)),
                                     display=display, preselect_bbox=(10, 10, 50, 50))
        assert summary.prompt_bbox == (10, 10, 50, 50)


class TestPhimCTaiChuaXacMinhHanhVi:
    """24-11 (review vòng 2, P1): vá `c` ở `chua_xac_minh` mới chỉ có test ĐỌC SOURCE.

    Đột biến "giữ điều kiện mới nhưng xoá `watch.reset()`" làm mọi test cũ vẫn XANH trong khi lỗi
    quay lại (bấm `c` không có tác dụng ⇒ kẹt "chưa xác minh" tới hết phiên). Test này chạy VÒNG LẶP
    THẬT của `run_interactive` và đọc `chua_xac_minh` mà visualizer nhận ở từng frame.
    """

    def test_bam_c_thoat_chua_xac_minh_va_xoa_quy_dao(self, tmp_path, write_video, monkeypatch):
        from src.live_pipeline import CONTINUE_KEY, QUIT_KEYS, run_interactive
        from src.prompt_selector import PromptSelector
        from src.synthetic_video import generate_tracking_sequence
        from src.tracker_engine import TrackingResult
        from src.visualizer import Visualizer

        A, B = (10, 10, 50, 50), (180, 10, 220, 50)      # nhảy 170 px > bán kính

        def _res(bbox):
            m = np.zeros((120, 240), bool)
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

        nhan = []
        goc = Visualizer.update

        def ghi(self, frame, result, **kw):
            nhan.append({"switch": kw.get("switch_warning"),
                         "chua": kw.get("chua_xac_minh")})
            return goc(self, frame, result, **kw)

        monkeypatch.setattr(Visualizer, "update", ghi)

        fx = generate_tracking_sequence(num_frames=60, frame_size=(120, 240),
                                        square_size=40, start=(10, 10), velocity=(0, 0))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        engine = Engine()
        state = {"n": 0, "da_bam_c": False, "quy_dao_sau_c": None}
        viz = Visualizer()

        def display(img, mode):
            state["n"] += 1
            if state["n"] >= 4 and not engine.jump:
                engine.jump = True               # cú nhảy SAU khi đã có mốc cũ
            if state["da_bam_c"] and state["quy_dao_sau_c"] is None:
                # chụp NGAY sau khi `c` được xử lý (vòng trước) — đây là chỗ bug "nối quỹ đạo
                # qua cú nhảy" lộ ra: điểm cũ (x≈30) còn nằm chung deque với vùng mới (x≈200)
                state["quy_dao_sau_c"] = viz.trajectory_points
            if nhan and nhan[-1]["chua"] and not state["da_bam_c"]:
                state["da_bam_c"] = True          # đã sang "chưa xác minh" ⇒ bấm `c`
                # SENTINEL (review vòng 3, P1): cắm 1 điểm của "vùng CŨ" NGAY trước khi bấm `c`.
                # Không có nó thì test vẫn xanh khi xoá hẳn call-site `clear_trajectory` ở nhánh `c`
                # (vì giai đoạn `nghi` đã xoá quỹ đạo mỗi frame ⇒ deque vốn đã sạch).
                viz._trajectory.append((30, 30))
                viz._traj_ts.append(0.0)
                return CONTINUE_KEY
            return list(QUIT_KEYS)[0] if state["n"] >= 60 else -1

        run_interactive(source=str(path), engine=engine, selector=PromptSelector(
            frame_shape=(120, 240, 3)), display=display, preselect_bbox=A, visualizer=viz)

        assert any(d["chua"] for d in nhan), "phải tới được trạng thái chưa xác minh (nếu không, test vô nghĩa)"
        chi_so_bam = next(i for i, d in enumerate(nhan) if d["chua"])
        sau = nhan[chi_so_bam + 1:]
        assert sau, "phải có frame render SAU khi bấm `c`"
        assert not any(d["chua"] for d in sau), "bấm `c` rồi vẫn 'chưa xác minh' ⇒ kẹt (bug P1-a)"
        assert not any(d["switch"] for d in sau), "bấm `c` rồi vẫn còn cờ nghi"
        snap = state["quy_dao_sau_c"]
        assert snap, "quỹ đạo sau khi bấm `c` rỗng ⇒ không chứng minh được gì"
        assert (30, 30) not in snap, ("sentinel vùng CŨ còn trong quỹ đạo sau `c` ⇒ call-site "
                                      "`clear_trajectory` ở nhánh `c` không chạy")
        assert any(x > 150 for x, _ in snap), "quỹ đạo sau `c` phải có điểm của vùng MỚI"


class TestDemChuaXacMinhDuongCli:
    """24-11 (ticket #47): đường `./run demoip` phải TỰ ĐẾM "chưa xác minh".

    Vì sao: mọi tuyên bố "44,3 % → 10,6 % + 33,7 %" trước đây chỉ kiểm được bằng **replay trên CSV**,
    vì `InteractiveSummary` không có bộ đếm ⇒ phiên live không sinh ra số nào. Đường web đã có
    (`status.json: chua_xac_minh_n`).
    """

    def test_summary_co_bo_dem_va_tang_trong_vong_lap(self, tmp_path, write_video):
        from src.live_pipeline import QUIT_KEYS, run_interactive
        from src.prompt_selector import PromptSelector
        from src.synthetic_video import generate_tracking_sequence
        from src.tracker_engine import TrackingResult

        A, B = (10, 10, 50, 50), (180, 10, 220, 50)

        def _res(bbox):
            m = np.zeros((120, 240), bool)
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

        fx = generate_tracking_sequence(num_frames=60, frame_size=(120, 240),
                                        square_size=40, start=(10, 10), velocity=(0, 0))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        engine = Engine()
        state = {"n": 0}

        def display(img, mode):
            state["n"] += 1
            if state["n"] >= 4 and not engine.jump:
                engine.jump = True
            return list(QUIT_KEYS)[0] if state["n"] >= 40 else -1

        summary = run_interactive(source=str(path), engine=engine,
                                  selector=PromptSelector(frame_shape=(120, 240, 3)),
                                  display=display, preselect_bbox=A)
        assert summary.chua_xac_minh_n > 0, "không đếm được frame 'chưa xác minh' trên đường CLI"
        # và không được đếm lẫn với "đang nghi" (2 trạng thái khác nhau)
        assert summary.chua_xac_minh_n < summary.processed


class TestPhimHoaThuong:
    """Caps Lock làm `c`/`r`/`q` im lặng không ăn — bug thật gặp lúc diễn tập 24-11.

    `cv2.waitKey` trả mã chữ HOA khi Caps Lock bật, mà các hằng số là `ord("c")`/`ord("r")`/`ord("q")`.
    Đây là đường thoát DUY NHẤT khỏi trạng thái `chua_xac_minh` khi re-ID tắt (mặc định `./run demoip`)
    ⇒ người diễn bấm mà không thấy gì rồi tưởng hệ treo.
    """

    def test_chu_hoa_duoc_doi_ve_thuong(self):
        from src.live_pipeline import CONTINUE_KEY, QUIT_KEYS, RESET_KEY, chuan_hoa_phim

        assert chuan_hoa_phim(ord("C")) == CONTINUE_KEY
        assert chuan_hoa_phim(ord("R")) == RESET_KEY
        assert chuan_hoa_phim(ord("Q")) == QUIT_KEYS[0]

    def test_khong_doi_phim_da_thuong_va_ESC(self):
        from src.live_pipeline import CONTINUE_KEY, chuan_hoa_phim

        assert chuan_hoa_phim(CONTINUE_KEY) == CONTINUE_KEY
        assert chuan_hoa_phim(27) == 27          # ESC
        assert chuan_hoa_phim(-1) == -1          # waitKey không có phím


class TestCoCongNghiDiToiCong:
    """Khoá DÂY NỐI: `settle_steps`/`max_jump_ratio` phải tới `IdentityWatch` THẬT.

    Review độc lập 24-11 (P1): 8 test mới của tôi chỉ kiểm hàm thuần/argparse ⇒ đột biến "xoá dòng
    truyền `settle_steps=_settle_steps(args)`" vẫn xanh. Test dưới bắt đột biến đó: cùng engine nhảy,
    `settle_steps=1` phải cho SỐ FRAME ẨN KHÁC `settle_steps=8`.
    """

    @staticmethod
    def _res(bbox):
        from src.tracker_engine import TrackingResult

        m = np.zeros((120, 240), bool)
        m[bbox[1]:bbox[3], bbox[0]:bbox[2]] = True
        return TrackingResult(frame_idx=0, mask=m, bbox=bbox, score=5.0, elapsed_ms=1.0)

    def _chay(self, tmp_path, write_video, **kw):
        from src.live_pipeline import QUIT_KEYS, run_interactive
        from src.prompt_selector import PromptSelector

        A, B = (20, 20, 60, 60), (150, 60, 190, 100)
        res = self._res

        class Engine:
            jump = True

            def start(self, frame, bbox):
                return res(A)

            def process(self, frame):
                return res(B)

            def reset(self):
                pass

        fx = generate_tracking_sequence(num_frames=40, frame_size=(120, 240),
                                        square_size=40, start=(10, 10), velocity=(0, 0))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        state = {"n": 0}

        def display(img, mode):
            state["n"] += 1
            return list(QUIT_KEYS)[0] if state["n"] >= 30 else -1

        return run_interactive(source=str(path), engine=Engine(),
                               selector=PromptSelector(frame_shape=(120, 240, 3)),
                               display=display, preselect_bbox=A, **kw)

    def test_settle_1_it_frame_an_hon_settle_8(self, tmp_path, write_video):
        it = self._chay(tmp_path, write_video, settle_steps=1)
        nhieu = self._chay(tmp_path, write_video, settle_steps=8)
        # `settle_steps` nhỏ ⇒ hạ mức SỚM hơn ⇒ nhiều frame "chưa xác minh" hơn. Nếu cờ KHÔNG tới
        # cổng (đột biến xoá dòng `settle_steps=_settle_steps(args)`) thì hai lần chạy BẰNG NHAU.
        assert nhieu.chua_xac_minh_n > 0, "engine nhảy phải làm cổng bật rồi hạ mức"
        assert it.chua_xac_minh_n > nhieu.chua_xac_minh_n, (
            "settle_steps=1 phải hạ mức SỚM hơn settle_steps=8 ⇒ nhiều frame chưa xác minh hơn")

    def test_max_jump_ratio_that_su_doi_hanh_vi(self, tmp_path, write_video):
        # Trần 0.9 (gần đường chéo) ⇒ engine nhảy 130 px không còn bị coi là nhảy.
        rong = self._chay(tmp_path, write_video, max_jump_ratio=0.9)
        chat = self._chay(tmp_path, write_video, max_jump_ratio=0.05)
        assert chat.chua_xac_minh_n > 0
        assert rong.chua_xac_minh_n < chat.chua_xac_minh_n, (
            "trần 0.9 (rộng) ⇒ không coi cú nhảy 130 px là nhảy ⇒ ít frame chưa xác minh hơn trần 0.05")


class TestPhimCHoaDiToiVongLap:
    """`chuan_hoa_phim` phải được ÁP trong vòng lặp — test hàm thuần không bắt được đột biến bỏ nó."""

    @staticmethod
    def _chay(tmp_path, write_video, bam_C):
        from src.live_pipeline import QUIT_KEYS, run_interactive
        from src.prompt_selector import PromptSelector
        from src.tracker_engine import TrackingResult

        A, B = (20, 20, 60, 60), (150, 60, 190, 100)

        def res(bbox):
            m = np.zeros((120, 240), bool)
            m[bbox[1]:bbox[3], bbox[0]:bbox[2]] = True
            return TrackingResult(frame_idx=0, mask=m, bbox=bbox, score=5.0, elapsed_ms=1.0)

        class Engine:
            jump = True

            def start(self, frame, bbox):
                return res(A)

            def process(self, frame):
                return res(B)

            def reset(self):
                pass

        fx = generate_tracking_sequence(num_frames=40, frame_size=(120, 240),
                                        square_size=40, start=(10, 10), velocity=(0, 0))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)
        state = {"n": 0, "bam": 0}

        def display(img, mode):
            state["n"] += 1
            if state["n"] >= 34:
                return list(QUIT_KEYS)[0]
            if bam_C and state["n"] >= 14:
                state["bam"] += 1
                return ord("C")           # Caps Lock bật ⇒ mã CHỮ HOA
            return -1

        summary = run_interactive(source=str(path), engine=Engine(),
                                  selector=PromptSelector(frame_shape=(120, 240, 3)),
                                  display=display, preselect_bbox=A)
        return summary, state

    def test_bam_C_hoa_lam_GIAM_frame_chua_xac_minh(self, tmp_path, write_video):
        co_bam, st = self._chay(tmp_path, write_video, bam_C=True)
        khong_bam, _ = self._chay(tmp_path, write_video, bam_C=False)
        assert st["bam"] > 0, "test phải thực sự bấm phím"
        # `c` (kể cả mã HOA) xoá cổng ⇒ phần còn lại của phiên KHÔNG bị "chưa xác minh".
        # Nếu `chuan_hoa_phim` bị bỏ (đột biến ở call-site), `c` không khớp ⇒ hai lần chạy BẰNG NHAU.
        assert co_bam.chua_xac_minh_n < khong_bam.chua_xac_minh_n, (
            f"bấm `C` hoa phải giảm frame chưa xác minh: {co_bam.chua_xac_minh_n} vs "
            f"{khong_bam.chua_xac_minh_n}")


class TestPhimHoaOModeChon:
    """Caps Lock lúc đang KÉO Ô (mode `select`): `q` hoa phải vẫn thoát (review vòng 2, P2-D)."""

    def test_bam_Q_hoa_thoat_duoc_khi_dang_chon(self, tmp_path, write_video):
        from src.live_pipeline import run_interactive
        from src.prompt_selector import PromptSelector

        fx = generate_tracking_sequence(num_frames=10, frame_size=(120, 240),
                                        square_size=40, start=(10, 10), velocity=(0, 0))
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)

        class Engine:
            def start(self, frame, bbox):        # không được gọi: chưa chọn ô
                raise AssertionError("chưa chọn ô mà engine.start() bị gọi")

            def process(self, frame):
                raise AssertionError

            def reset(self):
                pass

        mode_da_gap = {"select": 0}

        def display(img, mode):
            mode_da_gap[mode] = mode_da_gap.get(mode, 0) + 1
            return ord("Q")          # Caps Lock bật ⇒ 'Q' hoa, phải thoát ngay

        summary = run_interactive(source=str(path), engine=Engine(),
                                  selector=PromptSelector(frame_shape=(120, 240, 3)),
                                  display=display, preselect_bbox=None)
        assert mode_da_gap.get("select", 0) == 1, "phải thoát ngay ở frame chọn ô đầu tiên"
        assert summary.processed == 0
