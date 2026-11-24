

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
