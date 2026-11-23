"""Plan `24-11-2026-chong-tran-nen-cung-tong-chot.md`, việc 4 — cột chẩn đoán tràn.

⚠️ Đây KHÔNG phải cổng: plan đã chốt không nối luật diện tích vào `IdentityWatch` (mỗi cổng là latch
không tự hồi: phiên `144505` sẽ thành 98/194 = 50,5 % frame mang ô nét đứt thay vì 25,8 %). Các test
dưới chỉ chốt **số ghi ra artifact** đúng và không nói dối.
"""
import numpy as np

from src.bbox_area_watch import BboxAreaWatch


class TestBboxAreaWatch:
    def test_frame_dau_la_moc_ty_le_1(self):
        w = BboxAreaWatch()
        assert w.update(76, 76) == 1.0          # mốc: chính nó ⇒ 1,0

    def test_o_rong_khong_keo_moc_ve_0(self):
        """Mất dấu KHÔNG được cập nhật EMA — nếu không, chuỗi mất dấu kéo mốc về 0 rồi mọi frame
        sau đều bị coi là "tràn" (đúng loại lỗi khiến cổng báo oan)."""
        w = BboxAreaWatch()
        w.update(100, 100)                      # mốc 10 000
        for _ in range(50):
            assert w.update(0, 0) is None       # ô rỗng: chưa đo
        assert w.ema == 10_000                  # mốc KHÔNG đổi
        assert round(w.update(100, 100)) == 1   # vẫn đúng cỡ

    def test_o_qua_nho_thi_bo_qua(self):
        w = BboxAreaWatch(min_area=64)
        assert w.update(5, 5) is None           # 25 px < 64
        assert w.ema is None

    def test_bat_dung_cu_tran_that(self):
        """Ca thật phiên 144505 (f95→f96): 4 655 → 29 110 px trong MỘT bước."""
        w = BboxAreaWatch()
        for _ in range(20):
            w.update(*self._wxh(4655))
        ema_truoc = w.ema                          # tỉ lệ được tính so với EMA TRƯỚC frame này
        canh_moi = self._wxh(29110)[0]             # 170 → diện tích 170² = 28 900 (không phải 29 110)
        ti_le = w.update(canh_moi, canh_moi)
        assert round(ti_le, 2) == round(canh_moi ** 2 / ema_truoc, 2)
        # và tỉ lệ đó phải vượt ngưỡng 3,0 (ngưỡng của luật đề xuất — KHÔNG được nối vào cổng)
        assert ti_le > 3.0

    def test_khong_bao_dong_khi_vat_to_dan_deu(self):
        """Vật to dần từ từ (lại gần camera) — EMA bám theo, tỉ lệ quanh 1,0."""
        w = BboxAreaWatch()
        ti_le = []
        for i in range(60):
            canh = 76 + i                            # mỗi bước +1 px/cạnh
            ti_le.append(w.update(canh, canh))
        assert max(ti_le[5:]) < 1.6, f"tỉ lệ vượt 1,6 khi vật to dần: {max(ti_le[5:]):.2f}"

    @staticmethod
    def _wxh(dien_tich):
        canh = int(np.sqrt(dien_tich))
        return canh, canh
