"""Test LK tracker (`src/light_tracker.py`) — không cần model, dùng frame tổng hợp."""

import time

import cv2
import numpy as np
import pytest

from src.light_tracker import LkBoxTracker, shift_mask


def _frame_with_square(offset_x, offset_y, size=(120, 160), side=30):
    """Ảnh xám: nền nhiễu nhẹ + hình vuông sáng ở (offset) — để LK có texture mà bám."""
    rng = np.random.default_rng(7)
    frame = rng.integers(40, 60, size=size, dtype=np.uint8)
    x, y = 20 + offset_x, 20 + offset_y
    frame[y:y + side, x:x + side] = 220
    return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)


class TestLkBoxTracker:
    def test_bam_dung_do_dich_theo_truc_x(self):
        tracker = LkBoxTracker()
        first = _frame_with_square(0, 0)
        tracker.reset(cv2.cvtColor(first, cv2.COLOR_BGR2GRAY), (20, 20, 30, 30))

        bbox = None
        for step in range(1, 6):                 # dịch 3 px/frame
            gray = cv2.cvtColor(_frame_with_square(3 * step, 0), cv2.COLOR_BGR2GRAY)
            bbox, ok = tracker.update(gray)
            assert ok, f"mất dấu ở bước {step}"

        # literal tính tay: 5 bước × 3 px = 15 px
        assert abs(bbox[0] - (20 + 15)) <= 2
        assert abs(bbox[1] - 20) <= 2
        assert bbox[2] == 30 and bbox[3] == 30     # LK chỉ TỊNH TIẾN, không đổi kích thước

    def test_bam_dung_do_dich_theo_truc_y(self):
        tracker = LkBoxTracker()
        tracker.reset(cv2.cvtColor(_frame_with_square(0, 0), cv2.COLOR_BGR2GRAY), (20, 20, 30, 30))

        for step in range(1, 5):                 # dịch 2 px/frame
            gray = cv2.cvtColor(_frame_with_square(0, 2 * step), cv2.COLOR_BGR2GRAY)
            bbox, ok = tracker.update(gray)

        assert ok
        assert abs(bbox[1] - (20 + 8)) <= 2

    def test_chua_reset_thi_tra_false(self):
        tracker = LkBoxTracker()
        bbox, ok = tracker.update(np.zeros((48, 64), np.uint8))
        assert (bbox, ok) == (None, False)

    def test_khung_hinh_qua_nho_khong_gieo_duoc_diem(self):
        tracker = LkBoxTracker()
        tracker.reset(np.zeros((48, 64), np.uint8), (10, 10, 2, 2))
        assert tracker.update(np.zeros((48, 64), np.uint8)) == (None, False)

    def test_khong_theo_duoc_khi_frame_sau_doi_hoan_toan(self):
        """Nhiễu ngẫu nhiên hoàn toàn → không đủ điểm tin cậy, phải báo mất dấu (không bịa)."""
        tracker = LkBoxTracker()          # tham số mặc định: chốt chặn là độ tản, không phải số điểm
        rng = np.random.default_rng(3)
        tracker.reset(rng.integers(0, 255, (120, 160), dtype=np.uint8), (20, 20, 30, 30))

        noisy = rng.integers(0, 255, (120, 160), dtype=np.uint8)
        bbox, ok = tracker.update(noisy)
        assert ok is False
        assert bbox is None

    def test_chi_phi_duoi_nguong_33ms(self):
        """LK phải RẺ (mục tiêu < 10 ms/frame trên ảnh 160×120) để dùng 30 FPS."""
        tracker = LkBoxTracker()
        frames = [_frame_with_square(step, 0) for step in range(20)]
        tracker.reset(cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY), (20, 20, 30, 30))

        began = time.perf_counter()
        for frame in frames[1:]:
            tracker.update(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        per_frame_ms = (time.perf_counter() - began) * 1000 / (len(frames) - 1)

        assert per_frame_ms < 10.0, f"LK chậm bất thường: {per_frame_ms:.1f} ms/frame"


class TestShiftMask:
    def test_dich_dung_vi_tri(self):
        mask = np.zeros((40, 40), bool)
        mask[5:10, 5:10] = True

        moved = shift_mask(mask, 4, 3)
        assert moved[8:13, 9:14].all()
        assert moved.sum() == mask.sum()

    def test_dich_ra_ngoai_khung_bi_cat(self):
        mask = np.zeros((20, 20), bool)
        mask[0:5, 0:5] = True

        moved = shift_mask(mask, -10, -10)
        assert moved.sum() == 0                 # ra ngoài hết

    def test_dich_0_khong_doi_gi(self):
        mask = np.zeros((20, 20), bool)
        mask[2:6, 3:9] = True
        assert (shift_mask(mask, 0, 0) == mask).all()

    def test_khong_lam_thay_doi_mask_goc(self):
        mask = np.zeros((20, 20), bool)
        mask[2:6, 3:9] = True
        before = mask.copy()
        shift_mask(mask, 3, 3)
        assert (mask == before).all()


@pytest.mark.parametrize("bbox,expected", [
    ((10, 20, 30, 40), (10, 20, 40, 60)),
    ((0, 0, 5, 5), (0, 0, 5, 5)),
])
def test_chuyen_doi_bbox_giua_hai_quy_uoc(bbox, expected):
    from src.live_tracking import xywh_to_xyxy, xyxy_to_xywh

    assert xywh_to_xyxy(bbox) == expected
    assert xyxy_to_xywh(expected) == bbox
