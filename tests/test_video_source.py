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