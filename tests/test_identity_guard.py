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


class TestTaiBamSauKhiVatRoiKhung:
    """24-11 (người dùng báo, phiên `demoip_1124-193026`): *"ra khung khoảng 10 s, đưa vào khung lại

    thì bị nghi, từ đó không nhận diện lại nữa"*. Đọc CSV phiên đó: 15 frame `mask_area = 0` liền
    (f248–262), rồi f263 model trả một **mẩu rác 559 px** (0,346× tham chiếu), rồi f264 trả mask thật
    24 100 px ở chỗ khác ⇒ cổng chấm "nhảy" giữa MẨU RÁC và VẬT ⇒ báo nghi ⇒ latch giữ tới hết phiên
    (**132/404 frame = 32,7 %** chỉ còn ô nét đứt "chưa xác minh").
    Luật: vật rời khung rồi vào lại là **phiên bám mới** — không có cú nhảy nào để chấm.
    """

    A = (100, 100, 200, 200)       # vật lúc đầu
    B = (500, 300, 600, 480)       # chỗ khác hẳn (> 200 px) — nếu chấm sẽ bị coi là "nhảy"
    M = (300, 200, 380, 260)       # mẩu rác của lần dò lại (như f263)

    def test_vang_dai_roi_vao_lai_khong_bao(self):
        from src.identity_guard import IdentityWatch

        w = IdentityWatch(lost_reset_streak=3, reacq_grace_steps=2)
        w.update(self.A, self.A, (480, 640))
        for _ in range(5):                                   # 5 bước vắng (như f248–262)
            w.update(self.A, (0, 0, 0, 0), (480, 640), co_mask=False)
        assert w.nghi is False
        assert w.update((0, 0, 0, 0), self.M, (480, 640)) is False     # mẩu rác: miễn chấm
        assert w.vua_bao is False
        assert w.update(self.M, self.B, (480, 640)) is False           # bước 2 của phiên mới: miễn
        assert w.vua_bao is False
        assert w.nghi is False      # KHÔNG được bật latch — đây là điều người dùng thấy

    def test_het_grace_thi_cham_lai_nhu_cu(self):
        from src.identity_guard import IdentityWatch

        w = IdentityWatch(lost_reset_streak=3, reacq_grace_steps=2)
        for _ in range(4):
            w.update(self.A, (0, 0, 0, 0), (480, 640), co_mask=False)
        w.update((0, 0, 0, 0), self.B, (480, 640))           # bước 1 (miễn)
        w.update(self.B, (502, 302, 602, 478), (480, 640))   # bước 2 (miễn)
        # Sau grace: cú nhảy THẬT vẫn phải bị bắt (đừng "sửa" bằng cách tắt cổng)
        assert w.update((502, 302, 602, 478), self.A, (480, 640)) is True
        assert w.vua_bao is True

    def test_nhap_nhay_1_2_frame_van_cham(self):
        """Ngưỡng 3 frame vắng là ranh giới với NHẤP NHÁY: ca báo đúng `125109#137` chỉ vắng **1** frame."""
        from src.identity_guard import IdentityWatch

        for so_vang in (1, 2):
            w = IdentityWatch(lost_reset_streak=3, reacq_grace_steps=2)
            w.update(self.A, self.A, (480, 640))
            for _ in range(so_vang):
                w.update(self.A, (0, 0, 0, 0), (480, 640), co_mask=False)
            w.update((0, 0, 0, 0), self.M, (480, 640))       # mask trở lại
            assert w.update(self.M, self.B, (480, 640)) is True, \
                f"vắng {so_vang} frame là nhấp nháy ⇒ cú nhảy sau đó vẫn phải bị chấm"

    def test_tai_bam_xoa_latch_nghi(self):
        """Đường lui duy nhất khi re-ID TẮT: vật rời khung rồi vào lại ⇒ hết nghi (không kẹt vĩnh viễn)."""
        from src.identity_guard import IdentityWatch

        w = IdentityWatch(lost_reset_streak=3, reacq_grace_steps=2)
        w.update(self.A, self.B, (480, 640))
        assert w.nghi is True
        for _ in range(6):
            w.update(self.B, (0, 0, 0, 0), (480, 640), co_mask=False)
        w.update((0, 0, 0, 0), self.A, (480, 640))
        assert w.nghi is False and w.trang_thai == "ok"

    def test_tat_bang_0_la_hanh_vi_truoc_24_11(self):
        """`lost_reset_streak=0` phải tái lập được số cũ (báo oan ngay sau khi vắng)."""
        from src.identity_guard import IdentityWatch

        w = IdentityWatch(lost_reset_streak=0)
        for _ in range(5):
            w.update(self.A, (0, 0, 0, 0), (480, 640), co_mask=False)
        w.update((0, 0, 0, 0), self.M, (480, 640))
        assert w.update(self.M, self.B, (480, 640)) is True


class TestBannerDiTheoTrangThaiLatch:
    """24-11: banner "đổi đối tượng" phải tắt khi latch được xoá TỪ BÊN TRONG `watch.update`

    (tái bám sau khi vật rời khung). Bản cũ gán `switch = watch.nghi or switch` (sticky) ⇒ sau khi
    latch tự xoá, banner treo trên màn hình trong khi mask đã vẽ lại bình thường.
    """

    def test_source_khong_dinh_sticky(self):
        import inspect

        from src import live_pipeline as lp
        from src import smooth_display as sd

        for mod in (sd, lp):
            src = inspect.getsource(mod)
            assert "switch = watch.nghi or switch" not in src, \
                f"{mod.__name__}: `switch` còn dính sticky ⇒ banner không tắt khi latch tự xoá"


class TestBienCuaNguongVang:
    """Biên của `lost_reset_streak` — **TỔNG HỢP**, lấy ô của ca thật làm nguyên liệu.

    Vì sao tổng hợp: phiên `demoip_1121-121732` (cú báo đúng f178) **không tái lập được** bằng replay
    hiện tại — CSV không có cột `nghi_doi_tuong` và f178 là `reacquired=1` (re-ID bật) nên đường CLI đi
    nhánh `watch.reset()`; `data/eval_gate_rules_*` cho phiên đó `fire = 0` với **mọi** luật. Vì thế
    đây KHÔNG phải "chứng minh ngưỡng 3 giữ ca 121732" — nó chỉ khoá **biên**: `>= 3` (không phải
    `> 3`) và `1–2` bước vắng vẫn phải bị chấm. Test đỏ nếu ai đổi `>=` thành `>` hoặc hạ ngưỡng.
    """

    MOC = (566, 130, 656, 383)     # ô của ô-chai trước khi vắng (tâm ~611,256)
    NHay = (376, 42, 476, 121)     # f178: ô nhảy sang vùng khác hẳn

    def test_vua_bao_doc_duoc_truoc_lan_update_dau(self):
        """Property công khai ⇒ phải đọc được trên instance MỚI (không `AttributeError`).

        Review vòng 4: xoá `self._vua_bao = False` trong `__init__` thì không test nào đỏ.
        """
        from src.identity_guard import IdentityWatch

        assert IdentityWatch().vua_bao is False

    def test_vang_dung_2_frame_van_bi_cham(self):
        from src.identity_guard import IdentityWatch

        w = IdentityWatch(lost_reset_streak=3)
        w.update(self.MOC, self.MOC, (480, 640))
        for _ in range(2):                                    # f176–177: 2 frame rỗng
            w.update(self.MOC, (0, 0, 0, 0), (480, 640), co_mask=False)
        w.update((0, 0, 0, 0), self.NHay, (480, 640))          # f178
        assert w.update(self.NHay, self.MOC, (480, 640)) is True, (
            "vắng 2 frame < ngưỡng 3 ⇒ cú nhảy vẫn phải bị chấm "
            "(VÍ DỤ BIÊN — test tổng hợp; ca thật 121732 KHÔNG tái lập được bằng replay)")

    def test_bien_dung_3_frame_la_tai_bam(self):
        """`>= 3` (không phải `> 3`): đúng 3 frame vắng đã là phiên bám mới."""
        from src.identity_guard import IdentityWatch

        w = IdentityWatch(lost_reset_streak=3, reacq_grace_steps=2)
        w.update(self.MOC, self.MOC, (480, 640))
        for _ in range(3):
            w.update(self.MOC, (0, 0, 0, 0), (480, 640), co_mask=False)
        w.update((0, 0, 0, 0), self.NHay, (480, 640))
        assert w.update(self.NHay, self.MOC, (480, 640)) is False
        assert w.vua_bao is False


class TestBuocVosKhongPhaiFrameHienThi:
    """24-11 (review độc lập P1): đường web gọi `update()` mỗi frame PHÁT, mà `vos_every>1` ⇒ cùng một

    kết quả VOS lặp ~3,5 lần ⇒ `lost_reset_streak`/`reacq_grace_steps`/`settle_steps` co lại 3,5 lần
    (một VOS rỗng là reset; grace hết hạn trước bước VOS kế nên cú "mẩu rác → vật" vẫn bị chấm).
    """

    A = (100, 100, 200, 200)
    M = (300, 200, 380, 260)
    B = (500, 300, 600, 480)

    def test_lap_lai_cung_ket_qua_VOS_khong_dem_buoc(self):
        from src.identity_guard import IdentityWatch

        w = IdentityWatch(lost_reset_streak=3, reacq_grace_steps=2)
        w.update(self.A, self.A, (480, 640))
        # MỘT kết quả VOS rỗng, phát 3 lần (vos_every=3): 1 bước + 2 frame hiển thị lặp lại
        w.update(self.A, (0, 0, 0, 0), (480, 640), co_mask=False, buoc_moi=True)
        for _lap in range(2):
            w.update(self.A, (0, 0, 0, 0), (480, 640), co_mask=False, buoc_moi=False)
        # `_lost` phải là 1, KHÔNG phải 3 ⇒ chưa đủ ngưỡng ⇒ không reset
        assert w.update((0, 0, 0, 0), self.M, (480, 640), buoc_moi=False) is False
        # bước VOS mới đầu tiên sau khi vắng: vẫn chưa đủ 3 bước ⇒ KHÔNG phải phiên bám mới
        w.update((0, 0, 0, 0), self.M, (480, 640), buoc_moi=True)
        assert w.update(self.M, self.B, (480, 640), buoc_moi=True) is True, \
            "vắng 1 bước VOS (dù 3 frame hiển thị) là NHẤP NHÁY ⇒ cú nhảy vẫn phải bị chấm"

    def test_grace_khong_het_han_truoc_buoc_vos_ke(self):
        from src.identity_guard import IdentityWatch

        w = IdentityWatch(lost_reset_streak=3, reacq_grace_steps=2)
        for _ in range(4):
            w.update(self.A, (0, 0, 0, 0), (480, 640), co_mask=False, buoc_moi=True)
        # bước VOS 1 của phiên mới = mẩu rác, phát 4 frame hiển thị
        w.update((0, 0, 0, 0), self.M, (480, 640), buoc_moi=True)
        for _lap in range(3):
            w.update((0, 0, 0, 0), self.M, (480, 640), buoc_moi=False)
        # bước VOS 2 = mask thật 24k px ⇒ phải vẫn được MIỄN (grace tính theo BƯỚC VOS)
        assert w.update(self.M, self.B, (480, 640), buoc_moi=True) is False
        assert w.vua_bao is False

    def test_buoc_moi_false_khong_doi_trang_thai(self):
        from src.identity_guard import IdentityWatch

        w = IdentityWatch()
        w.update(self.A, self.B, (480, 640))
        assert w.nghi is True
        truoc = (w._lost, w._grace, w._settle, w.trang_thai)
        for _ in range(5):
            assert w.update(self.B, self.A, (480, 640), buoc_moi=False) is True
        assert (w._lost, w._grace, w._settle, w.trang_thai) == truoc, \
            "`buoc_moi=False` là NO-OP: không được đổi bộ đếm nào (review vòng 2, P3)"
        assert w.vua_bao is False, "`vua_bao` là cờ của LẦN GỌI NÀY (không phải của bước trước)"
