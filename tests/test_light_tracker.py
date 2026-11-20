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


# --- chế độ `scale=True`: nội suy cả TỈ LỆ + xoay (20-11) -------------------------------------
def _khung_vat(patch, *, ti_le=1.0, xoay=0.0, dx=0, dy=0, hinh=(240, 320), tam=(160, 120), seed=1):
    """Ảnh tổng hợp: nền nhiễu nhẹ CỐ ĐỊNH + một "vật" có texture, phóng to/xoay/dịch theo yêu cầu.

    Texture gắn vào vật (không phải nền ngẫu nhiên) — nếu nền ngẫu nhiên thì LK không khớp được gì và
    mọi ca đều "mất dấu", đúng cái bẫy đã gặp khi thử lần đầu.
    """
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    img = np.full(hinh, 128, np.uint8)
    img = (img + rng.normal(0, 2, img.shape)).clip(0, 255).astype(np.uint8)
    p = patch if ti_le == 1.0 else cv2.resize(patch, None, fx=ti_le, fy=ti_le)
    if xoay:
        m = cv2.getRotationMatrix2D((p.shape[1] / 2, p.shape[0] / 2), xoay, 1.0)
        p = cv2.warpAffine(p, m, (p.shape[1], p.shape[0]))
    ph, pw = p.shape
    x0, y0 = int(tam[0] - pw / 2 + dx), int(tam[1] - ph / 2 + dy)
    img[y0:y0 + ph, x0:x0 + pw] = p
    return img


def _patch_texture(seed=1):
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    return cv2.GaussianBlur((rng.random((90, 60)) * 255).astype(np.uint8), (3, 3), 0)


def test_scale_bat_duoc_vat_PHONG_TO_va_THU_NHO():
    """Tịnh tiến thuần KHÔNG THỂ chữa lệch kích thước (đo trên GT 20-11: ΔW/ΔH tới −132 px).

    Nghiệm thu: vật to 1,2× ⇒ ô bao phải to ~72×108; nhỏ 0,85× ⇒ ~51×77. Chế độ `shift` phải
    `ok=False` ở cả hai ca (đúng lý do phải thêm chế độ này).
    """
    from src.light_tracker import LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    b = (130, 75, 60, 90)
    for ti_le, rong_mong, cao_mong in ((1.2, 72, 108), (0.85, 51, 77)):
        f2 = _khung_vat(patch, ti_le=ti_le)
        t = LkBoxTracker(scale=False)
        t.reset(f1, b)
        assert t.update(f2)[0] is None, f"shift phải KHÔNG bám được khi vật co giãn {ti_le}"
        t = LkBoxTracker(scale=True)
        t.reset(f1, b)
        bbox, ok = t.update(f2)
        assert ok and abs(bbox[2] - rong_mong) <= 3 and abs(bbox[3] - cao_mong) <= 3, (ti_le, bbox)
        assert abs(t.last_scale - ti_le) < 0.06
        assert t.last_khop_similarity is True


def test_scale_bat_duoc_XOAY_va_van_tinh_dich_chuyen():
    from src.light_tracker import LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    # xoay 10°: ô bao bao ngoài 60×90 xoay 10° ≈ 74×99
    t = LkBoxTracker(scale=True)
    t.reset(f1, (130, 75, 60, 90))
    bbox, ok = t.update(_khung_vat(patch, xoay=10))
    assert ok and abs(bbox[2] - 74) <= 4 and abs(bbox[3] - 99) <= 4, bbox
    assert t.last_angle_deg < 0 and abs(abs(t.last_angle_deg) - 10) < 2      # xoay âm = cùng chiều
    # dịch thuần: cả hai chế độ phải ra CÙNG kết quả (không thêm sai số khi tỉ lệ = 1)
    for sc in (False, True):
        t = LkBoxTracker(scale=sc)
        t.reset(f1, (130, 75, 60, 90))
        assert t.update(_khung_vat(patch, dx=5, dy=3))[0] == (135, 78, 60, 90), sc


def test_scale_CONG_an_toan_tu_choi_bien_doi_qua_lon():
    """Vật "phóng" 1,6× trong một bước (> `scale_max` 1,25) là dấu hiệu khớp rác ⇒ KHÔNG được bịa
    ô bao to gấp rưỡi; phải rơi về tịnh tiến (và ở ca này tịnh tiến cũng mất dấu)."""
    from src.light_tracker import DEFAULT_SCALE_MAX, LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    t = LkBoxTracker(scale=True)
    t.reset(f1, (130, 75, 60, 90))
    bbox, ok = t.update(_khung_vat(patch, ti_le=1.6))
    assert ok is False and bbox is None
    assert DEFAULT_SCALE_MAX == 1.25          # nếu ai nới cổng, test các ca "quá lớn" phải xem lại
    assert t.last_khop_similarity is False


def test_scale_mat_dau_khi_vat_bien_mat():
    """Cổng `mad` phải còn hiệu lực: vật biến mất ⇒ không bám vào nền rồi báo ô bao sai."""
    import numpy as np
    from src.light_tracker import LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    rng = np.random.default_rng(7)
    nen = (rng.random(f1.shape) * 255).astype(np.uint8)      # đổi hẳn nội dung: không còn vật
    t = LkBoxTracker(scale=True, max_mad=1.5)
    t.reset(f1, (130, 75, 60, 90))
    bbox, ok = t.update(nen)
    assert ok is False and bbox is None


def test_warp_mask_bien_doi_cung_phep_voi_o_bao():
    """Mask phải co giãn CÙNG phép với ô bao, nếu không thì mask và ô lệch nhau trên hình."""
    import numpy as np
    from src.light_tracker import warp_mask
    mask = np.zeros((100, 100), bool)
    mask[40:60, 40:60] = True                               # khối 20×20 ở giữa
    # phóng 1,5× quanh tâm (50, 50) ⇒ khối 30×30
    m = np.array([[1.5, 0, -25.0], [0, 1.5, -25.0]], np.float32)
    ra = warp_mask(mask, m)
    assert ra.dtype == bool and ra.shape == mask.shape
    assert ra.sum() > mask.sum()                            # to ra
    ys, xs = np.where(ra)
    assert abs((ys.max() - ys.min() + 1) - 30) <= 2 and abs((xs.max() - xs.min() + 1) - 30) <= 2
    # ma trận None / identity ⇒ trả NGUYÊN mask (không tạo bản sao biến dạng)
    assert warp_mask(mask, None) is mask
    assert warp_mask(mask, np.array([[1, 0, 0], [0, 1, 0]], np.float32)) is mask


def test_che_do_shift_duoc_GHIM_tuyet_doi_khong_doi_so():
    """`scale=False` là chế độ đã dùng cho MỌI số công bố ⇒ phải ghim tuyệt đối (không dung sai ±2 px).

    `int(round(...))` + thứ tự `median → mad` là hai thứ dễ bị "sửa cho đẹp" và làm lệch 1 px mọi artifact.
    """
    import numpy as np
    from src.light_tracker import LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    f2 = _khung_vat(patch, dx=3, dy=2)               # dịch NGUYÊN pixel ⇒ kết quả phải chính xác
    t = LkBoxTracker(scale=False)
    t.reset(f1, (130, 75, 60, 90))
    bbox, ok = t.update(f2)
    assert ok is True
    assert bbox == (133, 77, 60, 90), f"chế độ mặc định phải giữ nguyên kết quả, nhận {bbox}"
    assert t.last_matrix is not None
    # `last_matrix` giữ dx,dy là SỐ THỰC (trung vị), còn bbox mới `int(round(...))` ⇒ ghim bbox tuyệt
    # đối, còn ma trận ghim theo dung sai 1e-2 (giá trị thực 2,9996/2,0002).
    assert np.allclose(t.last_matrix, [[1, 0, 3], [0, 1, 2]], atol=1e-2)
    assert t.last_khop_similarity is False and t.last_scale == 1.0 and t.last_angle_deg == 0.0


def test_warp_mask_tinh_tien_TRUNG_KHOP_shift_mask_tung_pixel():
    """`shift_mask` nay gọi `warp_mask`; hai hàm phải cho cùng kết quả pixel-exact (mask là 0/1)."""
    import numpy as np
    from src.light_tracker import shift_mask, warp_mask
    mask = np.zeros((40, 40), bool)
    mask[10:20, 10:20] = True
    for dx, dy in ((0, 0), (3, 2), (-7, 5), (100, 100)):
        a = shift_mask(mask, dx, dy)
        b = warp_mask(mask, np.array([[1, 0, dx], [0, 1, dy]], np.float32))
        assert (a == b).all()


def test_cong_similarity_chap_nhan_dung_nguong_va_tu_choi_khi_qua():
    """Gọi THẲNG `_khop_similarity` để khẳng định cổng (tỉ lệ/góc) hoạt động — test qua `update()` có
    thể pass nhờ cổng `mad` của nhánh tịnh tiến, tức không chứng minh được gì (review #65)."""
    import numpy as np
    from src.light_tracker import LkBoxTracker
    rng = np.random.default_rng(0)
    prev = (rng.random((64, 2)) * 100).astype(np.float32)
    t = LkBoxTracker(scale=True)
    # tỉ lệ 1,2 (trong cổng) ⇒ nhận, trả đúng tỉ lệ/góc
    m = np.array([[1.2, 0, 5], [0, 1.2, 7]], np.float32)
    ra = t._khop_similarity(prev, prev @ m[:, :2].T + m[:, 2])
    assert ra is not None and abs(ra[1] - 1.2) < 1e-3 and abs(ra[2]) < 1e-3
    # tỉ lệ 1,6 (ngoài cổng 1,25) ⇒ None
    m2 = np.array([[1.6, 0, 0], [0, 1.6, 0]], np.float32)
    assert t._khop_similarity(prev, prev @ m2[:, :2].T) is None
    # góc 20° (ngoài cổng 15°) ⇒ None
    a = np.radians(20.0)
    m3 = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0]], np.float32)
    assert t._khop_similarity(prev, prev @ m3[:, :2].T) is None
    # quá ít điểm ⇒ None
    assert t._khop_similarity(prev[:3], prev[:3]) is None


def test_last_scale_CHI_ghi_khi_similarity_that_su_duoc_dung():
    """Chẩn đoán chỉ được ghi khi similarity THẬT SỰ được dùng (P3 review #65).

    Hai ca chặn khác nhau, phải phủ CẢ HAI (bản đầu chỉ phủ ca `mad` mà docstring lại khai ca `bbox`):
      - bị chặn ở cổng **mad phần dư** (`max_mad` rất chặt);
      - bị chặn ở bước **bbox** (ô quá nhỏ ⇒ `_bbox_tu_matrix` trả None) — tỉ lệ vẫn qua cổng.
    """
    from src.light_tracker import LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    t = LkBoxTracker(scale=True, max_mad=0.05)     # ca 1: cổng mad rất chặt ⇒ phần dư bị chặn
    t.reset(f1, (130, 75, 60, 90))
    t.update(_khung_vat(patch, ti_le=1.2))
    assert t.last_khop_similarity is False
    assert t.last_scale == 1.0 and t.last_angle_deg == 0.0, "không dùng similarity thì không được khai tỉ lệ"
    # ca 2: bbox suy ra bị TỪ CHỐI (`_bbox_tu_matrix` trả None). Gọi thẳng hàm: qua `update()` không
    # tới được nhánh này vì `_seed` đã đòi ô ≥ 4 px mỗi chiều (đường `reset` chặn trước). Ô chủ yếu nằm
    # NGOÀI khung ⇒ sau khi kẹp còn 3 px < 4 ⇒ None.
    import numpy as np
    t2 = LkBoxTracker(scale=True)
    t2.reset(f1, (130, 75, 60, 90))
    t2._prev_bbox = (316, 236, 60, 40)                      # phần lớn ra ngoài khung 320×240
    assert t2._bbox_tu_matrix(np.eye(2, 3, dtype=np.float32), f1.shape) is None
    assert t2.last_khop_similarity is False, "bbox bị từ chối thì không được báo 'đã dùng similarity'"
    assert t2.last_scale == 1.0


def test_vat_bien_mat_tren_nen_CO_TEXTURE_thi_cong_TU_CHOI():
    """Đo lại cho đúng (bản đầu của test này khẳng định "cổng không phát hiện được" — SAI, đã kiểm):

    Vật dán vào nền có texture rồi biến mất ⇒ LK không khớp được điểm nào trên vật ⇒ điểm theo dõi
    không đủ / độ tản lớn ⇒ `ok=False` ở **cả hai** chế độ. Nền PHẲNG tuyệt đối là ca không dùng được
    để kết luận (LK không đủ điểm vì lý do khác), nên test dùng nền texture.
    """
    import cv2
    import numpy as np
    from src.light_tracker import LkBoxTracker
    rng = np.random.default_rng(3)
    nen = cv2.GaussianBlur((rng.random((240, 320)) * 255).astype(np.uint8), (5, 5), 0)
    co_vat = nen.copy()
    co_vat[75:165, 130:190] = _patch_texture(seed=9)
    for scale in (False, True):
        t = LkBoxTracker(scale=scale)
        t.reset(co_vat, (130, 75, 60, 90))
        bbox, ok = t.update(nen)                   # vật BIẾN MẤT, nền tĩnh lộ ra
        assert ok is False and bbox is None, (scale, bbox)
        # và khi vật chỉ dịch 6 px (còn trong khung) thì VẪN phải bám được — cổng không chặn bừa
        t.reset(co_vat, (130, 75, 60, 90))
        dich = nen.copy()
        dich[75:165, 136:196] = _patch_texture(seed=9)
        assert t.update(dich)[0] == (136, 75, 60, 90), scale


def test_ly_do_tu_choi_phan_biet_duoc_cac_nhanh():
    """`last_ly_do` là thứ làm cho việc ĐO hiểu đúng: "LK từ chối" gồm 4 nguyên nhân rất khác nhau.

    Ca thật đã bị hiểu sai (review #65 vòng 3): một frame không có ô hiển thị bị đọc thành "LK mất dấu
    ở frame đó" trong khi `_seed` rỗng vì bbox VOS suy biến ⇒ **LK chưa hề chạy**.
    """
    import numpy as np
    from src.light_tracker import LkBoxTracker
    # seed_rong: ô < 4 px (bbox VOS suy biến (0,0,1,1))
    t = LkBoxTracker(scale=True)
    t.reset(np.zeros((40, 40), np.uint8), (0, 0, 1, 1))
    assert t.update(np.zeros((40, 40), np.uint8)) == (None, False)
    assert t.last_ly_do == "seed_rong"
    # ok_shift / ok_scale
    patch = _patch_texture()
    for scale, ly_do in ((False, "ok_shift"), (True, "ok_scale")):
        f1 = _khung_vat(patch)
        t = LkBoxTracker(scale=scale)
        t.reset(f1, (130, 75, 60, 90))
        assert t.update(_khung_vat(patch, dx=3, dy=2))[1] is True
        assert t.last_ly_do == ly_do, (scale, t.last_ly_do)
    # mad_du (nhánh scale, phần dư bị chặn) — không được gọi là "thieu_diem"
    t = LkBoxTracker(scale=True, max_mad=0.01)
    f1 = _khung_vat(patch)
    t.reset(f1, (130, 75, 60, 90))
    t.update(_khung_vat(patch, ti_le=1.2))
    assert t.last_ly_do == "mad_du"


def test_bbox_bi_tu_choi_thi_ROI_VE_tinh_tien_va_bao_dung_ly_do(monkeypatch):
    """Trước đây test này **không thể đỏ**: cả hai nhánh (`if ok:` / `else:`) đều đúng ở mọi đường từ
    chối nhờ reset đầu `update()` (review #65 vòng 4). Nay: vá `_bbox_tu_matrix` trả `None` trên ĐƯỜNG
    CÔNG KHAI `update()` ⇒ phải có `last_ly_do == "bbox_hong"` + không báo "đã dùng similarity".

    Nếu ai chuyển phép ghi `last_khop_similarity`/`last_ly_do` lên trước bước bbox thì test ĐỎ.
    """
    from src.light_tracker import LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    t = LkBoxTracker(scale=True)
    t.reset(f1, (130, 75, 60, 90))
    goc_bbox = t._bbox_tu_matrix
    monkeypatch.setattr(t, "_bbox_tu_matrix", lambda *_a, **_k: None)
    bbox, ok = t.update(_khung_vat(patch, dx=3, dy=2))
    # Hai field: kết quả CUỐI (`ok_shift` — đã dùng tịnh tiến) và LÝ DO similarity không dùng.
    assert t.last_ly_do_khop == "bbox_hong", t.last_ly_do_khop
    assert t.last_ly_do == "ok_shift", t.last_ly_do
    assert t.last_khop_similarity is False
    assert t.last_scale == 1.0
    # và vẫn phải BÁM ĐƯỢC bằng tịnh tiến (không "chết" chỉ vì bbox similarity hỏng)
    assert ok is True and bbox == (133, 77, 60, 90), bbox
    # Bước KẾ tiếp hợp lệ (trả lại phép bbox thật) ⇒ lý do phải được XOÁ, không mang giá trị cũ sang.
    # Xoá dòng reset `last_ly_do_khop` đầu `update()` là test này ĐỎ.
    monkeypatch.setattr(t, "_bbox_tu_matrix", goc_bbox)
    t.update(_khung_vat(patch, dx=6, dy=4))
    assert t.last_ly_do_khop is None, t.last_ly_do_khop


def test_che_do_scale_TAT_thi_khong_bao_gio_co_ly_do_similarity():
    """`scale=False` ⇒ không có similarity để dùng ⇒ `last_ly_do_khop` phải là `None` ở mọi bước."""
    from src.light_tracker import LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    t = LkBoxTracker(scale=False)
    t.reset(f1, (130, 75, 60, 90))
    for dx in (2, 4, 6):
        bbox, ok = t.update(_khung_vat(patch, dx=dx))
        assert ok is True and t.last_ly_do == "ok_shift", (dx, ok, t.last_ly_do)
        assert t.last_ly_do_khop is None, (dx, t.last_ly_do_khop)
    # Bước KẾ tiếp hợp lệ ⇒ lý do phải được XOÁ (chứ không mang giá trị cũ sang). Xoá dòng reset đầu
    # `update()` là test này ĐỎ.
    t.update(_khung_vat(patch, dx=6, dy=4))
    assert t.last_ly_do_khop is None, t.last_ly_do_khop




def test_mad_du_o_che_do_scale_di_qua_nhanh_PHAN_DU(monkeypatch):
    """Ca `mad_du` phải chứng minh là nhánh **phần dư của similarity**, không phải nhánh tịnh tiến.

    Bản trước dùng `max_mad=0.01` ⇒ nhánh tịnh tiến cũng từ chối, nên không phân biệt được hai nhánh
    (review #65 vòng 4). Nay dùng spy trên `_khop_similarity`: phải ĐƯỢC GỌI và trả matrix.
    """
    from src.light_tracker import LkBoxTracker
    patch = _patch_texture()
    f1 = _khung_vat(patch)
    t = LkBoxTracker(scale=True, max_mad=0.01)
    t.reset(f1, (130, 75, 60, 90))
    da_goi = []
    goc = t._khop_similarity

    def spy(prev, moved):
        ra = goc(prev, moved)
        da_goi.append(ra)
        return ra

    monkeypatch.setattr(t, "_khop_similarity", spy)
    bbox, ok = t.update(_khung_vat(patch, ti_le=1.2))
    assert da_goi and da_goi[0] is not None, "phải khớp được similarity rồi mới bị cổng phần dư chặn"
    assert ok is False and bbox is None
    assert t.last_ly_do == "mad_du"
    # Similarity ĐÃ tính rồi bị cổng phần dư từ chối ⇒ phải khai lý do (nếu không thì `mad_du` này
    # không phân biệt được với `mad_du` của nhánh tịnh tiến)
    assert t.last_ly_do_khop == "mad_du"


def test_last_n_diem_phan_biet_CHUA_CHAY_voi_0_diem_va_so_diem_that():
    """`n_diem` phải phân biệt 3 trạng thái: chưa chạy LK (None) · 0 điểm (`seed_rong`/`lk_hong`) ·
    số điểm thật. Không có test nào chạm field này là mời mutant `if n:` lọt (review PR #66)."""
    import numpy as np

    from src.light_tracker import LkBoxTracker

    t = LkBoxTracker()
    assert t.last_n_diem is None                     # chưa reset
    gray = np.zeros((60, 90), np.uint8)
    t.reset(gray, (0, 0, 1, 1))                      # ô < 4 px ⇒ `_seed` rỗng
    bbox, ok = t.update(gray)
    assert ok is False and t.last_ly_do == "seed_rong" and t.last_n_diem == 0

    patch = _patch_texture()
    f1 = _khung_vat(patch)
    t2 = LkBoxTracker()
    t2.reset(f1, (130, 75, 60, 90))
    bbox, ok = t2.update(_khung_vat(patch, dx=3, dy=2))
    assert ok is True and t2.last_n_diem is not None and t2.last_n_diem > 0

    # `thieu_diem`: cổng `min_points` chặn, nhưng SỐ ĐIỂM vẫn phải đọc được (đúng mục đích của field —
    # phân biệt "cổng chặn vì tản" với "quá ít điểm"). Chuyển phép gán xuống dưới cổng là test ĐỎ.
    t3 = LkBoxTracker(min_points=10_000)
    t3.reset(f1, (130, 75, 60, 90))
    bbox, ok = t3.update(_khung_vat(patch, dx=3, dy=2))
    assert ok is False and t3.last_ly_do == "thieu_diem"
    assert t3.last_n_diem == 64, t3.last_n_diem            # lưới 8×8

    # reset đầu bước: mất `_prev_gray` ⇒ bước sau là `chua_reset` và `n_diem` phải về `None`
    t2._prev_gray = None
    t2.update(_khung_vat(patch, dx=6, dy=4))
    assert t2.last_ly_do == "chua_reset" and t2.last_n_diem is None
