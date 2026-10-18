"""Test seam VideoSource — interface thống nhất cho webcam / RTSP / video file.

Chỉ test hành vi công khai qua factory `open_video_source` + adapter (open/read/close/properties).
Số liệu kỳ vọng lấy từ fixture giả lập (nguồn độc lập với code chạy).
"""
import numpy as np
import pytest

from src.synthetic_video import generate_tracking_sequence
from src.video_source import open_video_source


class TestFileAdapter:
    """Seam VideoSource — file adapter đọc đúng số frame/kích thước/dtype (tiêu chí 1)."""

    def test_doc_dung_so_frame_kich_thuoc_dtype_tu_fixture(self, tmp_path, write_video):
        fx = generate_tracking_sequence(num_frames=12, frame_size=(120, 160), square_size=30)
        path = write_video(tmp_path / "seq.avi", fx.frames, fps=30)

        src = open_video_source(str(path)).open()
        assert src.frame_size == (160, 120)  # (W, H)
        assert src.source_fps == pytest.approx(30)

        frames = []
        while True:
            frame = src.read()
            if frame is None:
                break
            frames.append(frame)
        assert len(frames) == 12
        assert all(f.shape == (120, 160, 3) for f in frames)
        assert all(f.dtype == np.uint8 for f in frames)

        # Sau khi cạn nguồn, read tiếp vẫn None (an toàn khi gọi nhầm lần nữa)
        assert src.read() is None
        src.close()


class TestFactoryDinhTuyenKieuNguon:
    """Yêu cầu 4 của ticket: một interface duy nhất, chọn nguồn qua tham số (lazy — chưa mở)."""

    def test_int_chon_webcam_string_chon_kieu_roi_dinh(self):
        from src.video_source import CameraVideoSource, FileVideoSource, RtspVideoSource

        assert isinstance(open_video_source(0), CameraVideoSource)
        assert isinstance(open_video_source("1"), FileVideoSource)  # chuỗi thường xem là path
        assert isinstance(open_video_source("rtsp://192.168.1.10:554/stream"), RtspVideoSource)


class TestNguonLoi:
    """Yêu cầu 3 của ticket: nguồn lỗi → báo lỗi rõ ràng thay vì treo."""

    def test_file_khong_ton_tai_bao_file_not_found_ro_rang(self, tmp_path):
        src = open_video_source(str(tmp_path / "khong-co.avi"))
        with pytest.raises(FileNotFoundError, match="khong-co.avi"):
            src.open()

    def test_rtsp_khong_ket_noi_duoc_bao_connection_error(self):
        # Port 9 (discard) trên loopback — từ chối kết nối nhanh, không treo lâu
        src = open_video_source("rtsp://127.0.0.1:9/stream", open_timeout_ms=2000)
        with pytest.raises(ConnectionError, match="RTSP"):
            src.open()

    def test_read_truoc_open_bao_loi_ro_rang(self, tmp_path, write_video):
        fx = generate_tracking_sequence(num_frames=2, frame_size=(120, 160), square_size=30)
        src = open_video_source(str(write_video(tmp_path / "seq.avi", fx.frames)))
        with pytest.raises(RuntimeError, match="open()"):
            src.read()

class TestHttpSource:
    """Nguồn MJPEG/HTTP (điện thoại: IP Webcam, DroidCam…).

    Lỗi thật 18-10: `--source http://192.168.x.x:8080/video` bị coi là FILE →
    `FileNotFoundError: Không mở được video file` (thông báo sai đường, dễ gây lạc hướng).
    """

    def test_http_duoc_dinh_tuyen_sang_nguon_mang(self):
        from src.video_source import HttpVideoSource, open_video_source

        src = open_video_source("http://192.168.1.25:8080/video")
        assert isinstance(src, HttpVideoSource)
        assert isinstance(src, __import__("src.video_source", fromlist=["VideoSource"]).VideoSource)

    def test_https_cung_la_nguon_mang(self):
        from src.video_source import HttpVideoSource, open_video_source

        assert isinstance(open_video_source("https://cam.local/video"), HttpVideoSource)

    def test_loi_http_bao_huong_dan_lay_ip_that(self, monkeypatch):
        """Mở thất bại → thông báo nêu: kiểm tra IP thật, cùng Wi-Fi, đúng đường dẫn /video."""
        import cv2

        from src.video_source import open_video_source

        class FakeCap:
            def isOpened(self):
                return False

            def release(self):
                pass

            def set(self, *a, **k):
                return True

        monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: FakeCap())
        src = open_video_source("http://192.168.1.25:8080/video")
        try:
            src.open()
        except ConnectionError as err:
            msg = str(err)
            assert "http://192.168.1.25:8080/video" in msg
            assert "IP" in msg and ("Wi-Fi" in msg or "mạng" in msg)
        else:
            raise AssertionError("phải ném ConnectionError")

    def test_placeholder_bi_canh_bao_som(self, monkeypatch):
        """IP placeholder kiểu 192.168.x.x → báo lỗi nêu rõ 'IP thật' thay vì lỗi DNS thô."""
        import cv2

        from src.video_source import open_video_source

        class FakeCap:
            def isOpened(self):
                return False

            def release(self):
                pass

            def set(self, *a, **k):
                return True

        monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: FakeCap())
        with pytest.raises(ConnectionError, match="IP thật|placeholder"):
            open_video_source("http://192.168.x.x:8080/video").open()

    def test_file_that_su_van_bao_loi_file(self):
        from src.video_source import open_video_source

        with pytest.raises(FileNotFoundError, match="video file"):
            open_video_source("data/khong_ton_tai.mp4").open()
