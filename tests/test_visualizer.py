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
    def test_ghi_mp4_doc_lai_du_frame_dung_kich_thuoc(self, tmp_path, monkeypatch):
        out = tmp_path / "hud.mp4"
        # Đóng băng đồng hồ: từ ticket #44 nhịp ghi theo thời gian THỰC, nên test "1 lần update =
        # 1 frame" phải cố định thời gian, nếu không nó phụ thuộc tốc độ máy.
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: 0.0)
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

    def test_recording_chi_true_khi_da_ghi_duoc_frame(self, tmp_path):
        """`recording` = "đã ghi frame", không phải "writer đã mở".

        Vì sao cần: `run_live` chỉ chuyển mã bản H.264 khi `recording` — nếu mở writer mà chưa ghi
        frame nào thì file rỗng, và nếu mở LỖI mà file cùng tên từ lần trước còn đó thì sẽ chuyển mã
        bản CŨ rồi báo "phát được trên Chrome" (thành công giả, review 09-11).
        """
        viz = Visualizer()
        assert viz.recording is False                       # chưa mở gì

        path = tmp_path / "r.mp4"
        assert viz.open_recorder(str(path), fps=10, frame_size=(64, 48)) is True
        assert viz.recording is False, "mở writer chưa đủ — chưa có frame nào"

        frame = np.full((48, 64, 3), 100, np.uint8)
        viz.update(frame, TrackingResult(frame_idx=0, mask=None, bbox=(0, 0, 0, 0),
                                         score=0.0, elapsed_ms=1.0))
        assert viz.recording is True
        viz.close_recorder()
        assert viz.recording is False

    def test_close_recorder_khi_chua_mo_khong_crash(self):
        Visualizer().close_recorder()

    def test_chua_open_recorder_thi_update_khong_ghi(self, tmp_path):
        """Không bật ghi (config off) → vẫn update HUD bình thường, không tạo file."""
        viz = Visualizer()
        img = viz.update(_frame(), _result())
        assert img.shape == (240, 320, 3)
        assert not (tmp_path / "hud.mp4").exists()

class TestChiBaoMatDau:
    """Khi mask rỗng (mất dấu) phải có chỉ báo rõ — người dùng báo 18-10: mask biến mất
    im lặng sau khi chọn vào vùng nền, không biết đang mất dấu hay đang chạy đúng."""

    def test_dem_so_frame_mat_dau_va_chuoi_lien_tiep(self):
        viz = Visualizer()
        live = _result(frame_idx=0, bbox=(100, 100, 140, 140))
        lost = _result(frame_idx=1, bbox=(0, 0, 0, 0), mask_box=None)
        viz.update(_frame(), live)
        viz.update(_frame(), lost)
        viz.update(_frame(), lost)
        viz.update(_frame(), live)
        viz.update(_frame(), lost)
        assert viz.lost_frames == 3          # tổng số frame mất dấu
        assert viz.consecutive_lost == 1     # chuỗi hiện tại (reset sau frame bắt lại)

    def test_ve_banner_mat_dau_khi_mask_rong(self):
        """Banner vẽ ở GIỮA khung (không trùng HUD/mask/bbox) — so với frame gốc."""
        frame = _frame()
        img = Visualizer().update(
            frame, _result(frame_idx=1, bbox=(0, 0, 0, 0), mask_box=None))
        band = img[100:140, 160:300]   # vùng sạch: không HUD/mask/bbox
        assert not np.array_equal(band, frame[100:140, 160:300])

    def test_khong_ve_banner_khi_con_bam(self):
        frame = _frame()
        img = Visualizer().update(frame, _result(frame_idx=0, bbox=(100, 100, 140, 140)))
        # vùng sạch không có lớp overlay nào → giữ nguyên nền
        band = img[100:140, 160:300]
        assert np.array_equal(band, frame[100:140, 160:300])

    def test_reset_xoa_bo_dem_mat_dau(self):
        viz = Visualizer()
        viz.update(_frame(), _result(frame_idx=0, bbox=(0, 0, 0, 0), mask_box=None))
        assert viz.lost_frames == 1
        viz.reset()
        assert viz.lost_frames == 0 and viz.consecutive_lost == 0


class TestAnQuyDao:
    """Người dùng hỏi: 'đường hồng chi vậy, ẩn được không' — đó là quỹ đạo (trajectory)."""

    def _res(self, i, bbox):
        from src.tracker_engine import TrackingResult

        mask = np.zeros((120, 160), dtype=bool)
        mask[0:10, 0:10] = True
        return TrackingResult(frame_idx=i, mask=mask, bbox=bbox, score=1.0, elapsed_ms=10.0)

    def test_mac_dinh_ve_quy_dao(self):
        frame = np.zeros((120, 160, 3), np.uint8)
        viz = Visualizer(max_trajectory=10)
        viz.consume(self._res(0, (10, 10, 20, 20)))      # tâm (15,15)
        r2 = self._res(1, (130, 90, 140, 100))           # tâm (135,95)
        viz.consume(r2)                                  # cần ≥2 điểm mới có đường nối
        img = viz.render(frame, r2)
        # điểm giữa đoạn nối có màu (đường quỹ đạo tím)
        assert not np.array_equal(img[55, 75], frame[55, 75])

    def test_tat_quy_dao_thi_khong_ve_giua(self):
        frame = np.zeros((120, 160, 3), np.uint8)
        viz = Visualizer(max_trajectory=10, show_trajectory=False)
        viz.consume(self._res(0, (10, 10, 20, 20)))
        r2 = self._res(1, (130, 90, 140, 100))
        viz.consume(r2)
        img = viz.render(frame, r2)
        assert np.array_equal(img[55, 75], frame[55, 75])   # không có đường nối

    def test_tat_quy_dao_van_ve_mask_va_o_bao(self):
        img = Visualizer(show_trajectory=False).update(_frame(), _result())
        assert img.shape == (240, 320, 3)
        assert not np.array_equal(img[170, 120], np.array([40, 40, 40], np.uint8))  # mask vẫn tô


class TestCanhBaoDoiDoiTuong:
    """Cảnh báo khi nghi bám sang đối tượng khác (chọn mặt A, A trốn → nhảy sang B)."""

    def test_co_canh_bao_thi_ve_chu(self):
        frame = np.zeros((240, 320, 3), np.uint8)
        img = Visualizer().update(frame, _result(), switch_warning=True)
        assert not np.array_equal(img[96:112, :260], frame[96:112, :260])

    def test_khong_canh_bao_thi_khong_ve(self):
        frame = np.zeros((240, 320, 3), np.uint8)
        img = Visualizer().update(frame, _result(), switch_warning=False)
        assert np.array_equal(img[96:112, :260], frame[96:112, :260])


class TestTrangThaiTaiNhanDien:
    """HUD hiện trạng thái đang tìm lại + điểm khớp (ADR-0003, ticket 09)."""

    def _result(self, mask=True):
        from src.tracker_engine import TrackingResult
        m = np.ones((240, 320), bool) if mask else np.zeros((240, 320), bool)
        return TrackingResult(frame_idx=0, mask=m, bbox=(10, 10, 50, 50),
                              score=0.9, elapsed_ms=1.0)

    def test_trang_thai_reacquiring_ve_duoc_khong_crash(self, tmp_path):
        from src.visualizer import Visualizer
        vis = Visualizer()
        frame = np.zeros((240, 320, 3), np.uint8)
        img = vis.update(frame, self._result(mask=False),
                         reid_state="reacquiring", reid_score=0.42)
        assert img.shape == frame.shape and img.dtype == np.uint8

    def test_khong_co_trang_thai_van_nhu_cu(self):
        from src.visualizer import Visualizer
        vis = Visualizer()
        frame = np.zeros((240, 320, 3), np.uint8)
        img = vis.update(frame, self._result())
        assert img.shape == frame.shape


class TestToiUuVeChu:
    """Tối ưu 05-11-2026: chữ HUD render vào canvas nhỏ + cache, không chuyển cả khung sang PIL.

    Vì sao có test: cách cũ tốn 2,4 ms/dòng (tới 16,5 ms/render đủ HUD+banner) vì mỗi dòng
    phải `cvtColor` cả khung 640x480 sang PIL rồi chuyển lại. Test này khoá lại 2 tính chất
    quan trọng: (1) cùng một dòng chữ chỉ render glyph MỘT lần (cache hit), (2) chữ vẫn vẽ
    đúng chỗ và đúng màu như trước.
    """

    def test_cung_dong_chu_chi_render_glyph_mot_lan(self):
        from src import visualizer as vz

        font = find_vietnamese_font()
        if font is None:
            pytest.skip("máy không có font TTF phổ biến")
        vz._glyph_bgr.cache_clear()
        img = _frame()
        visualizer = Visualizer(font_path=font)
        visualizer._put_text(img, "Độ trễ: 223 ms/frame", (8, 20))
        hit_after_first = vz._glyph_bgr.cache_info()
        visualizer._put_text(img, "Độ trễ: 223 ms/frame", (8, 20))
        after_second = vz._glyph_bgr.cache_info()
        assert hit_after_first.misses == 1
        assert after_second.hits == 1

    def test_chu_ve_dung_mau_trang_o_dung_toa_do(self):
        """Chữ trắng trên nền tối: phải có pixel sáng trong vùng vẽ, ngoài vùng thì không."""
        font = find_vietnamese_font()
        if font is None:
            pytest.skip("máy không có font TTF phổ biến")
        img = _frame()
        Visualizer(font_path=font)._put_text(img, "Độ trễ: 223 ms/frame", (8, 20))
        assert img[20:40, 8:200].max() > 150          # có chữ
        assert np.array_equal(img[200:, :], _frame()[200:, :])   # không lem ra toàn khung


class TestKhongVeOChungKhiMatDau:
    """21-11: banner "MAT DAU" và một ô bao trên ảnh là **hai câu nói ngược nhau**.

    Đường worker (`live_tracking._annotate`) đã ẩn ô khi `bam = no_evidence`; CLI phải giống, nếu không
    buổi demo trên `./run demoip` lại vẽ ô của SAM 2 khi mask đã rỗng — đúng kiểu "ô ma" mà người xem
    không phân biệt được với "đang bám".
    """

    def test_masked_va_o_bao_khong_ve_khi_mat_dau(self):
        from src.live_tracking import _BAM_NO_EVIDENCE_FRAMES

        viz = Visualizer()
        for _ in range(_BAM_NO_EVIDENCE_FRAMES):     # cùng ngưỡng với worker live (2 frame)
            viz.update(_frame(), _result(frame_idx=0, bbox=(0, 0, 0, 0), mask_box=None))
        assert viz.consecutive_lost == _BAM_NO_EVIDENCE_FRAMES
        frame = _frame()
        # bbox KHÁC rỗng (SAM 2 vẫn trả bbox khi mask rỗng) → nếu vẽ thì sẽ thấy viền
        img = viz.render(frame, _result(frame_idx=1, bbox=(200, 200, 220, 220),
                                       mask_box=None))
        # Vùng bbox (200..220) phải NGUYÊN NỀN: không viền ô, không mask. HUD nằm ở góc trên trái
        # (y ≈ 8–60) nên vùng này sạch.
        assert np.array_equal(img[200:220, 200:220], frame[200:220, 200:220]), \
            "mất dấu mà vẫn vẽ ô bao ⇒ banner 'MAT DAU' và ảnh nói hai chuyện ngược nhau"

    def test_dung_sai_mot_frame_van_ve_o(self):
        """Dung sai MỘT frame mất dấu là BẮT BUỘC (cùng lý do `MISS_MIN` của watchdog): ẩn ô ngay frame
        đầu làm ô nhấp nháy khi model "chớp" mất vật 1 frame."""
        viz = Visualizer()
        viz.update(_frame(), _result(frame_idx=0, bbox=(0, 0, 0, 0), mask_box=None))
        frame = _frame()
        img = viz.render(frame, _result(frame_idx=1, bbox=(200, 200, 220, 220), mask_box=None))
        assert not np.array_equal(img[200:220, 200:220], frame[200:220, 200:220])

    def test_ve_lai_khi_co_bang_chung(self):
        viz = Visualizer()
        viz.update(_frame(), _result(frame_idx=0, bbox=(200, 200, 220, 220)))   # mask non-rỗng
        assert viz.consecutive_lost == 0
        frame = _frame()
        img = viz.render(frame, _result(frame_idx=1, bbox=(200, 200, 220, 220)))
        assert not np.array_equal(img[200:220, 200:220], frame[200:220, 200:220]), \
            "có bằng chứng mà không vẽ ô ⇒ test vô nghĩa"


class TestCanhBaoOChonPhuMat:
    """21-11: cảnh báo "ô chọn phủ khuôn mặt" phải VẼ LÊN ẢNH, không chỉ in console.

    Đo thật: console đã in `IoU 0.76` mà người dùng vẫn chọn ô trùm mặt 3 phiên liền ⇒ khoanh đỏ ô mặt
    là thứ không thể bỏ qua. Vẽ tự hết hạn để không che HUD cả phiên.
    """

    def test_ve_vien_do_quanh_o_mat(self):
        from src.visualizer import Visualizer

        viz = Visualizer()
        viz.canh_bao_o_chon_phu_mat((100, 60, 80, 90), giay=30)
        frame = _frame()
        img = viz.render(frame, _result(frame_idx=0, bbox=(200, 200, 220, 220)))
        vien = img[60:63, 100:180]                      # cạnh trên của ô mặt
        do = ((vien[:, :, 2] > 200) & (vien[:, :, 1] < 80) & (vien[:, :, 0] < 80)).sum()
        assert do > 100, f"không thấy viền đỏ (đếm {do} px)"

    def test_tu_het_han(self):
        from src.visualizer import Visualizer

        viz = Visualizer()
        viz.canh_bao_o_chon_phu_mat((100, 60, 80, 90), giay=0.0)   # hết hạn ngay
        frame = _frame()
        img = viz.render(frame, _result(frame_idx=0, bbox=(200, 200, 220, 220)))
        vien = img[60:63, 100:180]
        do = ((vien[:, :, 2] > 200) & (vien[:, :, 1] < 80) & (vien[:, :, 0] < 80)).sum()
        assert do == 0, "hết hạn rồi mà vẫn vẽ ⇒ cảnh báo sẽ che HUD cả phiên"

    def test_none_thi_khong_ve(self):
        from src.visualizer import Visualizer

        viz = Visualizer()
        viz.canh_bao_o_chon_phu_mat(None)
        img = viz.render(_frame(), _result(frame_idx=0, bbox=(200, 200, 220, 220)))
        assert img is not None


class TestHudNoiDungKhiVeto:
    """P1 review 21-11: khi ứng viên bị BỎ vì trùng khuôn mặt, HUD phải nói ĐÚNG lý do.

    Trước đó HUD in "DANG TIM LAI... (khop 0.90 / can 0.75)" ⇒ người xem (và hội đồng) hiểu
    NGƯỢC là "hệ đủ điểm mà không nhận = hệ hỏng", trong khi lý do thật là veto.
    """

    def _render(self, monkeypatch, **kw):
        viz = Visualizer()
        texts = []
        monkeypatch.setattr(viz, "_put_text", lambda img, text, org: texts.append(str(text)))
        viz.render(_frame(), _result(), **kw)
        return texts

    def test_bi_veto_thi_hien_ly_do_trung_khuon_mat(self, monkeypatch):
        texts = self._render(monkeypatch, reid_state="reacquiring",
                             reid_score=0.90, reid_vetoed=True)
        hud = " | ".join(texts)
        assert "KHUON MAT" in hud            # nói rõ lý do
        assert "can 0.7" not in hud          # KHÔNG hiện "khớp X / cần Y" (gây hiểu ngược)

    def test_khong_veto_thi_van_hien_khop_va_nguong(self, monkeypatch):
        viz = Visualizer()
        viz.reid_threshold = 0.75
        texts = []
        monkeypatch.setattr(viz, "_put_text", lambda img, text, org: texts.append(str(text)))
        viz.render(_frame(), _result(), reid_state="reacquiring",
                   reid_score=0.62, reid_vetoed=False)
        hud = " | ".join(texts)
        assert "khop 0.62" in hud and "can 0.75" in hud
        assert "KHUON MAT" not in hud


class TestBannerNoiDungTheoReId:
    """Ticket #43 — banner mất dấu phải nói ĐÚNG khả năng của hệ.

    Bối cảnh đo: phiên `demoip_1123-144505` (re-ID TẮT, `git_rev 42efc56`) có 13 frame mất dấu và
    banner in "MẤT DẤU — TỰ TÌM LẠI"; hệ **không có re-ID** nên không tự tìm lại được gì. Câu đó
    nằm trong `_web.mp4` nộp bài ⇒ người xem được hứa một việc hệ không làm được.
    """

    def test_khong_reid_thi_bao_bam_r(self):
        from src.visualizer import lost_banner_text
        assert "bấm r" in lost_banner_text(False)
        assert "TỰ TÌM LẠI" not in lost_banner_text(False)

    def test_co_reid_thi_noi_viec_DANG_LAM_khong_hua_ket_qua(self):
        """P2 review 23-11: "TỰ TÌM LẠI" là LỜI HỨA; ca `--reid --reid-cue face` bám vật thì kho mẫu
        rỗng ⇒ không bao giờ nhận lại (đo: 201 frame, 180 mất dấu, `reid_score = -1` cả phiên).
        Câu đúng là việc ĐANG LÀM."""
        from src.visualizer import lost_banner_text
        assert lost_banner_text(True) == "MẤT DẤU — ĐANG TÌM LẠI"

    def test_ban_ascii_khi_khong_co_font(self):
        from src.visualizer import lost_banner_text
        assert lost_banner_text(False, co_font=False) == "MAT DAU - BAM R CHON LAI"
        assert lost_banner_text(True, co_font=False) == "MAT DAU - DANG TIM LAI"

    def test_mac_dinh_visualizer_la_khong_reid(self):
        """Không ai nói gì ⇒ KHÔNG được hứa 'tự tìm lại' (mặc định an toàn)."""
        assert Visualizer().reid_enabled is False

    def test_render_truyen_dung_co_reid_xuong_banner(self, monkeypatch):
        viz = Visualizer()
        da_nhan = []
        monkeypatch.setattr(viz, "_draw_lost_banner", lambda img, tu_tim_lai=None:
                            da_nhan.append(tu_tim_lai))
        for co_reid in (False, True):
            viz.reid_enabled = co_reid
            # `update()` (không phải `render()`) để `consume()` đếm `consecutive_lost` trước.
            viz.update(_frame(), _result(frame_idx=1, bbox=(0, 0, 0, 0), mask_box=None))
        assert da_nhan[-2:] == [False, True]


class TestGhiVideoDungThoiGianThuc:
    """Ticket #44 — file video phải DÀI ĐÚNG bằng thời gian phiên chạy.

    Bối cảnh đo (phiên `demoip_1123-144505`): thời gian suy luận thật **30,76 s** nhưng `_web.mp4`
    chỉ **20,83 s** (625 frame @30 fps) ⇒ video chạy nhanh **1,48×**. Nguyên nhân: ghi 1 frame cho
    mỗi frame HIỂN THỊ, mà nhịp hiển thị thật của live chỉ ~20 fps trong khi nhãn fps là 30.

    Hệ quả nếu không sửa: mọi tuyên bố "quỹ đạo theo thời gian thực" trong video nộp bài đều sai
    thời lượng, và mọi phân tích chuyển động (nhanh/chậm, độ trễ) trên video bị lệch 1,5×.
    """

    @staticmethod
    def _clock(monkeypatch, start=0.0):
        """Đồng hồ giả: trả giá trị do test đặt vào."""
        hop = {"t": start}
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: hop["t"])
        return hop

    def test_muoi_frame_hien_thi_trong_mot_giay_voi_fps30_ra_30_frame(self, tmp_path, monkeypatch):
        hop = self._clock(monkeypatch)
        viz = Visualizer()
        out = tmp_path / "nhip.mp4"
        assert viz.open_recorder(str(out), fps=30.0, frame_size=(160, 120),
                                 pace_realtime=True) is True
        for i in range(10):
            hop["t"] = i * 0.1                 # 10 frame hiển thị trong đúng 1,0 s
            viz.update(np.full((120, 160, 3), 50, np.uint8),
                       TrackingResult(frame_idx=i, mask=None, bbox=(0, 0, 0, 0),
                                      score=0.0, elapsed_ms=1.0))
        viz.close_recorder()
        n = viz._frames_written
        # Mốc so là frame CUỐI ĐƯỢC HIỂN THỊ (t = 0,9 s), không phải 1,0 s: file chỉ dài tới frame
        # cuối đó. Dung sai 2 frame (làm tròn `int(...) + 1` + 1 frame giữ cuối).
        dai = n / 30.0
        assert abs(dai - 0.9) <= 2 / 30.0, \
            f"file dài {dai:.2f} s cho phiên hiển thị 0,90 s ({n} frame @30 fps)"

    def test_nhip_hien_thi_cham_hon_khong_lam_video_ngan_lai(self, tmp_path, monkeypatch):
        """Đúng ca đã đo: hiển thị 20 fps (thực tế live) với nhãn 30 fps → file vẫn đủ 30 frame/s."""
        hop = self._clock(monkeypatch)
        viz = Visualizer()
        assert viz.open_recorder(str(tmp_path / "c.mp4"), fps=30.0, frame_size=(160, 120),
                                 pace_realtime=True) is True
        for i in range(20):                    # 20 frame trong 1,0 s = 20 fps thật
            hop["t"] = i * 0.05
            viz.update(np.full((120, 160, 3), 50, np.uint8),
                       TrackingResult(frame_idx=i, mask=None, bbox=(0, 0, 0, 0),
                                      score=0.0, elapsed_ms=1.0))
        viz.close_recorder()
        assert 29 <= viz._frames_written <= 31, \
            f"{viz._frames_written} frame — 1,0 s @30 fps phải là ~30, không phải 20"

    def test_treo_dai_khong_bom_frame_va_khong_tich_no(self, tmp_path, monkeypatch):
        """Treo 10 s không được đẩy 300 frame lặp, và các lần ghi SAU không bị dính trần."""
        from src.visualizer import _MAX_LAP_FRAMES
        hop = self._clock(monkeypatch)
        viz = Visualizer()
        assert viz.open_recorder(str(tmp_path / "treo.mp4"), fps=30.0,
                                 frame_size=(160, 120), pace_realtime=True) is True
        img = np.full((120, 160, 3), 50, np.uint8)
        res = TrackingResult(frame_idx=0, mask=None, bbox=(0, 0, 0, 0), score=0.0, elapsed_ms=1.0)
        viz.update(img, res)
        truoc = viz._frames_written
        hop["t"] = 10.0                       # máy treo 10 s
        viz.update(img, res)
        assert viz._frames_written - truoc <= _MAX_LAP_FRAMES
        # Sau khi rebase, nhịp lại đúng: thêm 1 s ⇒ thêm ~30 frame (không phải 60/lần nữa)
        trước2 = viz._frames_written
        hop["t"] = 11.0
        viz.update(img, res)
        assert 25 <= viz._frames_written - trước2 <= 35, "rebase hỏng ⇒ mọi lần ghi sau dính trần"
        viz.close_recorder()


class TestNghiDoiTuongVeONetDut:
    """Ticket #45 (đường CLI) — khi `switch_warning` thì vẽ ô NÉT ĐỨT, không tô mask.

    Số đo: phiên `demoip_1123-144505`, cổng nghi bật ở f144 và không tự xoá ⇒ 25,8 % phiên trắng;
    đường worker đã đổi theo cùng luật (`live_tracking._annotate`), CLI phải giống để buổi demo
    không nói hai chuyện.
    """

    def test_co_o_net_dut_va_khong_to_mask(self):
        viz = Visualizer()
        frame = _frame()
        img = viz.render(frame, _result(frame_idx=0, bbox=(100, 100, 200, 180)),
                         switch_warning=True)
        # viền trên của ô: màu vàng cảnh báo (0,215,255) → G cao
        vien = img[100, 100:200]
        assert (vien[:, 1] > 180).any(), "thiếu ô nét đứt khi nghi"
        # bên trong ô: không được có mask cam (G≈140) trộn với nền (40) — phải là nền thuần
        trong = img[120:160, 120:180]
        assert np.allclose(trong, frame[120:160, 120:180]), "mask bị tô khi đang nghi"

    def test_mat_dau_that_thi_khong_ve_gi(self):
        """Mất dấu thật (mask rỗng) KHÁC nghi: không có gì để vẽ ⇒ giữ nguyên như cũ."""
        viz = Visualizer()
        frame = _frame()
        img = viz.render(frame, _result(frame_idx=1, bbox=(0, 0, 0, 0), mask_box=None),
                         switch_warning=False)
        assert np.array_equal(img[100:180, 100:200], frame[100:180, 100:200])


class TestNguonFileKhongBiKeoDai:
    """Ticket #44, chiều NGƯỢC LẠI — nguồn FILE phải ghi 1:1, không bị kéo dài theo tốc độ model.

    Vì sao cần test: `pace_realtime` bật cho MỌI nguồn sẽ làm clip 333 frame @30 fps (11 s) thành
    ~29 s vì model chạy 11,5 bước/s — video demo hoá slideshow. Cờ này chỉ được bật cho nguồn live.
    """

    def test_mac_dinh_khong_pace_thi_moi_lan_ve_la_mot_frame(self, tmp_path, monkeypatch):
        hop = {"t": 0.0}
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: hop["t"])
        viz = Visualizer()
        assert viz.open_recorder(str(tmp_path / "f.mp4"), fps=30.0,
                                 frame_size=(160, 120)) is True     # pace_realtime mặc định TẮT
        for i in range(10):
            hop["t"] = i * 0.1          # chậm hơn fps khai báo — nhưng KHÔNG được lặp frame
            viz.update(np.full((120, 160, 3), 50, np.uint8),
                       TrackingResult(frame_idx=i, mask=None, bbox=(0, 0, 0, 0),
                                      score=0.0, elapsed_ms=1.0))
        viz.close_recorder()
        assert viz._frames_written == 10


class TestPhatStats:
    """Ticket #44, phần ARTIFACT: phiên phải TỰ KHAI nhịp phát.

    Vì sao: bug "video ngắn hơn thực 1,48×" sống nhiều tuần **chỉ vì** không file nào trong repo có
    số về nhịp phát — phải mở mp4 bằng ffprobe mới biết. `ti_le_thoi_luong ≈ 1,0` là điều kiện
    kiểm được (và `democheck` mục 10 đọc chính field này).
    """

    def test_chua_ve_gi_thi_khong_khai(self):
        assert Visualizer().phat_stats() == {}

    def test_ti_le_bang_1_khi_ghi_dung_thoi_gian_thuc(self, tmp_path, monkeypatch):
        hop = {"t": 0.0}
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: hop["t"])
        viz = Visualizer()
        assert viz.open_recorder(str(tmp_path / "ok.mp4"), fps=30.0,
                                 frame_size=(160, 120), pace_realtime=True) is True
        for i in range(10):                 # 10 lần vẽ trong 1,0 s, pace bật
            hop["t"] = i * 0.1
            viz.update(np.full((120, 160, 3), 50, np.uint8),
                       TrackingResult(frame_idx=i, mask=None, bbox=(0, 0, 0, 0),
                                      score=0.0, elapsed_ms=1.0))
        st = viz.phat_stats()
        viz.close_recorder()
        assert st["frames_rendered"] == 10
        assert st["frames_written"] >= 28
        assert 0.9 <= st["ti_le_thoi_luong"] <= 1.1, st

    def test_ti_le_0_68_dung_ca_phien_144505(self, tmp_path, monkeypatch):
        """Ca thật: 625 frame @30 fps = 20,83 s trong phiên 30,76 s ⇒ 0,677."""
        hop = {"t": 0.0}
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: hop["t"])
        viz = Visualizer()
        assert viz.open_recorder(str(tmp_path / "x.mp4"), fps=30.0,
                                 frame_size=(160, 120)) is True   # KHÔNG pace: ghi 1:1
        for i in range(10):
            hop["t"] = i * 0.1
            viz.update(np.full((120, 160, 3), 50, np.uint8),
                       TrackingResult(frame_idx=i, mask=None, bbox=(0, 0, 0, 0),
                                      score=0.0, elapsed_ms=1.0))
        st = viz.phat_stats()
        viz.close_recorder()
        # 10 frame ghi / 0,9 s ⇒ 0,37 — cùng bản chất với 0,677 (video ngắn hơn thực)
        assert st["ti_le_thoi_luong"] < 0.95


class TestPacingBien_Review2311:
    """5 ca biên do review độc lập 23-11 chỉ ra là THIẾU test (mỗi ca là một cách file nói sai
    thời lượng mà không ai biết).
    """

    @staticmethod
    def _clock(monkeypatch, start=0.0):
        hop = {"t": start}
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: hop["t"])
        return hop

    @staticmethod
    def _ve(viz, i=0):
        viz.update(np.full((120, 160, 3), 50, np.uint8),
                   TrackingResult(frame_idx=i, mask=None, bbox=(0, 0, 0, 0),
                                  score=0.0, elapsed_ms=1.0))

    def test_fps_khai_bao_15_thi_ghi_15_frame_moi_giay(self, tmp_path, monkeypatch):
        """P1 review: `_recorder_fps` từng KHÔNG được gán ⇒ luôn 30 ⇒ `--record-fps 15` cho file
        DÀI GẤP 2 LẦN thực."""
        hop = self._clock(monkeypatch)
        viz = Visualizer()
        assert viz.open_recorder(str(tmp_path / "f15.mp4"), fps=15.0,
                                 frame_size=(160, 120), pace_realtime=True) is True
        for i in range(10):
            hop["t"] = i * 0.1
            self._ve(viz, i)
        n = viz._frames_written
        viz.close_recorder()
        assert 14 <= n <= 16, f"{n} frame — 0,9 s @15 fps phải là ~14, không phải ~27"

    def test_nhan_fps_thap_hon_nhip_ve_thi_khong_phinh_file(self, tmp_path, monkeypatch):
        """Chiều ngược lại (review P2): nhãn 10 fps mà vẽ 30 lần/s ⇒ phải ghi ~10 frame/s."""
        hop = self._clock(monkeypatch)
        viz = Visualizer()
        assert viz.open_recorder(str(tmp_path / "f10.mp4"), fps=10.0,
                                 frame_size=(160, 120), pace_realtime=True) is True
        for i in range(30):
            hop["t"] = i / 30.0
            self._ve(viz, i)
        n = viz._frames_written
        viz.close_recorder()
        assert n <= 12, f"{n} frame — 1,0 s @10 fps không được vượt ~10"

    def test_dong_hoc_nhay_lui_khong_no(self, tmp_path, monkeypatch):
        hop = self._clock(monkeypatch, start=10.0)
        viz = Visualizer()
        assert viz.open_recorder(str(tmp_path / "lui.mp4"), fps=30.0,
                                 frame_size=(160, 120), pace_realtime=True) is True
        for i in range(5):
            hop["t"] = 10.0 + i * 0.033
            self._ve(viz, i)
        truoc = viz._frames_written
        hop["t"] = 5.0                       # đồng hồ LÙI (NTP/test)
        self._ve(viz, 9)
        sau = viz._frames_written
        viz.close_recorder()
        assert sau - truoc <= 1, "đồng hồ lùi không được đẩy hàng loạt frame"
        assert truoc >= 3, "5 lần vẽ trong 0,13 s phải đã ghi được ≥3 frame"

    def test_mo_lai_recorder_khong_thua_frame_tu_file_truoc(self, tmp_path, monkeypatch):
        """P2 review: `_rec_t0` rò ⇒ file MỚI bắt đầu bằng hàng chục frame lặp."""
        hop = self._clock(monkeypatch)
        viz = Visualizer()
        assert viz.open_recorder(str(tmp_path / "a.mp4"), fps=30.0,
                                 frame_size=(160, 120), pace_realtime=True) is True
        for i in range(5):
            hop["t"] = i * 0.1
            self._ve(viz, i)
        viz.close_recorder()
        hop["t"] = 0.45                     # mở lại NGAY (< 1 frame sau)
        assert viz.open_recorder(str(tmp_path / "b.mp4"), fps=30.0,
                                 frame_size=(160, 120), pace_realtime=True) is True
        self._ve(viz, 99)
        n = viz._frames_written
        viz.close_recorder()
        assert n == 1, f"file mới có {n} frame ngay từ lần vẽ đầu — mốc thời gian bị rò"

    def test_o_net_dut_bien_va_o_1px_va_dai_0(self):
        import numpy as np
        from src.visualizer import ve_o_net_dut

        img = np.zeros((30, 40, 3), np.uint8)
        ve_o_net_dut(img, 0, 0, 39, 29)              # chạm đúng biên phải/dưới
        assert img.sum() > 0
        img2 = np.zeros((30, 40, 3), np.uint8)
        ve_o_net_dut(img2, 5, 5, 6, 6)               # ô 1×1
        ve_o_net_dut(img2, 5, 5, 6, 6, dai=0)        # dai=0 KHÔNG được ném
        img3 = np.zeros((30, 40, 3), np.uint8)
        ve_o_net_dut(img3, 5, 5, 10_000, 10_000)     # bbox hỏng: phải clamp, không treo
        assert img3.shape == (30, 40, 3)


class TestQuyDaoTheoThoiGian:
    """Plan 24-11 việc 5 — quỹ đạo phải dài theo THỜI GIAN, không theo SỐ ĐIỂM.

    Cùng deque 100 điểm mang nghĩa khác nhau theo tốc độ máy: **16 s** ở 6,3 bước/s nhưng **32 s** ở
    3,1 bước/s. Yêu cầu 5 của đề cương là "quỹ đạo theo thời gian thực" ⇒ đổi nghĩa theo máy là
    không bảo vệ được.
    """

    def test_cua_so_5_giay_cat_diem_cu(self, monkeypatch):
        hop = {"t": 100.0}
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: hop["t"])
        viz = Visualizer(max_trajectory=100, trajectory_seconds=5.0)
        for i in range(40):                    # 40 bước, mỗi bước 0,16 s = 6,4 s
            hop["t"] = 100.0 + i * 0.16
            viz.consume(TrackingResult(frame_idx=i, mask=np.ones((10, 10), bool),
                                       bbox=(10 + i, 10, 20 + i, 20), score=1.0, elapsed_ms=100.0))
        # 5 s / 0,16 s ≈ 31 điểm, phải ÍT hơn 40 và nhiều hơn 20
        assert 20 <= len(viz.trajectory_points) <= 34, len(viz.trajectory_points)

    def test_cung_5_giay_nhung_nhip_khac_nhau_ra_cung_do_dai_thoi_gian(self, monkeypatch):
        hop = {"t": 0.0}
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: hop["t"])
        dem = {}
        for nhip in (0.16, 0.32):             # 6,3 bước/s và 3,1 bước/s
            viz = Visualizer(max_trajectory=200, trajectory_seconds=5.0)
            for i in range(40):
                hop["t"] = i * nhip
                viz.consume(TrackingResult(frame_idx=i, mask=np.ones((10, 10), bool),
                                           bbox=(10, 10, 20, 20), score=1.0, elapsed_ms=100.0))
            dem[nhip] = len(viz.trajectory_points)
        # cùng 5 giây ⇒ số điểm tỉ lệ nghịch với nhịp (≈31 và ≈16)
        assert dem[0.16] > dem[0.32], dem
        assert abs(dem[0.16] / dem[0.32] - 2.0) < 0.4, dem

    def test_mac_dinh_van_theo_so_diem(self, monkeypatch):
        hop = {"t": 0.0}
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: hop["t"])
        viz = Visualizer(max_trajectory=10)
        for i in range(50):
            hop["t"] = i * 0.01
            viz.consume(TrackingResult(frame_idx=i, mask=np.ones((10, 10), bool),
                                       bbox=(10, 10, 20, 20), score=1.0, elapsed_ms=100.0))
        assert len(viz.trajectory_points) == 10

    def test_reset_xoa_ca_moc_thoi_gian(self, monkeypatch):
        hop = {"t": 0.0}
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: hop["t"])
        viz = Visualizer(trajectory_seconds=5.0)
        viz.consume(TrackingResult(frame_idx=0, mask=np.ones((10, 10), bool),
                                   bbox=(10, 10, 20, 20), score=1.0, elapsed_ms=100.0))
        viz.reset()
        assert len(viz.trajectory_points) == 0 and len(viz._traj_ts) == 0


class TestBienP2_Review2411:
    """3 lỗi biên do review 24-11 chỉ ra (mỗi lỗi làm quỹ đạo "đổi nghĩa" mà không ai biết)."""

    def test_cua_so_thoi_gian_khong_bi_tran_so_diem_cat(self, monkeypatch):
        """`max_trajectory=100` từng âm thầm cắt cửa sổ 5 s xuống 3,33 s ở 30 bước/s."""
        hop = {"t": 0.0}
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: hop["t"])
        viz = Visualizer(max_trajectory=100, trajectory_seconds=5.0)
        for i in range(180):                  # 30 bước/s × 6 s
            hop["t"] = i / 30.0
            viz.consume(TrackingResult(frame_idx=i, mask=np.ones((10, 10), bool),
                                       bbox=(10, 10, 20, 20), score=1.0, elapsed_ms=33.0))
        assert len(viz.trajectory_points) >= 140, len(viz.trajectory_points)

    def test_cua_so_cuc_nho_khong_lam_rong_quy_dao(self, monkeypatch):
        hop = {"t": 0.0}
        monkeypatch.setattr("src.visualizer.time.monotonic", lambda: hop["t"])
        viz = Visualizer(trajectory_seconds=1e-6)
        for i in range(5):
            hop["t"] = 100.0 + i
            viz.consume(TrackingResult(frame_idx=i, mask=np.ones((10, 10), bool),
                                       bbox=(10, 10, 20, 20), score=1.0, elapsed_ms=1.0))
            assert len(viz.trajectory_points) >= 1


class TestChuaXacMinh:
    """24-11: trạng thái THỨ BA — vẫn VẼ nhưng KHÁC kiểu (`chua_xac_minh`).

    Vì sao: phiên `demoip_1124-125109` — cổng báo đúng ở f137 rồi hệ tự bám lại đúng vật ở t≈40 s,
    nhưng latch chỉ xoá được bằng `r`/`c`/reacquire (re-ID tắt) ⇒ 109/246 = 44,3 % phiên trắng.
    Không thể ẩn tiếp (mất buổi demo) và KHÔNG thể vẽ y như đã kiểm (ca 21-11 bám sang cửa/tường
    cùng tông, 65 frame) ⇒ vẽ viền nét đứt, không tô, không quỹ đạo.
    """

    def test_mask_chi_ve_vien_khong_to(self):
        viz = Visualizer()
        frame = _frame()
        r = _result(frame_idx=0, bbox=(100, 150, 140, 190), mask_box=(100, 150, 140, 190))
        img = viz.render(frame, r, chua_xac_minh=True)
        # giữa mask: KHÔNG được tô cam (mask tin cậy tô 0,35 × (0,140,255) ⇒ G≈110)
        giua = img[165:180, 110:130]
        assert np.allclose(giua, frame[165:180, 110:130]), "mask bị TÔ như đã kiểm"
        # nhưng phải CÓ nét vẽ (viền mask màu cảnh báo) trên biên của mask
        vien = img[150:152, 100:140]
        assert (vien[:, 1] > 180).any(), "không vẽ viền mask ⇒ không thấy vùng đang bám"

    def test_mask_tin_cay_van_to_day(self):
        """Đối chứng: cùng kết quả, KHÔNG chua_xac_minh ⇒ phải tô (nếu không, test trên vô nghĩa)."""
        viz = Visualizer()
        frame = _frame()
        r = _result(frame_idx=0, bbox=(100, 150, 140, 190), mask_box=(100, 150, 140, 190))
        img = viz.render(frame, r)
        giua = img[165:180, 110:130]
        assert not np.allclose(giua, frame[165:180, 110:130]), "mask tin cậy phải được tô"

    def test_khong_ve_quy_dao_khi_chua_xac_minh(self):
        from src.visualizer import _COLOR_TRAJECTORY

        viz = Visualizer()
        for i in range(4):
            viz.consume(_result(frame_idx=i, bbox=(100 + i * 30, 150, 140 + i * 30, 190),
                                mask_box=(100 + i * 30, 150, 140 + i * 30, 190)))
        frame = _frame()
        r = _result(frame_idx=9, bbox=(200, 150, 240, 190), mask_box=(200, 150, 240, 190))
        img = viz.render(frame, r, chua_xac_minh=True)
        tim = (np.abs(img.astype(int) - np.array(_COLOR_TRAJECTORY)).sum(axis=2) < 30)
        assert not tim.any(), "quỹ đạo là dấu vết của vật ĐANG được kiểm ⇒ không vẽ khi chưa xác minh"

    def test_mo_ta_hien_chu_chua_xac_minh(self, monkeypatch):
        """HUD phải NÓI ra (nếu không, người xem tưởng mask đã kiểm)."""
        viz = Visualizer()
        da_ve = []
        monkeypatch.setattr(viz, "_put_text", lambda img, chu, pos: da_ve.append((chu, pos)))
        viz.render(_frame(), _result(frame_idx=0, bbox=(100, 150, 140, 190),
                                     mask_box=(100, 150, 140, 190)), chua_xac_minh=True)
        chu = " ".join(c for c, _ in da_ve)
        assert "CHUA XAC MINH" in chu
        assert "c:" in chu and "r:" in chu, "phải nói phím nào để xác nhận / chọn lại"

    def test_nghi_thi_khong_in_chong_banner_mat_dau(self, monkeypatch):
        """24-11: phiên thật t≈47 s có 2 banner cùng lúc (NGHI + MẤT DẤU) — hai câu nói hai chuyện.

        REVIEW vòng 2 (P2): bản đầu đặt `consecutive_lost = 0` ⇒ banner KHÔNG BAO GIỜ được vẽ kể cả
        khi bỏ hẳn điều kiện `not switch_warning` ⇒ test vô nghĩa. Đúng ca bug phải là
        `consecutive_lost > 0` **VÀ** đang NGHI.
        """
        viz = Visualizer()
        viz.consecutive_lost = 3
        goi = []
        monkeypatch.setattr(viz, "_draw_lost_banner", lambda img, tu_tim: goi.append(tu_tim))
        viz.render(_frame(), _result(frame_idx=0, bbox=(100, 150, 140, 190),
                                     mask_box=(100, 150, 140, 190)), switch_warning=True)
        assert goi == [], "đang NGHI thì không vẽ banner MẤT DẤU"

    def test_mat_dau_that_van_in_banner(self, monkeypatch):
        """Đối chứng: mất dấu thật (không nghi) thì banner PHẢI hiện — đừng chặn quá tay."""
        viz = Visualizer()
        viz.consecutive_lost = 3
        goi = []
        monkeypatch.setattr(viz, "_draw_lost_banner", lambda img, tu_tim: goi.append(tu_tim))
        viz.render(_frame(), _result(frame_idx=1, bbox=(0, 0, 0, 0), mask_box=None))
        assert len(goi) == 1


class TestGuardMaskKhacCo:
    """24-11 (review vòng 2, P3): mask khác kích thước frame KHÔNG được vẽ (vẽ là sai toạ độ).

    `cv2.findContours`/`drawContours` không ném khi mask nhỏ hơn frame ⇒ bỏ guard là vẽ lệch trong
    im lặng, nên phải có test bắt.
    """

    def test_mask_nho_hon_frame_khong_ve_gi(self, monkeypatch):
        viz = Visualizer()
        frame = np.zeros((200, 320, 3), np.uint8)
        mask = np.zeros((48, 64), bool)
        mask[10:30, 10:30] = True
        # ô bao đặt XA vùng mask (mask 48×64 nằm ở góc trên-trái): nếu vẽ mask lệch cỡ thì pixel
        # xuất hiện đúng ở (10..30, 10..30), còn ô nét đứt thì ở (200..240, 100..160)
        r = TrackingResult(frame_idx=0, mask=mask, bbox=(200, 100, 240, 160),
                           score=1.0, elapsed_ms=1.0)
        goi = []
        monkeypatch.setattr("cv2.drawContours", lambda *a, **k: goi.append(1))
        viz.render(frame, r, chua_xac_minh=True)
        # Chỉ assert ĐIỂM GỌI vẽ: HUD (chữ FPS/ô nét đứt) cũng vẽ lên ảnh nên so pixel ở vùng mask
        # nhỏ sẽ dính chữ HUD — đúng cái bẫy làm test cũ vô nghĩa.
        assert goi == [], "mask khác cỡ frame vẫn được vẽ ⇒ sai toạ độ trong im lặng"
        # đối chứng: mask ĐÚNG cỡ thì phải vẽ (nếu không, test trên vô nghĩa)
        dung_co = np.zeros((200, 320), bool)
        dung_co[150:190, 20:60] = True
        r2 = TrackingResult(frame_idx=0, mask=dung_co, bbox=(20, 150, 60, 190),
                            score=1.0, elapsed_ms=1.0)
        viz.render(frame, r2, chua_xac_minh=True)
        assert goi, "mask đúng cỡ mà không vẽ viền ⇒ test trên không chứng minh được gì"
