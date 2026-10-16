"""Test PromptSelector — máy trạng thái chọn ô bằng kéo chuột (ticket 05).

Seam theo spec: PromptSelector test headless qua sự kiện chuột tổng hợp
(không cần cửa sổ thật); phần gắn vào window + kéo thật kiểm thủ công.
"""
import cv2
import numpy as np

from src.prompt_selector import PromptSelector


class TestStateMachine:
    """Máy trạng thái kéo-thả → bbox, không cần GUI."""

    def _drag(self, sel, start, end):
        """Mô phỏng kéo chuột: down → move → up."""
        sel.on_mouse(cv2.EVENT_LBUTTONDOWN, start[0], start[1], 0, None)
        sel.on_mouse(cv2.EVENT_MOUSEMOVE, end[0], end[1], 0, None)
        sel.on_mouse(cv2.EVENT_LBUTTONUP, end[0], end[1], 0, None)

    def test_ban_dau_trang_thai_idle_chua_co_bbox(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        assert sel.state == "idle"
        assert not sel.has_bbox()
        assert sel.bbox is None

    def test_keo_chuot_tu_trai_tren_xuong_duoi_phai_bbox_chuan_hoa(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        self._drag(sel, (50, 50), (150, 200))
        assert sel.state == "done"
        assert sel.has_bbox()
        assert sel.bbox == (50, 50, 150, 200)

    def test_keo_theo_huong_nguoc_bbox_van_chuan_hoa_x1y1_nho_hon(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        self._drag(sel, (150, 200), (50, 50))
        assert sel.bbox == (50, 50, 150, 200)

    def test_click_nho_hon_nguong_khong_tao_bbox_ve_lai_idle(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        self._drag(sel, (100, 100), (103, 103))  # 3x3 — quá nhỏ
        assert sel.state == "idle"
        assert not sel.has_bbox()
        assert sel.bbox is None

    def test_take_bbox_tra_bbox_va_reset_ve_idle_san_sang_chon_lai(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        self._drag(sel, (50, 50), (150, 200))
        bbox = sel.take_bbox()
        assert bbox == (50, 50, 150, 200)
        assert sel.state == "idle"
        assert not sel.has_bbox()
        # chọn lại được ngay sau khi take
        self._drag(sel, (10, 10), (60, 60))
        assert sel.has_bbox()
        assert sel.bbox == (10, 10, 60, 60)

    def test_reset_xoa_bbox_va_trang_thai(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        self._drag(sel, (50, 50), (150, 200))
        sel.reset()
        assert sel.state == "idle"
        assert sel.bbox is None
        assert not sel.has_bbox()

    def test_toa_do_keo_ngoai_khung_bi_clip_vao_frame(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        # kéo ra ngoài mép phải/dưới
        self._drag(sel, (300, 200), (400, 300))
        # clip về (319, 239) — mép frame
        assert sel.bbox == (300, 200, 319, 239)

    def test_dang_keo_thay_doi_end_va_chua_done(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        sel.on_mouse(cv2.EVENT_LBUTTONDOWN, 50, 50, 0, None)
        sel.on_mouse(cv2.EVENT_MOUSEMOVE, 80, 90, 0, None)
        assert sel.state == "dragging"
        assert not sel.has_bbox()
        sel.on_mouse(cv2.EVENT_MOUSEMOVE, 120, 130, 0, None)
        assert sel.state == "dragging"
        sel.on_mouse(cv2.EVENT_LBUTTONUP, 120, 130, 0, None)
        assert sel.bbox == (50, 50, 120, 130)

    def test_bind_frame_reset_va_cap_nhat_kich_thuoc(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        self._drag(sel, (50, 50), (150, 200))
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        sel.bind(frame)
        assert sel.state == "idle"
        assert not sel.has_bbox()
        # giờ kéo với toạ độ thuộc frame lớn hơn
        self._drag(sel, (100, 100), (300, 400))
        assert sel.bbox == (100, 100, 300, 400)


class TestDraw:
    """draw() vẽ khung trực quan — smoke: không crash, đúng kích thước."""

    def test_draw_idle_khong_crash_va_dung_kich_thuoc(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        img = sel.draw(frame)
        assert img.shape == (240, 320, 3)
        assert img.dtype == np.uint8

    def test_draw_dang_keo_co_khung_khac_frame_goc(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        sel.on_mouse(cv2.EVENT_LBUTTONDOWN, 50, 50, 0, None)
        sel.on_mouse(cv2.EVENT_MOUSEMOVE, 150, 200, 0, None)
        img = sel.draw(frame)
        # khung vẽ thêm → có pixel khác 0
        assert img.shape == (240, 320, 3)
        assert img.sum() > 0

    def test_draw_done_co_khung_xac_nhan(self):
        sel = PromptSelector(frame_shape=(240, 320, 3))
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        sel.on_mouse(cv2.EVENT_LBUTTONDOWN, 50, 50, 0, None)
        sel.on_mouse(cv2.EVENT_LBUTTONUP, 150, 200, 0, None)
        img = sel.draw(frame)
        assert img.shape == (240, 320, 3)
        assert img.sum() > 0