"""Test bộ sinh ảnh giả lập (fixture) dùng cho test TrackerEngine (ticket 02).

Chỉ test hành vi công khai qua API `generate_tracking_sequence` — không đụng nội bộ.
Số liệu kỳ vọng trong test là LITERAL tính tay (nguồn độc lập), không tính lại bằng code.
"""
import numpy as np
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

class TestCheMotPhan:
    """Tên đề tài nói "bị che khuất MỘT PHẦN" → fixture phải mô phỏng được mức che 0–100%."""

    def _dem_pixel_doi_tuong(self, frame, bbox):
        x1, y1, x2, y2 = bbox
        vung = frame[y1:y2, x1:x2]
        mau = np.array(SQUARE_COLOR, dtype=np.uint8)
        return int(np.all(vung == mau, axis=-1).sum())

    def test_che_mot_nua_con_lai_dung_nua_o(self):
        fx = generate_tracking_sequence(num_frames=3, frame_size=(240, 320), square_size=40,
                                        start=(20, 20), occlusion_frames=(1,),
                                        occlusion_fraction=0.5)
        full = self._dem_pixel_doi_tuong(fx.frames[0], fx.bboxes[0])     # 40*40
        half = self._dem_pixel_doi_tuong(fx.frames[1], fx.bboxes[1])
        assert full == 1600
        assert half == 800          # đúng một nửa còn nhìn thấy
        assert fx.occluded[1] is True or fx.occluded[1]

    def test_che_hoan_toan_khong_con_pixel(self):
        fx = generate_tracking_sequence(num_frames=3, frame_size=(240, 320), square_size=40,
                                        start=(20, 20), occlusion_frames=(1,),
                                        occlusion_fraction=1.0)
        assert self._dem_pixel_doi_tuong(fx.frames[1], fx.bboxes[1]) == 0

    def test_khong_che_thi_giu_nguyen_toan_bo(self):
        fx = generate_tracking_sequence(num_frames=3, frame_size=(240, 320), square_size=40,
                                        start=(20, 20), occlusion_frames=(1,),
                                        occlusion_fraction=0.0)
        assert self._dem_pixel_doi_tuong(fx.frames[1], fx.bboxes[1]) == 1600


class TestMaskGroundTruth:
    """GT mask theo pixel — thiếu nó thì mọi "chất lượng phân đoạn" chỉ là IoU hộp bao."""

    def test_mask_gt_khop_dung_pixel_mau_o_vuong(self):
        from src.mask_filter import mask_iou
        from src.synthetic_video import SQUARE_COLOR, generate_tracking_sequence

        fx = generate_tracking_sequence(num_frames=5, frame_size=(120, 160), square_size=30,
                                        start=(10, 10), velocity=(5, 0))
        for index, frame in enumerate(fx.frames):
            thuc_te = (frame == SQUARE_COLOR).all(axis=2)
            assert mask_iou(fx.masks[index], thuc_te) == 1.0, f"frame {index}"

    def test_mask_gt_tru_dung_phan_bi_che(self):
        from src.synthetic_video import generate_tracking_sequence

        fx = generate_tracking_sequence(num_frames=6, frame_size=(120, 160), square_size=40,
                                        start=(10, 10), velocity=(0, 0),
                                        occlusion_frames=(2,), occlusion_fraction=0.5)
        assert fx.masks[1].sum() == 40 * 40                  # không che
        assert fx.masks[2].sum() == 40 * 20                  # che một nửa theo chiều ngang
        assert fx.occluded[2] and not fx.occluded[1]

    def test_che_hoan_toan_thi_mask_gt_rong(self):
        from src.synthetic_video import generate_tracking_sequence

        fx = generate_tracking_sequence(num_frames=4, frame_size=(120, 160), square_size=20,
                                        start=(10, 10), velocity=(0, 0),
                                        occlusion_frames=(1,), occlusion_fraction=1.0)
        assert not fx.masks[1].any(), "che kín ⇒ không còn pixel nào nhìn thấy được"
        assert fx.occluded[1]

    def test_bbox_gt_van_giu_vi_tri_khi_bi_che(self):
        """Ô bao lý thuyết không đổi khi bị che (dùng để nói rõ GT bbox ≠ GT mask)."""
        from src.synthetic_video import generate_tracking_sequence

        fx = generate_tracking_sequence(num_frames=3, frame_size=(120, 160), square_size=20,
                                        start=(10, 10), velocity=(2, 0),
                                        occlusion_frames=(1,), occlusion_fraction=1.0)
        assert fx.bboxes[1] == (12, 10, 32, 30)
