"""Test bộ sinh ảnh giả lập (fixture) dùng cho test TrackerEngine (ticket 02).

Chỉ test hành vi công khai qua API `generate_tracking_sequence` — không đụng nội bộ.
Số liệu kỳ vọng trong test là LITERAL tính tay (nguồn độc lập), không tính lại bằng code.
"""
import numpy as np
import pytest
import pytest

from src.synthetic_video import BACKGROUND_COLOR, SQUARE_COLOR, generate_tracking_sequence


class TestHinhDangFrame:
    def test_sinh_dung_so_frame_kich_thuoc_va_dtype(self):
        # Cấu hình: 5 frame, 240x320 — kỳ vọng shape (N,H,W,3), dtype uint8
        fx = generate_tracking_sequence(num_frames=5, frame_size=(240, 320), square_size=40)

        assert fx.frames.shape == (5, 240, 320, 3)
        assert fx.frames.dtype == np.uint8
        assert len(fx.bboxes) == 5
        assert len(fx.occluded) == 5


class TestQuyDao:
    """Đáp án quỹ đạo là LITERAL tính tay từ tham số (nguồn độc lập với code)."""

    def test_bbox_theo_quy_dao_tuyen_tinh_tinh_tay(self):
        # start=(20,20), velocity=(4,2), square=40 → frame i: (20+4i, 20+2i, 60+4i, 60+2i)
        fx = generate_tracking_sequence(
            num_frames=5, frame_size=(240, 320), square_size=40, start=(20, 20), velocity=(4, 2)
        )
        assert fx.bboxes[0] == (20, 20, 60, 60)
        assert fx.bboxes[3] == (32, 26, 72, 66)  # frame cuối: (36, 28, 76, 68)
        assert fx.bboxes[4] == (36, 28, 76, 68)

    def test_pixel_tam_o_doi_xung_voi_bbox_va_mau_dung(self):
        # Trung tâm ô ở frame 3: x = (32+72)//2 = 52, y = (26+66)//2 = 46
        fx = generate_tracking_sequence(
            num_frames=5, frame_size=(240, 320), square_size=40, start=(20, 20), velocity=(4, 2)
        )
        assert tuple(fx.frames[3, 46, 52, :]) == SQUARE_COLOR
        # Pixel nền xa ô (góc trái trên) phải là màu nền
        assert tuple(fx.frames[3, 5, 5, :]) == BACKGROUND_COLOR


class TestCheKhuat:
    """Yêu cầu 3 của ticket: ô bị che trong các frame chỉ định nhưng quỹ đạo đáp án vẫn đúng."""

    def test_o_bi_an_khoi_frame_nhung_bbox_dat_an_van_theo_quy_dao(self):
        fx = generate_tracking_sequence(
            num_frames=5,
            frame_size=(240, 320),
            square_size=40,
            start=(20, 20),
            velocity=(4, 2),
            occlusion_frames=(2,),
        )
        # Frame 2: ô bị che → vùng ô phải bằng màu nền (không còn ô màu cam)
        assert tuple(fx.frames[2, 46, 52, :]) == BACKGROUND_COLOR
        # Nhưng đáp án quỹ đạo vẫn tiếp tục như không có che khuất
        assert fx.bboxes[2] == (28, 24, 68, 64)
        assert fx.bboxes[3] == (32, 26, 72, 66)
        assert tuple(fx.occluded) == (False, False, True, False, False)


class TestCauHinhLoi:
    def test_quy_dao_tran_frame_bao_loi_ro_rang(self):
        # start=(300, 20) với frame rộng 320, ô 40px → frame 0 đã tràn (x2 = 340 > 320)
        with pytest.raises(ValueError, match="tràn frame"):
            generate_tracking_sequence(
                num_frames=4, frame_size=(240, 320), square_size=40, start=(300, 20)
            )