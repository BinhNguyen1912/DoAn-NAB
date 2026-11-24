import pytest
class TestLaNguonLive:
    """Ticket #44 — `--record` chỉ giữ nhịp THỜI GIAN THỰC cho nguồn LIVE, không cho file."""

    def test_webcam_va_url_la_live(self):
        from tools.run_live import _la_nguon_live

        assert _la_nguon_live(0) is True
        assert _la_nguon_live("0") is True
        assert _la_nguon_live("rtsp://cam/x") is True
        assert _la_nguon_live("http://172.19.176.1:8090/snapshot.jpg") is True
        assert _la_nguon_live("https://host/video") is True

    def test_file_va_thu_muc_khong_phai_live(self):
        from tools.run_live import _la_nguon_live

        assert _la_nguon_live("data/binh1.mp4") is False
        assert _la_nguon_live("clip.avi") is False

    def test_khong_co_source_thi_khong_live(self):
        """Stub `args` không khai `source` (test cũ) ⇒ mặc định KHÔNG live, không được ném."""
        from tools.run_live import _la_nguon_live

        assert _la_nguon_live(None) is False


class TestCuaCongNghiDaGhiThat:
    """Provenance của cổng nghi phải là biến ĐIỀU KHIỂN THẬT, không phải hằng số trông giống biến.

    Review độc lập 24-11 (P1): `run_info` ghi `settle_steps: 8` cho mọi phiên (84 file) trong khi
    **không tồn tại cờ nào** điều khiển nó ⇒ trường đó trông như knob nhưng là hằng số. Thêm nữa
    ngưỡng `max_jump_ratio = 0,25×đường chéo` phụ thuộc KÍCH THƯỚC KHUNG mà không file nào ghi
    khung ⇒ phiên 1280×720 bị replay bằng trần 200 px (đúng phải 367 px) trong im lặng.
    """

    def test_co_co_dong_lenh_settle_va_max_jump(self):
        from tools.run_live import build_parser

        a = build_parser().parse_args(["--source", "0", "--settle-steps", "3",
                                       "--max-jump-ratio", "0.3"])
        assert a.settle_steps == 3
        assert a.max_jump_ratio == 0.3
        mac_dinh = build_parser().parse_args(["--source", "0"])
        assert mac_dinh.settle_steps is None      # None = dùng mặc định của IdentityWatch
        assert mac_dinh.max_jump_ratio is None

    def test_settle_steps_doc_tu_args(self):
        from types import SimpleNamespace

        from src.identity_guard import DEFAULT_SETTLE_STEPS
        from tools.run_live import _settle_steps

        assert _settle_steps(SimpleNamespace(settle_steps=2)) == 2
        assert _settle_steps(SimpleNamespace(settle_steps=None)) == DEFAULT_SETTLE_STEPS
        assert _settle_steps(SimpleNamespace()) == DEFAULT_SETTLE_STEPS

    def test_settle_steps_0_va_am_khong_bi_nuot(self):
        """P1-1 của review: `0` là giá trị HỢP LỆ (TẮT cổng), `x or default` cũ nuốt thành 8."""
        from types import SimpleNamespace

        from tools.run_live import _settle_steps

        assert _settle_steps(SimpleNamespace(settle_steps=0)) == 0
        assert _settle_steps(SimpleNamespace(settle_steps=-3)) == 0

    def test_headless_KHONG_ghi_co_khi_nguoi_dung_truyen(self):
        """P2-A: `./run video --settle-steps 3` đi headless (không dựng cổng) ⇒ run_info phải là None."""
        from types import SimpleNamespace

        from tools.run_live import _max_jump_ratio, _settle_steps

        a = SimpleNamespace(settle_steps=3, max_jump_ratio=0.4, _co_cong_nghi=False)
        assert _settle_steps(a) is None
        assert _max_jump_ratio(a) is None

    def test_max_jump_ratio_ghi_dung_gia_tri_mac_dinh(self):
        from types import SimpleNamespace

        from src.identity_guard import DEFAULT_MAX_JUMP_RATIO
        from tools.run_live import _max_jump_ratio

        assert _max_jump_ratio(SimpleNamespace(max_jump_ratio=None)) == DEFAULT_MAX_JUMP_RATIO
        assert _max_jump_ratio(SimpleNamespace(max_jump_ratio=0.3)) == 0.3

    def test_watch_nhan_settle_va_max_jump_qua_kwarg(self):
        """Hai cờ phải ĐI ĐẾN cổng thật (không chỉ vào run_info)."""
        from src.identity_guard import IdentityWatch

        w = IdentityWatch(settle_steps=2, max_jump_ratio=0.3)
        assert w.settle_steps == 2
        assert w.max_jump_ratio == 0.3


class TestCoCongNghiDuocTruyenTuRunLive:
    """Khoá dây nối CUỐI: `run_live._run_display` phải truyền 2 cờ xuống runner.

    Review độc lập 24-11 (P1-3): đột biến "xoá dòng `settle_steps=_settle_steps(args)` /
    `max_jump_ratio=args.max_jump_ratio` trong `run_live.py`" vẫn xanh vì mọi test chỉ chạm hàm thuần.
    Cách bắt: gọi `_run_display` với runner bị stub và kiểm kwargs nhận được.
    """

    @pytest.mark.parametrize("smooth", [True, False])
    def test_hai_co_toi_runner(self, monkeypatch, smooth):
        import types

        import cv2

        from tools import run_live

        nhan = {}

        from src.live_pipeline import InteractiveSummary

        def fake_smooth(**kw):
            nhan.update(kw)
            return InteractiveSummary()

        def fake_interactive(**kw):
            nhan.update(kw)
            return InteractiveSummary()

        monkeypatch.setattr(run_live, "run_smooth_display", fake_smooth)
        monkeypatch.setattr(run_live, "run_interactive", fake_interactive)
        monkeypatch.setattr(cv2, "namedWindow", lambda *a, **k: None)
        monkeypatch.setattr(cv2, "setMouseCallback", lambda *a, **k: None)
        monkeypatch.setattr(run_live, "_window_closed", lambda *a, **k: False)
        monkeypatch.setattr(run_live, "_make_visualizer", lambda args: None)
        monkeypatch.setattr(run_live, "_make_metrics", lambda args: None)
        monkeypatch.setattr(run_live, "_make_reid_session", lambda engine, args: None)
        monkeypatch.setattr(run_live, "_load_bbox", lambda args, first_frame=None: None)

        args = run_live.build_parser().parse_args(
            ["--source", "x", "--settle-steps", "3", "--max-jump-ratio", "0.4"])
        args.smooth = smooth
        args.metrics_csv = args.metrics_summary = None
        args._metrics = None
        run_live._run_display(engine=types.SimpleNamespace(), args=args)

        assert nhan.get("settle_steps") == 3
        assert nhan.get("max_jump_ratio") == 0.4


class TestCoModelOverride:
    """`--model-override k=v`: ép kiểu đúng, khoá lạ ⇒ SystemExit (không để hydra bỏ qua im lặng)."""

    def test_ep_kieu_va_lap_lai(self):
        from tools.run_live import _model_overrides, build_parser

        a = build_parser().parse_args([
            "--source", "x",
            "--model-override", "kf_score_weight=0.5",
            "--model-override", "samurai_mode=false",
            "--model-override", "stable_frames_threshold=8"])
        assert _model_overrides(a) == {"kf_score_weight": 0.5, "samurai_mode": False,
                                       "stable_frames_threshold": 8}

    def test_khoa_la_bi_chan(self):
        import pytest

        from tools.run_live import _model_overrides, build_parser

        a = build_parser().parse_args(["--source", "x", "--model-override", "kf_scor=0.5"])
        with pytest.raises(SystemExit, match="không hợp lệ"):
            _model_overrides(a)

    def test_sai_dinh_dang_bi_chan(self):
        import pytest

        from tools.run_live import _model_overrides, build_parser

        a = build_parser().parse_args(["--source", "x", "--model-override", "kf_score_weight"])
        with pytest.raises(SystemExit, match="KEY=VALUE"):
            _model_overrides(a)


class TestLostResetStreak:
    """24-11: `--lost-reset-streak` (vắng >= N bước = vật rời khung) phải đi đủ đường như

    `--settle-steps` — có cờ THẬT (không ghi `run_info` một giá trị không cờ nào đổi được, đúng lỗi
    P1 review 24-11), `0` là giá trị hợp lệ (tái lập hành vi trước 24-11), headless ghi `None`.
    """

    def test_mac_dinh_va_co_cli(self):
        from tools.run_live import build_parser, _lost_reset_streak

        mac_dinh = build_parser().parse_args(["--source", "0"])
        assert mac_dinh.lost_reset_streak is None
        from src.identity_guard import DEFAULT_LOST_RESET_STREAK

        assert _lost_reset_streak(mac_dinh) == DEFAULT_LOST_RESET_STREAK
        a = build_parser().parse_args(["--source", "0", "--lost-reset-streak", "5"])
        assert _lost_reset_streak(a) == 5

    def test_0_va_am_khong_bi_nuot(self):
        from types import SimpleNamespace

        from tools.run_live import _lost_reset_streak

        assert _lost_reset_streak(SimpleNamespace(lost_reset_streak=0)) == 0
        assert _lost_reset_streak(SimpleNamespace(lost_reset_streak=-2)) == 0

    def test_headless_ghi_none(self):
        from types import SimpleNamespace

        from tools.run_live import _lost_reset_streak

        assert _lost_reset_streak(SimpleNamespace(lost_reset_streak=3, _co_cong_nghi=False)) is None
