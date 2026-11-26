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

    def test_nguong_hop_sat_mep_la_2px(self):
        """Khoá `SAT_MEP = 2`: ngưỡng này đổi 1 → 2 px từng làm 337 → 274 cờ mà không ai ghi lại (review 27-11)."""
        m = self._mask()
        m[10:40, 0] = True                          # mask chỉ chạm mép TRÁI (không chạm trên/dưới)
        assert not psm.qc(m, [2, 10, 40, 40], 64, 48)["cham_bien"], "hộp cách mép 2 px ⇒ coi là hộp sát"
        assert psm.qc(m, [3, 10, 40, 40], 64, 48)["cham_bien"], "hộp cách mép 3 px ⇒ phải báo"


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

    def test_imwrite_loi_khong_cong_bo(self, tmp_path, monkeypatch):
        """`cv2.imwrite` trả False (đĩa đầy/quyền) mà không kiểm ⇒ artifact công bố `so_mask` > số PNG thật.

        Review 27-11 (P2): cổng "không công bố khi lỗi" trước chỉ bắt lỗi model/đọc frame.
        """
        rec = {"phien": "p", "buoc": 0, "frame_idx": 0, "box": [10, 10, 50, 40],
               "nhan": "sai", "video_rong": 64, "video_cao": 48, "fps": 10.0}

        class CapGia:
            def set(self, *a):
                return True
            def get(self, *a):
                return 0
            def read(self):
                return True, np.zeros((48, 64, 3), np.uint8)

        class EngineOk:
            def start(self, *a, **k):
                m = np.zeros((48, 64), bool)
                m[10:40, 10:50] = True
                return type("KQ", (), {"mask": m})()

        monkeypatch.setattr(psm.L, "_mo_video", lambda ten: (CapGia(), 10.0, 20, 64, 48))
        monkeypatch.setattr(psm.L, "_CAP_LOCK", __import__("contextlib").nullcontext())
        monkeypatch.setattr(psm.cv2, "imwrite", lambda *a, **k: False)
        ban_ghi, dem = psm.sinh_mask(EngineOk(), [rec], tmp_path, ghi_de=True)
        assert dem["loi_ghi"] == 1 and dem["moi"] == 0, dem
        assert ban_ghi == [], "không được công bố mask chưa ghi được ra đĩa"

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


class TestDonCache:
    def test_xoa_va_DEM_file_khi_van_tay_doi(self, tmp_path):
        import cv2
        (tmp_path / ".dau_van_tay").write_text("cu", encoding="utf-8")
        d = tmp_path / "p"
        d.mkdir()
        for i in range(3):
            cv2.imwrite(str(d / f"{i:05d}.png"), np.zeros((4, 4), np.uint8))
        assert psm.don_cache_neu_can(tmp_path, "moi") == 3
        assert not d.exists() and (tmp_path / ".dau_van_tay").read_text() == "moi"

    def test_van_tay_khong_doi_thi_khong_dung(self, tmp_path):
        (tmp_path / ".dau_van_tay").write_text("same", encoding="utf-8")
        (tmp_path / "p").mkdir()
        assert psm.don_cache_neu_can(tmp_path, "same") == 0
        assert (tmp_path / "p").is_dir()

    def test_tu_choi_thu_muc_KHONG_phai_cache(self, tmp_path):
        """`--out data` từng xoá `data/nhan` vì hàm dọn không kiểm đây có phải thư mục cache (review 27-11, P1)."""
        quan_trong = tmp_path / "nhan"
        quan_trong.mkdir()
        (quan_trong / "p.jsonl").write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError):
            psm.don_cache_neu_can(tmp_path, "moi")
        assert (quan_trong / "p.jsonl").is_file(), "không được xoá thư mục không phải cache"

    def test_thu_muc_chua_ton_tai_thi_tao_moi(self, tmp_path):
        assert psm.don_cache_neu_can(tmp_path / "moi", "v1") == 0
        assert (tmp_path / "moi" / ".dau_van_tay").read_text() == "v1"


class TestThuThap:
    def _dat(self, tmp_path, monkeypatch, dong: list[dict], co_csv=True, co_video=True):
        monkeypatch.setattr(psm, "NHAN", tmp_path / "nhan")
        monkeypatch.setattr(psm, "DATA", tmp_path)
        (tmp_path / "nhan").mkdir()
        (tmp_path / "nhan" / "p.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in dong), encoding="utf-8")
        if co_csv:
            (tmp_path / "p_metrics.csv").write_text("frame_idx\n0\n", encoding="utf-8")
            monkeypatch.setattr(psm.L, "doc_phien_cached", lambda p: {"frames": [{}] * 3})
        monkeypatch.setattr(psm.L, "_mo_video",
                            lambda ten: (object(), 10.0, 3, 64, 48) if co_video else None)
        monkeypatch.setattr(psm.L, "chi_so_khung", lambda phien, buoc: (0, None))

    def test_khong_co_nhan_thi_tra_rong(self, tmp_path, monkeypatch):
        monkeypatch.setattr(psm, "NHAN", tmp_path / "nhan")
        (tmp_path / "nhan").mkdir()
        viec, bo_qua, dong = psm.thu_thap_muc_tieu()
        assert viec == [] and bo_qua == {"file": {}, "buoc": {}} and dong["tho"] == 0

    def test_phien_thieu_csv_duoc_DEM(self, tmp_path, monkeypatch):
        """Mục tiêu bị bỏ phải ĐẾM theo lý do (bản đầu im lặng ⇒ `loi_* = 0` bị đọc là 'không mất gì')."""
        self._dat(tmp_path, monkeypatch, [{"buoc": 0, "nhan": "sai", "bbox_dung": [1, 1, 9, 9]}],
                  co_csv=False)
        viec, bo_qua, _ = psm.thu_thap_muc_tieu()
        assert viec == [] and bo_qua["file"].get("thieu_csv") == 1, bo_qua

    def test_phien_thieu_video_duoc_DEM(self, tmp_path, monkeypatch):
        """Phải chạm nhánh `thieu_video`: bản đầu ca này thiếu luôn CSV nên nhánh không bao giờ chạy."""
        self._dat(tmp_path, monkeypatch, [{"buoc": 0, "nhan": "sai", "bbox_dung": [1, 1, 9, 9]}],
                  co_video=False)
        viec, bo_qua, _ = psm.thu_thap_muc_tieu()
        assert viec == [] and bo_qua["file"].get("thieu_video") == 1, bo_qua

    def test_nhan_cuoi_bo_hop_duoc_DEM(self, tmp_path, monkeypatch):
        """Bước TỪNG có hộp nhưng nhãn CUỐI bỏ `bbox_dung` bị `continue` im lặng (review 27-11)."""
        self._dat(tmp_path, monkeypatch, [
            {"buoc": 0, "nhan": "sai", "bbox_dung": [1, 1, 9, 9]},
            {"buoc": 0, "nhan": "dung"},
        ])
        viec, bo_qua, dong = psm.thu_thap_muc_tieu()
        assert viec == [] and bo_qua["buoc"].get("nhan_cuoi_khong_co_hop") == 1, bo_qua
        assert dong == {"tho": 1, "trung_lap": 0, "cua_buoc_bi_bo": 1}, dong

    def test_so_hoc_dong_va_buoc(self, tmp_path, monkeypatch):
        """`tho − trung_lap − cua_buoc_bi_bo` phải bằng số BƯỚC sinh được ("1 490 dòng → 1 251 mask")."""
        self._dat(tmp_path, monkeypatch, [
            {"buoc": 0, "nhan": "sai", "bbox_dung": [1, 1, 9, 9]},
            {"buoc": 0, "nhan": "sai", "bbox_dung": [2, 2, 9, 9]},
            {"buoc": 1, "nhan": "sai", "bbox_dung": [1, 1, 9, 9]},
        ])
        viec, _, dong = psm.thu_thap_muc_tieu()
        assert len(viec) == 2, viec
        assert dong == {"tho": 3, "trung_lap": 1, "cua_buoc_bi_bo": 0}, dong
