"""Test geometry_guard — xác thực hình học và sinh prompt tương phản cho vật ít texture (Ticket 03)."""

from src.geometry_guard import GeometricProfile, generate_contrast_points


class TestGeometricProfile:
    def test_chua_du_mau_thi_cho_qua(self):
        prof = GeometricProfile(min_samples=3)
        assert prof.is_ready is False
        assert prof.is_compatible((100, 100, 200, 200)) is True

    def test_luu_lich_su_va_tinh_thong_ke(self):
        prof = GeometricProfile(min_samples=3)
        prof.update((100, 100, 150, 220))  # w=50, h=120, ar=50/120=0.4167, area=6000
        prof.update((102, 100, 152, 220))
        prof.update((104, 101, 154, 221))
        assert prof.is_ready is True
        st = prof.stats()
        assert st is not None
        assert abs(st.mean_w - 50.0) < 1.0
        assert abs(st.mean_h - 120.0) < 1.0
        assert abs(st.mean_area - 6000.0) < 100.0
        assert abs(st.mean_aspect_ratio - 0.4167) < 0.01

    def test_ung_vien_cung_hinh_dang_duoc_chap_nhan(self):
        prof = GeometricProfile(min_samples=3)
        for _ in range(5):
            prof.update((100, 100, 150, 220))  # remote 50x120
        # Ứng viên chiếc remote khi quay lại: 48x118 (sai số nhỏ)
        cand_remote = (200, 200, 248, 318)
        assert prof.is_compatible(cand_remote) is True

    def test_loai_bo_mang_tuong_hoac_cong_tac_khac_ti_le(self):
        prof = GeometricProfile(min_samples=3)
        for _ in range(5):
            prof.update((100, 100, 150, 220))  # remote 50x120 (ar = 0.417)

        # Mảng tường rộng (ar ngang = 150/40 = 3.75): sai lệch tỉ lệ lớn
        cand_tuong_ngang = (200, 200, 350, 240)
        assert prof.is_compatible(cand_tuong_ngang) is False

        # Mảng tường vuông lớn (200x200 = 40000 px vs 6000 px): sai lệch diện tích lớn
        cand_tuong_vuong = (200, 200, 400, 400)
        assert prof.is_compatible(cand_tuong_vuong) is False


class TestGenerateContrastPoints:
    def test_sinh_diem_tam_va_diem_ngoai_bien(self):
        bbox = (100, 100, 160, 220)  # w=60, h=120
        frame_shape = (480, 640)
        points, labels = generate_contrast_points(bbox, frame_shape, margin=10)

        # Điểm đầu tiên là positive ở tâm
        assert labels[0] == 1
        assert points[0] == (130.0, 160.0)

        # Các điểm còn lại là negative nằm ngoài bbox
        assert all(lbl == 0 for lbl in labels[1:])
        assert len(points) >= 3
        for px, py in points[1:]:
            # Nằm ngoài bounding box
            assert px < 100 or px > 160 or py < 100 or py > 220
            # Nằm trong khung hình
            assert 0 <= px < 640 and 0 <= py < 480
