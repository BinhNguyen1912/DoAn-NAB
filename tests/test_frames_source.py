"""Test nguồn dạng THƯ MỤC ẢNH (frames) — SAM 2 gốc nhận thư mục JPEG, không nhận video.

Dữ liệu thật trong repo: `data/demo_input_frames/` = 90 ảnh 1280x720 tách từ video demo.
Người dùng cần chạy được:  ./run video data/demo_input_frames
"""
import cv2
import numpy as np
import pytest

from src.video_source import FramesVideoSource, open_video_source


def _make_dir(tmp_path, n=3, size=(120, 160), color=100):
    d = tmp_path / "frames"
    d.mkdir()
    for i in range(n):
        img = np.full((size[0], size[1], 3), color + i, np.uint8)
        cv2.imwrite(str(d / f"{i:05d}.jpg"), img)
    return d


class TestFramesSource:
    def test_doc_dung_thu_tu_va_het_thi_tra_none(self, tmp_path):
        d = _make_dir(tmp_path, n=3)
        src = FramesVideoSource(str(d)).open()
        frames = [src.read() for _ in range(3)]
        assert all(f is not None for f in frames)
        # thứ tự đúng: 00000, 00001, 00002 (giá trị pixel tăng dần)
        assert [int(f[0, 0, 0]) for f in frames] == [100, 101, 102]
        assert src.read() is None          # cạn nguồn
        src.close()

    def test_kich_thuoc_va_fps_nguon(self, tmp_path):
        d = _make_dir(tmp_path, size=(120, 160))
        src = FramesVideoSource(str(d)).open()
        assert src.frame_size == (160, 120)     # (W, H)
        assert src.source_fps > 0
        src.close()

    def test_thu_muc_rong_bao_loi_ro_rang(self, tmp_path):
        d = tmp_path / "rong"
        d.mkdir()
        with pytest.raises(FileNotFoundError, match="không có ảnh"):
            FramesVideoSource(str(d)).open()

    def test_factory_tra_dung_loai_cho_thu_muc(self, tmp_path):
        d = _make_dir(tmp_path)
        assert isinstance(open_video_source(str(d)), FramesVideoSource)

    def test_factory_van_tra_file_video_cho_duong_dan_file(self, tmp_path):
        f = tmp_path / "x.mp4"
        f.write_bytes(b"x")
        assert not isinstance(open_video_source(str(f)), FramesVideoSource)
