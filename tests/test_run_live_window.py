"""Test phát hiện "người dùng đóng cửa sổ" — bug WSLg map cửa sổ trễ (27-10-2026).

Vì sao có file này: `./run video` (chế độ chọn đối tượng) tự thoát ngay sau frame đầu với log
"cửa sổ đã đóng — thoát", vì `cv2.getWindowProperty(WND_PROP_VISIBLE)` trả 0 trong khoảng
vài trăm ms đầu khi WSLg chưa map xong cửa sổ. Test khoá lại: **chưa từng thấy cửa sổ → chưa
coi là đóng**; đã thấy hiện rồi mới biến mất → mới là đóng.

Chỉ monkeypatch `cv2.getWindowProperty` (không mở cửa sổ thật — GUI thật làm SIGABRT khi headless).
"""
import cv2

import tools.run_live as run_live


def _fake_visibility(monkeypatch, values):
    """Giả lập chuỗi giá trị trả về của getWindowProperty theo từng lần gọi."""
    seq = list(values)

    def fake(_window, _prop):
        return seq.pop(0) if seq else 0

    monkeypatch.setattr(cv2, "getWindowProperty", fake)


class TestWindowClosedGrace:
    def test_chua_tung_hien_thi_khong_coi_la_dong(self, monkeypatch):
        """WSLg map trễ → 0 ngay sau imshow, nhưng KHÔNG được tự thoát."""
        _fake_visibility(monkeypatch, [0, 0, 0])
        seen = {"ok": False}
        for _ in range(3):
            assert run_live._window_closed("win", seen) is False
        assert seen["ok"] is False

    def test_hien_roi_bien_mat_phai_du_3_lan_moi_la_dong(self, monkeypatch):
        """WSLg có thể báo "không thấy" 1-2 frame khi vẽ lại → chưa được thoát."""
        _fake_visibility(monkeypatch, [1, 0, 0, 0])
        seen = {"ok": False}
        assert run_live._window_closed("win", seen) is False   # hiện
        assert run_live._window_closed("win", seen) is False   # miss 1
        assert run_live._window_closed("win", seen) is False   # miss 2
        assert run_live._window_closed("win", seen) is True    # miss 3 → đóng

    def test_hien_lai_thi_reset_dem_miss(self, monkeypatch):
        _fake_visibility(monkeypatch, [1, 0, 0, 1, 0, 0, 0, 0])
        seen = {"ok": False}
        flags = [run_live._window_closed("win", seen) for _ in range(8)]
        # 1 hiện | 0,0 miss→2 | 1 hiện lại (reset) | 0,0,0 miss→3 = đóng | còn lại vẫn đóng
        assert flags == [False, False, False, False, False, False, True, True]

    def test_cv2_loi_thi_coi_la_dong(self, monkeypatch):
        def boom(_window, _prop):
            raise cv2.error("window destroyed")

        monkeypatch.setattr(cv2, "getWindowProperty", boom)
        assert run_live._window_closed("win", {"ok": True}) is True

    def test_khong_truyen_state_giu_hanh_vi_cu(self, monkeypatch):
        """Chỗ khác gọi không truyền state → hành vi cũ: 0 nghĩa là đã đóng."""
        _fake_visibility(monkeypatch, [0])
        assert run_live._window_closed("win") is True
