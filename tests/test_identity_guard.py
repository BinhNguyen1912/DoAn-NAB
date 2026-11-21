"""Test phát hiện "đổi danh tính" — chọn mặt A, A trốn thì nó nhảy sang mặt B.

Nguyên nhân: SAM 2 bám *vật thể* bằng bộ nhớ; khi A bị che, bộ nhớ mơ hồ và mô hình có thể
bắt sang vật thể giống nhất (B). Đây là giới hạn "re-identification" (ngoài phạm vi spec),
nhưng hệ thống phải **cảnh báo** thay vì âm thầm bám sai.
"""

from src.identity_guard import is_suspect_switch


class TestIsSuspectSwitch:
    def test_dung_yen_khong_canh_bao(self):
        assert is_suspect_switch((100, 100, 160, 160), (102, 101, 162, 161), (480, 640)) is False

    def test_nhay_sang_goc_khung_khac_la_nghi_ngo(self):
        # người A ở trái, bỗng "bám" sang người B ở phải
        assert is_suspect_switch((40, 100, 120, 200), (500, 100, 600, 200), (480, 640)) is True

    def test_nhay_vua_phai_trong_nguong_khong_canh_bao(self):
        # di chuyển 60 px trên khung rộng 640 (~9% chiều ngang) — người đi bộ bình thường
        assert is_suspect_switch((100, 100, 160, 160), (160, 110, 220, 170), (480, 640)) is False

    def test_bbox_rong_khong_xet(self):
        assert is_suspect_switch((0, 0, 0, 0), (500, 100, 600, 200), (480, 640)) is False
        assert is_suspect_switch((100, 100, 160, 160), (0, 0, 0, 0), (480, 640)) is False

    def test_vat_the_bay_ngang_nhanh_bi_nghi_ngo_dung(self):
        """Chim/bóng bay nhanh thật cũng bị cảnh báo — chấp nhận: cảnh báo chỉ là 'nghi ngờ'."""
        assert is_suspect_switch((10, 10, 40, 40), (600, 10, 630, 40), (480, 640)) is True

    def test_nguong_tuy_chinh(self):
        prev, cur = (100, 100, 160, 160), (200, 100, 260, 160)   # nhảy 100 px
        assert is_suspect_switch(prev, cur, (480, 640), max_jump_ratio=0.5) is False
        assert is_suspect_switch(prev, cur, (480, 640), max_jump_ratio=0.05) is True


class TestIdentityWatch:
    """Cổng "nghi đổi đối tượng" **CÓ NHỚ** (21-11).

    Vì sao có latch: đo trên phiên thật `demoip_1121-121732`, cổng nhảy báo ĐÚNG ở f178 khi hệ bám
    sang cửa/tường be cùng tông, nhưng sau cú nhảy chuyển động lại mượt nên cổng KHÔNG báo lại —
    hệ vẫn vẽ mask sai thêm 65 frame. Cảnh báo 1 lần mà không nhớ là cảnh báo vô dụng.
    """

    def test_bao_mot_lan_roi_giu_trang_thai(self):
        from src.identity_guard import IdentityWatch

        w = IdentityWatch()
        a, b, c = (100, 100, 200, 200), (105, 102, 205, 202), (500, 400, 600, 480)
        assert w.update(a, b, (480, 640)) is False        # đi tiếp bình thường
        assert w.nghi is False
        assert w.update(b, c, (480, 640)) is True         # nhảy > 200 px ⇒ nghi
        assert w.nghi is True
        # Frame sau KHÔNG nhảy nữa nhưng vẫn phải báo nghi (đúng ca f179 của phiên thật)
        assert w.update(c, (502, 402, 602, 478), (480, 640)) is True
        assert w.nghi is True

    def test_reset_xoa_trang_thai(self):
        from src.identity_guard import IdentityWatch

        w = IdentityWatch()
        w.update((100, 100, 200, 200), (600, 400, 620, 480), (480, 640))
        assert w.nghi is True
        w.reset()
        assert w.nghi is False
        assert w.update((100, 100, 200, 200), (103, 103, 203, 203), (480, 640)) is False

    def test_o_rong_khong_bi_coi_la_doi_doi_tuong(self):
        from src.identity_guard import IdentityWatch

        w = IdentityWatch()
        # mất dấu → hiện lại ở chỗ khác: KHÔNG phải "đổi danh tính" (luật của is_suspect_switch)
        assert w.update((100, 100, 200, 200), (0, 0, 0, 0), (480, 640)) is False
        assert w.update((0, 0, 0, 0), (600, 400, 620, 480), (480, 640)) is False
        assert w.nghi is False
