"""Test Visualizer — HUD đầy đủ: mask + ô bao + quỹ đạo + FPS/độ trễ + ghi video (ticket 06).

Spec testing decisions: Visualizer smoke test (không crash, ảnh đúng kích thước);
làm kỹ hơn: assert pixel từng lớp overlay + tràn deque không xảy ra + mp4 đọc lại được.
"""
import cv2
import numpy as np
import pytest

from src.tracker_engine import TrackingResult
from src.visualizer import Visualizer, find_vietnamese_font


def _frame(h=240, w=320, color=(40, 40, 40)):
    return np.full((h, w, 3), color, dtype=np.uint8)


def _result(frame_idx=0, bbox=(200, 200, 220, 220), mask_box=(100, 150, 140, 190),
            score=0.9, elapsed_ms=500.0):
    """TrackingResult với mask nằm ở vùng riêng, lệch khỏi bbox để tách lớp overlay."""
    mask = np.zeros((240, 320), dtype=bool)
    if mask_box is not None:
        x1, y1, x2, y2 = mask_box
        mask[y1:y2, x1:x2] = True
    return TrackingResult(
        frame_idx=frame_idx, mask=mask, bbox=bbox, score=score, elapsed_ms=elapsed_ms,
    )


BG = np.array([40, 40, 40])


class TestHud:
    def test_hud_dong_thu_ba_hien_diem_tin_cay(self):
        """HUD phải hiện điểm tin cậy — để người dùng so sánh các lần chọn (18-10)."""
        lines = Visualizer().hud_lines(score=8.26, fps=0.2, ms=5047.0)
        assert len(lines) == 3
        assert "Điểm tin cậy" in lines[2]
        assert "8.3" in lines[2]

    def test_hud_giu_nguyen_fps_va_do_tre(self):
        lines = Visualizer().hud_lines(score=8.26, fps=0.2, ms=5047.0)
        assert "FPS" in lines[0] and "0.2" in lines[0]
        assert "Độ trễ" in lines[1] and "5047" in lines[1]

    def test_update_khong_crash_va_dung_kich_thuoc(self):
        img = Visualizer().update(_frame(), _result())
        assert img.shape == (240, 320, 3)
        assert img.dtype == np.uint8

    def test_mask_da_to_mau_ban_trong_suot(self):
        img = Visualizer().update(_frame(), _result(mask_box=(100, 150, 140, 190)))
        # pixel giữa mask bị đổi màu so với nền (alpha blend, không phải tô đặc)
        mid = img[170, 120].astype(int)
        assert not np.array_equal(mid, BG)
        # và không phải tô 100% màu overlay (0,140,255) — vẫn còn nền pha vào
        assert not np.array_equal(mid, np.array([0, 140, 255]))

    def test_bbox_co_o_bao_ke_do(self):
        img = Visualizer().update(_frame(), _result(bbox=(200, 200, 220, 220)))
        # cạnh trên của ô bao đổi màu so với nền
        assert not np.array_equal(img[200, 205:215].mean(axis=0).astype(int), BG)

    def test_hud_co_text_fps_va_do_tre(self):
        frame = _frame()
        img = Visualizer().update(frame, _result(bbox=(280, 280, 300, 300)))
        # vùng HUD góc trên trái có pixel khác frame gốc
        assert not np.array_equal(img[5:60, 5:250], frame[5:60, 5:250])

    def test_hud_fps_hieu_dung_tu_latency(self):
        viz = Visualizer()
        for ms in (500.0, 1500.0):
            viz.update(_frame(), _result(elapsed_ms=ms))
        # FPS hiệu dụng = 1000/mean(1000) = 1.0
        assert viz.effective_fps == pytest.approx(1.0)


class TestQuyDao:
    def _moving_result(self, i):
        """bbox di chuyển theo đường chéo: tâm (110+5i, 110+5i)."""
        return _result(
            frame_idx=i, bbox=(100 + 5 * i, 100 + 5 * i, 120 + 5 * i, 120 + 5 * i),
            mask_box=(300, 10, 310, 20),
        )

    def test_quy_dao_theo_tam_gioi_han_deque(self):
        viz = Visualizer(max_trajectory=50)
        for i in range(60):  # nhiều hơn maxlen
            viz.update(_frame(), self._moving_result(i))
        pts = viz.trajectory_points
        assert len(pts) == 50                          # không tràn bộ nhớ
        assert pts[-1] == (110 + 5 * 59, 110 + 5 * 59)  # tâm mới nhất
        # điểm cũ nhất còn giữ là của frame 10 (60 điểm - 50 maxlen)
        assert pts[0] == (110 + 5 * 10, 110 + 5 * 10)

    def test_polyline_duoc_ve_giua_hai_tam(self):
        viz = Visualizer(max_trajectory=10)
        viz.update(_frame(), self._moving_result(0))     # tâm (110,110)
        img = viz.update(_frame(), self._moving_result(10))  # tâm (160,160)
        # điểm giữa đoạn nối 2 tâm phải được vẽ (nền là 40,40,40)
        mid = img[135, 135].astype(int)
        assert not np.array_equal(mid, BG)

    def test_bbox_rong_khong_them_diem_quy_dao(self):
        viz = Visualizer()
        viz.update(_frame(), _result(bbox=(200, 200, 220, 220)))
        viz.update(_frame(), _result(bbox=(0, 0, 0, 0)))  # mask rỗng → bbox (0,0,0,0)
        assert len(viz.trajectory_points) == 1  # không thêm điểm rác (0,0)

    def test_reset_dua_quy_dao_ve_rong(self):
        """Chọn lại đối tượng (phím r) → quỹ đạo đối tượng cũ phải bị xoá."""
        viz = Visualizer()
        viz.update(_frame(), self._moving_result(0))
        viz.update(_frame(), self._moving_result(1))
        viz.reset()
        assert len(viz.trajectory_points) == 0
        assert viz.effective_fps == 0.0


class TestNhanTiengViet:
    def test_tim_font_tieng_viet(self):
        """Môi trường test phải tìm được font TTF hỗ trợ tiếng Việt (hoặc skip)."""
        font = find_vietnamese_font()
        if font is None:
            pytest.skip("máy không có font TTF phổ biến — fallback cv2.putText ASCII")
        assert font.endswith((".ttf", ".otf"))

    def test_nhan_tieng_viet_ve_duoc_ky_tu_co_dau(self):
        """"Độ trễ", "quỹ đạo" — PIL render được ký tự có dấu (không lỗi/toe)."""
        font = find_vietnamese_font()
        if font is None:
            pytest.skip("máy không có font TTF phổ biến")
        frame = _frame()
        img = Visualizer().update(frame, _result(bbox=(280, 280, 300, 300)))
        # HUD vẽ được — có pixel khác frame gốc trong vùng HUD
        assert not np.array_equal(img[5:60, 5:300], frame[5:60, 5:300])


class TestGhiVideo:
    def test_ghi_mp4_doc_lai_du_frame_dung_kich_thuoc(self, tmp_path):
        out = tmp_path / "hud.mp4"
        viz = Visualizer()
        assert viz.open_recorder(str(out)) is True
        for i in range(3):
            img = viz.update(_frame(), self._moving_result_cls(i))
            assert img.shape == (240, 320, 3)
        viz.close_recorder()

        cap = cv2.VideoCapture(str(out))
        assert cap.isOpened()
        n = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            n += 1
            assert frame.shape == (240, 320, 3)
        cap.release()
        assert n == 3  # đúng luồng demo: mỗi frame overlay được ghi 1 lần

    @staticmethod
    def _moving_result_cls(i):
        mask = np.zeros((240, 320), dtype=bool)
        mask[10:20, 300:310] = True
        return TrackingResult(
            frame_idx=i, mask=mask, bbox=(100 + 5 * i, 100 + 5 * i, 120 + 5 * i, 120 + 5 * i),
            score=0.9, elapsed_ms=500.0,
        )

    def test_ghi_mo_khong_duong_dan_khong_hop_le_tra_false(self, tmp_path):
        viz = Visualizer()
        assert viz.open_recorder(str(tmp_path / "khong-the" / "x.mp4"),
                                 frame_size=(320, 240)) is False

    def test_close_recorder_khi_chua_mo_khong_crash(self):
        Visualizer().close_recorder()

    def test_chua_open_recorder_thi_update_khong_ghi(self, tmp_path):
        """Không bật ghi (config off) → vẫn update HUD bình thường, không tạo file."""
        viz = Visualizer()
        img = viz.update(_frame(), _result())
        assert img.shape == (240, 320, 3)
        assert not (tmp_path / "hud.mp4").exists()