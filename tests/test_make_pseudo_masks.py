"""Test cho `scripts/make_pseudo_masks.py` — đường biến 1 490 hộp GT thành mask nháp.

Vì sao có test: mask này sẽ được dùng để (a) mở rộng phép đo mIoU và (b) làm dữ liệu sửa tay. Hai lỗi
phải bị chặn bằng máy:
  1. **hộp ↔ frame lệch** (dùng phép ánh xạ bước→frame khác với UI gán nhãn) ⇒ mask của frame khác
     được ghi tên của bước này, im lặng;
  2. **QC bỏ sót ca xấu** mà không đếm ⇒ người dùng tưởng "0 cảnh báo = toàn mask tốt".
"""
from __future__ import annotations

import importlib.util
import json
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
        """`nghi` phải là OR của **MỌI** cờ — lấy tập cờ ĐỘNG, không hard-code 4 tên.

        Bản đầu hard-code `("rong","nho","tran","cham_bien")`: thêm một cờ mới vào `qc()` mà quên
        `nghi` thì test vẫn xanh (review độc lập 26-11, P2).
        """
        m = self._mask()
        m[0, 0] = True       # chạm biên, hộp ở giữa, diện tích 1 px
        q = psm.qc(m, [20, 20, 40, 40], 64, 48)
        co = set(q) - {"nghi", "ty_le_dien_tich", "dien_tich", "dien_tich_hop"}
        assert all(isinstance(q[k], bool) for k in co), f"cờ phải là bool: {co}"
        assert q["nghi"] == any(q[k] for k in co), f"nghi phải là OR của {sorted(co)}"

    def test_cham_bien_theo_TUNG_phia(self):
        """Hộp chạm ĐÁY không được miễn cho mask tràn sang TRÁI.

        Bản đầu dùng `hop_cham` = OR 4 phía ⇒ bỏ sót chiều này (review độc lập 26-11, P2).
        """
        m = self._mask()
        m[10:48, 10:50] = True                 # chạm đáy
        m[:, 0] = True                          # VÀ chạm trái
        q = psm.qc(m, [10, 10, 50, 47], 64, 48)   # hộp chạm đáy nhưng KHÔNG chạm trái
        assert q["cham_bien"], "mask chạm trái mà hộp không ⇒ phải cảnh báo"


class TestSinhMask:
    def test_dung_cache_khong_goi_model_lai(self, tmp_path, monkeypatch):
        import cv2
        rec = {"phien": "p", "buoc": 3, "frame_idx": 5, "box": [10, 10, 50, 40],
               "nhan": "sai", "video_rong": 64, "video_cao": 48, "fps": 10.0}
        thu_muc = tmp_path / "p"
        thu_muc.mkdir(parents=True)
        m = np.zeros((48, 64), np.uint8)
        m[10:40, 10:50] = 255
        # tên file có hash HỘP ⇒ dùng đúng hàm sinh tên, đừng hard-code (nếu không test tự tạo bẫy)
        cv2.imwrite(str(thu_muc / f"00003_{psm.bam_hop(rec['box'])}.png"), m)

        class EngineChet:
            def start(self, *a, **k):
                raise AssertionError("không được gọi model khi đã có cache")

        ban_ghi, dem = psm.sinh_mask(EngineChet(), [rec], tmp_path, ghi_de=True)
        assert dem["co_cache"] == 1 and dem["moi"] == 0
        assert ban_ghi[0]["qc"]["ty_le_dien_tich"] == 1.0

    def test_model_loi_khong_lam_chet_ca_lo(self, tmp_path, monkeypatch):
        """Một frame lỗi phải được ĐẾM vào `loi_mask` và bỏ qua, không ném ra ngoài.

        Bản đầu test này **không bao giờ chạm model** (thiếu video ⇒ chỉ tăng `loi_doc_frame`) nên xoá
        cả `try/except` vẫn xanh — đúng "test giả" mà review độc lập 26-11 (P1) bắt được.
        """
        import numpy as np
        rec = {"phien": "p", "buoc": 0, "frame_idx": 0, "box": [10, 10, 50, 40],
               "nhan": "sai", "video_rong": 64, "video_cao": 48, "fps": 10.0}

        class CapGia:
            def set(self, *a):
                return True
            def get(self, *a):
                return 0
            def read(self):
                return True, np.zeros((48, 64, 3), np.uint8)

        monkeypatch.setattr(psm.L, "_mo_video", lambda ten: (CapGia(), 10.0, 20, 64, 48))
        monkeypatch.setattr(psm.L, "_CAP_LOCK", __import__("contextlib").nullcontext())

        class EngineHong:
            def start(self, *a, **k):
                raise RuntimeError("model phân kỳ")

        ban_ghi, dem = psm.sinh_mask(EngineHong(), [rec], tmp_path, ghi_de=True)
        assert dem["loi_mask"] == 1 and dem["loi_doc_frame"] == 0, dem
        assert ban_ghi == [], "không được ghi bản ghi cho mask lỗi"

    def test_doi_hop_thi_ten_file_doi(self, tmp_path):
        """Đổi `bbox_dung` phải ra TÊN FILE khác ⇒ cache tự miss (review 26-11, P1)."""
        assert psm.bam_hop([10, 10, 50, 40]) != psm.bam_hop([11, 10, 50, 40])
        assert psm.bam_hop([10, 10, 50, 40]) == psm.bam_hop([10, 10, 50, 40])

    def test_van_tay_doi_khi_doi_image_size(self):
        a = psm.dau_van_tay(512, "ckpt.pt", "cfg.yaml")
        b = psm.dau_van_tay(1024, "ckpt.pt", "cfg.yaml")
        assert a != b, "đổi image_size mà vân tay không đổi ⇒ phục vụ mask sai cấu hình"


class TestThuThap:
    def test_khong_co_nhan_thi_tra_rong(self, tmp_path, monkeypatch):
        monkeypatch.setattr(psm, "NHAN", tmp_path / "nhan")
        (tmp_path / "nhan").mkdir()
        viec, bo_qua = psm.thu_thap_muc_tieu()
        assert viec == [] and bo_qua == {}

    def test_phien_thieu_video_duoc_DEM(self, tmp_path, monkeypatch):
        """Mục tiêu bị bỏ phải ĐẾM theo lý do (bản đầu im lặng ⇒ `loi_* = 0` bị đọc là 'không mất gì')."""
        monkeypatch.setattr(psm, "NHAN", tmp_path / "nhan")
        monkeypatch.setattr(psm, "DATA", tmp_path)
        (tmp_path / "nhan").mkdir()
        (tmp_path / "nhan" / "p.jsonl").write_text(
            json.dumps({"buoc": 0, "nhan": "sai", "bbox_dung": [1, 1, 9, 9]}) + "\n",
            encoding="utf-8")
        viec, bo_qua = psm.thu_thap_muc_tieu()
        assert viec == [] and bo_qua.get("thieu_csv") == 1, bo_qua
