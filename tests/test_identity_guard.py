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


class TestSearchWindowMotionGate:
    """Ticket 02: Ràng buộc không gian chuyển động dựa trên kích thước & LK velocity."""

    def test_search_window_radius_vat_nho_chat_hon_vat_to(self):
        from src.identity_guard import search_window_radius

        frame_shape = (480, 640)  # diagonal = 800
        small_box = (100, 100, 140, 140)  # size = 40
        big_box = (100, 100, 300, 300)    # size = 200

        r_small = search_window_radius(small_box, frame_shape)
        r_big = search_window_radius(big_box, frame_shape)

        assert r_small < r_big
        assert r_small < 120.0  # chặt hơn ngưỡng 200 px (25%) cũ rất nhiều
        assert r_big <= 200.0   # không vượt trần 25% đường chéo

    def test_search_window_mo_rong_theo_lk_velocity(self):
        from src.identity_guard import search_window_radius

        box = (100, 100, 150, 150)
        frame_shape = (480, 640)
        r_tinh = search_window_radius(box, frame_shape, lk_velocity=None)
        r_dong = search_window_radius(box, frame_shape, lk_velocity=(30.0, 40.0))  # mag = 50

        assert r_dong > r_tinh
        assert abs((r_dong - r_tinh) - 50.0) < 1e-3

    def test_ca_remote_nhay_114px_bi_chan_boi_search_window(self):
        """Ca remote trắng máy lạnh (f109->f110 trong track_identity.py): nhảy 114 px phải bị chặn."""
        from src.identity_guard import is_suspect_switch

        prev_remote = (200, 200, 250, 250)  # size = 50 px
        jumped_wall = (314, 200, 364, 250)  # nhảy 114 px sang tường/máy lạnh
        frame_shape = (480, 640)

        assert is_suspect_switch(prev_remote, jumped_wall, frame_shape) is True

    def test_di_chuyen_theo_huong_lk_khong_bi_nghi_oan(self):
        """Vật di chuyển 60 px nhưng có LK xác nhận cùng hướng thì KHÔNG bị báo oan."""
        from src.identity_guard import is_suspect_switch

        prev = (100, 100, 150, 150)
        cur = (160, 100, 210, 150)  # dịch 60 px theo trục x
        frame_shape = (480, 640)
        lk_vel = (58.0, 0.0)

        assert is_suspect_switch(prev, cur, frame_shape, lk_velocity=lk_vel) is False



class TestIdentityWatchTuHaMuc:
    """Trạng thái THỨ BA (24-11): `nghi` → `chua_xac_minh` sau `settle_steps` bước ổn định.

    Vì sao phải có (đo phiên `demoip_1124-125109`, 246 frame): cổng báo đúng ở f137 (ô nhảy sang
    tóc), rồi hệ **tự bám lại đúng vật** ở t≈40 s, nhưng latch chỉ xoá được bằng `r`/`c`/reacquire
    (re-ID đang TẮT) ⇒ **109/246 = 44,3 % phiên** chỉ có ô nét đứt. Replay **22 phiên ĐO ĐƯỢC /
    4 346 frame**: ẩn 32,67 % → 4,16 % (còn mask 29,71 % → 3,38 %); 28,51 % frame chuyển sang "chưa
    xác minh" (`data/replay_latch_settle_2026-11-24_metrics.json`). ĐỪNG trích "20,17 % → 2,57 %":
    số đó trộn 17 phiên thiếu cột `mask_area` (AGENTS §6).
    """

    A = (100, 100, 200, 200)
    B = (600, 400, 620, 480)      # nhảy vô lý

    def _nghi(self, settle=8):
        from src.identity_guard import IdentityWatch

        w = IdentityWatch(settle_steps=settle)
        w.update(self.A, (105, 102, 205, 202), (480, 640))
        assert w.update((105, 102, 205, 202), self.B, (480, 640)) is True
        return w

    def test_du_so_buoc_on_dinh_thi_ha_muc(self):
        from src.identity_guard import TRANG_THAI_CHUA_XAC_MINH, TRANG_THAI_NGHI

        w = self._nghi(settle=3)
        assert w.trang_thai == TRANG_THAI_NGHI
        b2 = (601, 401, 621, 479)
        assert w.update(self.B, b2, (480, 640)) is True          # bước 1
        assert w.update(b2, (602, 402, 620, 478), (480, 640)) is True   # bước 2
        assert w.update((602, 402, 620, 478), (603, 403, 619, 477), (480, 640)) is False
        assert w.trang_thai == TRANG_THAI_CHUA_XAC_MINH
        assert w.nghi is False and w.chua_xac_minh is True

    def test_mask_rong_khong_tinh_la_on_dinh(self):
        from src.identity_guard import TRANG_THAI_NGHI

        w = self._nghi(settle=2)
        # Không có mask = không có gì để tin ⇒ KHÔNG được hạ mức (nếu hạ, hệ vẽ một vùng không tồn tại)
        for _ in range(10):
            assert w.update(self.B, (0, 0, 0, 0), (480, 640), co_mask=False) is True
        assert w.trang_thai == TRANG_THAI_NGHI

    def test_nhay_lai_trong_luc_chua_xac_minh_quay_ve_nghi(self):
        from src.identity_guard import TRANG_THAI_NGHI

        w = self._nghi(settle=1)
        assert w.update(self.B, (601, 401, 621, 479), (480, 640)) is False   # hạ mức
        assert w.chua_xac_minh is True
        assert w.update((601, 401, 621, 479), (100, 60, 140, 200), (480, 640)) is True
        assert w.trang_thai == TRANG_THAI_NGHI

    def test_settle_0_la_hanh_vi_cu_an_toi_het_phien(self):
        from src.identity_guard import TRANG_THAI_NGHI

        w = self._nghi(settle=0)
        for i in range(20):
            w.update((600 + i, 400, 620, 480), (601 + i, 401, 621, 479), (480, 640))
        assert w.trang_thai == TRANG_THAI_NGHI     # tái lập được số của phiên trước 24-11
        assert w.chua_xac_minh is False

    def test_reset_ve_ok_tu_ca_hai_trang_thai(self):
        from src.identity_guard import TRANG_THAI_OK

        for buoc in (0, 1):
            w = self._nghi(settle=1)
            for i in range(buoc):
                w.update((600, 400, 620, 480), (601, 401, 621, 479), (480, 640))
            w.reset()
            assert w.trang_thai == TRANG_THAI_OK
            assert w.nghi is False and w.chua_xac_minh is False

    def test_settle_am_bi_kep_ve_0_khong_crash(self):
        """`settle_steps` âm ⇒ kẹp về 0 (= hành vi cũ), KHÔNG ném và KHÔNG hạ mức ngầm."""
        from src.identity_guard import IdentityWatch

        w = IdentityWatch(settle_steps=-5)
        assert w.settle_steps == 0
        w.update(self.A, (105, 102, 205, 202), (480, 640))
        assert w.update((105, 102, 205, 202), self.B, (480, 640)) is True
        for i in range(20):
            w.update((600 + i, 400, 620, 480), (601 + i, 401, 621, 479), (480, 640))
        assert w.chua_xac_minh is False
