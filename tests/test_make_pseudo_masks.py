"""Test cho `scripts/make_pseudo_masks.py` — đường biến 1 490 hộp GT thành mask nháp.

Vì sao có test: mask này sẽ được dùng để (a) mở rộng phép đo mIoU và (b) làm dữ liệu sửa tay. Hai lỗi
phải bị chặn bằng máy:
  1. **hộp ↔ frame lệch** (dùng phép ánh xạ bước→frame khác với UI gán nhãn) ⇒ mask của frame khác
     được ghi tên của bước này, im lặng;
  2. **QC bỏ sót ca xấu** mà không đếm ⇒ người dùng tưởng "0 cảnh báo = toàn mask tốt".
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import numpy as np
import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


def _nap(ten: str, duong: pathlib.Path):
    spec = importlib.util.spec_from_file_location(ten, duong)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ten] = mod
    spec.loader.exec_module(mod)
    return mod


psm = _nap("make_pseudo_masks", REPO / "scripts" / "make_pseudo_masks.py")


class TestOHopLe:
    def test_hop_trong_khung(self):
        assert psm.o_hop_le([10, 10, 50, 40], 64, 48)

    @pytest.mark.parametrize("box", [
        [10, 10, 50, 60],          # y2 vượt khung cao=48
        [-5, 10, 50, 40],          # x1 âm
        [50, 10, 10, 40],          # x2 < x1
        [10, 10, 12, 40],          # hẹp 2 px (< 3)
        [10, 10, 10, 40],          # suy biến
        None, "abc", [1, 2, 3], [np.nan, 0, 5, 5],
    ])
    def test_hop_khong_dung_bi_tu_choi(self, box):
        assert not psm.o_hop_le(box, 64, 48)


class TestQc:
    def _mask(self, h=48, w=64):
        return np.zeros((h, w), bool)

    def test_mask_rong(self):
        q = psm.qc(self._mask(), [10, 10, 50, 40], 64, 48)
        assert q["rong"] and q["nghi"] and q["dien_tich"] == 0

    def test_mask_khop_hop(self):
        m = self._mask()
        m[10:40, 10:50] = True                       # đúng bằng hộp ⇒ tỉ lệ 1,0
        q = psm.qc(m, [10, 10, 50, 40], 64, 48)
        assert q["ty_le_dien_tich"] == 1.0 and not q["nghi"]
        assert not q["cham_bien"]

    def test_mask_nho_hon_hop(self):
        m = self._mask()
        m[10:13, 10:13] = True                       # 9 / 1200 px ⇒ 0,0075
        q = psm.qc(m, [10, 10, 50, 40], 64, 48)
        assert q["nho"] and q["nghi"]

    def test_mask_tran_ra_ngoai(self):
        m = self._mask()
        m[:, :] = True                               # cả khung >> hộp
        q = psm.qc(m, [10, 10, 50, 40], 64, 48)
        assert q["tran"] and q["nghi"]

    def test_cham_bien_chi_khi_hop_KHONG_cham(self):
        """Ca thật (ảnh `demoip_1104-212328#4`): hộp cắt mất phần dưới của vật ⇒ mask nới tới mép."""
        m = self._mask()
        m[10:48, 10:50] = True                       # chạm mép dưới
        q = psm.qc(m, [10, 10, 50, 40], 64, 48)
        assert q["cham_bien"] and q["nghi"], "mask chạm biên mà hộp không ⇒ phải cảnh báo"
        # nếu CHÍNH hộp chạm biên thì không phải cảnh báo
        q2 = psm.qc(m, [10, 10, 50, 47], 64, 48)
        assert not q2["cham_bien"]

    def test_moi_co_duoc_dem_va_khong_co_co_nao_bi_an(self):
        """`nghi` phải là OR của 4 cờ (đừng để cờ mới thêm mà không vào `nghi`)."""
        m = self._mask()
        m[0, 0] = True       # chạm biên, hộp ở giữa, diện tích 1 px
        q = psm.qc(m, [20, 20, 40, 40], 64, 48)
        assert q["nghi"] == any(q[k] for k in ("rong", "nho", "tran", "cham_bien"))


class TestSinhMask:
    def test_dung_cache_khong_goi_model_lai(self, tmp_path, monkeypatch):
        import cv2
        rec = {"phien": "p", "buoc": 3, "frame_idx": 5, "box": [10, 10, 50, 40],
               "nhan": "sai", "rong": 64, "cao": 48, "fps": 10.0}
        thu_muc = tmp_path / "p"
        thu_muc.mkdir(parents=True)
        m = np.zeros((48, 64), np.uint8)
        m[10:40, 10:50] = 255
        cv2.imwrite(str(thu_muc / "00003.png"), m)

        class EngineChet:
            def start(self, *a, **k):
                raise AssertionError("không được gọi model khi đã có cache")

        ban_ghi, dem = psm.sinh_mask(EngineChet(), [rec], tmp_path, ghi_de=True)
        assert dem["co_cache"] == 1 and dem["moi"] == 0
        assert ban_ghi[0]["qc"]["ty_le_dien_tich"] == 1.0

    def test_model_loi_khong_lam_chet_ca_lo(self, tmp_path, monkeypatch):
        """Một frame lỗi phải được ĐẾM và bỏ qua, không ném ra ngoài."""
        rec = {"phien": "p", "buoc": 0, "frame_idx": 0, "box": [10, 10, 50, 40],
               "nhan": "sai", "rong": 64, "cao": 48, "fps": 10.0}

        class EngineHong:
            def start(self, *a, **k):
                raise RuntimeError("model phân kỳ")

        monkeypatch.setattr(psm, "thu_thap_muc_tieu", lambda: [rec])
        # không có video/CSV ⇒ nhánh lỗi đọc frame được đếm, không ném
        _, dem = psm.sinh_mask(EngineHong(), [rec], tmp_path, ghi_de=True)
        assert dem["loi_doc_frame"] + dem["loi_mask"] == 1


class TestThuThap:
    def test_khong_co_nhan_thi_tra_rong(self, tmp_path, monkeypatch):
        monkeypatch.setattr(psm, "NHAN", tmp_path / "nhan")
        (tmp_path / "nhan").mkdir()
        assert psm.thu_thap_muc_tieu() == []
