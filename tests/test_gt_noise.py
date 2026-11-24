"""Test cho `scripts/gt_noise.py` (plan 24-11 P1-b) — đo nhiễu của CHÍNH GT."""
import numpy as np


def _viet(d, idx, arr):
    import cv2
    d.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(d / f"gt_{idx:06d}.png"), (arr * 255).astype("uint8"))


class TestGtNoise:
    def test_iou_giua_hai_lan_to(self, tmp_path):
        import scripts.gt_noise as gn
        a, b = tmp_path / "a", tmp_path / "b"
        g = np.zeros((10, 10))
        g[0:5, 0:10] = 1                                  # 50 px
        g2 = np.zeros((10, 10))
        g2[0:5, 0:5] = 1                                  # 25 px (tô lại hụt nửa)
        _viet(a, 0, g)
        _viet(b, 0, g2)
        kq = gn.do(a, b)["ket_qua"]
        assert kq["ioU_GT_mean"] == 0.5
        assert kq["nguong_khong_ket_luan"] == 0.5          # 1 − IoU
        assert kq["n"] == 1

    def test_gt_rong_ca_hai_thi_khong_cham(self, tmp_path):
        """`IoU(rỗng, rỗng) = 1,0` là bẫy đã gặp 3 lần trong repo ⇒ phải là `None`, không phải 1,0."""
        import scripts.gt_noise as gn
        a, b = tmp_path / "a", tmp_path / "b"
        _viet(a, 0, np.zeros((8, 8)))
        _viet(b, 0, np.zeros((8, 8)))
        kq = gn.do(a, b)["ket_qua"]
        assert kq["ioU_GT_mean"] is None
        assert kq["frames"][0]["gt_rong_ca_hai"] is True

    def test_chi_cham_frame_co_o_ca_hai(self, tmp_path):
        import scripts.gt_noise as gn
        a, b = tmp_path / "a", tmp_path / "b"
        _viet(a, 0, np.ones((4, 4)))
        _viet(b, 0, np.ones((4, 4)))
        _viet(a, 1, np.ones((4, 4)))                       # chỉ có ở A
        payload = gn.do(a, b)
        assert payload["ket_qua"]["n"] == 1
        assert payload["frame_chi_co_a"] == [1]

    def test_kich_thuoc_lech_thi_ghi_loi_khong_giet(self, tmp_path):
        import scripts.gt_noise as gn
        a, b = tmp_path / "a", tmp_path / "b"
        _viet(a, 0, np.ones((4, 4)))
        _viet(b, 0, np.ones((8, 8)))
        kq = gn.do(a, b)["ket_qua"]
        assert "loi" in kq["frames"][0]
        assert kq["ioU_GT_mean"] is None
