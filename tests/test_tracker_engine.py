"""Test seam TrackerEngine — bọc SAMURAI thành streaming per-frame (ticket 02).

Nguyên tắc: chỉ test hành vi công khai của engine. Đáp án quỹ đạo lấy từ fixture
(synthetic square — nguồn độc lập), ngưỡng IoU quy định theo tiêu chí của ticket.
Chạy chậm (build model + propagation thật) — đánh dấu `slow`.
"""
import numpy as np
import pytest

from src.synthetic_video import generate_tracking_sequence


def iou(box_a, box_b):
    """IoU 2 bbox (x1, y1, x2, y2) — cài đặt độc lập, không dựa vào code sản phẩm."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@pytest.mark.slow
class TestTrackerEngineStreaming:
    """Chuỗi test theo tiêu chí ticket 02 — chạy trên fixture giả lập."""

    def test_start_frame_0_mask_khong_rong_va_iou_dat_nguong(self, samurai_engine):
        """Tiêu chí 1 (phần start): frame 0 → mask không rỗng, bbox IoU ≥ 0.5."""
        fx = generate_tracking_sequence(num_frames=1, frame_size=(240, 320), square_size=40, start=(60, 60))
        res = samurai_engine.start(fx.frames[0], fx.bboxes[0])

        assert res.mask.shape == (240, 320)
        assert res.mask.dtype == bool
        assert res.mask.sum() > 0, "mask frame 0 không được rỗng ngay khi prompt chính xác"
        assert iou(res.bbox, fx.bboxes[0]) >= 0.5
        assert res.elapsed_ms > 0
        assert np.isfinite(res.score)

    def test_process_theo_frames_iou_dat_o_cac_frame_mau(self, samurai_engine):
        """Tiêu chí 1 (phần process): feed 10 frame giả lập → bbox theo quỹ đạo, IoU ≥ 0.5."""
        fx = generate_tracking_sequence(num_frames=10, frame_size=(240, 320), square_size=40, start=(60, 60))
        engine = samurai_engine

        res0 = engine.start(fx.frames[0], fx.bboxes[0])
        assert iou(res0.bbox, fx.bboxes[0]) >= 0.5

        results = [engine.process(fx.frames[i]) for i in range(1, 10)]
        # Khoảng trống giữa bbox trả về và đáp án phải nhỏ (nhớ theo index: frames[i-1] trong results)
        for i in (2, 5, 9):
            res = results[i - 1]
            assert res.frame_idx == i
            assert res.mask.shape == (240, 320)
            assert res.elapsed_ms > 0
            assert np.isfinite(res.score)
            assert iou(res.bbox, fx.bboxes[i]) >= 0.5, f"IoU tại frame {i} thấp hơn ngưỡng"

    def test_frame_bi_che_khong_crash_va_ket_qua_hop_le(self, samurai_engine):
        """Tiêu chí 2: đố bị che khuất 2 frame → engine không crash, trả kết quả hợp lệ."""
        fx = generate_tracking_sequence(
            num_frames=8, frame_size=(240, 320), square_size=40, start=(60, 60), occlusion_frames=(3, 4)
        )
        engine = samurai_engine
        engine.start(fx.frames[0], fx.bboxes[0])

        for i in range(1, 8):
            res = engine.process(fx.frames[i])  # frame 3, 4 bị che — không được ném exception
            assert res.frame_idx == i
            assert res.mask.shape == (240, 320)
            assert res.mask.dtype == bool
            assert np.isfinite(res.score)
            if not fx.occluded[i]:
                # Trước/sau che khuất, mask có thể rỗng (hệ thống dừng track) nhưng phải là hợp lệ
                # — ở đây ô xuất hiện lại cùng vị trí quỹ đạo nên kỳ vọng bám lại tốt
                if res.mask.sum() > 0:
                    assert iou(res.bbox, fx.bboxes[i]) >= 0.3, (
                        f"frame {i} (ngoài che khuất) bám lại yếu: IoU < 0.3"
                    )