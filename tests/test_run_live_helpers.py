

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
